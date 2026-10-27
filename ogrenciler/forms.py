from django import forms

from .models import AkademikDonem, Bolum, Ogrenci, ProgramKaydi, ogrenci_no_dogrulayici


class OgrenciEkleFormu(forms.Form):
    ogrenci_no = forms.CharField(label="Öğrenci no", max_length=12, validators=[ogrenci_no_dogrulayici],
                                 help_text="Öğrencinin kullanıcı adı olarak da kullanılır.")
    ad = forms.CharField(label="Ad", max_length=80)
    soyad = forms.CharField(label="Soyad", max_length=80)
    eposta = forms.EmailField(label="Okul e-postası")
    ana_dal_bolumu = forms.ModelChoiceField(label="Ana dal bölümü", queryset=Bolum.objects.all())
    tur = forms.ChoiceField(label="Program türü", choices=ProgramKaydi.Tur.choices)
    kabul_donemi = forms.ModelChoiceField(label="Kabul dönemi", queryset=AkademikDonem.objects.exclude(donem="YAZ"))

    def clean_ogrenci_no(self):
        no = self.cleaned_data["ogrenci_no"]
        if Ogrenci.objects.filter(ogrenci_no=no).exists():
            raise forms.ValidationError("Bu öğrenci numarası zaten kayıtlı.")
        return no

    def clean_eposta(self):
        return self.cleaned_data["eposta"].strip().lower()


class KoordinatorNotuFormu(forms.Form):
    metin = forms.CharField(label="Yeni not", max_length=4000,
                            widget=forms.Textarea(attrs={"rows": 3}))
