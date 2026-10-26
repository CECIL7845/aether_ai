from django.conf import settings
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness + readiness: confirms the database and pgvector extension are reachable."""

    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        checks = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cursor.fetchone()
            checks["database"] = "ok"
            checks["pgvector"] = row[0] if row else "missing"
        except Exception:
            checks["database"] = "unavailable"
        healthy = checks.get("database") == "ok" and checks.get("pgvector") != "missing"
        return Response(
            {"status": "ok" if healthy else "degraded", "product": settings.PRODUCT_NAME, "checks": checks},
            status=200 if healthy else 503,
        )
