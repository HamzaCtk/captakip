from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.yetki import KOORDINATOR, OGRENCI, rol_gerekli
from ogrenciler.models import AkademikDonem
from ogrenciler.views import erisilebilir_ogrenci
from ortak.modeller import OnayDurumu
from ortak import depo

from . import servisler
from .models import Belge, BelgeIstegi, BelgeTuru


class BelgeYuklemeFormu(forms.Form):
    tur = forms.ChoiceField(label="Belge türü", choices=BelgeTuru.choices)
    donem = forms.ModelChoiceField(label="Dönem", queryset=AkademikDonem.objects.all(), required=False,
                                   help_text="Ders kayıt formu ve transkriptler için zorunludur.")
    dosya = forms.FileField(label="Dosya", help_text="PDF, PNG veya JPEG · en fazla 10 MB",
                            widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg"}))
    aciklama = forms.CharField(label="Açıklama (isteğe bağlı)", max_length=300, required=False)

    def __init__(self, *args, ogrenci_mi=False, donemler=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ogrenci_mi:
            self.fields["tur"].choices = [c for c in BelgeTuru.choices if c[0] != BelgeTuru.KURUL_KARARI]
        if donemler is not None:
            self.fields["donem"].queryset = donemler


class IstekFormu(forms.Form):
    tur = forms.ChoiceField(label="İstenen belge", choices=BelgeTuru.choices)
    aciklama = forms.CharField(label="Açıklama", max_length=2000, widget=forms.Textarea(attrs={"rows": 2}))
    son_tarih = forms.DateField(label="Son tarih (isteğe bağlı)", required=False,
                                widget=forms.DateInput(attrs={"type": "date"}))


def _donemler(ogrenci):
    program = ogrenci.guncel_program
    guncel = AkademikDonem.guncel()
    qs = AkademikDonem.objects.all()
    if program:
        qs = qs.filter(sira__gte=program.kabul_donemi.sira)
    if guncel:
        qs = qs.filter(sira__lte=guncel.sira)
    return qs.order_by("-sira")


def belgeler_sayfasi(request, ogrenci_no):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    tum = list(ogrenci.belgeler.select_related("donem", "istek", "onceki_surum", "olusturan"))
    guncel = [b for b in tum if b.guncel_mi]
    eski_surumler = {}
    for b in tum:
        if b.onceki_surum_id:
            eski_surumler.setdefault(b.pk, [])
    baglam = {
        "ogrenci": ogrenci, "program": ogrenci.guncel_program, "sekme": "belgeler",
        "guncel": guncel, "tum": tum,
        "istekler": ogrenci.belge_istekleri.select_related("isteyen").prefetch_related("belgeler"),
        "form": BelgeYuklemeFormu(ogrenci_mi=request.user.rol == OGRENCI, donemler=_donemler(ogrenci)),
        "koordinator": request.user.rol == KOORDINATOR,
        "yukleyebilir": request.user.rol == KOORDINATOR or request.user.rol == OGRENCI,
        "transkript_eksik": _eksik_transkriptler(ogrenci),
        "acik_istek": sum(1 for i in ogrenci.belge_istekleri.all() if i.acik_mi),
    }
    if request.user.rol == KOORDINATOR:
        baglam["istek_formu"] = IstekFormu()
    return render(request, "belgeler/belgeler.html", baglam)


def _eksik_transkriptler(ogrenci):
    """Not girilmeyi bekleyen dersi olup transkripti yüklenmemiş dönemler."""
    from dersler.models import DersDenemesi
    donemler = {d.donem for d in DersDenemesi.objects.filter(
        ogrenci_dersi__program_kaydi__ogrenci=ogrenci, onay_durumu=OnayDurumu.ONAYLANDI,
        durum=DersDenemesi.Durum.ALINDI).select_related("donem")}
    return sorted([d for d in donemler if not servisler.transkript_yuklendi_mi(ogrenci, d)], key=lambda d: d.sira)


@require_POST
def belge_yukle(request, ogrenci_no):
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    form = BelgeYuklemeFormu(request.POST, request.FILES, ogrenci_mi=request.user.rol == OGRENCI,
                             donemler=_donemler(ogrenci))
    istek = onceki = None
    if request.POST.get("istek"):
        istek = get_object_or_404(BelgeIstegi, pk=_sayi(request.POST["istek"]), ogrenci=ogrenci)
    if request.POST.get("onceki"):
        onceki = get_object_or_404(Belge, pk=_sayi(request.POST["onceki"]), ogrenci=ogrenci)
    if not form.is_valid() and not (istek or onceki):
        hatalar = "; ".join(f"{form.fields[k].label}: {' '.join(v)}" if k in form.fields else " ".join(v)
                            for k, v in form.errors.items())
        messages.error(request, f"Belge yüklenemedi. {hatalar}")
        return redirect("belgeler", ogrenci_no=ogrenci_no)
    try:
        veri = form.cleaned_data if form.is_valid() else {}
        servisler.belge_yukle(yapan=request.user, ogrenci=ogrenci, dosya=request.FILES.get("dosya"),
                              tur=veri.get("tur") or (istek.tur if istek else onceki.tur),
                              donem=veri.get("donem"), aciklama=veri.get("aciklama", ""),
                              istek=istek, onceki=onceki, request=request)
        messages.success(request, "Belge yüklendi" + (" ve onaya gönderildi." if request.user.rol == OGRENCI else "."))
    except (ValidationError, PermissionDenied) as e:
        messages.error(request, "Belge yüklenemedi: " + (" ".join(e.messages) if isinstance(e, ValidationError) else str(e)))
    return redirect("belgeler", ogrenci_no=ogrenci_no)


def _sayi(deger):
    try:
        return int(deger)
    except (TypeError, ValueError):
        raise Http404


def belge_indir(request, ogrenci_no, pk):
    """Belge yalnızca yetki kontrolünden sonra indirilir. Tarayıcıda açılmaz
    (attachment) ve içeriğin çalıştırılmasını engelleyen başlıklar eklenir."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    belge = get_object_or_404(Belge, pk=pk, ogrenci=ogrenci)
    dosya = depo.ac(belge.dosya_yolu)
    if dosya is None:
        raise Http404("Dosya bulunamadı.")
    cevap = FileResponse(dosya, as_attachment=True, filename=belge.orijinal_ad, content_type=belge.mime)
    cevap["X-Content-Type-Options"] = "nosniff"
    cevap["Content-Security-Policy"] = "default-src 'none'; sandbox"
    cevap["Cache-Control"] = "private, no-store"
    return cevap


@require_POST
@rol_gerekli(KOORDINATOR)
def istek_olustur(request, ogrenci_no):
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    form = IstekFormu(request.POST)
    if form.is_valid():
        try:
            servisler.istek_olustur(yapan=request.user, ogrenci=ogrenci, request=request, **form.cleaned_data)
            messages.success(request, "Ek belge isteği öğrenciye iletildi.")
        except ValidationError as e:
            messages.error(request, " ".join(e.messages))
    else:
        messages.error(request, "İstek oluşturulamadı; alanları kontrol edin.")
    return redirect("belgeler", ogrenci_no=ogrenci_no)
