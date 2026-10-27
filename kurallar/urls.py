from django.urls import path

from . import views

urlpatterns = [
    path("", views.kural_ayarlari, name="kural_ayarlari"),
    path("yeni/<str:tur>/", views.surum_yeni, name="surum_yeni"),
]
