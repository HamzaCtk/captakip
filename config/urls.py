from django.urls import include, path

from accounts.views import anasayfa
from dersler.views_onay import onay_kuyrugu
from ortak.saglik import saglik

urlpatterns = [
    path("", anasayfa, name="anasayfa"),
    path("saglik/", saglik, name="saglik"),
    path("hesap/", include("accounts.urls")),
    path("ogrenciler/", include("ogrenciler.urls")),
    path("dersler/", include("dersler.urls")),
    path("kurallar/", include("kurallar.urls")),
    path("aktarim/", include("aktarim.urls")),
    path("onay/", onay_kuyrugu, name="onay_kuyrugu"),
    path("", include("mesajlar.urls")),
]
