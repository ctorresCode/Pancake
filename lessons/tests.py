import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Assignment, Classroom, Exercise, ExerciseResult, Lesson, LessonProgress, Membership

User = get_user_model()


def make_user(*args, **kwargs):
    kwargs.setdefault("role_confirmed", True)
    return User.objects.create_user(*args, **kwargs)


class PancakeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)
        cls.lesson = Lesson.objects.get(slug="demo-learn-english-with-music")
        cls.student = make_user("ana", "ana@example.com", "pass12345!")
        cls.teacher = make_user("profe", "profe@example.com", "pass12345!", is_staff=True, role="admin")
        cls.lesson.owner = cls.teacher
        cls.lesson.save()
        cls.classroom = Classroom.objects.create(name="English 1", teacher=cls.teacher)
        Assignment.objects.create(classroom=cls.classroom, lesson=cls.lesson)
        Membership.objects.create(classroom=cls.classroom, user=cls.student)

    def post_json(self, url, data=None):
        return self.client.post(url, json.dumps(data or {}), content_type="application/json")

    def ex(self, type_):
        return self.lesson.exercises.get(type=type_)

    # Páginas
    def test_public_pages(self):
        for name in ("landing", "account_login", "account_signup"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_student_pages(self):
        self.client.force_login(self.student)
        for url in (
            reverse("lessons:home"),
            reverse("lessons:progress"),
            reverse("lessons:vocabulary"),
            self.lesson.get_absolute_url(),
        ):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
        r = self.client.get(self.lesson.get_absolute_url())
        payload = r.context["payload"]
        self.assertEqual(len(payload["exercises"]), 6)
        # no se filtra la respuesta correcta al navegador
        self.assertNotIn("Extraños / desconocidos\", \"is_correct", r.content.decode())
        self.assertNotIn("correct_bool", r.content.decode())

    def test_panel_is_teacher_only(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("panel:dashboard")), reverse("lessons:home"))
        self.client.force_login(self.teacher)
        for url in (
            reverse("panel:dashboard"),
            reverse("panel:lessons"),
            reverse("panel:lesson_create"),
            reverse("panel:lesson_edit", args=[self.lesson.pk]),
            reverse("panel:exercise_create", args=[self.lesson.pk]),
            reverse("panel:students"),
            reverse("panel:student_detail", args=[self.student.pk]),
            reverse("panel:classes"),
            reverse("panel:class_detail", args=[self.classroom.pk]),
            reverse("panel:users"),
        ):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        for ex in self.lesson.exercises.all():
            self.assertEqual(self.client.get(reverse("panel:exercise_edit", args=[ex.pk])).status_code, 200)

    def test_unpublished_hidden_from_students(self):
        Lesson.objects.filter(pk=self.lesson.pk).update(published=False)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.lesson.get_absolute_url()).status_code, 404)

    # Corrección
    def test_check_all_types_and_xp(self):
        self.client.force_login(self.student)
        mc = self.ex(Exercise.MULTIPLE_CHOICE)
        wrong = mc.options.filter(is_correct=False).first()
        right = mc.options.get(is_correct=True)

        d = self.post_json(reverse("lessons:api_check", args=[mc.pk]), {"answer": wrong.pk}).json()
        self.assertFalse(d["correct"])
        self.assertEqual(d["correctAnswer"], right.text)
        self.assertEqual(d["streak"], 1)

        d = self.post_json(reverse("lessons:api_check", args=[mc.pk]), {"answer": right.pk}).json()
        self.assertTrue(d["correct"])
        self.assertEqual(d["xpGained"], 5)  # mitad por no ser al primer intento

        fb = self.ex(Exercise.FILL_BLANK)
        d = self.post_json(reverse("lessons:api_check", args=[fb.pk]), {"answer": fb.options.get(is_correct=True).pk}).json()
        self.assertEqual(d["xpGained"], 10)

        tf = self.ex(Exercise.TRUE_FALSE)
        self.assertTrue(self.post_json(reverse("lessons:api_check", args=[tf.pk]), {"answer": "true"}).json()["correct"])

        ow = self.ex(Exercise.ORDER_WORDS)
        words = "I just want to tell you how I'm feeling".split()
        self.assertFalse(self.post_json(reverse("lessons:api_check", args=[ow.pk]), {"answer": words[::-1]}).json()["correct"])
        self.assertTrue(self.post_json(reverse("lessons:api_check", args=[ow.pk]), {"answer": words}).json()["correct"])

        ls = self.ex(Exercise.LISTENING)
        self.post_json(reverse("lessons:api_check", args=[ls.pk]), {"answer": ls.options.get(is_correct=True).pk})

        fc = self.ex(Exercise.FLASHCARD)
        self.assertTrue(self.post_json(reverse("lessons:api_vocab", args=[fc.pk])).json()["saved"])
        d = self.post_json(reverse("lessons:api_check", args=[fc.pk]), {"answer": "ok"}).json()
        self.assertTrue(d["lessonDone"])
        self.assertTrue(d["justCompleted"])
        self.assertEqual(d["correctCount"], 6)

        self.student.refresh_from_db()
        self.assertEqual(self.student.xp, 5 + 10 + 10 + 5 + 10 + 10)
        self.assertTrue(LessonProgress.objects.get(user=self.student, lesson=self.lesson).completed_at)
        # repetir una correcta no da XP extra
        d = self.post_json(reverse("lessons:api_check", args=[tf.pk]), {"answer": "true"}).json()
        self.assertEqual(d["xpGained"], 0)
        self.assertFalse(d["justCompleted"])

        for name in ("lessons:home", "lessons:progress", "lessons:vocabulary"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_listen_type_normalization(self):
        e = Exercise.objects.create(
            lesson=self.lesson, type=Exercise.LISTEN_TYPE, trigger_seconds=90, answer_text="I'm fine|I am fine"
        )
        self.assertTrue(e.check_answer("i’m FINE!"))
        self.assertTrue(e.check_answer("I am fine."))
        self.assertFalse(e.check_answer("I fine"))

    def test_streak(self):
        u = self.student
        u.last_activity = timezone.localdate() - timedelta(days=1)
        u.streak = 4
        u.save()
        self.assertTrue(u.register_activity(10))
        self.assertEqual(u.streak, 5)
        self.assertFalse(u.register_activity(10))
        self.assertEqual(u.streak, 5)
        u.last_activity = timezone.localdate() - timedelta(days=3)
        self.assertEqual(u.current_streak, 0)
        u.register_activity(0)
        self.assertEqual(u.streak, 1)

    def test_skip_and_progress(self):
        self.client.force_login(self.student)
        ex = self.lesson.exercises.first()
        self.post_json(reverse("lessons:api_skip", args=[ex.pk]))
        self.assertEqual(ExerciseResult.objects.get(user=self.student, exercise=ex).status, "skipped")
        self.post_json(reverse("lessons:api_progress", args=[self.lesson.pk]), {"percent": 40, "position": 50})
        self.post_json(reverse("lessons:api_progress", args=[self.lesson.pk]), {"percent": 20, "position": 30})
        p = LessonProgress.objects.get(user=self.student, lesson=self.lesson)
        self.assertEqual((p.watched_percent, p.last_position), (40, 30))

    # Panel: crear lección y ejercicios
    def test_teacher_creates_lesson_and_exercises(self):
        self.client.force_login(self.teacher)
        r = self.client.post(reverse("panel:lesson_create"), {
            "title": "Greetings", "level": "A1", "order": 2,
            "youtube_id": "https://www.youtube.com/watch?v=abcdefghijk&t=10s", "description": "", "published": "on",
        })
        lesson = Lesson.objects.get(title="Greetings")
        self.assertRedirects(r, reverse("panel:lesson_edit", args=[lesson.pk]))
        self.assertEqual(lesson.youtube_id, "abcdefghijk")

        def mgmt(total=4, initial=0):
            return {"opt-TOTAL_FORMS": str(total), "opt-INITIAL_FORMS": str(initial), "opt-MIN_NUM_FORMS": "0", "opt-MAX_NUM_FORMS": "6"}

        url = reverse("panel:exercise_create", args=[lesson.pk])
        base = {"type": "multiple_choice", "trigger_seconds": "1:20", "prompt": "How are you?", "xp": "10", **mgmt()}
        # sin respuesta correcta -> error
        r = self.client.post(url, {**base, "opt-0-text": "Fine", "opt-1-text": "Bad"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Mark exactly one answer as correct")
        # válido
        r = self.client.post(url, {**base, "opt-0-text": "Fine", "opt-0-is_correct": "on", "opt-1-text": "Bad"})
        self.assertRedirects(r, reverse("panel:lesson_edit", args=[lesson.pk]))
        ex = lesson.exercises.get()
        self.assertEqual(ex.trigger_seconds, 80)
        self.assertEqual(ex.options.count(), 2)
        self.assertEqual(ex.correct_display(), "Fine")

        # true/false y fill blank inválido
        r = self.client.post(url, {"type": "true_false", "trigger_seconds": "90", "sentence": "Hi is formal", "correct_bool": "false", "xp": "10", **mgmt()})
        self.assertEqual(lesson.exercises.get(type="true_false").correct_bool, False)
        r = self.client.post(url, {"type": "fill_blank", "trigger_seconds": "95", "sentence": "no blank", "xp": "10", **mgmt()})
        self.assertContains(r, "___")

        # editar: cambiar la correcta
        edit = reverse("panel:exercise_edit", args=[ex.pk])
        o1, o2 = ex.options.all()
        r = self.client.post(edit, {
            **base, **mgmt(total=3, initial=2),
            "opt-0-id": o1.pk, "opt-0-text": "Fine",
            "opt-1-id": o2.pk, "opt-1-text": "Bad", "opt-1-is_correct": "on",
            "opt-2-text": "",
        })
        self.assertRedirects(r, reverse("panel:lesson_edit", args=[lesson.pk]))
        self.assertEqual(ex.correct_display(), "Bad")

    def test_lessons_keep_their_order(self):
        Lesson.objects.create(title="Tercera", level="A1", order=3, youtube_id="abcdefghijk", published=True)
        Lesson.objects.create(title="Segunda", level="A1", order=2, youtube_id="abcdefghijk", published=True)
        Lesson.objects.create(title="Basica", level="A2", order=1, youtube_id="abcdefghijk", published=True)
        self.client.force_login(self.teacher)
        r = self.client.get(reverse("panel:lessons"))
        self.assertEqual([l.title for l in r.context["lessons"]][:3], [self.lesson.title, "Segunda", "Tercera"])

    def test_review_shows_last_answer(self):
        self.client.force_login(self.student)
        mc = self.ex(Exercise.MULTIPLE_CHOICE)
        wrong = mc.options.filter(is_correct=False).first()
        self.post_json(reverse("lessons:api_check", args=[mc.pk]), {"answer": wrong.pk})
        self.assertEqual(ExerciseResult.objects.get(user=self.student, exercise=mc).last_answer, wrong.pk)
        data = self.client.get(self.lesson.get_absolute_url()).context["payload"]["exercises"]
        ex = next(e for e in data if e["id"] == mc.pk)
        self.assertEqual(ex["lastAnswer"], wrong.pk)
        self.assertEqual(ex["correctAnswer"], mc.options.get(is_correct=True).text)
        # los que no ha respondido no revelan la respuesta correcta
        other = next(e for e in data if e["id"] != mc.pk)
        self.assertNotIn("correctAnswer", other)


    # Clases
    def test_student_only_sees_assigned_lessons(self):
        other = Lesson.objects.create(title="Not assigned", level="A1", youtube_id="abcdefghijk", published=True)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(other.get_absolute_url()).status_code, 404)
        ex = Exercise.objects.create(lesson=other, type=Exercise.TRUE_FALSE, sentence="x", correct_bool=True)
        self.assertEqual(self.post_json(reverse("lessons:api_check", args=[ex.pk]), {"answer": "true"}).status_code, 404)
        # un alumno sin clases no ve nada
        loner = make_user("solo", "solo@example.com", "pass12345!")
        self.client.force_login(loner)
        self.assertEqual(self.client.get(self.lesson.get_absolute_url()).status_code, 404)
        self.assertContains(self.client.get(reverse("lessons:home")), "Join your class")

    def test_join_with_code_and_due_dates(self):
        teacher = make_user("t2", "t2@example.com", "pass12345!", role="teacher")
        lesson = Lesson.objects.create(title="Verbs", level="A1", youtube_id="abcdefghijk", published=True, owner=teacher)
        room = Classroom.objects.create(name="English 2", teacher=teacher)
        Assignment.objects.create(classroom=room, lesson=lesson, due_date=timezone.localdate() - timedelta(days=1))
        new = make_user("luis", "luis@example.com", "pass12345!")
        self.client.force_login(new)
        r = self.client.post(reverse("lessons:join"), {"code": "zzz-zzz"})
        self.assertContains(r, "couldn&#x27;t find a class")
        # el código acepta minúsculas y guion
        code = room.code_display.lower()
        self.assertContains(self.client.get(reverse("lessons:join_code", args=[code])), "Join English 2?")
        self.assertRedirects(self.client.post(reverse("lessons:join"), {"code": code}), reverse("lessons:home"))
        self.assertTrue(Membership.objects.filter(user=new, classroom=room).exists())
        r = self.client.get(reverse("lessons:home"))
        self.assertContains(r, "English 2")
        self.assertContains(r, "Late, was due")
        self.assertEqual(self.client.get(lesson.get_absolute_url()).status_code, 200)

    def test_teachers_only_touch_their_own_stuff(self):
        teacher = make_user("t3", "t3@example.com", "pass12345!", role="teacher")
        self.client.force_login(teacher)
        self.assertEqual(self.client.get(reverse("panel:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("panel:lesson_edit", args=[self.lesson.pk])).status_code, 404)
        ex = self.lesson.exercises.first()
        self.assertEqual(self.client.get(reverse("panel:exercise_edit", args=[ex.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("panel:class_detail", args=[self.classroom.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("panel:student_detail", args=[self.student.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse("panel:users")), reverse("panel:dashboard"))
        # crea su clase y asigna su lección
        self.client.post(reverse("panel:classes"), {"name": "Night class"})
        room = Classroom.objects.get(name="Night class")
        self.assertEqual(room.teacher, teacher)
        self.client.post(reverse("panel:lesson_create"), {"title": "Mine", "youtube_id": "abcdefghijk", "level": "A1"})
        mine = Lesson.objects.get(title="Mine")
        self.assertEqual(mine.owner, teacher)
        self.client.post(reverse("panel:class_detail", args=[room.pk]), {"action": "assign", "lesson": mine.pk, "due_date": "2030-01-15"})
        self.assertEqual(room.assignments.get().due_date.isoformat(), "2030-01-15")
        # no puede asignar lecciones de otros
        self.client.post(reverse("panel:class_detail", args=[room.pk]), {"action": "assign", "lesson": self.lesson.pk})
        self.assertEqual(room.assignments.count(), 1)

    def test_admin_changes_roles(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse("panel:users"), {"user": self.student.pk, "role": "teacher"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "teacher")
        self.assertTrue(self.student.is_teacher)
        self.assertFalse(self.student.is_staff)
        # no se puede quitar el rol a sí mismo
        self.client.post(reverse("panel:users"), {"user": self.teacher.pk, "role": "student"})
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, "admin")
        # nadie más puede volverse admin
        self.client.post(reverse("panel:users"), {"user": self.student.pk, "role": "admin"})
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "teacher")
        self.assertNotContains(self.client.get(reverse("panel:users")), 'value="admin"')

    # Registro y roles
    def test_signup_lets_you_pick_student_or_teacher(self):
        data = {"email": "new@example.com", "username": "newprof", "password1": "Pancake#2026x", "password2": "Pancake#2026x"}
        r = self.client.post(reverse("account_signup"), {**data, "role": "teacher"})
        self.assertEqual(r.status_code, 302)
        u = User.objects.get(username="newprof")
        self.assertEqual((u.role, u.role_confirmed, u.is_staff), ("teacher", True, False))
        self.assertEqual(self.client.get(reverse("panel:dashboard")).status_code, 200)
        self.client.logout()
        # admin no se puede elegir
        r = self.client.post(reverse("account_signup"), {**data, "email": "x@example.com", "username": "sneaky", "role": "admin"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(username="sneaky").exists())

    def test_google_users_choose_role_first(self):
        u = User.objects.create_user("googler", "g@example.com", "pass12345!")  # como queda tras entrar con Google
        self.client.force_login(u)
        self.assertRedirects(self.client.get(reverse("lessons:home")), reverse("choose_role"))
        self.assertRedirects(self.client.get(reverse("panel:dashboard")), reverse("choose_role"))
        self.assertEqual(self.client.get(reverse("choose_role")).status_code, 200)
        self.client.post(reverse("choose_role"), {"role": "admin"})
        u.refresh_from_db()
        self.assertFalse(u.role_confirmed)
        self.assertRedirects(self.client.post(reverse("choose_role"), {"role": "student"}), reverse("lessons:home"))
        u.refresh_from_db()
        self.assertEqual((u.role, u.role_confirmed), ("student", True))
        self.assertEqual(self.client.get(reverse("lessons:home")).status_code, 200)

    def test_superuser_is_always_admin(self):
        boss = User.objects.create_superuser("boss", "boss@example.com", "pass12345!")
        self.assertEqual((boss.role, boss.role_confirmed, boss.is_admin), ("admin", True, True))

    def test_brevo_backend_builds_the_request(self):
        from unittest import mock

        from django.core import mail
        from django.test import override_settings

        with override_settings(
            EMAIL_BACKEND="pancake.email_backend.BrevoEmailBackend",
            BREVO_API_KEY="xkeysib-test",
            DEFAULT_FROM_EMAIL="Pancake <profe@example.com>",
        ), mock.patch("pancake.email_backend.requests.post") as post:
            post.return_value.raise_for_status.return_value = None
            sent = mail.send_mail("Reset your password", "Hello", None, ["ana@example.com"])
        self.assertEqual(sent, 1)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["headers"]["api-key"], "xkeysib-test")
        self.assertEqual(kwargs["json"]["sender"], {"name": "Pancake", "email": "profe@example.com"})
        self.assertEqual(kwargs["json"]["to"], [{"email": "ana@example.com"}])
        self.assertEqual(kwargs["json"]["subject"], "Reset your password")

    def test_join_code_attempts_are_limited(self):
        from django.core.cache import cache
        cache.clear()
        self.client.force_login(self.student)
        for _ in range(15):
            self.client.post(reverse("lessons:join"), {"code": "AAA-AAA"})
        r = self.client.post(reverse("lessons:join"), {"code": self.classroom.code})
        self.assertContains(r, "Too many tries")
        cache.clear()
