from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from lessons.models import Classroom, ExerciseResult, LessonProgress, VocabItem

from .forms import ProfileForm, RoleForm
from .models import User


@login_required
def choose_role(request):
    user = request.user
    if user.role_confirmed:
        return redirect("lessons:home")
    form = RoleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.role = form.cleaned_data["role"]
        user.role_confirmed = True
        user.save(update_fields=["role", "role_confirmed"])
        return redirect("panel:dashboard" if user.is_teacher else "lessons:home")
    return render(request, "account/choose_role.html", {"form": form})


@login_required
def profile(request):
    user = request.user
    form = ProfileForm(request.POST or None, request.FILES or None, instance=user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("profile")
    stats = ExerciseResult.objects.filter(user=user).aggregate(
        correct=Count("id", filter=Q(status=ExerciseResult.CORRECT)),
        wrong=Count("id", filter=Q(status=ExerciseResult.WRONG)),
    )
    answered = stats["correct"] + stats["wrong"]
    return render(
        request,
        "account/profile.html",
        {
            "form": form,
            "accuracy": round(stats["correct"] * 100 / answered) if answered else 0,
            "completed": LessonProgress.objects.filter(user=user, completed_at__isnull=False).count(),
            "classes": Classroom.objects.filter(memberships__user=user).select_related("teacher"),
            "vocab": VocabItem.objects.filter(user=user).count(),
        },
    )


@login_required
def avatar(request, pk):
    user = get_object_or_404(User, pk=pk, avatar__isnull=False)
    response = HttpResponse(bytes(user.avatar), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=31536000"  # la URL cambia cuando cambia la foto
    return response
