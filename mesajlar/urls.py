from django.urls import path

from . import views

urlpatterns = [
    path("mesajlar/", views.mesaj_kutusu, name="mesaj_kutusu"),
    path("bildirimler/", views.bildirimler, name="bildirimler"),
    path("bildirimler/okundu/", views.tumunu_okundu, name="bildirim_tumunu_okundu"),
    path("bildirimler/<int:pk>/", views.bildirim_ac, name="bildirim_ac"),
]
