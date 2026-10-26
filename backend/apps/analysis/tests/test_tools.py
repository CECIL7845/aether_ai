import pytest
from django.core.files.base import ContentFile

from apps.accounts.models import User
from apps.analysis.calculator import CalcError, evaluate
from apps.analysis.models import AnalysisResult
from apps.analysis.tools import ToolContext, ToolError, run_tool
from apps.analysis.views import safe_cell
from apps.chat.models import Conversation
from apps.documents.models import Document
from apps.documents.tests.files import make_xlsx

pytestmark = pytest.mark.django_db

# Synthetic sales data (not real business data).
SALES_CSV = b"""date,region,product,units,revenue
2026-01-05,Accra,Cement,10,1200.50
2026-01-07,Kumasi,Cement,4,480
2026-02-02,Accra,Paint,7,350
2026-02-10,Tamale,Cement,,0
2026-03-01,Accra,Cement,3,360
2026-03-15,Kumasi,Paint,12,600
"""


def make_dataset(user, name="sales.csv", data=SALES_CSV, kind="csv"):
    doc = Document(user=user, title=name, kind=kind, size=len(data), sha256=f"sha-{name}-{len(data)}",
                   status="ready")
    doc.file.save(name, ContentFile(data), save=False)
    doc.save()
    return doc


@pytest.fixture
def ctx():
    user = User.objects.create_user("ama@example.com", "correct-horse-battery-9")
    conv = Conversation.objects.create(user=user)
    doc = make_dataset(user)
    conv.documents.add(doc)
    return ToolContext(user=user, conversation=conv, datasets=[doc])


def test_list_and_describe(ctx):
    listing = run_tool(ctx, "list_datasets", {})
    sheet = listing["datasets"][0]["sheets"][0]
    assert sheet["rows"] == 6 and [c["name"] for c in sheet["columns"]] == ["date", "region", "product", "units",
                                                                            "revenue"]
    profile = run_tool(ctx, "describe_dataset", {"dataset_id": ctx.datasets[0].pk})
    cols = {c["name"]: c for c in profile["columns"]}
    assert cols["revenue"]["sum"] == pytest.approx(2990.5)
    assert cols["units"]["missing"] == 1 and cols["units"]["max"] == 12
    assert cols["date"]["dtype"].startswith("datetime64") and cols["date"]["min"].startswith("2026-01-05")
    assert cols["region"]["top_values"][0] == {"value": "Accra", "count": 3}


def test_group_aggregate_sort_matches_pandas_ground_truth(ctx):
    r = run_tool(ctx, "query_dataset", {
        "dataset_id": ctx.datasets[0].pk,
        "group_by": ["region"],
        "aggregations": [{"func": "sum", "column": "revenue"}, {"func": "count"}],
        "sort": [{"column": "sum(revenue)", "descending": True}],
    })
    assert r["columns"] == ["region", "sum(revenue)", "count"]
    assert r["rows"] == [["Accra", 1910.5, 3], ["Kumasi", 1080.0, 2], ["Tamale", 0.0, 1]]
    stored = AnalysisResult.objects.get(pk=r["result_id"])
    assert stored.query["group_by"] == ["region"] and stored.total_rows == 3


def test_filters_dates_and_case_insensitive_columns(ctx):
    r = run_tool(ctx, "query_dataset", {
        "dataset_id": ctx.datasets[0].pk,
        "filters": [{"column": "Product", "op": "==", "value": "Cement"},
                    {"column": "date", "op": ">=", "value": "2026-02-01"}],
        "aggregations": [{"func": "sum", "column": "revenue"}],
    })
    assert r["rows"] == [[360.0]] and r["rows_matching_filters"] == 2  # Tamale (0) + Accra March (360)


def test_null_and_in_filters(ctx):
    r = run_tool(ctx, "query_dataset", {"dataset_id": ctx.datasets[0].pk,
                                        "filters": [{"column": "units", "op": "is_null"}], "select": ["region"]})
    assert r["rows"] == [["Tamale"]]
    r = run_tool(ctx, "query_dataset", {"dataset_id": ctx.datasets[0].pk,
                                        "filters": [{"column": "region", "op": "in", "value": ["Tamale", "Kumasi"]}],
                                        "aggregations": [{"func": "count"}]})
    assert r["rows"] == [[3]]


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ({"dataset_id": 99999}, "No dataset with id"),
        ({"dataset_id": "1; DROP TABLE"}, "must be an integer"),
        ({"filters": [{"column": "nope", "op": "=="}]}, "Unknown column 'nope'"),
        ({"filters": [{"column": "region", "op": "LIKE", "value": "A%"}]}, "Unsupported filter op"),
        ({"filters": [{"column": "units", "op": ">", "value": "lots"}]}, "does not match the type"),
        ({"aggregations": [{"func": "sum", "column": "region"}]}, "non-numeric"),
        ({"aggregations": [{"func": "eval", "column": "units"}]}, "func"),
        ({"aggregations": [{"func": "mean"}]}, "needs a column"),
    ],
)
def test_invalid_arguments_are_rejected_with_reasons(ctx, args, message):
    args = {"dataset_id": ctx.datasets[0].pk, **args}
    with pytest.raises(ToolError, match=message):
        run_tool(ctx, "query_dataset", args)


