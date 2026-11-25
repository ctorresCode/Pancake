# Pancake

Plataforma para practicar inglés con videos de YouTube. El profe sube un video, pone preguntas en el minuto que quiera y a los alumnos les van saliendo debajo mientras lo ven. Ganan XP, mantienen una racha diaria y guardan vocabulario.

Hecho con Django y PostgreSQL.

## Correrlo en local

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Hay que entrar por `http://localhost:8000`. Con `127.0.0.1` YouTube no deja reproducir los videos.

Para tener una lección de ejemplo: `python manage.py seed_demo`

### Archivo .env

```
DEBUG=True
SECRET_KEY=algo-largo-y-secreto
DB_NAME=pancake
DB_USER=...
DB_PASSWORD=...
DB_HOST=127.0.0.1
DB_PORT=5432
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

Si las variables de Google están vacías, el botón "Continue with Google" no aparece.

## Roles

- **Admin**: puede todo. Cambia el rol de los usuarios en Teacher panel > Users.
- **Teacher**: crea sus lecciones y sus clases, y ve a sus alumnos.
- **Student**: se une a una clase con el código y hace las lecciones asignadas.

Todos se registran como alumnos; el admin decide quién es profe.

## En producción

Corre en Railway. `railway.json` tiene el comando de arranque (migraciones, archivos estáticos y gunicorn).
Variables que necesita: `DATABASE_URL`, `SECRET_KEY`, `DEBUG=False`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.
Si se usa un dominio propio, también `PANCAKE_DOMAIN`.

En Google Cloud hay que agregar `https://<dominio>/cuenta/google/login/callback/` como URI de redireccionamiento.

## Tests

```
python manage.py test lessons
```
