from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .forms import RoleForm


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
