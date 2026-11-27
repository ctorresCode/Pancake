import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Assignment,
    Classroom,
    DailyXP,
    Exercise,
    ExerciseResult,
    Lesson,
    LessonProgress,
    Membership,
    VocabItem,
    clean_code,
)


def landing(request):
    if request.user.is_authenticated:
        return redirect("panel:classes" if request.user.is_teacher else "lessons:home")
    return render(request, "landing.html")


def lessons_for(user):
    """Lecciones que este usuario puede abrir."""
    if user.is_admin:
        return Lesson.objects.all()
    assigned = Q(published=True, assignments__classroom__memberships__user=user)
    if user.is_teacher:
        return Lesson.objects.filter(Q(owner=user) | assigned).distinct()
    return Lesson.objects.filter(assigned).distinct()


def _visible_lessons(user):
    return lessons_for(user).annotate(n_exercises=Count("exercises", distinct=True)).order_by("level", "order", "id")


def _can_open(user, lesson_id):
    return lessons_for(user).filter(pk=lesson_id).exists()


@login_required
def home(request):
    user = request.user
    if user.is_teacher:  # la lista del alumno no aplica al profe; su inicio es My classes
        return redirect("panel:classes")
    today = timezone.localdate()
    n_exercises = dict(Exercise.objects.values("lesson").annotate(n=Count("id")).values_list("lesson", "n"))
    done_counts = dict(
        ExerciseResult.objects.filter(user=user)
        .exclude(status=ExerciseResult.SKIPPED)
        .values("exercise__lesson")
        .annotate(n=Count("id"))
        .values_list("exercise__lesson", "n")
    )
    completed = set(
        LessonProgress.objects.filter(user=user, completed_at__isnull=False).values_list("lesson_id", flat=True)
    )

    def decorate(lesson):
        lesson.n_exercises = n_exercises.get(lesson.pk, 0)
        lesson.done_exercises = done_counts.get(lesson.pk, 0)
        # Si el profe añadió ejercicios después, vuelve a quedar pendiente
        lesson.is_completed = lesson.pk in completed and lesson.done_exercises >= lesson.n_exercises
        lesson.is_current = False
        return lesson

    classes, seen = [], set()
    published = Assignment.objects.filter(lesson__published=True).select_related("lesson").defer("lesson__image")
    memberships = Membership.objects.filter(user=user).select_related("classroom__teacher").defer("classroom__image").prefetch_related(
        Prefetch("classroom__assignments", queryset=published, to_attr="published_assignments")
    )
    for m in memberships:
        items = []
        for a in m.classroom.published_assignments:
            decorate(a.lesson)
            done = a.lesson.is_completed
            a.is_late = bool(a.due_date and a.due_date < today and not done)
            a.due_today = a.due_date == today
            a.due_soon = bool(a.due_date and not done and 0 <= (a.due_date - today).days <= 2)
            items.append(a)
            seen.add(a.lesson.pk)
        classes.append({"classroom": m.classroom, "items": items})

    # La primera lección pendiente es "la que toca"
    for c in classes:
        pending = next((a for a in c["items"] if not a.lesson.is_completed), None)
        if pending:
            pending.lesson.is_current = True
            break

    today_xp = DailyXP.objects.filter(user=user, day=today).values_list("xp", flat=True).first() or 0
    return render(
        request,
        "lessons/home.html",
        {
            "classes": classes,
            "completed_count": len({a.lesson.pk for c in classes for a in c["items"] if a.lesson.is_completed}),
            "total_lessons": len(seen),
            "today_xp": today_xp,
            "daily_goal": 50,
        },
    )


@login_required
def join(request, code=None):
    user = request.user
    raw = request.POST.get("code") if request.method == "POST" else code
    classroom, error = None, None
    # Límite de intentos para que no se puedan adivinar códigos probando muchos seguidos
    key = f"join-tries:{user.pk}"
    if raw and cache.get(key, 0) >= 15:
        error = "Too many tries. Wait a few minutes and try again."
        raw = None
    if raw:
        classroom = Classroom.objects.filter(code=clean_code(raw)).select_related("teacher").first()
        if not classroom:
            error = "We couldn't find a class with that code. Check it and try again."
            cache.set(key, cache.get(key, 0) + 1, 600)
    if request.method == "POST" and classroom:
        if classroom.teacher_id == user.pk:
            messages.info(request, "You're the teacher of this class.")
            return redirect("panel:class_detail", pk=classroom.pk)
        _, created = Membership.objects.get_or_create(user=user, classroom=classroom)
        if created:
            messages.success(request, f"You joined {classroom.name}!")
        else:
            messages.info(request, f"You're already in {classroom.name}.")
        return redirect("lessons:home")
    return render(request, "lessons/join.html", {"classroom": classroom, "error": error, "code": raw or ""})


