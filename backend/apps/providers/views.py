from rest_framework.response import Response
from rest_framework.views import APIView

from .registry import MODELS, available_models, default_model


class ModelListView(APIView):
    def get(self, request):
        available = {m.id for m in available_models()}
        default = default_model()
        return Response({
            "default": default.id if default else None,
            "models": [{**m.public_dict(), "available": m.id in available} for m in MODELS],
        })
