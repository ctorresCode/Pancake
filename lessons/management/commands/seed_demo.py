"""Crea una lección de ejemplo para probar Pancake.

Uso: python manage.py seed_demo
"""
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand

from lessons.models import Exercise, Lesson, Option


class Command(BaseCommand):
    help = "Crea una lección de demostración con todos los tipos de ejercicio."

    def handle(self, *args, **options):
        Site.objects.update_or_create(
            pk=settings.SITE_ID, defaults={"domain": "localhost:8000", "name": "Pancake"}
        )

        lesson, created = Lesson.objects.get_or_create(
            slug="demo-learn-english-with-music",
            defaults={
                "title": "Learn English with Music",
                "description": "Lección de ejemplo: practica vocabulario y gramática con una canción famosa.",
                "level": "A1",
                "order": 1,
                "youtube_id": "dQw4w9WgXcQ",
                "published": True,
            },
        )
        if not created:
            self.stdout.write(self.style.WARNING("La lección demo ya existe; no se tocó."))
            return

        def ex(**kw):
            opts = kw.pop("options", [])
            e = Exercise.objects.create(lesson=lesson, **kw)
            for text, ok in opts:
                Option.objects.create(exercise=e, text=text, is_correct=ok)
            return e

        ex(
            type=Exercise.MULTIPLE_CHOICE, trigger_seconds=22,
            prompt='What does "strangers" mean?',
            explanation="A stranger is a person you don't know.",
            options=[("Extraños / desconocidos", True), ("Amigos", False), ("Vecinos", False), ("Familiares", False)],
        )
        ex(
            type=Exercise.FILL_BLANK, trigger_seconds=29,
            sentence="You know the rules and so ___ I.",
            explanation='"So do I" = "yo también" (con verbos en presente simple).',
            options=[("do", True), ("am", False), ("does", False), ("have", False)],
        )
        ex(
            type=Exercise.TRUE_FALSE, trigger_seconds=52,
            sentence='"Never gonna" is an informal way to say "never going to".',
            correct_bool=True,
            explanation='"Gonna" = "going to" en inglés hablado e informal.',
        )
        ex(
            type=Exercise.ORDER_WORDS, trigger_seconds=42,
            sentence="I just want to tell you how I'm feeling",
            extra_words="feel, said",
            pause_video=True,
        )
        ex(
            type=Exercise.LISTENING, trigger_seconds=60, clip_start=43, clip_end=48,
            prompt="Listen again: what is the singer going to do?",
            options=[("Never give you up", True), ("Never call you up", False), ("Never pick you up", False)],
        )
        ex(
            type=Exercise.FLASHCARD, trigger_seconds=70,
            sentence="to let (someone) down",
            answer_text="decepcionar / fallarle a alguien",
            explanation="Ej: \"Don't let me down\" = \"No me falles\".",
        )
        self.stdout.write(self.style.SUCCESS(f"Lección demo creada: {lesson.title} ({lesson.exercises.count()} ejercicios)"))