def _next_lesson(user, lesson):
    """La siguiente lección en la misma clase (o en las propias, si es profe)."""
    order = None
    m = Membership.objects.filter(user=user, classroom__assignments__lesson=lesson).select_related("classroom").first()
    if m:
        order = list(m.classroom.assignments.filter(lesson__published=True).values_list("lesson__slug", flat=True))
    elif user.is_teacher:
        own = Lesson.objects.all() if user.is_admin else Lesson.objects.filter(owner=user)
        order = list(own.order_by("level", "order", "id").values_list("slug", flat=True))
    if not order or lesson.slug not in order:
        return None
    i = order.index(lesson.slug)
    return order[i + 1] if i + 1 < len(order) else None


@login_required
def lesson_detail(request, slug):
    lesson = get_object_or_404(lessons_for(request.user), slug=slug)
    exercises = list(lesson.exercises.prefetch_related("options"))
    results = {r.exercise_id: r for r in ExerciseResult.objects.filter(user=request.user, exercise__lesson=lesson)}
    saved = set(VocabItem.objects.filter(user=request.user, exercise__lesson=lesson).values_list("exercise_id", flat=True))
    progress = LessonProgress.objects.filter(user=request.user, lesson=lesson).first()
    payload = {
        "lessonId": lesson.pk,
        "videoId": lesson.youtube_id,
        "startAt": progress.last_position if progress and not progress.completed_at else 0,
        "watched": progress.watched_percent if progress else 0,
        "exercises": [ex.public_data(results.get(ex.pk), ex.pk in saved) for ex in exercises],
    }
    can_edit = request.user.is_admin or lesson.owner_id == request.user.pk
    return render(
        request,
        "lessons/lesson.html",
        {
            "lesson": lesson,
            "exercises": exercises,
            "payload": payload,
            "next_slug": _next_lesson(request.user, lesson),
            "can_edit": can_edit,
        },
    )


