from rest_framework.routers import DefaultRouter

from .views import AnalysisResultViewSet

router = DefaultRouter()
router.register("analysis-results", AnalysisResultViewSet, basename="analysis-result")
urlpatterns = router.urls
