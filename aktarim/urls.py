from django.urls import path

from . import views

urlpatterns = [
    path("", views.aktarim_listesi, name="aktarim_listesi"),
    path("sablon/<str:tur>/", views.sablon_indir, name="aktarim_sablon"),
    path("<int:pk>/", views.aktarim_detay, name="aktarim_detay"),
    path("<int:pk>/uygula/", views.aktarim_uygula, name="aktarim_uygula"),
    path("<int:pk>/vazgec/", views.aktarim_vazgec, name="aktarim_vazgec"),
]
