from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from .models import Kullanici

GUVENLI_METOTLAR = ("GET", "HEAD", "OPTIONS")


class SifreDegistirmeZorunluMiddleware:
    """Geçici şifreyle giren kullanıcı, kendi şifresini belirleyene kadar
    başka hiçbir sayfaya gidemez."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.sifre_degistirmeli:
            izinli = {reverse("sifre_degistir"), reverse("cikis")}
            if request.path not in izinli and not request.path.startswith("/static/"):
                return redirect("sifre_degistir")
        return self.get_response(request)


class SaltOkunurRolMiddleware:
    """İkinci savunma hattı: Bölüm başkanı hiçbir şeyi değiştiremez.

    Görünümlerdeki rol kontrolleri bir yerde unutulsa bile, bölüm başkanından
    gelen veri değiştirici istekler (POST/PUT/DELETE) burada reddedilir.
    Yalnızca kendi şifresini değiştirmesine ve çıkış yapmasına izin verilir.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (user.is_authenticated
                and user.rol == Kullanici.Rol.BOLUM_BASKANI
                and request.method not in GUVENLI_METOTLAR):
            izinli = {reverse("sifre_degistir"), reverse("cikis")}
            if request.path not in izinli:
                raise PermissionDenied("Bölüm başkanı rolü salt okunurdur.")
        return self.get_response(request)
