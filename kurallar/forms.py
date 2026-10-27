from django import forms
from django.utils import timezone

from belgeler.models import Belge, BelgeTuru
from ogrenciler.models import AkademikDonem, AnaDalKaydi, Karar
from ortak.modeller import OnayDurumu

from .tanimlar import PARAMETRELER


class TarihGirdisi(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        super().__init__(format="%Y-%m-%d", **kw)


class SurumFormu(forms.Form):
    ad = forms.CharField(label="Sürüm adı", max_length=200,
                         help_text="Ör. Çift Ana Dal Yönergesi (Senato 12.03.2027 değişikliği)")
    dayanak = forms.CharField(label="Dayanak", max_length=300,
                              help_text="Senato karar tarihi ve sayısı, değişen maddeler")
    yururluk_baslangic = forms.DateField(label="Yürürlük başlangıcı", widget=TarihGirdisi())

    def __init__(self, *args, onceki=None, **kw):
        super().__init__(*args, **kw)
        degerler = {p.anahtar: p.deger for p in onceki.parametreler.all()} if onceki else {}
        self.parametre_alanlari = []
        for anahtar, etiket, _tip, *_varsayilan, dayanak in PARAMETRELER:
            ad = f"p_{anahtar}"
            self.fields[ad] = forms.CharField(label=etiket, required=False, max_length=300,
                                              initial=degerler.get(anahtar, ""),
                                              help_text=f"{dayanak} · Boş bırakılırsa kural uygulanmaz.")
            self.parametre_alanlari.append(ad)

    def degerler(self):
        return {ad[2:]: self.cleaned_data.get(ad, "") for ad in self.parametre_alanlari}

    def temel_alanlar(self):
        return [self[a] for a in ("ad", "dayanak", "yururluk_baslangic")]

    def parametreler(self):
        return [self[a] for a in self.parametre_alanlari]


def _donemler(program):
    guncel = AkademikDonem.guncel()
    qs = AkademikDonem.objects.filter(sira__gte=program.kabul_donemi.sira - 10).exclude(donem="YAZ")
    if guncel:
        qs = qs.filter(sira__lte=guncel.sira)
    return qs.order_by("-sira")


class AnaDalFormu(forms.ModelForm):
    class Meta:
        model = AnaDalKaydi
        fields = ["donem", "gano", "ana_dal_durumu", "kaynak_aciklama"]
        labels = {"donem": "Dönem (sonu itibarıyla)", "ana_dal_durumu": "Ana dal durumu"}

    def __init__(self, *args, program, **kw):
        super().__init__(*args, **kw)
        self.fields["donem"].queryset = _donemler(program)
        self.fields["donem"].initial = self.fields["donem"].queryset.first()


class KararFormu(forms.Form):
    tur = forms.ChoiceField(label="Karar türü", choices=Karar.Tur.choices)
    kurul = forms.CharField(label="Kararı veren kurul / makam", max_length=120,
                            initial="Teknoloji Fakültesi Yönetim Kurulu")
    karar_tarihi = forms.DateField(label="Karar tarihi", widget=TarihGirdisi())
    karar_sayisi = forms.CharField(label="Karar sayısı", max_length=50, help_text="Ör. 2026/45-3")
    donem = forms.ModelChoiceField(label="Dönem (kayıt dondurmada)", queryset=AkademikDonem.objects.none(),
                                   required=False)
    dayanak_belge = forms.ModelChoiceField(label="Dayanak belge (kurul kararı yazısı)",
                                           queryset=Belge.objects.none(), empty_label="Belge seçin…",
                                           help_text="Önce Belgeler sekmesinden 'Kurul kararı' türünde yükleyin.")
    gerekce = forms.CharField(label="Gerekçe / özet", widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, program, **kw):
        super().__init__(*args, **kw)
        self.fields["donem"].queryset = _donemler(program)
        self.fields["dayanak_belge"].queryset = Belge.objects.filter(
            ogrenci=program.ogrenci, tur=BelgeTuru.KURUL_KARARI, onay_durumu=OnayDurumu.ONAYLANDI,
            sonraki_surum__isnull=True).order_by("-id")
        self.fields["dayanak_belge"].label_from_instance = \
            lambda b: f"{b.orijinal_ad} · {b.aciklama or 'kurul kararı'} " \
                      f"({timezone.localtime(b.olusturma_zamani):%d.%m.%Y})"
        turler = [("DONDURMA", "Kayıt dondurma"), ("KAYIT_SILME", "Kayıt silme"),
                  ("AYRILMA", "Kendi isteğiyle ayrılma"), ("DERS_SAYMA", "Derslerin ana dalda sayılması")]
        turler.insert(1, ("MEZUNIYET", "Mezuniyet (diploma)") if program.tur == "CAP"
                      else ("SERTIFIKA", "Yan dal sertifikası"))
        self.fields["tur"].choices = turler
