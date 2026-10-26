from django.conf import settings
from django.db import models


class AnalysisResult(models.Model):
    """A table computed by a deterministic analysis tool; kept so it can be charted and downloaded."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="analysis_results")
    conversation = models.ForeignKey("chat.Conversation", on_delete=models.CASCADE, related_name="analysis_results")
    document = models.ForeignKey("documents.Document", null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=200)
    query = models.JSONField()  # the validated operation that produced this result (reproducibility)
    columns = models.JSONField()
    rows = models.JSONField()  # capped at ANALYSIS_RESULT_MAX_ROWS
    total_rows = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
