# Pancake

Watch. Practice. Progress.

Plataforma para aprender inglés con videos de YouTube y ejercicios que aparecen mientras se ve el video.

## Arrancar en local

```powershell
.\venv\Scripts\activate
python manage.py migrate
python manage.py seed_demo        # lección de ejemplo (opcional)
python manage.py runserver
```

Abre **http://localhost:8000** (no `127.0.0.1`: YouTube bloquea los videos embebidos en esa dirección).

## Roles
- **Profesor / admin**: usuario con `is_staff`. Ve el *Panel del profe* (`/panel/`) para crear lecciones y ejercicios.
  Crear uno: `python manage.py createsuperuser`.
- **Estudiante**: cualquiera que se registre (correo + usuario + contraseña, o Google).

## Configuración (`.env`)
| Variable | Para qué |
|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL |
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | Django |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Login con Google (el botón aparece solo si están puestas) |
| `TIME_ZONE` | Zona horaria para la racha diaria (por defecto `America/Santo_Domingo`) |

### Login con Google
En Google Cloud Console → APIs y servicios → Credenciales → *ID de cliente OAuth* (aplicación web), con el URI de redirección autorizado:
`http://localhost:8000/cuenta/google/login/callback/` (y el equivalente con el dominio real en producción).

## Tipos de ejercicio
Elegir la respuesta, completar la frase, verdadero o falso, ordenar palabras, escuchar y elegir, escuchar y escribir, y palabra nueva (se guarda en *Mi vocabulario*).

## Pruebas
```powershell
python manage.py test lessons
```
