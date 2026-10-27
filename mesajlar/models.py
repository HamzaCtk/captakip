"""Koordinatör ile öğrenci arasındaki yazışma ve sistem içi bildirimler.

- Her öğrencinin tek bir konuşması vardır: o öğrencinin tüm mesajları.
  Öğrenci yalnızca kendi konuşmasını görür; koordinatör hepsini görür ve
  yazar; bölüm başkanı yalnızca okur.
- Mesajlar silinemez ve gönderildikten sonra metni değiştirilemez. Yalnızca
  "okundu" zamanı sonradan işaretlenir.
- Mesaja tek bir ek dosya (PDF, PNG, JPEG) eklenebilir. Ek, belgelerle aynı
  güvenlik denetiminden geçer ve aynı korunan klasörde rastgele adla durur.
- Bildirim: onay, red, iptal, düzeltme, belge isteği ve yeni uyarı olaylarında
  ilgili kişiye düşen kısa not. Bildirimler de silinmez; okundu olarak işaretlenir.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from ortak.modeller import SilinemezModel


class Mesaj(SilinemezModel):
    ogrenci = models.ForeignKey("ogrenciler.Ogrenci", on_delete=models.PROTECT, related_name="mesajlar",
                                help_text="Konuşmanın sahibi olan öğrenci.")
    gonderen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    metin = models.TextField("Mesaj", max_length=4000)
    zaman = models.DateTimeField(default=timezone.now, db_index=True)
    # Karşı taraf (öğrenci için koordinatör, koordinatör için öğrenci) ilk okuduğunda dolar
    okunma_zamani = models.DateTimeField(null=True, blank=True)
    okuyan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                               null=True, blank=True)
    # Ek dosya (isteğe bağlı; dosyanın kendisi korunan klasörde durur)
    ek_yolu = models.CharField(max_length=200, blank=True, editable=False)
    ek_adi = models.CharField(max_length=150, blank=True)
    ek_boyut = models.PositiveIntegerField(null=True, blank=True)
    ek_sha256 = models.CharField(max_length=64, blank=True)
    ek_mime = models.CharField(max_length=40, blank=True)

    # Sonradan değiştirilmesine izin verilen tek alanlar
    DEGISEBILIR = {"okunma_zamani", "okuyan"}

    class Meta:
        verbose_name = "Mesaj"
        verbose_name_plural = "Mesajlar"
        ordering = ["zaman", "id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            alanlar = set(kwargs.get("update_fields") or ())
            if not alanlar or not alanlar <= self.DEGISEBILIR:
                raise PermissionDenied("Gönderilmiş mesaj değiştirilemez.")
        super().save(*args, **kwargs)

    @property
    def ogrenciden_mi(self):
        return self.gonderen_id == self.ogrenci.kullanici_id

    @property
    def ek_var_mi(self):
        return bool(self.ek_yolu)

    def __str__(self):
        return f"{self.ogrenci.ogrenci_no} · {self.zaman:%d.%m.%Y %H:%M} · {self.metin[:40]}"


class Bildirim(SilinemezModel):
    class Tur(models.TextChoices):
        ONAY = "ONAY", "Onay"
        RED = "RED", "Red"
        IPTAL = "IPTAL", "İptal"
        DUZELTME = "DUZELTME", "Düzeltme"
        BELGE_ISTEGI = "BELGE_ISTEGI", "Belge isteği"
        UYARI = "UYARI", "Uyarı"

    alici = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bildirimler")
    tur = models.CharField(max_length=14, choices=Tur.choices)
    metin = models.CharField(max_length=400)
    # Tıklanınca gidilecek sayfa (yalnızca site içi yol, ör. /ogrenciler/231101001/)
    baglanti = models.CharField(max_length=200, blank=True)
    ogrenci_no = models.CharField(max_length=20, blank=True)
    zaman = models.DateTimeField(default=timezone.now, db_index=True)
    okunma_zamani = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Bildirim"
        verbose_name_plural = "Bildirimler"
        ordering = ["-zaman", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None and set(kwargs.get("update_fields") or ()) != {"okunma_zamani"}:
            raise PermissionDenied("Bildirim değiştirilemez.")
        super().save(*args, **kwargs)

    @property
    def okundu_mu(self):
        return self.okunma_zamani is not None

    def __str__(self):
        return f"{self.alici} · {self.get_tur_display()} · {self.metin[:40]}"
