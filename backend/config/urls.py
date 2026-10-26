from django.contrib import admin
from django.urls import include, path

from apps.core.views import HealthView
from apps.providers.views import ModelListView
from apps.usage.views import MyUsageView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view()),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/models/", ModelListView.as_view()),
    path("api/usage/me/", MyUsageView.as_view()),
    path("api/", include("apps.chat.urls")),
]
