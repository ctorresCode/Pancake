import io

from django import forms
from django.utils import timezone
from PIL import Image, ImageOps

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


class ProfileForm(forms.ModelForm):
    photo = forms.ImageField(required=False, label="Profile photo")
    remove_photo = forms.BooleanField(required=False, label="Remove my photo")

    class Meta:
        model = User
        # El nombre no se edita aquí: así el profe siempre sabe quién es cada alumno
        fields = ["bio"]
        labels = {"bio": "About me"}
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 3, "maxlength": 280, "placeholder": "e.g. I'm learning English to travel."}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("That photo is too big. Use one under 5 MB.")
        return photo

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("remove_photo"):
            user.avatar, user.avatar_updated = None, None
        elif self.cleaned_data.get("photo"):
            user.avatar = shrink(self.cleaned_data["photo"])
            user.avatar_updated = timezone.now()
        if commit:
            user.save()
        return user


def shrink(upload, size=256):
    """Recorta la foto al centro en cuadrado y la guarda chica en JPEG."""
    img = Image.open(upload)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):  # fondo blanco para PNG transparentes
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        img = bg
    img = img.convert("RGB")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()
