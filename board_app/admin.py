from django.contrib import admin
from .models import User, EmailConfirmation, Ad, Response


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "is_staff", "is_superuser")
    search_fields = ("email",)


@admin.register(EmailConfirmation)
class EmailConfirmationAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "is_confirmed", "created_at", "expires_at")
    search_fields = ("user__email",)


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "is_published", "created_at")
    list_filter = ("category", "is_published", "created_at")
    search_fields = ("title", "content", "author__email")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("ad", "author", "status", "created_at")
    list_filter = ("status", "created_at", "ad__category")
    search_fields = ("ad__title", "author__email", "text")