def test_limit_is_capped_and_total_reported(ctx):
    r = run_tool(ctx, "query_dataset", {"dataset_id": ctx.datasets[0].pk, "limit": 2})
    assert r["returned_rows"] == 2 and r["result_rows"] == 6 and len(r["rows"]) == 2
    r = run_tool(ctx, "query_dataset", {"dataset_id": ctx.datasets[0].pk, "limit": 10_000})
    assert len(r["rows"]) == 6  # capped at MAX_RETURN_ROWS, here limited by data


def test_chart_validation(ctx):
    r = run_tool(ctx, "query_dataset", {"dataset_id": ctx.datasets[0].pk, "group_by": ["region"],
                                        "aggregations": [{"func": "sum", "column": "revenue"}]})
    chart = run_tool(ctx, "create_chart", {"result_id": r["result_id"], "chart_type": "bar", "x": "region",
                                           "y": ["sum(revenue)"], "title": "Revenue by region"})
    assert chart["data"][0] == {"x": "Accra", "sum(revenue)": 1910.5}
    with pytest.raises(ToolError, match="not numeric"):
        run_tool(ctx, "create_chart", {"result_id": r["result_id"], "chart_type": "bar", "x": "sum(revenue)",
                                       "y": ["region"]})
    with pytest.raises(ToolError, match="Unknown x column"):
        run_tool(ctx, "create_chart", {"result_id": r["result_id"], "chart_type": "line", "x": "month",
                                       "y": ["sum(revenue)"]})


def test_other_users_datasets_and_results_are_unreachable(ctx):
    other = User.objects.create_user("kofi@example.com", "correct-horse-battery-9")
    other_conv = Conversation.objects.create(user=other)
    other_doc = make_dataset(other, "secret.csv", b"salary\n9000\n")
    other_ctx = ToolContext(user=other, conversation=other_conv, datasets=[other_doc])
    r = run_tool(other_ctx, "query_dataset", {"dataset_id": other_doc.pk})
    with pytest.raises(ToolError, match="No dataset with id"):
        run_tool(ctx, "query_dataset", {"dataset_id": other_doc.pk})
    with pytest.raises(ToolError, match="No result with id"):
        run_tool(ctx, "create_chart", {"result_id": r["result_id"], "chart_type": "bar", "x": "salary",
                                       "y": ["salary"]})


def test_xlsx_sheets(ctx):
    doc = make_dataset(ctx.user, "book.xlsx", make_xlsx([["item", "qty"], ["a", 2], ["b", 5]], sheet="Stock"), "xlsx")
    ctx.datasets.append(doc)
    r = run_tool(ctx, "query_dataset", {"dataset_id": doc.pk, "sheet": "Stock",
                                        "aggregations": [{"func": "sum", "column": "qty"}]})
    assert r["rows"] == [[7]]
    with pytest.raises(ToolError, match="Available sheets: Stock"):
        run_tool(ctx, "describe_dataset", {"dataset_id": doc.pk, "sheet": "Nope"})


def test_unknown_tool(ctx):
    with pytest.raises(ToolError, match="Unknown tool"):
        run_tool(ctx, "os_system", {"cmd": "rm -rf /"})


@pytest.mark.parametrize(("expr", "value"), [("(1910.5 - 1080) / 1080 * 100", 76.898148), ("2^10", 1024),
                                             ("round(sqrt(2), 3)", 1.414), ("1,200 * 3", 3600)])
def test_calculator(expr, value):
    assert evaluate(expr) == pytest.approx(value, rel=1e-6)


@pytest.mark.parametrize("expr", ["__import__('os').system('ls')", "open('/etc/passwd')", "().__class__",
                                  "9**9**9", "1/0", "x + 1", "[1,2][0]"])
def test_calculator_rejects_non_arithmetic(expr):
    with pytest.raises(CalcError):
        evaluate(expr)


def test_csv_download_is_owner_only_and_formula_safe(api, ctx):
    result = AnalysisResult.objects.create(user=ctx.user, conversation=ctx.conversation, title="Export",
                                           query={}, columns=["name", "value"],
                                           rows=[["=HYPERLINK(\"http://evil\")", -5], ["@SUM(A1)", 3]], total_rows=2)
    api.force_authenticate(ctx.user)
    body = api.get(f"/api/analysis-results/{result.pk}/download/").content.decode()
    assert "'=HYPERLINK" in body and "'@SUM" in body and "\r\n-5" not in body.replace(",-5", ",NUM")
    assert ",-5" in body  # negative numbers are left alone
    other = User.objects.create_user("kofi@example.com", "correct-horse-battery-9")
    api.force_authenticate(other)
    assert api.get(f"/api/analysis-results/{result.pk}/download/").status_code == 404


def test_safe_cell():
    assert safe_cell("=1+1") == "'=1+1" and safe_cell("-3.5") == "-3.5" and safe_cell(None) == ""


def test_sort_accepts_source_column_name_for_single_aggregate(ctx):
    r = run_tool(ctx, "query_dataset", {"dataset_id": ctx.datasets[0].pk, "group_by": ["region"],
                                        "aggregations": [{"func": "sum", "column": "revenue"}],
                                        "sort": [{"column": "revenue", "descending": True}]})
    assert [row[0] for row in r["rows"]] == ["Accra", "Kumasi", "Tamale"]
