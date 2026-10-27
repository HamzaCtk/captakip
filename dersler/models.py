"""Ders kataloğu, protokol şablonları, öğrencinin ders listesi ve denemeler."""
from django.core.exceptions import ValidationError
from django.db import models

from ortak.modeller import OnayDurumu, OnayliKayit, SilinemezModel


class Ders(SilinemezModel):
    """Bölümün ders kataloğu. Ders silinmez; pasife alınır."""

    class Tur(models.TextChoices):
        ZORUNLU = "ZORUNLU", "Zorunlu"
        SECMELI = "SECMELI", "Seçmeli"

    kod = models.CharField("Ders kodu", max_length=12, unique=True)
    ad = models.CharField("Ders adı", max_length=150)
    akts = models.PositiveSmallIntegerField("AKTS")
    yariyil = models.PositiveSmallIntegerField("Yarıyıl", null=True, blank=True)
    tur = models.CharField("Tür", max_length=8, choices=Tur.choices, default=Tur.ZORUNLU)
    aktif = models.BooleanField("Aktif", default=True)

    class Meta:
        verbose_name = "Ders"
        verbose_name_plural = "Ders kataloğu"
        ordering = ["yariyil", "kod"]

    def __str__(self):
        return f"{self.kod} {self.ad}"


class ProtokolSablonu(SilinemezModel):
    """Bir ana dal bölümünden gelen ÇAP öğrencilerinin alacağı ders paketi
    (Kabul ve Ders Protokol Formu). YDP için ilan edilen ders havuzu da
    aynı yapıyla tutulur."""
    ad = models.CharField("Şablon adı", max_length=150)
    program_turu = models.CharField(max_length=3, choices=[("CAP", "ÇAP"), ("YDP", "YDP")])
    ana_dal_bolumu = models.ForeignKey("ogrenciler.Bolum", on_delete=models.PROTECT,
                                       null=True, blank=True, related_name="protokoller",
                                       help_text="YDP havuzu için boş bırakılır.")
    aktif = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Protokol şablonu"
        verbose_name_plural = "Protokol şablonları"

    def toplam_akts(self):
        return sum(k.akts for k in self.kalemler.all())

    def __str__(self):
        return self.ad


