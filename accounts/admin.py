from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "xp", "streak", "date_joined")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Pancake", {"fields": ("role", "xp", "streak", "best_streak", "last_activity")}),
    )
