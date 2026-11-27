import re

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone
from PIL import Image

from pancake.images import open_photo, to_jpeg

from lessons.models import Exercise, Lesson, Option, fmt_time

YT_PATTERNS = [
    r"(?:v=|/embed/|/shorts/|/live/|youtu\.be/)([A-Za-z0-9_-]{11})",
    r"^([A-Za-z0-9_-]{11})$",
]


def parse_youtube_id(value):
    value = (value or "").strip()
    for pattern in YT_PATTERNS:
        m = re.search(pattern, value)
        if m:
            return m.group(1)
    return None


class TimestampField(forms.CharField):
    """Acepta '1:20', '01:20', '1:02:03' o segundos ('80')."""

    def prepare_value(self, value):
        if isinstance(value, int):
            return fmt_time(value)
        return value

    def to_python(self, value):
        value = (value or "").strip()
        if not value:
            return None
        if re.fullmatch(r"\d+", value):
            return int(value)
        if re.fullmatch(r"\d+(:\d{1,2}){1,2}", value):
            total = 0
            for part in value.split(":"):
                total = total * 60 + int(part)
            return total
        raise forms.ValidationError("Use m:ss (for example 1:20) or seconds.")


class LessonForm(forms.ModelForm):
    youtube_id = forms.CharField(
        label="YouTube video link (optional)",
        required=False,
        help_text="Open the video on YouTube, copy the link at the top and paste it here. Leave it empty for a lesson with exercises only.",
        widget=forms.TextInput(attrs={"placeholder": "https://www.youtube.com/watch?v=..."}),
    )

    class Meta:
        model = Lesson
        fields = ["title", "youtube_id", "level", "description"]
        labels = {"title": "Lesson name", "level": "Level", "description": "Short description (optional)"}
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Greetings in English"}),
            "level": forms.RadioSelect,
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. Learn how to say hello and goodbye."}),
        }

    photo = forms.ImageField(
        label="Photo (optional)",
        required=False,
        help_text="Shown above the exercises when the lesson has no video, and as the lesson's cover.",
    )
    remove_photo = forms.BooleanField(required=False, label="Remove the photo")

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 8 * 1024 * 1024:
            raise forms.ValidationError("That photo is too big. Use one under 8 MB.")
        if photo:
            try:
                self.photo_bytes = shrink_photo(photo)
            except ValueError:
                raise forms.ValidationError("We couldn't open that photo. Try a JPG or PNG.")
        return photo

    def save(self, commit=True):
        lesson = super().save(commit=False)
        if self.cleaned_data.get("remove_photo"):
            lesson.image, lesson.image_updated = None, None
        elif getattr(self, "photo_bytes", None):
            lesson.image = self.photo_bytes
            lesson.image_updated = timezone.now()
        if commit:
            lesson.save()
        return lesson

    def clean_youtube_id(self):
        if not self.cleaned_data["youtube_id"].strip():
            return ""
        vid = parse_youtube_id(self.cleaned_data["youtube_id"])
        if not vid:
            raise forms.ValidationError("That doesn't look like a YouTube video. Paste the full YouTube link.")
        return vid


class ExerciseForm(forms.ModelForm):
    trigger_seconds = TimestampField(label="Shows up at", help_text="Minute:second of the video.")
    clip_start = TimestampField(label="Clip from", required=False)
    clip_end = TimestampField(label="Clip to", required=False)
    correct_bool = forms.TypedChoiceField(
        label="The sentence is",
        choices=[("true", "True"), ("false", "False")],
        coerce=lambda v: v == "true",
        required=False,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Exercise
        fields = [
            "type",
            "trigger_seconds",
            "prompt",
            "sentence",
            "answer_text",
            "extra_words",
            "correct_bool",
            "clip_start",
            "clip_end",
            "explanation",
            "pause_video",
            "xp",
        ]
        widgets = {"type": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.correct_bool is not None:
            self.initial["correct_bool"] = "true" if self.instance.correct_bool else "false"
        for name in ("clip_start", "clip_end", "trigger_seconds"):
            if isinstance(self.initial.get(name), int):
                self.initial[name] = fmt_time(self.initial[name])

    def clean(self):
        data = super().clean()
        t = data.get("type")
        sentence = (data.get("sentence") or "").strip()
        if t in Exercise.CLIP_TYPES and not self.instance.lesson.youtube_id:
            self.add_error("type", "This lesson has no video, so it can't use listening exercises.")
        if t == Exercise.FILL_BLANK and "___" not in sentence:
            self.add_error("sentence", "Write the sentence with ___ where the missing word goes.")
        if t == Exercise.TRUE_FALSE:
            if not sentence:
                self.add_error("sentence", "Write the sentence.")
            if data.get("correct_bool") in (None, ""):
                self.add_error("correct_bool", "Choose true or false.")
        else:
            data["correct_bool"] = None
        if t == Exercise.ORDER_WORDS and len(sentence.split()) < 2:
            self.add_error("sentence", "Write the correct sentence (at least 2 words).")
        if t == Exercise.LISTEN_TYPE and not (data.get("answer_text") or "").strip():
            self.add_error("answer_text", "Write what is said in the clip.")
        if t == Exercise.FLASHCARD:
            if not sentence:
                self.add_error("sentence", "Write the word or expression.")
            if not (data.get("answer_text") or "").strip():
                self.add_error("answer_text", "Write what it means.")
        if t in (Exercise.MULTIPLE_CHOICE, Exercise.LISTENING) and not (data.get("prompt") or "").strip():
            self.add_error("prompt", "Write the question.")
        start, end = data.get("clip_start"), data.get("clip_end")
        if start is not None and end is not None and end <= start:
            self.add_error("clip_end", "The clip has to end after it starts.")
        return data


class BaseOptionFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, exercise_type=None, **kwargs):
        self.exercise_type = exercise_type
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.exercise_type not in Exercise.OPTION_TYPES:
            return
        alive = [
            f
            for f in self.forms
            if f.cleaned_data and not f.cleaned_data.get("DELETE") and (f.cleaned_data.get("text") or "").strip()
        ]
        if len(alive) < 2:
            raise forms.ValidationError("Add at least 2 answers.")
        n_correct = sum(1 for f in alive if f.cleaned_data.get("is_correct"))
        if n_correct != 1:
            raise forms.ValidationError("Mark exactly one answer as correct.")


OptionFormSet = inlineformset_factory(
    Exercise,
    Option,
    formset=BaseOptionFormSet,
    fields=["text", "is_correct"],
    extra=4,
    max_num=6,
    can_delete=True,
    widgets={"text": forms.TextInput(attrs={"placeholder": "Write an answer"})},
)


def shrink_photo(upload, max_side=1280):
    """Reduce la foto para que pese poco, sin recortarla. ValueError si no es una foto válida."""
    img = open_photo(upload, max_side)
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    return to_jpeg(img)
