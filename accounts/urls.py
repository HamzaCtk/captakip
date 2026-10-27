from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("giris/", views.GirisView.as_view(), name="giris"),
    path("cikis/", LogoutView.as_view(), name="cikis"),  # yalnızca POST ile çalışır
    path("sifre-degistir/", views.SifreDegistirView.as_view(), name="sifre_degistir"),
    path("hesaplar/", views.hesap_listesi, name="hesap_listesi"),
    path("hesaplar/yeni/", views.hesap_olustur, name="hesap_olustur"),
    path("hesaplar/<int:pk>/sifre-sifirla/", views.hesap_sifre_sifirla, name="hesap_sifre_sifirla"),
    path("hesaplar/<int:pk>/aktiflik/", views.hesap_aktiflik_degistir, name="hesap_aktiflik_degistir"),
]
