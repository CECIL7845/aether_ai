import csv
import io

from django.http import HttpResponse
from django.utils.text import slugify
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.serializers import ModelSerializer

from .models import AnalysisResult

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value) -> str:
    """Prevents CSV/formula injection when the file is opened in a spreadsheet program."""
    if value is None:
        return ""
    text = str(value)
    if text.startswith(_FORMULA_PREFIXES) and not _is_number(text):
        return "'" + text
    return text


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


class AnalysisResultSerializer(ModelSerializer):
    class Meta:
        model = AnalysisResult
        fields = ("id", "title", "query", "columns", "total_rows", "created_at")


class AnalysisResultViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AnalysisResultSerializer

    def get_queryset(self):
        return AnalysisResult.objects.filter(user=self.request.user)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        result = self.get_object()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([safe_cell(c) for c in result.columns])
        for row in result.rows:
            writer.writerow([safe_cell(v) for v in row])
        response = HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")
        name = slugify(result.title)[:60] or "result"
        response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
        return response