def _json_body(request):
    try:
        data = json.loads(request.body or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _lesson_state(user, lesson):
    total = lesson.exercises.count()
    qs = ExerciseResult.objects.filter(user=user, exercise__lesson=lesson)
    answered = qs.exclude(status=ExerciseResult.SKIPPED).count()
    correct = qs.filter(status=ExerciseResult.CORRECT).count()
    lesson_xp = qs.aggregate(s=Sum("xp_awarded"))["s"] or 0
    just_completed = False
    if total and answered >= total:
        progress, _ = LessonProgress.objects.get_or_create(user=user, lesson=lesson)
        if not progress.completed_at:
            progress.completed_at = timezone.now()
            progress.save(update_fields=["completed_at", "updated_at"])
            just_completed = True
    return {
        "total": total,
        "answered": answered,
        "correctCount": correct,
        "lessonXp": lesson_xp,
        "lessonDone": bool(total and answered >= total),
        "justCompleted": just_completed,
    }


@login_required
@require_POST
def api_check(request, pk):
    exercise = get_object_or_404(Exercise.objects.select_related("lesson").defer("lesson__image"), pk=pk)
    if not _can_open(request.user, exercise.lesson_id):
        return JsonResponse({"error": "not found"}, status=404)
    answer = _json_body(request).get("answer")
    with transaction.atomic():
        # Bloquea al alumno: dos respuestas seguidas no pueden pisarse el XP
        user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
        result, _ = ExerciseResult.objects.select_for_update().get_or_create(
            user=user, exercise=exercise, defaults={"status": ExerciseResult.SKIPPED}
        )
        correct = exercise.check_answer(answer)
        xp_gained = 0
        if correct and result.status != ExerciseResult.CORRECT:
            first_try = result.attempts == 0
            xp_gained = exercise.xp if first_try else max(exercise.xp // 2, 1)
            result.xp_awarded += xp_gained
        result.attempts += 1
        # Se guarda para mostrarla al repasar; si es enorme o rara, no se guarda
        result.last_answer = answer if len(json.dumps(answer)) <= 2000 else None
        if correct:
            result.status = ExerciseResult.CORRECT
        elif result.status != ExerciseResult.CORRECT:
            result.status = ExerciseResult.WRONG
        result.save()
        streak_up = user.register_activity(xp_gained)
        if xp_gained:
            row, _ = DailyXP.objects.get_or_create(user=user, day=timezone.localdate())
            DailyXP.objects.filter(pk=row.pk).update(xp=F("xp") + xp_gained)

    data = {
        "correct": correct,
        "status": result.status,
        "correctAnswer": "" if correct else exercise.correct_display(),
        "explanation": exercise.explanation,
        "xpGained": xp_gained,
        "totalXp": user.xp,
        "streak": user.current_streak,
        "streakUp": streak_up,
    }
    data.update(_lesson_state(user, exercise.lesson))
    return JsonResponse(data)


@login_required
@require_POST
def api_skip(request, pk):
    exercise = get_object_or_404(Exercise, pk=pk)
    if not _can_open(request.user, exercise.lesson_id):
        return JsonResponse({"error": "not found"}, status=404)
    ExerciseResult.objects.get_or_create(
        user=request.user, exercise=exercise, defaults={"status": ExerciseResult.SKIPPED}
    )
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_vocab(request, pk):
    exercise = get_object_or_404(Exercise, pk=pk, type=Exercise.FLASHCARD)
    if not _can_open(request.user, exercise.lesson_id):
        return JsonResponse({"error": "not found"}, status=404)
    item = VocabItem.objects.filter(user=request.user, exercise=exercise).first()
    if item:
        item.delete()
        return JsonResponse({"saved": False})
    VocabItem.objects.create(user=request.user, exercise=exercise)
    return JsonResponse({"saved": True})


@login_required
@require_POST
def api_progress(request, pk):
    lesson = get_object_or_404(lessons_for(request.user), pk=pk)
    body = _json_body(request)
    try:
        percent = max(0, min(100, int(body.get("percent", 0))))
        position = max(0, min(86400, int(body.get("position", 0))))
    except (TypeError, ValueError, OverflowError):
        return JsonResponse({"error": "bad data"}, status=400)
    progress, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
    progress.watched_percent = max(progress.watched_percent, percent)
    progress.last_position = position
    progress.save(update_fields=["watched_percent", "last_position", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
def my_progress(request):
    user = request.user
    if user.is_teacher:
        return teacher_progress(request)
    results = ExerciseResult.objects.filter(user=user)
    stats = results.aggregate(
        correct=Count("id", filter=Q(status=ExerciseResult.CORRECT)),
        wrong=Count("id", filter=Q(status=ExerciseResult.WRONG)),
    )
    attempted = stats["correct"] + stats["wrong"]
    accuracy = round(stats["correct"] * 100 / attempted) if attempted else 0

    progress = {p.lesson_id: p for p in LessonProgress.objects.filter(user=user)}
    per_lesson = (
        results.exclude(status=ExerciseResult.SKIPPED)
        .values("exercise__lesson")
        .annotate(answered=Count("id"), correct=Count("id", filter=Q(status=ExerciseResult.CORRECT)))
    )
    per_lesson = {r["exercise__lesson"]: r for r in per_lesson}
    rows = []
    for lesson in _visible_lessons(user):
        p = progress.get(lesson.pk)
        r = per_lesson.get(lesson.pk, {})
        if not p and not r:
            continue
        rows.append(
            {
                "lesson": lesson,
                "watched": p.watched_percent if p else 0,
                "answered": r.get("answered", 0),
                "correct": r.get("correct", 0),
                "completed": bool(p and p.completed_at),
            }
        )

    # Actividad de los últimos 7 días
    today = timezone.localdate()
    per_day = dict(DailyXP.objects.filter(user=user, day__gte=today - timedelta(days=6)).values_list("day", "xp"))
    week = [{"day": d, "xp": per_day.get(d) or 0} for d in (today - timedelta(days=o) for o in range(6, -1, -1))]
    max_xp = max([d["xp"] for d in week] + [1])
    for d in week:
        d["height"] = round(d["xp"] * 100 / max_xp)

    return render(
        request,
        "lessons/progress.html",
        {
            "stats": stats,
            "accuracy": accuracy,
            "rows": rows,
            "completed_count": sum(1 for r in rows if r["completed"]),
            "week": week,
            "vocab_count": VocabItem.objects.filter(user=user).count(),
        },
    )


@login_required
def vocabulary(request):
    items = VocabItem.objects.filter(user=request.user).select_related("exercise__lesson").defer("exercise__lesson__image")
    return render(request, "lessons/vocabulary.html", {"items": items})


@login_required
@require_POST
def vocab_remove(request, pk):
    VocabItem.objects.filter(user=request.user, pk=pk).delete()
    return redirect("lessons:vocabulary")


def teacher_progress(request):
    """My progress del profe: lo que ha creado y cómo van sus alumnos."""
    user = request.user
    today = timezone.localdate()
    classes = list(
        Classroom.objects.filter(teacher=user)
        .annotate(n_students=Count("memberships", distinct=True), n_lessons=Count("assignments", distinct=True))
        .order_by("name")
    )
    lessons = Lesson.objects.filter(owner=user)
    student_ids = set(Membership.objects.filter(classroom__in=classes).values_list("user_id", flat=True))

    # Avance por clase: lecciones asignadas terminadas / (alumnos x lecciones)
    done = set(
        LessonProgress.objects.filter(user_id__in=student_ids, completed_at__isnull=False).values_list("user_id", "lesson_id")
    )
    members = {}
    for cid, uid in Membership.objects.filter(classroom__in=classes).values_list("classroom_id", "user_id"):
        members.setdefault(cid, []).append(uid)
    assigned = {}
    for cid, lid in Assignment.objects.filter(classroom__in=classes).values_list("classroom_id", "lesson_id"):
        assigned.setdefault(cid, []).append(lid)
    for c in classes:
        total = len(members.get(c.pk, [])) * len(assigned.get(c.pk, []))
        finished = sum(1 for u in members.get(c.pk, []) for l in assigned.get(c.pk, []) if (u, l) in done)
        c.percent = round(finished * 100 / total) if total else 0

    answers = ExerciseResult.objects.filter(user_id__in=student_ids, exercise__lesson__in=lessons).exclude(
        status=ExerciseResult.SKIPPED
    )
    stats = answers.aggregate(total=Count("id"), correct=Count("id", filter=Q(status=ExerciseResult.CORRECT)))
    per_day = dict(
        answers.filter(updated_at__date__gte=today - timedelta(days=6))
        .annotate(d=TruncDate("updated_at"))
        .values("d")
        .annotate(n=Count("id"))
        .values_list("d", "n")
    )
    week = [{"day": d, "xp": per_day.get(d) or 0} for d in (today - timedelta(days=o) for o in range(6, -1, -1))]
    top = max([d["xp"] for d in week] + [1])
    for d in week:
        d["height"] = round(d["xp"] * 100 / top)

    return render(
        request,
        "lessons/teacher_progress.html",
        {
            "classes": classes,
            "n_students": len(student_ids),
            "n_lessons": lessons.count(),
            "n_published": lessons.filter(published=True).count(),
            "n_exercises": Exercise.objects.filter(lesson__in=lessons).count(),
            "n_completed": LessonProgress.objects.filter(
                user_id__in=student_ids, lesson__in=lessons, completed_at__isnull=False
            ).count(),
            "answers": stats["total"],
            "accuracy": round(stats["correct"] * 100 / stats["total"]) if stats["total"] else 0,
            "active_week": ExerciseResult.objects.filter(
                user_id__in=student_ids, updated_at__date__gte=today - timedelta(days=6)
            ).values("user_id").distinct().count(),
            "week": week,
        },
    )


@login_required
def lesson_image(request, pk):
    lesson = get_object_or_404(lessons_for(request.user).filter(image__isnull=False), pk=pk)
    response = HttpResponse(bytes(lesson.image), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=31536000"  # la URL cambia cuando cambia la foto
    return response


@login_required
def class_image(request, pk):
    """Imagen de la clase: la ven su profe, sus alumnos y el admin."""
    user = request.user
    rooms = Classroom.objects.filter(image__isnull=False)
    if not user.is_admin:
        rooms = rooms.filter(Q(teacher=user) | Q(memberships__user=user)).distinct()
    room = get_object_or_404(rooms, pk=pk)
    response = HttpResponse(bytes(room.image), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=31536000"
    return response
