"""İlk koordinatör hesabını komut satırından açar.

Kullanım:
    python manage.py koordinator_olustur --kullanici-adi koordinator --email koord@selcuk.edu.tr
"""
import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Kullanici
from denetim.kayit import kaydet


class Command(BaseCommand):
    help = "İlk koordinatör hesabını oluşturur."

    def add_arguments(self, parser):
        parser.add_argument("--kullanici-adi", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument("--ad", default="")
        parser.add_argument("--soyad", default="")

    def handle(self, *args, **o):
        if Kullanici.objects.filter(username=o["kullanici_adi"]).exists():
            raise CommandError("Bu kullanıcı adı zaten var.")
        sifre = getpass.getpass("Şifre: ")
        if sifre != getpass.getpass("Şifre (tekrar): "):
            raise CommandError("Şifreler eşleşmiyor.")
        kullanici = Kullanici(
            username=o["kullanici_adi"], email=o["email"],
            first_name=o["ad"], last_name=o["soyad"],
            rol=Kullanici.Rol.KOORDINATOR, sifre_degistirmeli=False,
        )
        try:
            validate_password(sifre, kullanici)
        except ValidationError as e:
            raise CommandError(" ".join(e.messages))
        kullanici.set_password(sifre)
        kullanici.save()
        kaydet(None, "HESAP_OLUSTURULDU", nesne=kullanici,
               yeni={"rol": kullanici.rol}, aciklama="Komut satırından ilk koordinatör")
        self.stdout.write(self.style.SUCCESS(f"Koordinatör oluşturuldu: {kullanici.username}"))
