"""Configuración de Pancake."""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Falta SECRET_KEY. En el servidor es obligatoria.")
    SECRET_KEY = "dev-insecure-key-solo-local"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Dominio propio (ej. pancakeenglish.com), se pone en PANCAKE_DOMAIN
PANCAKE_DOMAIN = os.getenv("PANCAKE_DOMAIN", "").strip()
# Railway pone su dominio en RAILWAY_PUBLIC_DOMAIN (ej. pancake-production.up.railway.app)
for domain in {PANCAKE_DOMAIN, os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()} - {""}:
    ALLOWED_HOSTS.append(domain)
    CSRF_TRUSTED_ORIGINS.append(f"https://{domain}")
if os.getenv("RAILWAY_ENVIRONMENT"):  # dentro de Railway: aceptar sus dominios aunque se creen después
    ALLOWED_HOSTS.append(".up.railway.app")
    CSRF_TRUSTED_ORIGINS.append("https://*.up.railway.app")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
    "lessons",
    "panel",
]

MIDDLEWARE = [
    "accounts.middleware.LocalhostRedirectMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "accounts.middleware.ChooseRoleMiddleware",
]

ROOT_URLCONF = "pancake.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.pancake",
            ],
        },
    },
]

WSGI_APPLICATION = "pancake.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "pancake"),
        "USER": os.getenv("DB_USER", "carlos"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}
# En Railway la base de datos llega como DATABASE_URL
if os.getenv("DATABASE_URL"):
    DATABASES["default"] = dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=600, conn_health_checks=True)

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "America/Santo_Domingo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # el JavaScript de la lección lee el token desde la página, no de la cookie
X_FRAME_OPTIONS = "DENY"

# YouTube exige el Referer para reproducir videos embebidos (si no: "video no disponible")
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

DEFAULT_AUTO_FIELD ="django.db.models.BigAutoField"
SITE_ID = 1

# Login (django-allauth)
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "lessons:home"
ACCOUNT_LOGOUT_REDIRECT_URL = "landing"
ACCOUNT_LOGIN_METHODS = {"email", "username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.forms.SignupForm"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_ON_GET = False

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_AUTO_SIGNUP = True
# Correo: Brevo (o Resend) por API. Sin clave, los correos solo se imprimen en la consola.
# La verificación queda opcional hasta probar que los correos llegan; luego se pone
# ACCOUNT_EMAIL_VERIFICATION=mandatory en las variables del servidor.
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
if BREVO_API_KEY:
    EMAIL_BACKEND = "pancake.email_backend.BrevoEmailBackend"
elif RESEND_API_KEY:
    EMAIL_BACKEND = "pancake.email_backend.ResendEmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "").strip() or "Pancake <support.pancake@gmail.com>"
SENDS_EMAIL = bool(BREVO_API_KEY or RESEND_API_KEY)
ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "optional" if SENDS_EMAIL else "none")
# Unir una cuenta de Google con una cuenta local del mismo correo solo es seguro si los correos se verifican
SOCIALACCOUNT_EMAIL_AUTHENTICATION = ACCOUNT_EMAIL_VERIFICATION == "mandatory"
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = SOCIALACCOUNT_EMAIL_AUTHENTICATION
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APPS": (
            [{"client_id": GOOGLE_CLIENT_ID, "secret": GOOGLE_CLIENT_SECRET, "key": ""}]
            if GOOGLE_ENABLED
            else []
        ),
    }
}


# HTTPS
# En local (DEBUG=True) todo sigue en http://localhost.
# En el servidor (DEBUG=False) todo va por HTTPS: redirección, cookies seguras y HSTS.
USE_HTTPS = env_bool("USE_HTTPS", not DEBUG)
if USE_HTTPS:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # el hosting termina el SSL delante de Django
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Empieza en 1 hora; cuando todo funcione bien se puede subir a 31536000 (1 año)
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"  # para que Google reciba https:// en la redirección
