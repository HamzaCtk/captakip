"""Öğrenci, program kaydı ve programa bağlı kayıtlar.

Merkezde ProgramKaydi vardır: bir öğrencinin bir ÇAP veya YDP programına
kaydı. Dersler, dönem durumları, ana dal bilgileri ve kararlar öğrenciye
değil bu kayda bağlanır (ÇAP'tan YDP'ye geçişte geçmiş korunur, ÇAP Md. 8/g).
"""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from ortak.modeller import OnayDurumu, OnayliKayit, SilinemezModel


class Bolum(SilinemezModel):
    """Öğrencinin ana dal bölümü (ör. Elektrik-Elektronik Mühendisliği)."""
    kod = models.CharField("Kod", max_length=10, unique=True)
    ad = models.CharField("Bölüm adı", max_length=120)
    fakulte = models.CharField("Fakülte", max_length=120)

    class Meta:
        verbose_name = "Bölüm"
        verbose_name_plural = "Bölümler"
        ordering = ["ad"]

    def __str__(self):
        return self.ad


class AkademikDonem(SilinemezModel):
    """2025-2026 Güz gibi bir akademik dönem. 'sira' alanı dönemleri
    kronolojik sıralamak ve "üst üste iki dönem" kontrolü için kullanılır."""

    class Donem(models.TextChoices):
        GUZ = "GUZ", "Güz"
        BAHAR = "BAHAR", "Bahar"
        YAZ = "YAZ", "Yaz"

    yil = models.CharField("Akademik yıl", max_length=9,
                           validators=[RegexValidator(r"^\d{4}-\d{4}$", "Örnek: 2025-2026")])
    donem = models.CharField("Dönem", max_length=5, choices=Donem.choices)
    sira = models.PositiveIntegerField(unique=True, editable=False)

    class Meta:
        verbose_name = "Akademik dönem"
        verbose_name_plural = "Akademik dönemler"
        ordering = ["sira"]
        constraints = [models.UniqueConstraint(fields=["yil", "donem"], name="donem_tekil")]

    def save(self, *args, **kwargs):
        baslangic = int(self.yil[:4])
        self.sira = baslangic * 10 + {"GUZ": 1, "BAHAR": 2, "YAZ": 3}[self.donem]
        super().save(*args, **kwargs)

    @classmethod
    def guncel(cls, tarih=None):
        """Bugünün tarihine göre içinde bulunulan dönem (Eylül-Ocak Güz,
        Şubat-Haziran Bahar, Temmuz-Ağustos Yaz)."""
        tarih = tarih or timezone.localdate()
        y, a = tarih.year, tarih.month
        if a >= 9:
            yil, donem = f"{y}-{y + 1}", "GUZ"
        elif a == 1:
            yil, donem = f"{y - 1}-{y}", "GUZ"
        elif a <= 6:
            yil, donem = f"{y - 1}-{y}", "BAHAR"
        else:
            yil, donem = f"{y - 1}-{y}", "YAZ"
        return cls.objects.filter(yil=yil, donem=donem).first()

    def __str__(self):
        return f"{self.yil} {self.get_donem_display()}"


ogrenci_no_dogrulayici = RegexValidator(r"^\d{9,12}$", "Öğrenci numarası 9-12 haneli rakamlardan oluşmalıdır.")


class Ogrenci(SilinemezModel):
    """Kişi bilgisi. Öğrenci numarası tekil anahtardır (ileride OBİS ile
    eşleştirme bu numara üzerinden yapılır)."""
    kullanici = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                     related_name="ogrenci")
    ogrenci_no = models.CharField("Öğrenci no", max_length=12, unique=True,
                                  validators=[ogrenci_no_dogrulayici])
    ad = models.CharField("Ad", max_length=80)
    soyad = models.CharField("Soyad", max_length=80)
    eposta = models.EmailField("Okul e-postası")
    ana_dal_bolumu = models.ForeignKey(Bolum, on_delete=models.PROTECT,
                                       verbose_name="Ana dal bölümü")
    olusturma_zamani = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Öğrenci"
        verbose_name_plural = "Öğrenciler"
        ordering = ["ogrenci_no"]

    @property
    def ad_soyad(self):
        return f"{self.ad} {self.soyad}"

    @property
    def guncel_program(self):
        """Aktif veya dondurulmuş program kaydı; yoksa en son kayıt."""
        return (self.programlar.filter(durum__in=ProgramKaydi.ACIK_DURUMLAR).first()
                or self.programlar.order_by("-kayit_zamani").first())

    def __str__(self):
        return f"{self.ogrenci_no} {self.ad_soyad}"


