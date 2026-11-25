import secrets

from django.db import migrations

CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Lesson = apps.get_model("lessons", "Lesson")
    Classroom = apps.get_model("lessons", "Classroom")
    Membership = apps.get_model("lessons", "Membership")
    Assignment = apps.get_model("lessons", "Assignment")

    # Los que ya eran staff pasan a ser admin
    User.objects.filter(is_staff=True).update(role="admin")

    admin = User.objects.filter(role="admin").order_by("id").first()
    if not admin:
        return  # base de datos nueva, no hay nada que pasar

    Lesson.objects.filter(owner__isnull=True).update(owner=admin)

    published = list(Lesson.objects.filter(published=True).order_by("level", "order", "id"))
    students = list(User.objects.filter(is_staff=False, is_superuser=False))
    if not published or not students:
        return

    # Clase "General" para que los alumnos actuales sigan viendo sus lecciones
    code = "".join(secrets.choice(CODE_CHARS) for _ in range(6))
    while Classroom.objects.filter(code=code).exists():
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(6))
    general = Classroom.objects.create(name="General", teacher=admin, code=code)
    for lesson in published:
        Assignment.objects.create(classroom=general, lesson=lesson)
    for student in students:
        Membership.objects.create(classroom=general, user=student)


class Migration(migrations.Migration):
    dependencies = [
        ("lessons", "0006_classes"),
        ("accounts", "0003_classes"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
