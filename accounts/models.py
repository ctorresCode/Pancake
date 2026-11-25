from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Usuario de Pancake: alumno, profesor o admin.

    El admin puede todo y es quien nombra profesores.
    Un profesor maneja sus lecciones y sus clases.
    """

    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    ROLES = [(STUDENT, "Student"), (TEACHER, "Teacher"), (ADMIN, "Admin")]

    role = models.CharField("role", max_length=10, choices=ROLES, default=STUDENT)
    role_confirmed = models.BooleanField(default=False)  # False hasta que elige alumno o profe
    email = models.EmailField("email", unique=True)
    xp = models.PositiveIntegerField("XP", default=0)
    streak = models.PositiveIntegerField("streak", default=0)
    best_streak = models.PositiveIntegerField("best streak", default=0)
    last_activity = models.DateField("last activity", null=True, blank=True)
    bio = models.CharField("about me", max_length=280, blank=True)
    # La foto va en la base de datos (ya reducida) porque Railway borra los archivos subidos al desplegar
    avatar = models.BinaryField(null=True, blank=True, editable=False)
    avatar_updated = models.DateTimeField(null=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        # El superusuario (createsuperuser) siempre es admin y no tiene que elegir rol
        if self.is_superuser:
            self.role = self.ADMIN
            self.role_confirmed = True
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.role == self.ADMIN or self.is_superuser

    @property
    def is_teacher(self):
        """Profesores y admins entran al panel."""
        return self.role in (self.TEACHER, self.ADMIN) or self.is_superuser

    @property
    def avatar_url(self):
        if not self.avatar_updated:
            return ""
        from django.urls import reverse
        return f"{reverse('avatar', args=[self.pk])}?v={int(self.avatar_updated.timestamp())}"

    @property
    def display_name(self):
        return self.first_name or self.username

    @property
    def current_streak(self):
        """La racha sigue viva si practicó hoy o ayer."""
        if not self.last_activity:
            return 0
        if timezone.localdate() - self.last_activity > timedelta(days=1):
            return 0
        return self.streak

    @property
    def practiced_today(self):
        return self.last_activity == timezone.localdate()

    def register_activity(self, xp_gained=0):
        """Suma XP y actualiza la racha diaria. Devuelve True si la racha subió hoy."""
        today = timezone.localdate()
        streak_up = False
        if self.last_activity != today:
            if self.last_activity == today - timedelta(days=1):
                self.streak += 1
            else:
                self.streak = 1
            self.last_activity = today
            self.best_streak = max(self.best_streak, self.streak)
            streak_up = True
        self.xp += xp_gained
        self.save(update_fields=["xp", "streak", "best_streak", "last_activity"])
        return streak_up
