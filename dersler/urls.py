from django.urls import path

from . import views

urlpatterns = [
    path("", views.katalog, name="katalog"),
    path("yeni/", views.ders_formu, name="ders_ekle"),
    path("<int:pk>/duzenle/", views.ders_formu, name="ders_duzenle"),
    path("<int:pk>/aktiflik/", views.ders_aktiflik, name="ders_aktiflik"),
]
