from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "display_name", "is_active", "is_staff", "date_joined")
    search_fields = ("email", "display_name")
    list_filter = ("is_active", "is_staff")
    exclude = ("password",)
    readonly_fields = ("last_login", "date_joined")
