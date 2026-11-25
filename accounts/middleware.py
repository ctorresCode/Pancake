from django.conf import settings
from django.http import HttpResponseRedirect


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
