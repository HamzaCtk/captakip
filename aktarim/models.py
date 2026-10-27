"""Geçmiş verilerin CSV dosyasıyla toplu aktarımı.

Her yükleme bir AktarimIslemi kaydıdır ve silinmez. Dosya korunan klasörde
saklanır (özeti/SHA-256 ile). Akış iki adımlıdır:
1. Önizleme: dosya veritabanına hiçbir şey yazılmadan, gerçek servislerle
   "deneme olarak" işlenir ve her satırın sonucu gösterilir.
2. Uygulama: koordinatör onaylarsa aynı dosya tek bir işlemde (transaction)
   uygulanır. Bir satır bile hata verirse hiçbir satır yazılmaz.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from ortak.modeller import SilinemezModel


class AktarimIslemi(SilinemezModel):
    class Tur(models.TextChoices):
        OGRENCI = "OGRENCI", "Öğrenci kayıtları"
        NOT = "NOT", "Ders ve not geçmişi"
        ANA_DAL = "ANA_DAL", "Ana dal GANO bilgisi"

    class Durum(models.TextChoices):
        ONIZLENDI = "ONIZLENDI", "Önizlendi"
        UYGULANDI = "UYGULANDI", "Uygulandı"
        VAZGECILDI = "VAZGECILDI", "Vazgeçildi"

    tur = models.CharField("Aktarım türü", max_length=8, choices=Tur.choices)
    dosya_adi = models.CharField(max_length=150)
    dosya_yolu = models.CharField(max_length=200, editable=False)
    boyut = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    kodlama = models.CharField(max_length=20)
    ayirac = models.CharField(max_length=4)
    yukleyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    zaman = models.DateTimeField(default=timezone.now)
    durum = models.CharField(max_length=10, choices=Durum.choices, default=Durum.ONIZLENDI)
    satir_sayisi = models.PositiveIntegerField(default=0)
    hata_sayisi = models.PositiveIntegerField(default=0)
    onizleme = models.JSONField("Satır sonuçları", default=list)
    uygulayan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+")
    uygulama_zamani = models.DateTimeField(null=True, blank=True)

    # Kayıt oluştuktan sonra yalnızca bu alanlar değişebilir
    DEGISEBILIR = {"durum", "uygulayan", "uygulama_zamani", "onizleme", "hata_sayisi"}

    class Meta:
        verbose_name = "Aktarım işlemi"
        verbose_name_plural = "Aktarım işlemleri"
        ordering = ["-zaman", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            alanlar = set(kwargs.get("update_fields") or ())
            if not alanlar or not alanlar <= self.DEGISEBILIR:
                raise PermissionDenied("Aktarım kaydının dosya bilgileri değiştirilemez.")
        super().save(*args, **kwargs)

    @property
    def uygulanabilir_mi(self):
        return self.durum == self.Durum.ONIZLENDI and self.hata_sayisi == 0 and self.satir_sayisi > 0

    def __str__(self):
        return f"#{self.pk} {self.get_tur_display()} · {self.dosya_adi}"
