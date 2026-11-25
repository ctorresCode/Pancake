from datetime import date, timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from lessons.models import (
    Assignment,
    Classroom,
    Exercise,
    ExerciseResult,
    Lesson,
    LessonProgress,
    Membership,
    Option,
    new_class_code,
)

from .forms import BaseOptionFormSet, ExerciseForm, LessonForm

User = get_user_model()


def teacher_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_teacher:
            messages.error(request, "That page is only for teachers.")
            return redirect("lessons:home")
        return view(request, *args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            messages.error(request, "That page is only for the admin.")
            return redirect("panel:dashboard")
        return view(request, *args, **kwargs)

    return wrapper


# --- Qué ve cada profesor (el admin ve todo) ---

def my_lessons(user):
    return Lesson.objects.all() if user.is_admin else Lesson.objects.filter(owner=user)


def my_classes(user):
    return Classroom.objects.all() if user.is_admin else Classroom.objects.filter(teacher=user)


def my_students(user):
    students = User.objects.filter(role=User.STUDENT)
    if user.is_admin:
        return students
    return students.filter(memberships__classroom__teacher=user).distinct()


def option_formset(exercise, data=None, exercise_type=None):
    existing = exercise.options.count() if exercise.pk else 0
    FormSet = inlineformset_factory(
        Exercise,
        Option,
        formset=BaseOptionFormSet,
        fields=["text", "is_correct"],
        extra=max(4 - existing, 1),
        max_num=6,
        can_delete=True,
    )
    return FormSet(data, instance=exercise, prefix="opt", exercise_type=exercise_type)


@teacher_required
def dashboard(request):
    user = request.user
    today = timezone.localdate()
    students = my_students(user)
    lessons = my_lessons(user)
    results = ExerciseResult.objects.filter(user__in=students, exercise__lesson__in=lessons)
    answered = results.exclude(status=ExerciseResult.SKIPPED)
    stats = answered.aggregate(total=Count("id"), correct=Count("id", filter=Q(status=ExerciseResult.CORRECT)))
    accuracy = round(stats["correct"] * 100 / stats["total"]) if stats["total"] else 0
    hard = (
        Exercise.objects.filter(lesson__in=lessons)
        .annotate(
            tries=Count("results", filter=~Q(results__status=ExerciseResult.SKIPPED) & Q(results__user__in=students)),
            wrong=Count("results", filter=Q(results__status=ExerciseResult.WRONG) & Q(results__user__in=students)),
        )
        .filter(tries__gte=1, wrong__gte=1)
        .select_related("lesson")
        .order_by("-wrong")[:5]
    )
    return render(
        request,
        "panel/dashboard.html",
        {
            "n_students": students.count(),
            "n_classes": my_classes(user).count(),
            "active_today": students.filter(last_activity=today).count(),
            "active_week": students.filter(last_activity__gte=today - timedelta(days=6)).count(),
            "n_lessons": lessons.count(),
            "n_published": lessons.filter(published=True).count(),
            "accuracy": accuracy,
            "answered_total": stats["total"],
            "top": students.order_by("-xp")[:5],
            "recent": answered.select_related("user", "exercise__lesson").order_by("-updated_at")[:8],
            "hard": hard,
        },
    )


# --- Lecciones ---

@teacher_required
def lesson_list(request):
    lessons = (
        my_lessons(request.user)
        .select_related("owner")
        .annotate(
            n_exercises=Count("exercises", distinct=True),
            n_classes=Count("assignments", distinct=True),
            n_completed=Count("progress", filter=Q(progress__completed_at__isnull=False), distinct=True),
        )
        .order_by("level", "order", "id")
    )
    return render(request, "panel/lesson_list.html", {"lessons": lessons})


@teacher_required
def lesson_create(request):
    form = LessonForm(request.POST or None, initial={"level": "A1"})
    if request.method == "POST" and form.is_valid():
        lesson = form.save(commit=False)
        lesson.owner = request.user
        lesson.order = (Lesson.objects.filter(level=lesson.level).aggregate(m=Max("order"))["m"] or 0) + 1
        lesson.save()
        messages.success(request, "Lesson created! Now add some exercises.")
        return redirect("panel:lesson_edit", pk=lesson.pk)
    return render(request, "panel/lesson_form.html", {"form": form})


@teacher_required
def lesson_edit(request, pk):
    lesson = get_object_or_404(my_lessons(request.user), pk=pk)
    form = LessonForm(request.POST or None, instance=lesson)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Lesson saved.")
        return redirect("panel:lesson_edit", pk=lesson.pk)
    exercises = lesson.exercises.prefetch_related("options").order_by("trigger_seconds", "id")
    classes = Classroom.objects.filter(assignments__lesson=lesson).order_by("name")
    return render(
        request,
        "panel/lesson_form.html",
        {"form": form, "lesson": lesson, "exercises": exercises, "assigned_classes": classes},
    )


@teacher_required
@require_POST
def lesson_toggle(request, pk):
    lesson = get_object_or_404(my_lessons(request.user), pk=pk)
    lesson.published = not lesson.published
    lesson.save(update_fields=["published", "updated_at"])
    messages.success(request, f"{lesson.title} is now {'published' if lesson.published else 'a draft'}.")
    return redirect(request.POST.get("next") or "panel:lessons")


@teacher_required
def lesson_delete(request, pk):
    lesson = get_object_or_404(my_lessons(request.user), pk=pk)
    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Lesson deleted.")
        return redirect("panel:lessons")
    return render(request, "panel/confirm_delete.html", {"object": lesson, "kind": "this lesson"})


# --- Ejercicios ---

def _exercise_form(request, lesson, exercise):
    form = ExerciseForm(request.POST or None, instance=exercise)
    ex_type = request.POST.get("type") if request.method == "POST" else exercise.type
    formset = option_formset(exercise, request.POST or None, exercise_type=ex_type)
    if request.method == "POST":
        needs_options = ex_type in Exercise.OPTION_TYPES
        if form.is_valid() and (not needs_options or formset.is_valid()):
            with transaction.atomic():
                exercise = form.save(commit=False)
                exercise.lesson = lesson
                exercise.save()
                if needs_options:
                    formset.instance = exercise
                    formset.save()
                else:
                    exercise.options.all().delete()
            messages.success(request, "Exercise saved.")
            if "add_another" in request.POST:
                return redirect("panel:exercise_create", lesson_pk=lesson.pk)
            return redirect("panel:lesson_edit", pk=lesson.pk)
    return render(
        request,
        "panel/exercise_form.html",
        {
            "form": form,
            "formset": formset,
            "lesson": lesson,
            "exercise": exercise if exercise.pk else None,
            "type_help": EXERCISE_HELP,
            "more_open": ex_type in {e[0] for e in EXERCISE_HELP if not e[4]},
        },
    )


# (tipo, nombre, descripción, icono, ¿se muestra siempre?)
EXERCISE_HELP = [
    (Exercise.MULTIPLE_CHOICE, "Choose the answer", "A question with a few answers.", "list-checks", True),
    (Exercise.FILL_BLANK, "Fill in the blank", "A sentence with a missing word.", "pencil-line", True),
    (Exercise.TRUE_FALSE, "True or false", "Is the sentence right or not?", "scales", True),
    (Exercise.ORDER_WORDS, "Order the words", "The student builds the sentence.", "puzzle-piece", True),
    (Exercise.LISTENING, "Listen and choose", "Replays a short part of the video.", "headphones", False),
    (Exercise.LISTEN_TYPE, "Listen and type", "The student types what they heard.", "keyboard", False),
    (Exercise.FLASHCARD, "New word", "An expression to save.", "cards", False),
]


@teacher_required
def exercise_create(request, lesson_pk):
    lesson = get_object_or_404(my_lessons(request.user), pk=lesson_pk)
    last = lesson.exercises.order_by("-trigger_seconds").first()
    exercise = Exercise(lesson=lesson, trigger_seconds=(last.trigger_seconds + 30) if last else 30)
    return _exercise_form(request, lesson, exercise)


@teacher_required
def exercise_edit(request, pk):
    exercise = get_object_or_404(
        Exercise.objects.select_related("lesson").filter(lesson__in=my_lessons(request.user)), pk=pk
    )
    return _exercise_form(request, exercise.lesson, exercise)


@teacher_required
def exercise_delete(request, pk):
    exercise = get_object_or_404(
        Exercise.objects.select_related("lesson").filter(lesson__in=my_lessons(request.user)), pk=pk
    )
    if request.method == "POST":
        lesson_pk = exercise.lesson_id
        exercise.delete()
        messages.success(request, "Exercise deleted.")
        return redirect("panel:lesson_edit", pk=lesson_pk)
    return render(request, "panel/confirm_delete.html", {"object": exercise, "kind": "this exercise"})


# --- Clases ---

@teacher_required
def class_list(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()[:80]
        if not name:
            messages.error(request, "Give the class a name.")
            return redirect("panel:classes")
        classroom = Classroom.objects.create(name=name, teacher=request.user)
        messages.success(request, f"Class created. Share the code {classroom.code_display} with your students.")
        return redirect("panel:class_detail", pk=classroom.pk)
    classes = (
        my_classes(request.user)
        .select_related("teacher")
        .annotate(n_students=Count("memberships", distinct=True), n_lessons=Count("assignments", distinct=True))
    )
    return render(request, "panel/class_list.html", {"classes": classes})


@teacher_required
def class_detail(request, pk):
    classroom = get_object_or_404(my_classes(request.user).select_related("teacher"), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "assign":
            lesson = my_lessons(request.user).filter(pk=request.POST.get("lesson")).first()
            due = request.POST.get("due_date") or None
            if not lesson:
                messages.error(request, "Choose a lesson to assign.")
            else:
                try:
                    due = date.fromisoformat(due) if due else None
                except ValueError:
                    due = None
                _, created = Assignment.objects.update_or_create(
                    classroom=classroom, lesson=lesson, defaults={"due_date": due}
                )
                messages.success(request, f"{lesson.title} {'assigned' if created else 'updated'}.")
                if not lesson.published:
                    messages.info(request, "Heads up: that lesson is still a draft. Publish it so students can see it.")
        elif action == "unassign":
            Assignment.objects.filter(classroom=classroom, pk=request.POST.get("assignment")).delete()
            messages.success(request, "Lesson removed from the class.")
        elif action == "remove_student":
            Membership.objects.filter(classroom=classroom, user_id=request.POST.get("user")).delete()
            messages.success(request, "Student removed from the class.")
        elif action == "new_code":
            classroom.code = new_class_code()
            classroom.save(update_fields=["code"])
            messages.success(request, f"New code: {classroom.code_display}. The old one doesn't work anymore.")
        elif action == "rename":
            name = request.POST.get("name", "").strip()[:80]
            if name:
                classroom.name = name
                classroom.save(update_fields=["name"])
                messages.success(request, "Class renamed.")
        return redirect("panel:class_detail", pk=classroom.pk)

    assignments = list(classroom.assignments.select_related("lesson"))
    lesson_ids = [a.lesson_id for a in assignments]
    assigned = set(lesson_ids)
    available = my_lessons(request.user).exclude(pk__in=assigned).order_by("level", "order", "id")

    members = list(classroom.memberships.select_related("user"))
    done = {}
    for user_id, lesson_id in LessonProgress.objects.filter(
        user__in=[m.user_id for m in members], lesson_id__in=lesson_ids, completed_at__isnull=False
    ).values_list("user_id", "lesson_id"):
        done.setdefault(user_id, set()).add(lesson_id)
    today = timezone.localdate()
    for a in assignments:
        a.n_done = sum(1 for m in members if a.lesson_id in done.get(m.user_id, set()))
        a.is_past = bool(a.due_date and a.due_date < today)
    for m in members:
        m.n_done = len(done.get(m.user_id, set()))

    join_url = request.build_absolute_uri(reverse("lessons:join_code", args=[classroom.code]))
    return render(
        request,
        "panel/class_detail.html",
        {
            "classroom": classroom,
            "assignments": assignments,
            "available": available,
            "members": members,
            "n_lessons": len(assignments),
            "join_url": join_url,
        },
    )


@teacher_required
def class_delete(request, pk):
    classroom = get_object_or_404(my_classes(request.user), pk=pk)
    if request.method == "POST":
        classroom.delete()
        messages.success(request, "Class deleted.")
        return redirect("panel:classes")
    return render(request, "panel/confirm_delete.html", {"object": classroom, "kind": "this class"})


# --- Alumnos ---

@teacher_required
def student_list(request):
    q = request.GET.get("q", "").strip()
    students = my_students(request.user).annotate(
        n_completed=Count("lesson_progress", filter=Q(lesson_progress__completed_at__isnull=False), distinct=True),
    )
    if q:
        students = students.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
    return render(request, "panel/student_list.html", {"students": students.order_by("-xp"), "q": q})


@teacher_required
def student_detail(request, pk):
    student = get_object_or_404(my_students(request.user), pk=pk)
    progress = {p.lesson_id: p for p in LessonProgress.objects.filter(user=student)}
    per_lesson = {
        r["exercise__lesson"]: r
        for r in ExerciseResult.objects.filter(user=student)
        .exclude(status=ExerciseResult.SKIPPED)
        .values("exercise__lesson")
        .annotate(answered=Count("id"), correct=Count("id", filter=Q(status=ExerciseResult.CORRECT)))
    }
    rows = []
    lessons = my_lessons(request.user).annotate(n=Count("exercises")).order_by("level", "order", "id")
    for lesson in lessons:
        p, r = progress.get(lesson.pk), per_lesson.get(lesson.pk)
        if p or r:
            rows.append(
                {
                    "lesson": lesson,
                    "watched": p.watched_percent if p else 0,
                    "answered": r["answered"] if r else 0,
                    "correct": r["correct"] if r else 0,
                    "completed": bool(p and p.completed_at),
                }
            )
    xp_total = ExerciseResult.objects.filter(user=student).aggregate(s=Sum("xp_awarded"))["s"] or 0
    classes = my_classes(request.user).filter(memberships__user=student)
    return render(
        request,
        "panel/student_detail.html",
        {"student": student, "rows": rows, "xp_total": xp_total, "classes": classes},
    )


# --- Usuarios (solo admin) ---

@admin_required
def user_list(request):
    if request.method == "POST":
        target = get_object_or_404(User, pk=request.POST.get("user"))
        role = request.POST.get("role")
        if target.pk == request.user.pk:
            messages.error(request, "You can't change your own role.")
        elif role in dict(User.ROLES):
            target.role = role
            target.is_staff = role == User.ADMIN  # solo el admin entra al admin de Django
            target.save(update_fields=["role", "is_staff"])
            messages.success(request, f"{target.display_name} is now {target.get_role_display().lower()}.")
        return redirect(f"{reverse('panel:users')}?q={request.POST.get('q', '')}")
    q = request.GET.get("q", "").strip()
    users = User.objects.order_by("-date_joined")
    if q:
        users = users.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
    return render(request, "panel/user_list.html", {"users": users, "q": q, "roles": User.ROLES})
