"""Sürümlü kural ayarları, donmuş değerlendirmeler ve uyarılar.

- Kural sürümü ve parametreleri değiştirilemez. Yönerge değişince yeni sürüm
  açılır, eskisinin geçerliliği kapanır; eski sürüm silinmez.
- Her değerlendirme, kullandığı sürümü ve girdi değerlerini donmuş olarak
  saklar. Kural sonradan değişse de geçmiş değerlendirme yeniden yazılmaz.
- Uyarı karar değildir; koordinatör "görüldü" veya "karara bağlandı" diye kapatır.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from ortak.modeller import SilinemezModel

from .tanimlar import coz


class DegistirilemezModel(SilinemezModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk is not None and not getattr(self, "_izinli_guncelleme", False):
            raise PermissionDenied(f"{self._meta.verbose_name} değiştirilemez; yeni sürüm oluşturun.")
        super().save(*args, **kwargs)


class KuralSurumu(DegistirilemezModel):
    program_turu = models.CharField(max_length=3, choices=[("CAP", "ÇAP"), ("YDP", "YDP")])
    ad = models.CharField("Sürüm adı", max_length=200)
    dayanak = models.CharField("Dayanak (yönerge / karar)", max_length=300)
    yururluk_baslangic = models.DateField("Yürürlük başlangıcı")
    yururluk_bitis = models.DateField("Yürürlük bitişi", null=True, blank=True)
    olusturan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True,
                                  blank=True, related_name="+")
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Kural sürümü"
        verbose_name_plural = "Kural sürümleri"
        ordering = ["program_turu", "-yururluk_baslangic", "-id"]

    def degerler(self):
        """{anahtar: çözülmüş değer} sözlüğü."""
        return {p.anahtar: coz(p.anahtar, p.deger) for p in self.parametreler.all()}

    def kapat(self, tarih):
        """Yalnızca geçerlilik bitişi işlenebilir (değerler değişmez)."""
        self.yururluk_bitis = tarih
        self._izinli_guncelleme = True
        self.save(update_fields=["yururluk_bitis"])
        self._izinli_guncelleme = False

    @classmethod
    def gecerli(cls, program_turu, tarih=None):
        tarih = tarih or timezone.localdate()
        return cls.objects.filter(program_turu=program_turu, yururluk_baslangic__lte=tarih) \
            .filter(models.Q(yururluk_bitis__isnull=True) | models.Q(yururluk_bitis__gte=tarih)) \
            .order_by("-yururluk_baslangic", "-id").first()

    def __str__(self):
        return f"{self.get_program_turu_display()} · {self.ad} ({self.yururluk_baslangic:%d.%m.%Y})"


class KuralParametresi(DegistirilemezModel):
    surum = models.ForeignKey(KuralSurumu, on_delete=models.PROTECT, related_name="parametreler")
    anahtar = models.CharField(max_length=40)
    deger = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "Kural parametresi"
        verbose_name_plural = "Kural parametreleri"
        constraints = [models.UniqueConstraint(fields=["surum", "anahtar"], name="parametre_tekil")]


class KuralDegerlendirmesi(DegistirilemezModel):
    program_kaydi = models.ForeignKey("ogrenciler.ProgramKaydi", on_delete=models.PROTECT,
                                      related_name="degerlendirmeler")
    surum = models.ForeignKey(KuralSurumu, on_delete=models.PROTECT, related_name="+")
    zaman = models.DateTimeField(default=timezone.now)
    tetikleyen = models.CharField(max_length=80)
    yapan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                              related_name="+")
    girdi = models.JSONField("Değerlendirme anındaki veriler")
    sonuc = models.JSONField("Bulgular")

    class Meta:
        verbose_name = "Kural değerlendirmesi"
        verbose_name_plural = "Kural değerlendirmeleri"
        ordering = ["-zaman", "-id"]


class Uyari(SilinemezModel):
    class Seviye(models.TextChoices):
        BILGI = "BILGI", "Bilgi"
        UYARI = "UYARI", "Uyarı"
        KRITIK = "KRITIK", "Kritik"

    class Durum(models.TextChoices):
        ACIK = "ACIK", "Açık"
        GORULDU = "GORULDU", "Görüldü"
        KARARA_BAGLANDI = "KARARA_BAGLANDI", "Karara bağlandı"
        GECERSIZ = "GECERSIZ", "Koşul ortadan kalktı"

    program_kaydi = models.ForeignKey("ogrenciler.ProgramKaydi", on_delete=models.PROTECT, related_name="uyarilar")
    degerlendirme = models.ForeignKey(KuralDegerlendirmesi, on_delete=models.PROTECT, related_name="uyarilar")
    kural = models.CharField(max_length=40)
    seviye = models.CharField(max_length=6, choices=Seviye.choices)
    mesaj = models.CharField(max_length=400)
    dayanak = models.CharField(max_length=200, blank=True)
    durum = models.CharField(max_length=16, choices=Durum.choices, default=Durum.ACIK)
    kapatan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+")
    kapatma_zamani = models.DateTimeField(null=True, blank=True)
    kapatma_notu = models.CharField(max_length=500, blank=True)
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Uyarı"
        verbose_name_plural = "Uyarılar"
        ordering = ["durum", "-zaman"]

    @property
    def acik_mi(self):
        return self.durum == self.Durum.ACIK