class ProgramKaydi(SilinemezModel):
    class Tur(models.TextChoices):
        CAP = "CAP", "Çift Anadal (ÇAP)"
        YDP = "YDP", "Yan Dal (YDP)"

    class Durum(models.TextChoices):
        AKTIF = "AKTIF", "Aktif"
        DONDURULDU = "DONDURULDU", "Dondurulmuş"
        MEZUN = "MEZUN", "Mezun (diploma)"
        SERTIFIKA = "SERTIFIKA", "Sertifika aldı"
        SILINDI = "SILINDI", "Kaydı silindi"
        AYRILDI = "AYRILDI", "Kendi isteğiyle ayrıldı"

    ACIK_DURUMLAR = [Durum.AKTIF, Durum.DONDURULDU]

    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name="programlar")
    tur = models.CharField("Program türü", max_length=3, choices=Tur.choices)
    kabul_donemi = models.ForeignKey(AkademikDonem, on_delete=models.PROTECT,
                                     related_name="+", verbose_name="Kabul dönemi")
    protokol = models.ForeignKey("dersler.ProtokolSablonu", on_delete=models.PROTECT,
                                 null=True, blank=True, related_name="programlar")
    durum = models.CharField("Durum", max_length=12, choices=Durum.choices, default=Durum.AKTIF)
    onceki_kayit = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="sonraki_kayitlar",
                                     help_text="ÇAP'tan YDP'ye geçişte önceki kayıt (ÇAP Md. 8/g)")
    kayit_zamani = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Program kaydı"
        verbose_name_plural = "Program kayıtları"
        ordering = ["-kayit_zamani"]
        constraints = [
            # Bir öğrencinin aynı anda bölümümüzde tek açık kaydı olabilir
            # (ÇAP Md. 5/ğ: aynı programda hem ÇAP hem YDP olamaz).
            models.UniqueConstraint(fields=["ogrenci"], condition=Q(durum__in=["AKTIF", "DONDURULDU"]),
                                    name="tek_acik_program"),
        ]

    # --- Ders takibi özetleri (yalnızca onaylı kayıtlar hesaba girer) -------
    def aktif_dersler(self):
        from dersler.models import OgrenciDersi
        return self.dersler.exclude(liste_durumu=OgrenciDersi.ListeDurumu.CIKARILDI) \
                           .filter(onay_durumu=OnayDurumu.ONAYLANDI)

    def akts_ozeti(self):
        toplam = tamamlanan = 0
        for d in self.aktif_dersler():
            toplam += d.akts
            if d.tamamlandi_mi:
                tamamlanan += d.akts
        return {"toplam": toplam, "tamamlanan": tamamlanan, "kalan": toplam - tamamlanan}

    def __str__(self):
        return f"{self.ogrenci} — {self.get_tur_display()} ({self.kabul_donemi})"


