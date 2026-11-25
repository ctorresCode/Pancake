from django.conf import settings


def pancake(request):
    return {"GOOGLE_ENABLED": settings.GOOGLE_ENABLED}
