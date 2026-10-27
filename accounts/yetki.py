"""Rol tabanlı erişim kontrolü.

Görünümlerde (view) şöyle kullanılır:

    class OgrenciListesi(RolGerekli, ListView):
        izinli_roller = [Kullanici.Rol.KOORDINATOR, Kullanici.Rol.BOLUM_BASKANI]

Yetkisi olmayan kullanıcı 403 (Erişim engellendi) sayfası görür.
"""
from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .models import Kullanici

KOORDINATOR = Kullanici.Rol.KOORDINATOR
OGRENCI = Kullanici.Rol.OGRENCI
BOLUM_BASKANI = Kullanici.Rol.BOLUM_BASKANI

# Kayıtları görebilen roller (öğrenci yalnızca kendini görür; o kontrol
# ilgili görünümde ayrıca yapılır)
YONETIM_ROLLERI = [KOORDINATOR, BOLUM_BASKANI]


class RolGerekli(LoginRequiredMixin):
    izinli_roller = []

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.rol not in self.izinli_roller:
            raise PermissionDenied("Bu sayfaya erişim yetkiniz yok.")
        return super().dispatch(request, *args, **kwargs)


def rol_gerekli(*roller):
    """Fonksiyon tabanlı görünümler için dekoratör."""
    def dekorator(gorunum):
        @wraps(gorunum)
        def sarmal(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                return redirect_to_login(request.get_full_path())
            if request.user.rol not in roller:
                raise PermissionDenied("Bu sayfaya erişim yetkiniz yok.")
            return gorunum(request, *args, **kwargs)
        return sarmal
    return dekorator
