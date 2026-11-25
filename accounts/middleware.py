from datetime import date

from django.conf import settings
from django.http import HttpResponseRedirect
from django.urls import reverse


class LocalhostRedirectMiddleware:
    """En desarrollo, manda 127.0.0.1 a localhost: YouTube bloquea los videos embebidos en 127.0.0.1."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host()
        if settings.DEBUG and host.startswith("127.0.0.1"):
            return HttpResponseRedirect(
                f"{request.scheme}://{host.replace('127.0.0.1', 'localhost', 1)}{request.get_full_path()}"
            )
        return self.get_response(request)


class ChooseRoleMiddleware:
    """Quien entró con Google y todavía no eligió si es alumno o profe, lo elige antes de seguir."""

    ALLOWED = ("/cuenta/", "/static/", "/django-admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not user.role_confirmed
            and not request.path.startswith(self.ALLOWED)
        ):
            return HttpResponseRedirect(reverse("choose_role"))
        return self.get_response(request)


class RefreshSessionMiddleware:
    """La sesión dura SESSION_COOKIE_AGE desde la última visita, no desde el login.
    Se renueva una vez al día para no escribir en la base de datos en cada página."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            today = date.today().isoformat()
            if request.session.get("refreshed") != today:
                request.session["refreshed"] = today  # marcarla como modificada renueva cookie y vencimiento
        return response