class DonemKaydi(OnayliKayit):
    """Programın bir dönemdeki durumu. "İki dönem üst üste ders almama"
    kuralı (ÇAP Md. 9/d, YDP Md. 7/4) bu tabloya göre değerlendirilir."""

    class KayitDurumu(models.TextChoices):
        AKTIF = "AKTIF", "Aktif"
        DONDURULDU = "DONDURULDU", "Dondurulmuş (mazeretli)"
        IZINLI = "IZINLI", "İzinli"

    program_kaydi = models.ForeignKey(ProgramKaydi, on_delete=models.PROTECT, related_name="donemler")
    donem = models.ForeignKey(AkademikDonem, on_delete=models.PROTECT, related_name="+")
    kayit_durumu = models.CharField(max_length=12, choices=KayitDurumu.choices, default=KayitDurumu.AKTIF)
    notlar_gonderildi = models.BooleanField("Dönem sonu notları onaya gönderildi", default=False)

    class Meta:
        verbose_name = "Dönem kaydı"
        verbose_name_plural = "Dönem kayıtları"
        ordering = ["donem__sira"]
        constraints = [models.UniqueConstraint(fields=["program_kaydi", "donem"], name="donem_kaydi_tekil")]

    def __str__(self):
        return f"{self.program_kaydi.ogrenci.ogrenci_no} {self.donem} {self.get_kayit_durumu_display()}"


class AnaDalKaydi(SilinemezModel):
    """Kurallar için gereken ana dal bilgisi. Yalnızca koordinatör girer ve
    kaynağını belirtir (sistem ana dal derslerini izlemez)."""

    class AnaDalDurumu(models.TextChoices):
        AKTIF = "AKTIF", "Aktif"
        DONDURULDU = "DONDURULDU", "Kaydı dondurulmuş"
        MEZUN = "MEZUN", "Ana daldan mezun"

    program_kaydi = models.ForeignKey(ProgramKaydi, on_delete=models.PROTECT, related_name="ana_dal_kayitlari")
    donem = models.ForeignKey(AkademikDonem, on_delete=models.PROTECT, related_name="+")
    gano = models.DecimalField("Ana dal GANO", max_digits=3, decimal_places=2,
                               validators=[MinValueValidator(0), MaxValueValidator(4)])
    ana_dal_durumu = models.CharField(max_length=12, choices=AnaDalDurumu.choices, default=AnaDalDurumu.AKTIF)
    kaynak_aciklama = models.CharField("Kaynak", max_length=200,
                                       help_text="Ör. öğrenci işleri yazısı, ana dal transkripti")
    giren = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Ana dal kaydı"
        verbose_name_plural = "Ana dal kayıtları"
        ordering = ["-donem__sira", "-zaman"]


class KoordinatorNotu(SilinemezModel):
    """Öğrenci kartına koordinatörün düştüğü not. Öğrenci göremez."""
    ogrenci = models.ForeignKey(Ogrenci, on_delete=models.PROTECT, related_name="koordinator_notlari")
    yazan = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    metin = models.TextField("Not", max_length=4000)
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Koordinatör notu"
        verbose_name_plural = "Koordinatör notları"
        ordering = ["-zaman"]


class Karar(SilinemezModel):
    """Kurul kararının sisteme işlenmesi (kabul, dondurma, mezuniyet,
    sertifika, kayıt silme). Kararı kurul verir; koordinatör işler."""

    class Tur(models.TextChoices):
        DONDURMA = "DONDURMA", "Kayıt dondurma"
        MEZUNIYET = "MEZUNIYET", "Mezuniyet (diploma)"
        SERTIFIKA = "SERTIFIKA", "Yan dal sertifikası"
        KAYIT_SILME = "KAYIT_SILME", "Kayıt silme"
        AYRILMA = "AYRILMA", "Kendi isteğiyle ayrılma"
        DERS_SAYMA = "DERS_SAYMA", "Derslerin ana dalda sayılması"

    program_kaydi = models.ForeignKey(ProgramKaydi, on_delete=models.PROTECT, related_name="kararlar")
    tur = models.CharField(max_length=12, choices=Tur.choices)
    kurul = models.CharField("Kararı veren kurul / makam", max_length=120)
    karar_tarihi = models.DateField("Karar tarihi")
    karar_sayisi = models.CharField("Karar sayısı", max_length=50)
    gerekce = models.TextField("Gerekçe")
    dayanak_belge = models.ForeignKey("belgeler.Belge", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="+", help_text="Kurul kararı yazısı")
    isleyen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    zaman = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Karar"
        verbose_name_plural = "Kararlar"
        ordering = ["-karar_tarihi"]
