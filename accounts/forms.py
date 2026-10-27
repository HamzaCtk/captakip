from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import Kullanici


class GirisFormu(AuthenticationForm):
    username = forms.CharField(
        label="Kullanıcı adı",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
    password = forms.CharField(
        label="Şifre",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    error_messages = {
        # Kullanıcı adı mı şifre mi yanlış, bilerek söylenmez
        # (saldırgana hangi kullanıcı adlarının var olduğunu sızdırmamak için)
        "invalid_login": "Kullanıcı adı veya şifre hatalı.",
        "inactive": "Bu hesap pasif durumda.",
    }


class HesapOlusturmaFormu(forms.ModelForm):
    """Koordinatörün yönetim hesabı (koordinatör / bölüm başkanı) açması için.

    Öğrenci hesapları öğrenci kartıyla birlikte açılır (2. adım).
    """

    rol = forms.ChoiceField(
        label="Rol",
        choices=[
            (Kullanici.Rol.KOORDINATOR, "Koordinatör"),
            (Kullanici.Rol.BOLUM_BASKANI, "Bölüm Başkanı"),
        ],
    )

    class Meta:
        model = Kullanici
        fields = ["username", "first_name", "last_name", "email", "rol"]
        labels = {
            "username": "Kullanıcı adı",
            "first_name": "Ad",
            "last_name": "Soyad",
            "email": "E-posta",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if not email:
            raise forms.ValidationError("E-posta zorunludur.")
        if Kullanici.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Bu e-posta ile kayıtlı bir hesap zaten var.")
        return email
