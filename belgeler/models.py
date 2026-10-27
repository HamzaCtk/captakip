"""Belge arşivi ve ek belge istekleri.

- Her yüklenen dosya ayrı bir Belge kaydıdır. Yenilenen belge eskisinin
  yerine geçmez; 'onceki_surum' ile zincirlenir, eski sürüm arşivde kalır.
- Dosyalar web sunucusunun doğrudan sunmadığı bir klasörde, rastgele
  adlarla saklanır; yalnızca yetki kontrolü yapan indirme adresinden alınır.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from ortak.modeller import OnayliKayit, SilinemezModel


class BelgeTuru(models.TextChoices):
    PROTOKOL_FORMU = "PROTOKOL_FORMU", "Kabul ve Ders Protokol Formu"
    DERS_KAYIT_FORMU = "DERS_KAYIT_FORMU", "Ders Kayıt Formu"
    TRANSKRIPT = "TRANSKRIPT", "ÇAP/YDP not belgesi (transkript)"
    ANA_DAL_TRANSKRIPT = "ANA_DAL_TRANSKRIPT", "Ana dal transkripti"
    MUAFIYET_FORMU = "MUAFIYET_FORMU", "Özel Şartlı Derslerin Muafiyeti Formu"
    KURUL_KARARI = "KURUL_KARARI", "Yönetim kurulu kararı / resmi yazı"
    DIGER = "DIGER", "Diğer"


# Dönem bilgisi zorunlu olan belge türleri
DONEMLI_TURLER = {BelgeTuru.DERS_KAYIT_FORMU, BelgeTuru.TRANSKRIPT, BelgeTuru.ANA_DAL_TRANSKRIPT}


class BelgeIstegi(SilinemezModel):
    """Koordinatörün öğrenciden ek belge talebi."""

    class Durum(models.TextChoices):
        BEKLIYOR = "BEKLIYOR", "Belge bekleniyor"
        YUKLENDI = "YUKLENDI", "Yüklendi, inceleniyor"
        ONAYLANDI = "ONAYLANDI", "Onaylandı"
        REDDEDILDI = "REDDEDILDI", "Reddedildi, yeniden yüklenmeli"

    ogrenci = models.ForeignKey("ogrenciler.Ogrenci", on_delete=models.PROTECT, related_name="belge_istekleri")
    isteyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    tur = models.CharField("İstenen belge türü", max_length=20, choices=BelgeTuru.choices)
    aciklama = models.TextField("Açıklama", max_length=2000)
    son_tarih = models.DateField("Son tarih", null=True, blank=True)
    durum = models.CharField(max_length=12, choices=Durum.choices, default=Durum.BEKLIYOR)
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Belge isteği"
        verbose_name_plural = "Belge istekleri"
        ordering = ["-zaman"]

    @property
    def acik_mi(self):
        return self.durum in (self.Durum.BEKLIYOR, self.Durum.REDDEDILDI)

    def __str__(self):
        return f"{self.get_tur_display()} — {self.get_durum_display()}"


class Belge(OnayliKayit):
    ogrenci = models.ForeignKey("ogrenciler.Ogrenci", on_delete=models.PROTECT, related_name="belgeler")
    tur = models.CharField("Belge türü", max_length=20, choices=BelgeTuru.choices)
    donem = models.ForeignKey("ogrenciler.AkademikDonem", on_delete=models.PROTECT, null=True, blank=True,
                              related_name="+", verbose_name="Dönem")
    aciklama = models.CharField("Açıklama", max_length=300, blank=True)
    # Dosya bilgileri (dosyanın kendisi korunan klasörde durur)
    dosya_yolu = models.CharField(max_length=200, editable=False)
    orijinal_ad = models.CharField(max_length=150)
    boyut = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    mime = models.CharField(max_length=40)
    onceki_surum = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True,
                                        related_name="sonraki_surum")
    istek = models.ForeignKey(BelgeIstegi, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="belgeler")

    class Meta:
        verbose_name = "Belge"
        verbose_name_plural = "Belgeler"
        ordering = ["-olusturma_zamani"]

    @property
    def guncel_mi(self):
        return not hasattr(self, "sonraki_surum")  # sonraki sürümü yoksa günceldir

    @property
    def surum_no(self):
        n, b = 1, self
        while b.onceki_surum_id:
            n, b = n + 1, b.onceki_surum
        return n

    def __str__(self):
        donem = f" {self.donem}" if self.donem_id else ""
        return f"{self.get_tur_display()}{donem} ({self.orijinal_ad})"


class DepolananDosya(SilinemezModel):
    """Yüklenen bir dosyanın içeriği (veritabanı deposu kullanılırken).

    Canlı ortamda (Render ücretsiz plan) sunucu diski kalıcı değildir; site
    uyuyup uyandığında diske yazılan dosyalar kaybolur. Bu yüzden canlıda
    belge, mesaj eki ve CSV dosyalarının içeriği burada saklanır. Kayıt
    silinemez ve değiştirilemez; içerik SHA-256 özetiyle birlikte tutulur.
    """
    yol = models.CharField(max_length=200, unique=True, editable=False)
    icerik = models.BinaryField(editable=False)
    boyut = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Depolanan dosya"
        verbose_name_plural = "Depolanan dosyalar"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("Depolanan dosya değiştirilemez.")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.yol