class ProtokolKalemi(SilinemezModel):
    """Şablondaki bir ders ya da seçmeli slotu ("5. Yarıyıl Teknik Seçmeli")."""
    sablon = models.ForeignKey(ProtokolSablonu, on_delete=models.PROTECT, related_name="kalemler")
    sira = models.PositiveSmallIntegerField()
    ders = models.ForeignKey(Ders, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    slot_aciklama = models.CharField(max_length=100, blank=True,
                                     help_text="Ders yerine seçmeli slotu ise açıklaması")
    yariyil = models.PositiveSmallIntegerField(null=True, blank=True)
    akts = models.PositiveSmallIntegerField()
    ozel_sart = models.TextField("Özel şart (muafiyet)", blank=True)

    class Meta:
        ordering = ["sablon", "sira"]
        constraints = [models.UniqueConstraint(fields=["sablon", "sira"], name="kalem_sira_tekil")]

    @property
    def secmeli_slot_mu(self):
        return self.ders_id is None

    def __str__(self):
        return str(self.ders) if self.ders else self.slot_aciklama


class OgrenciDersi(OnayliKayit):
    """Öğrencinin alacağı ders listesindeki bir kalem.

    AKTS değeri kalemde saklanır: katalogdaki ders sonradan değişse de
    öğrencinin geçmişi bozulmaz.
    """

    class ListeDurumu(models.TextChoices):
        AKTIF = "AKTIF", "Listede"
        MUAF = "MUAF", "Muaf"
        CIKARILDI = "CIKARILDI", "Listeden çıkarıldı"

    program_kaydi = models.ForeignKey("ogrenciler.ProgramKaydi", on_delete=models.PROTECT,
                                      related_name="dersler")
    ders = models.ForeignKey(Ders, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    slot_aciklama = models.CharField(max_length=100, blank=True)
    yariyil = models.PositiveSmallIntegerField(null=True, blank=True)
    akts = models.PositiveSmallIntegerField()
    liste_durumu = models.CharField(max_length=10, choices=ListeDurumu.choices, default=ListeDurumu.AKTIF)
    protokol_kalemi = models.ForeignKey(ProtokolKalemi, on_delete=models.PROTECT, null=True, blank=True,
                                        related_name="+")
    doldurdugu_slot = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True,
                                        related_name="dolduranlar",
                                        help_text="Bu ders bir seçmeli slotunu dolduruyorsa o slot")
    sira = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Öğrenci dersi"
        verbose_name_plural = "Öğrenci dersleri"
        ordering = ["sira", "id"]

    def clean(self):
        if not self.ders_id and not self.slot_aciklama:
            raise ValidationError("Ders ya da seçmeli slot açıklaması gereklidir.")

    @property
    def gorunen_ad(self):
        return self.ders.ad if self.ders else self.slot_aciklama

    @property
    def onayli_denemeler(self):
        return [d for d in self.denemeler.all() if d.onay_durumu == OnayDurumu.ONAYLANDI]

    @property
    def tamamlandi_mi(self):
        """Muaf ya da onaylı bir denemede geçmiş ise tamamlanmıştır."""
        if self.liste_durumu == self.ListeDurumu.MUAF and self.onayli_mi:
            return True
        return any(d.durum == DersDenemesi.Durum.GECTI for d in self.onayli_denemeler)

    @property
    def gorunen_durum(self):
        """Ekranda gösterilecek durum: liste durumu ya da son onaylı deneme."""
        if self.liste_durumu != self.ListeDurumu.AKTIF:
            return self.get_liste_durumu_display()
        if not self.ders_id:
            return "Ders seçilmedi"
        onayli = self.onayli_denemeler
        if onayli:
            return onayli[-1].get_durum_display()
        if any(d.onay_durumu == OnayDurumu.BEKLIYOR for d in self.denemeler.all()):
            return "Onay bekliyor"
        return "Henüz alınmadı"

    @property
    def slot_secimi_bekliyor(self):
        return self.dolduranlar.filter(onay_durumu=OnayDurumu.BEKLIYOR).exists()

    @property
    def gecerli_denemeler(self):
        """Reddedilen/iptal edilenler hariç, kronolojik denemeler."""
        return [d for d in self.denemeler.all()
                if d.onay_durumu not in (OnayDurumu.REDDEDILDI, OnayDurumu.IPTAL)]

    def __str__(self):
        return f"{self.program_kaydi.ogrenci.ogrenci_no} — {self.gorunen_ad}"


class DersDenemesi(OnayliKayit):
    """Bir dersin bir dönemde alınışı. Ders tekrar alınırsa yeni satır açılır."""

    class Durum(models.TextChoices):
        PLANLANDI = "PLANLANDI", "Planlandı"
        ALINDI = "ALINDI", "Alındı"
        GECTI = "GECTI", "Geçti"
        KALDI = "KALDI", "Kaldı"

    # Selçuk Üniversitesi harf notları (4'lük sistem karşılıklarıyla)
    HARF_NOTLARI = [("AA", "AA (4,00)"), ("BA", "BA (3,50)"), ("BB", "BB (3,00)"),
                    ("CB", "CB (2,50)"), ("CC", "CC (2,00)"), ("DC", "DC (1,50)"),
                    ("DD", "DD (1,00)"), ("FD", "FD (0,50)"), ("FF", "FF (0,00)")]

    ogrenci_dersi = models.ForeignKey(OgrenciDersi, on_delete=models.PROTECT, related_name="denemeler")
    donem = models.ForeignKey("ogrenciler.AkademikDonem", on_delete=models.PROTECT, related_name="+")
    durum = models.CharField(max_length=10, choices=Durum.choices, default=Durum.PLANLANDI)
    harf_notu = models.CharField(max_length=2, choices=HARF_NOTLARI, blank=True)

    class Meta:
        verbose_name = "Ders denemesi"
        verbose_name_plural = "Ders denemeleri"
        ordering = ["donem__sira", "id"]

    @property
    def bekleyen_not(self):
        return next((n for n in self.not_girisleri.all() if n.onay_durumu == OnayDurumu.BEKLIYOR), None)

    @property
    def not_girilebilir_mi(self):
        """Onaylı, "alındı" durumundaki ve bekleyen not girişi olmayan deneme."""
        return (self.onay_durumu == OnayDurumu.ONAYLANDI and self.durum == self.Durum.ALINDI
                and self.bekleyen_not is None)

    def __str__(self):
        return f"{self.ogrenci_dersi} / {self.donem} / {self.get_durum_display()}"


class NotGirisi(OnayliKayit):
    """Öğrencinin dönem sonunda girdiği not. Ders denemesinin kendisi
    onaylı ve kilitli olduğu için not ayrı bir kayıt olarak onaya gider;
    koordinatör onaylayınca denemenin notu ve sonucu işlenir."""
    deneme = models.ForeignKey(DersDenemesi, on_delete=models.PROTECT, related_name="not_girisleri")
    harf_notu = models.CharField(max_length=2, choices=DersDenemesi.HARF_NOTLARI)

    class Meta:
        verbose_name = "Not girişi"
        verbose_name_plural = "Not girişleri"
        ordering = ["olusturma_zamani"]

    def __str__(self):
        return f"{self.deneme} → {self.harf_notu}"
