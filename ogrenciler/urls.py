from django.urls import path

from belgeler import views as belge_views
from dersler import views_onay
from kurallar import views as kural_views
from mesajlar import views as mesaj_views

from . import views

urlpatterns = [
    path("", views.ogrenci_listesi, name="ogrenci_listesi"),
    path("yeni/", views.ogrenci_ekle, name="ogrenci_ekle"),
    path("<str:ogrenci_no>/", views.ogrenci_karti, name="ogrenci_karti"),
    path("<str:ogrenci_no>/not/", views.koordinator_notu_ekle, name="koordinator_notu_ekle"),
    # Onay mekanizması (önce özel adresler, sonra genel kayıt işlemi)
    path("<str:ogrenci_no>/ders-sec/", views_onay.ders_sec, name="ders_sec"),
    path("<str:ogrenci_no>/deneme-ekle/", views_onay.deneme_ekle, name="deneme_ekle"),
    path("<str:ogrenci_no>/deneme/<int:pk>/not-gir/", views_onay.not_gir, name="not_gir"),
    path("<str:ogrenci_no>/deneme/<int:pk>/duzelt/", views_onay.deneme_duzelt, name="deneme_duzelt"),
    path("<str:ogrenci_no>/ders/<int:pk>/liste-durumu/", views_onay.liste_durumu, name="liste_durumu"),
    path("<str:ogrenci_no>/durum/", kural_views.ogrenci_durum, name="ogrenci_durum"),
    path("<str:ogrenci_no>/durum/ana-dal/", kural_views.ana_dal_ekle, name="ana_dal_ekle"),
    path("<str:ogrenci_no>/durum/degerlendir/", kural_views.simdi_degerlendir, name="simdi_degerlendir"),
    path("<str:ogrenci_no>/durum/uyari/<int:pk>/", kural_views.uyari_durumu, name="uyari_durumu"),
    path("<str:ogrenci_no>/durum/karar/", kural_views.karar_isle, name="karar_isle"),
    path("<str:ogrenci_no>/belgeler/", belge_views.belgeler_sayfasi, name="belgeler"),
    path("<str:ogrenci_no>/belgeler/yukle/", belge_views.belge_yukle, name="belge_yukle"),
    path("<str:ogrenci_no>/belgeler/istek/", belge_views.istek_olustur, name="belge_istek"),
    path("<str:ogrenci_no>/belgeler/<int:pk>/indir/", belge_views.belge_indir, name="belge_indir"),
    path("<str:ogrenci_no>/mesajlar/", mesaj_views.konusma, name="konusma"),
    path("<str:ogrenci_no>/mesajlar/gonder/", mesaj_views.mesaj_gonder, name="mesaj_gonder"),
    path("<str:ogrenci_no>/mesajlar/<int:pk>/ek/", mesaj_views.ek_indir, name="mesaj_ek_indir"),
    path("<str:ogrenci_no>/kayit/<str:tur>/<int:pk>/<str:eylem>/", views_onay.kayit_islemi, name="kayit_islemi"),
]
