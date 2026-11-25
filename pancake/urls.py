from django.contrib import admin
from django.urls import include, path

from accounts import views as account_views
from lessons import views as lesson_views

urlpatterns = [
    path("", lesson_views.landing, name="landing"),
    path("cuenta/rol/", account_views.choose_role, name="choose_role"),
    path("perfil/", account_views.profile, name="profile"),
    path("perfil/foto/<int:pk>/", account_views.avatar, name="avatar"),
    path("cuenta/", include("allauth.urls")),
    path("aprender/", include("lessons.urls")),
    path("panel/", include("panel.urls")),
    path("django-admin/", admin.site.urls),
]
