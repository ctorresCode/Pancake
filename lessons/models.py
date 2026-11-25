import random
import re
import secrets
import unicodedata

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify

LEVELS = [
    ("A1", "Beginner (A1)"),
    ("A2", "Elementary (A2)"),
    ("B1", "Intermediate (B1)"),
    ("B2", "Upper intermediate (B2)"),
    ("C1", "Advanced (C1)"),
]


def fmt_time(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


def normalize_text(value):
    """Lowercase, no accents, no punctuation, single spaces."""
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = value.lower().replace("’", "'")
    value = re.sub(r"[^\w\s']", " ", value)
    return " ".join(value.split())


class Lesson(models.Model):
    title = models.CharField("title", max_length=160)
    slug = models.SlugField(unique=True, max_length=180, blank=True)
    description = models.TextField("description", blank=True)
    level = models.CharField("level", max_length=2, choices=LEVELS, default="A1")
    order = models.PositiveIntegerField("lesson number", default=1)
    youtube_id = models.CharField("YouTube video ID", max_length=20)
    published = models.BooleanField("published", default=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="lessons_owned"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["level", "order", "id"]
        verbose_name = "lesson"
        verbose_name_plural = "lessons"

    def __str__(self):
        return f"{self.title} ({self.level})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:150] or "leccion"
            slug, n = base, 2
            while Lesson.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("lessons:detail", args=[self.slug])

    @property
    def thumbnail(self):
        # mqdefault es 320x180: más liviana que hqdefault y sin franjas negras
        return f"https://img.youtube.com/vi/{self.youtube_id}/mqdefault.jpg"


class Exercise(models.Model):
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    TRUE_FALSE = "true_false"
    ORDER_WORDS = "order_words"
    LISTENING = "listening"
    LISTEN_TYPE = "listen_type"
    FLASHCARD = "flashcard"

    TYPES = [
        (MULTIPLE_CHOICE, "Choose the answer"),
        (FILL_BLANK, "Fill in the blank"),
        (TRUE_FALSE, "True or false"),
        (ORDER_WORDS, "Order the words"),
        (LISTENING, "Listen and choose"),
        (LISTEN_TYPE, "Listen and type"),
        (FLASHCARD, "New word"),
    ]
    OPTION_TYPES = {MULTIPLE_CHOICE, FILL_BLANK, LISTENING}
    CLIP_TYPES = {LISTENING, LISTEN_TYPE}

    LABELS = {
        MULTIPLE_CHOICE: "Choose the answer",
        FILL_BLANK: "Fill in the blank",
        TRUE_FALSE: "True or false?",
        ORDER_WORDS: "Order the words",
        LISTENING: "What did you hear?",
        LISTEN_TYPE: "Listen and type",
        FLASHCARD: "New expression",
    }

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="exercises")
    type = models.CharField("type", max_length=20, choices=TYPES, default=MULTIPLE_CHOICE)
    trigger_seconds = models.PositiveIntegerField("shows up at (seconds)", default=0)
    prompt = models.CharField("question / instruction", max_length=300, blank=True)
    sentence = models.CharField(
        "sentence",
        max_length=300,
        blank=True,
        help_text="Fill in the blank: use ___ for the gap. Order the words: the correct sentence. New word: the expression.",
    )
    answer_text = models.CharField(
        "typed answer / meaning",
        max_length=300,
        blank=True,
        help_text="Listen and type: the correct answer (separate alternatives with |). New word: its meaning.",
    )
    extra_words = models.CharField(
        "extra words", max_length=200, blank=True, help_text="Separated by commas."
    )
    correct_bool = models.BooleanField("the statement is true", null=True, blank=True)
    clip_start = models.PositiveIntegerField("clip start (s)", null=True, blank=True)
    clip_end = models.PositiveIntegerField("clip end (s)", null=True, blank=True)
    explanation = models.CharField("explanation", max_length=400, blank=True)
    pause_video = models.BooleanField("pause the video when it shows up", default=False)
    xp = models.PositiveSmallIntegerField("XP", default=10)

    class Meta:
        ordering = ["trigger_seconds", "id"]
        verbose_name = "exercise"

    def __str__(self):
        return f"{self.get_type_display()} @ {fmt_time(self.trigger_seconds)}"

    @property
    def trigger_label(self):
        return fmt_time(self.trigger_seconds)

    @property
    def label(self):
        return self.LABELS.get(self.type, "Exercise")

    @property
    def title_text(self):
        """Texto principal que se muestra al estudiante."""
        if self.prompt:
            return self.prompt
        if self.type == self.FILL_BLANK:
            return "Fill in the blank:"
        if self.type == self.ORDER_WORDS:
            return "Put the words in order"
        if self.type == self.LISTEN_TYPE:
            return "Type what you heard"
        return self.label

    def tiles(self):
        words = self.sentence.split()
        extras = [w.strip() for w in self.extra_words.split(",") if w.strip()]
        tiles = words + extras
        rnd = random.Random(self.pk)
        for _ in range(5):
            rnd.shuffle(tiles)
            if tiles != words + extras or len(tiles) < 2:
                break
        return tiles

    def public_data(self, result=None, saved=False):
        """Datos que recibe el navegador (sin respuestas correctas)."""
        data = {
            "id": self.pk,
            "type": self.type,
            "label": self.label,
            "trigger": self.trigger_seconds,
            "triggerLabel": self.trigger_label,
            "title": self.title_text,
            "pause": self.pause_video,
            "xp": self.xp,
            "status": result.status if result else None,
        }
        # Si ya lo respondió, se manda su respuesta y la correcta para el repaso
        if result and result.status in (ExerciseResult.CORRECT, ExerciseResult.WRONG) and self.type != self.FLASHCARD:
            data["lastAnswer"] = result.last_answer
            data["correctAnswer"] = self.correct_display()
            data["explanation"] = self.explanation
        if self.type in self.OPTION_TYPES:
            data["options"] = [{"id": o.pk, "text": o.text} for o in self.options.all()]
        if self.type == self.FILL_BLANK:
            data["sentence"] = self.sentence
        if self.type == self.TRUE_FALSE:
            data["statement"] = self.sentence
        if self.type == self.ORDER_WORDS:
            data["tiles"] = self.tiles()
        if self.type in self.CLIP_TYPES:
            start = self.clip_start if self.clip_start is not None else max(self.trigger_seconds - 5, 0)
            end = self.clip_end if self.clip_end is not None else self.trigger_seconds
            data["clip"] = [start, max(end, start + 1)]
        if self.type == self.FLASHCARD:
            data["expression"] = self.sentence
            data["meaning"] = self.answer_text
            data["explanation"] = self.explanation
            data["saved"] = saved
        return data

    def correct_display(self):
        if self.type in self.OPTION_TYPES:
            # all() aprovecha el prefetch_related cuando la vista lo hizo
            return next((o.text for o in self.options.all() if o.is_correct), "")
        if self.type == self.TRUE_FALSE:
            return "True" if self.correct_bool else "False"
        if self.type == self.ORDER_WORDS:
            return self.sentence
        if self.type == self.LISTEN_TYPE:
            return self.answer_text.split("|")[0].strip()
        return ""

    def check_answer(self, answer):
        """Devuelve True si la respuesta es correcta."""
        if self.type == self.FLASHCARD:
            return True
        if self.type in self.OPTION_TYPES:
            try:
                return self.options.filter(pk=int(answer), is_correct=True).exists()
            except (TypeError, ValueError):
                return False
        if self.type == self.TRUE_FALSE:
            if isinstance(answer, str):
                answer = answer.lower() == "true"
            return bool(answer) == bool(self.correct_bool)
        if self.type == self.ORDER_WORDS:
            if isinstance(answer, list):
                answer = " ".join(str(w) for w in answer)
            return normalize_text(answer) == normalize_text(self.sentence)
        if self.type == self.LISTEN_TYPE:
            given = normalize_text(str(answer))
            return any(given == normalize_text(alt) for alt in self.answer_text.split("|") if alt.strip())
        return False


class Option(models.Model):
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="options")
    text = models.CharField("text", max_length=200)
    is_correct = models.BooleanField("correct", default=False)

    class Meta:
        ordering = ["id"]
        verbose_name = "option"
        verbose_name_plural = "options"

    def __str__(self):
        return self.text


