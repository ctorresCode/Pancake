from django.contrib import admin
from django.urls import include, path

from lessons import views as lesson_views

urlpatterns = [
    path("", lesson_views.landing, name="landing"),
    path("cuenta/", include("allauth.urls")),
    path("aprender/", include("lessons.urls")),
    path("panel/", include("panel.urls")),
    path("django-admin/", admin.site.urls),
]
