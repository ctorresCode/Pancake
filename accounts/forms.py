from django import forms

from .models import User

# Al registrarse solo se puede elegir alumno o profe. Admin no se elige.
ROLE_CHOICES = [(User.STUDENT, "I'm a student"), (User.TEACHER, "I'm a teacher")]


class SignupForm(forms.Form):
    """Campo extra del registro de allauth (ACCOUNT_SIGNUP_FORM_CLASS)."""

    role = forms.ChoiceField(choices=ROLE_CHOICES, initial=User.STUDENT, widget=forms.RadioSelect)

    def signup(self, request, user):
        user.role = self.cleaned_data["role"]
        user.role_confirmed = True
        user.save(update_fields=["role", "role_confirmed"])


class RoleForm(forms.Form):
    """Para quien entra con Google por primera vez."""

    role = forms.ChoiceField(choices=ROLE_CHOICES, initial=User.STUDENT, widget=forms.RadioSelect)
