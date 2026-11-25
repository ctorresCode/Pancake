from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("lecciones/", views.lesson_list, name="lessons"),
    path("lecciones/nueva/", views.lesson_create, name="lesson_create"),
    path("lecciones/<int:pk>/", views.lesson_edit, name="lesson_edit"),
    path("lecciones/<int:pk>/publicar/", views.lesson_toggle, name="lesson_toggle"),
    path("lecciones/<int:pk>/asignar/", views.lesson_assign, name="lesson_assign"),
    path("lecciones/<int:pk>/eliminar/", views.lesson_delete, name="lesson_delete"),
    path("lecciones/<int:lesson_pk>/ejercicios/nuevo/", views.exercise_create, name="exercise_create"),
    path("ejercicios/<int:pk>/", views.exercise_edit, name="exercise_edit"),
    path("ejercicios/<int:pk>/eliminar/", views.exercise_delete, name="exercise_delete"),
    path("clases/", views.class_list, name="classes"),
    path("clases/<int:pk>/", views.class_detail, name="class_detail"),
    path("clases/<int:pk>/eliminar/", views.class_delete, name="class_delete"),
    path("usuarios/", views.user_list, name="users"),
    path("estudiantes/", views.student_list, name="students"),
    path("estudiantes/<int:pk>/", views.student_detail, name="student_detail"),
]
