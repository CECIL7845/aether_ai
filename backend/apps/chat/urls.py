from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("conversations", views.ConversationViewSet, basename="conversation")

urlpatterns = [
    path("conversations/<int:conversation_id>/messages/", views.send_message),
    path("conversations/<int:conversation_id>/regenerate/", views.regenerate),
    path("conversations/<int:conversation_id>/messages/<int:message_id>/edit/", views.edit_message),
    *router.urls,
]
