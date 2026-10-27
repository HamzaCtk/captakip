"""Birden fazla tabloda ortak kullanılan model parçaları.

1) SilinemezModel: Hiçbir kayıt veritabanından silinemez. Yanlış kayıt
   "İPTAL" olarak işaretlenir (e-posta: "Hiçbir veri tamamen silinmemeli").

2) OnayliKayit: Öğrencinin girebildiği her tablonun ortak onay alanları.
   Öğrencinin girdiği kayıt BEKLİYOR durumunda başlar; koordinatör
   onaylayana kadar kesinleşmez ve kural hesaplarına girmez.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class SilinemezQuerySet(models.QuerySet):
    def delete(self):
        raise PermissionDenied("Bu kayıtlar silinemez; iptal olarak işaretleyin.")


class SilinemezModel(models.Model):
    objects = SilinemezQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Bu kayıt silinemez; iptal olarak işaretleyin.")


class OnayDurumu(models.TextChoices):
    BEKLIYOR = "BEKLIYOR", "Onay bekliyor"
    ONAYLANDI = "ONAYLANDI", "Onaylandı"
    REDDEDILDI = "REDDEDILDI", "Reddedildi"
    IPTAL = "IPTAL", "İptal"


class Kaynak(models.TextChoices):
    """Verinin sisteme nereden geldiği (ileride OBİS entegrasyonu için)."""
    OGRENCI = "OGRENCI", "Öğrenci"
    KOORDINATOR = "KOORDINATOR", "Koordinatör"
    AKTARIM = "AKTARIM", "Geçmiş veri aktarımı"
    OBIS = "OBIS", "OBİS"


class OnayliKayit(SilinemezModel):
    onay_durumu = models.CharField(
        "Onay durumu", max_length=12, choices=OnayDurumu.choices,
        default=OnayDurumu.BEKLIYOR, db_index=True,
    )
    kaynak = models.CharField("Kaynak", max_length=12, choices=Kaynak.choices,
                              default=Kaynak.OGRENCI)
    olusturan = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="+", null=True, blank=True,
    )
    olusturma_zamani = models.DateTimeField(default=timezone.now)
    onaylayan = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="+", null=True, blank=True,
    )
    onay_zamani = models.DateTimeField(null=True, blank=True)
    gerekce = models.TextField("Gerekçe (red / iptal / düzeltme)", blank=True)

    class Meta:
        abstract = True

    @property
    def onayli_mi(self):
        return self.onay_durumu == OnayDurumu.ONAYLANDI

    @property
    def kilitli_mi(self):
        """Onaylanan, reddedilen veya iptal edilen kaydı öğrenci değiştiremez."""
        return self.onay_durumu != OnayDurumu.BEKLIYOR