class ExerciseResult(models.Model):
    CORRECT = "correct"
    WRONG = "wrong"
    SKIPPED = "skipped"
    STATUSES = [(CORRECT, "Correct"), (WRONG, "Wrong"), (SKIPPED, "Skipped")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="results")
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="results")
    status = models.CharField(max_length=10, choices=STATUSES)
    attempts = models.PositiveIntegerField(default=0)
    xp_awarded = models.PositiveIntegerField(default=0)
    last_answer = models.JSONField(null=True, blank=True)  # lo último que respondió el alumno
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "exercise")]


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    watched_percent = models.PositiveSmallIntegerField(default=0)
    last_position = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "lesson")]


class VocabItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vocab")
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "exercise")]
        ordering = ["-created_at"]


CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I/L para que no se confundan


def new_class_code():
    while True:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(6))
        if not Classroom.objects.filter(code=code).exists():
            return code


def clean_code(value):
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


class Classroom(models.Model):
    name = models.CharField("class name", max_length=80)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="classrooms_taught")
    code = models.CharField(max_length=12, unique=True, blank=True)
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, through="Membership", related_name="classrooms")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "class"
        verbose_name_plural = "classes"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = new_class_code()
        super().save(*args, **kwargs)

    @property
    def code_display(self):
        return f"{self.code[:3]}-{self.code[3:]}"


class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="memberships")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "classroom")]
        ordering = ["joined_at"]


class Assignment(models.Model):
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name="assignments")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="assignments")
    due_date = models.DateField("due date", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("classroom", "lesson")]
        ordering = [models.F("due_date").asc(nulls_last=True), "created_at", "id"]
