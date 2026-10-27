"""Sistem içi bildirim üretmek için tek giriş noktası.

Diğer servisler (onay, red, belge isteği, kural motoru) işlemlerinin sonunda
buradaki fonksiyonları çağırır. Bildirim, işlemle aynı veritabanı işlemi
(transaction) içinde yazılır: işlem geri alınırsa bildirim de oluşmaz.

Kullanım:
    from mesajlar.bildirim import ogrenciye_bildir
    ogrenciye_bildir(ogrenci, "RED", "Ders kaydınız reddedildi: ...", baglanti=...)
"""
from django.urls import reverse

from accounts.models import Kullanici

from .models import Bildirim


def bildir(alicilar, tur, metin, baglanti="", ogrenci_no=""):
    """Her alıcıya bir bildirim yazar. Pasif hesaplara bildirim gitmez."""
    if isinstance(alicilar, Kullanici):
        alicilar = [alicilar]
    Bildirim.objects.bulk_create([
        Bildirim(alici=a, tur=tur, metin=metin[:400], baglanti=baglanti[:200], ogrenci_no=ogrenci_no)
        for a in alicilar if a is not None and a.is_active
    ])


def ogrenciye_bildir(ogrenci, tur, metin, baglanti=None):
    """Öğrencinin kendisine bildirim. Bağlantı verilmezse öğrenci kartına gider."""
    bildir(ogrenci.kullanici, tur, metin,
           baglanti or reverse("ogrenci_karti", args=[ogrenci.ogrenci_no]), ogrenci.ogrenci_no)


def koordinatorlere_bildir(tur, metin, baglanti="", ogrenci_no="", haric=None):
    """Tüm aktif koordinatörlere bildirim (işlemi yapan koordinatör hariç)."""
    alicilar = Kullanici.objects.filter(rol=Kullanici.Rol.KOORDINATOR, is_active=True)
    if haric is not None:
        alicilar = alicilar.exclude(pk=haric.pk)
    bildir(list(alicilar), tur, metin, baglanti, ogrenci_no)
