import pytest

from apps.documents.chunking import CHUNK_CHARS, chunk_segments
from apps.documents.extract import ExtractionError, Segment, extract, kind_for

from .files import make_docx, make_encrypted_pdf, make_pdf, make_xlsx, make_zip_bomb_docx


def test_pdf_text_keeps_page_numbers():
    result = extract("pdf", make_pdf(["Revenue grew 12 percent", "Costs fell in Kumasi"]))
    assert result.page_count == 2
    assert [(s.page, s.text) for s in result.segments] == [(1, "Revenue grew 12 percent"), (2, "Costs fell in Kumasi")]


def test_password_protected_pdf_is_rejected_with_reason():
    with pytest.raises(ExtractionError, match="password-protected"):
        extract("pdf", make_encrypted_pdf("secret"))


def test_scanned_pdf_without_text_is_not_reported_as_read():
    with pytest.raises(ExtractionError, match="scanned image"):
        extract("pdf", make_pdf(["", ""]))


def test_pdf_page_limit(settings):
    settings.MAX_PDF_PAGES = 2
    with pytest.raises(ExtractionError, match="limit is 2"):
        extract("pdf", make_pdf(["a", "b", "c"]))


def test_damaged_pdf():
    with pytest.raises(ExtractionError, match="damaged"):
        extract("pdf", b"%PDF-1.4\n garbage")


def test_docx_headings_and_tables():
    data = make_docx("Leave policy", ["Staff get 20 days."], [["Grade", "Days"], ["Senior", "25"]])
    result = extract("docx", data)
    text = "\n".join(s.text for s in result.segments)
    assert "## Leave policy" in text and "Staff get 20 days." in text and "Senior | 25" in text
    assert result.segments[0].location == "Section: Leave policy"


def test_xlsx_rows_with_header_and_formulas_not_evaluated():
    data = make_xlsx([["Region", "Revenue"], ["Accra", 1200], ["Kumasi", 800], ["Total", "=SUM(B2:B3)"]])
    result = extract("xlsx", data)
    assert result.segments[0].location == "Sales, rows 2–4"
    assert "Region, Revenue" in result.segments[0].text and "Accra, 1200" in result.segments[0].text
    assert "SUM" not in result.segments[0].text  # cached value only (none here), formula text never executed


def test_csv_and_text():
    assert "Accra" in extract("csv", b"city;pop\nAccra;2.5m\n").segments[0].text
    assert extract("text", "Akwaaba — welcome".encode("utf-16")).segments[0].text == "Akwaaba — welcome"


@pytest.mark.parametrize(
    ("kind", "data", "message"),
    [
        ("pdf", b"MZ\x90\x00 fake exe", "not a valid PDF"),
        ("docx", b"%PDF-1.4 not a docx", "not a valid .docx"),
        ("text", b"\x7fELF\x02\x01\x01\x00binary", "binary"),
        ("text", b"", "empty"),
    ],
)
def test_content_must_match_extension(kind, data, message):
    with pytest.raises(ExtractionError, match=message):
        extract(kind, data)


def test_zip_bomb_is_rejected_before_parsing(settings):
    settings.MAX_UNCOMPRESSED_MB = 1
    with pytest.raises(ExtractionError, match="unsafe size"):
        extract("docx", make_zip_bomb_docx(3))


def test_unsupported_extension():
    with pytest.raises(ExtractionError, match="Unsupported"):
        kind_for("setup.exe")
    assert kind_for("Report.PDF") == "pdf"
    assert kind_for("main.py") == "text"


def test_chunking_packs_small_and_splits_large_segments_keeping_pages():
    segments = [Segment("short one", page=1), Segment("short two", page=2), Segment("x. " * 3000, page=3)]
    chunks = chunk_segments(segments)
    assert chunks[0].text == "short one\n\nshort two" and chunks[0].location == "Pages 1–2"
    big = [c for c in chunks if c.page_start == 3]
    assert len(big) > 1 and all(len(c.text) <= CHUNK_CHARS for c in big)
