from django.urls import path

from . import views

app_name = "lessons"

urlpatterns = [
    path("", views.home, name="home"),
    path("progreso/", views.my_progress, name="progress"),
    path("vocabulario/", views.vocabulary, name="vocabulary"),
    path("unirse/", views.join, name="join"),
    path("unirse/<str:code>/", views.join, name="join_code"),
    path("vocabulario/<int:pk>/quitar/", views.vocab_remove, name="vocab_remove"),
    path("leccion/<slug:slug>/", views.lesson_detail, name="detail"),
    path("leccion/<int:pk>/foto/", views.lesson_image, name="lesson_image"),
    path("clase/<int:pk>/foto/", views.class_image, name="class_image"),
    path("api/ejercicio/<int:pk>/check/", views.api_check, name="api_check"),
    path("api/ejercicio/<int:pk>/skip/", views.api_skip, name="api_skip"),
    path("api/ejercicio/<int:pk>/vocab/", views.api_vocab, name="api_vocab"),
    path("api/leccion/<int:pk>/progreso/", views.api_progress, name="api_progress"),
]
