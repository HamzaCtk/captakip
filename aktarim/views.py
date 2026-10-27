from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.yetki import BOLUM_BASKANI, KOORDINATOR, rol_gerekli

from . import okuyucu, servisler
from .models import AktarimIslemi


class YuklemeFormu(forms.Form):
    tur = forms.ChoiceField(label="Ne aktarılacak?", choices=AktarimIslemi.Tur.choices)
    dosya = forms.FileField(label="CSV dosyası", help_text="Noktalı virgül (;) veya virgülle ayrılmış, en fazla "
                                                           "2 MB / 2000 satır.",
                            widget=forms.ClearableFileInput(attrs={"accept": ".csv,text/csv"}))


def _sutun_rehberi():
    rehber = []
    for tur, ad in AktarimIslemi.Tur.choices:
        rehber.append({"tur": tur, "ad": ad, "sutunlar": [
            {"anahtar": a, "zorunlu": z, "diger": [x for x in adlar if x != a]}
            for a, z, adlar in okuyucu.SUTUNLAR[tur]]})
    return rehber


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def aktarim_listesi(request):
    form = YuklemeFormu(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if request.user.rol != KOORDINATOR:
            raise Http404
        if form.is_valid():
            try:
                islem = servisler.yukle(yapan=request.user, request=request, tur=form.cleaned_data["tur"],
                                        dosya=form.cleaned_data["dosya"])
            except ValidationError as e:
                form.add_error("dosya", e)
            else:
                return redirect("aktarim_detay", pk=islem.pk)
    return render(request, "aktarim/liste.html", {
        "form": form, "islemler": AktarimIslemi.objects.select_related("yukleyen", "uygulayan")[:50],
        "rehber": _sutun_rehberi()})


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def aktarim_detay(request, pk):
    islem = get_object_or_404(AktarimIslemi, pk=pk)
    hatalar = [s for s in islem.onizleme if s["durum"] == "HATA"]
    return render(request, "aktarim/detay.html", {"islem": islem, "hatalar": hatalar,
                                                  "tamamlar": [s for s in islem.onizleme if s["durum"] == "TAMAM"]})


@require_POST
@rol_gerekli(KOORDINATOR)
def aktarim_uygula(request, pk):
    islem = get_object_or_404(AktarimIslemi, pk=pk)
    try:
        islem, ekler = servisler.uygula(yapan=request.user, islem=islem, request=request)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
        return redirect("aktarim_detay", pk=pk)
    messages.success(request, f"Aktarım uygulandı: {islem.satir_sayisi} satır işlendi.")
    # Geçici şifreler yalnızca bu yanıtta bir kez gösterilir, hiçbir yerde saklanmaz
    cevap = render(request, "aktarim/sonuc.html", {"islem": islem, "sifreler": ekler})
    cevap["Cache-Control"] = "no-store"
    return cevap


@require_POST
@rol_gerekli(KOORDINATOR)
def aktarim_vazgec(request, pk):
    islem = get_object_or_404(AktarimIslemi, pk=pk)
    try:
        servisler.vazgec(yapan=request.user, islem=islem, request=request)
        messages.success(request, "Aktarımdan vazgeçildi; hiçbir veri yazılmadı.")
    except ValidationError as e:
        messages.error(request, " ".join(e.messages))
    return redirect("aktarim_listesi")


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def sablon_indir(request, tur):
    if tur not in okuyucu.SABLONLAR:
        raise Http404
    cevap = HttpResponse(okuyucu.sablon_metni(tur), content_type="text/csv; charset=utf-8")
    cevap["Content-Disposition"] = f'attachment; filename="sablon_{tur.lower()}.csv"'
    cevap["X-Content-Type-Options"] = "nosniff"
    return cevap
