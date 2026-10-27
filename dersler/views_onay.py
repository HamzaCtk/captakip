"""Onay mekanizması ekranları.

Bu görünümler kural uygulamaz; yalnızca formu okuyup dersler/servisler.py
içindeki fonksiyonları çağırır. Yetki ve kilit kontrolleri serviste yapılır.
"""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.yetki import BOLUM_BASKANI, KOORDINATOR, rol_gerekli
from ogrenciler.models import AkademikDonem
from ogrenciler.views import erisilebilir_ogrenci
from ortak.guvenlik import guvenli_yonlendir
from ortak.modeller import Kaynak

from . import servisler
from .models import Ders, DersDenemesi, NotGirisi, OgrenciDersi

from belgeler import servisler as belge_servis
from belgeler.models import Belge

TURLER = {"ders": OgrenciDersi, "deneme": DersDenemesi, "not": NotGirisi, "belge": Belge}


def _geri(request, ogrenci_no=None):
    # ZAP bulgusu: önceden "/" ile başlamayan değer redirect()'e sayfa adı olarak
    # gidiyor ve 500 hatası veriyordu. Artık yalnızca site içi yol kabul edilir.
    hedef = request.POST.get("geri") or request.GET.get("geri")
    if ogrenci_no:
        return guvenli_yonlendir(request, hedef, "ogrenci_karti", ogrenci_no=ogrenci_no)
    return guvenli_yonlendir(request, hedef, "anasayfa")


def _hata(request, e):
    metin = " ".join(e.messages) if isinstance(e, ValidationError) else str(e)
    messages.error(request, metin or "İşlem yapılamadı.")


def _sayi(deger):
    try:
        return int(deger)
    except (TypeError, ValueError):
        raise Http404


def _ogrencinin_kaydi(request, ogrenci_no, model, pk):
    """Kaydı, URL'deki öğrenciye ait olduğunu doğrulayarak getirir."""
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    pk = _sayi(pk)
    alan = {OgrenciDersi: "program_kaydi__ogrenci", DersDenemesi: "ogrenci_dersi__program_kaydi__ogrenci",
            NotGirisi: "deneme__ogrenci_dersi__program_kaydi__ogrenci", Belge: "ogrenci"}[model]
    return ogrenci, get_object_or_404(model, pk=pk, **{alan: ogrenci})


@require_POST
def kayit_islemi(request, ogrenci_no, tur, pk, eylem):
    """Onayla / reddet / geri çek / iptal et."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    model = TURLER.get(tur)
    if model is None:
        raise Http404
    ogrenci, kayit = _ogrencinin_kaydi(request, ogrenci_no, model, pk)
    gerekce = request.POST.get("gerekce", "")[:1000]
    try:
        if model is Belge:
            # Belgeler silinemez/geri çekilemez; yalnızca onay ve red vardır
            if eylem == "onayla":
                belge_servis.belge_onayla(yapan=request.user, belge=kayit, request=request)
                messages.success(request, "Belge onaylandı.")
            elif eylem == "reddet":
                belge_servis.belge_reddet(yapan=request.user, belge=kayit, gerekce=gerekce, request=request)
                messages.success(request, "Belge reddedildi; öğrenci yeni sürüm yükleyebilir. Eski sürüm arşivde kalır.")
            else:
                raise PermissionDenied("Belgeler silinemez veya geri çekilemez.")
        elif eylem == "onayla":
            servisler.onayla(yapan=request.user, kayit=kayit, request=request)
            messages.success(request, "Kayıt onaylandı ve kilitlendi.")
        elif eylem == "reddet":
            servisler.reddet(yapan=request.user, kayit=kayit, gerekce=gerekce, request=request)
            messages.success(request, "Kayıt reddedildi. Kayıt silinmedi, gerekçesiyle görünür kalacak.")
        elif eylem == "geri-cek":
            servisler.geri_cek(yapan=request.user, kayit=kayit, request=request)
            messages.success(request, "Kaydınızı geri çektiniz.")
        elif eylem == "iptal":
            servisler.iptal_et(yapan=request.user, kayit=kayit, gerekce=gerekce, request=request)
            messages.success(request, "Kayıt iptal edildi.")
        else:
            raise Http404
    except (ValidationError, PermissionDenied) as e:
        _hata(request, e)
    return _geri(request, ogrenci_no)


@require_POST
def ders_sec(request, ogrenci_no):
    """Seçmeli slotunu doldurma (ÇAP), havuzdan ders ekleme (YDP) veya
    koordinatörün listeye ders eklemesi. Ders yalnızca katalogdan seçilir."""
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    program = ogrenci.guncel_program
    kod = request.POST.get("ders_kodu", "").strip()
    ders = Ders.objects.filter(kod=kod, aktif=True).first()
    slot = None
    if request.POST.get("slot"):
        slot = get_object_or_404(OgrenciDersi, pk=_sayi(request.POST["slot"]), program_kaydi=program)
    try:
        if ders is None:
            raise ValidationError(f"'{kod}' kodlu aktif bir ders katalogda yok. Katalogda olmayan ders "
                                  "için koordinatöre mesajla talep gönderin.")
        servisler.ders_ekle(yapan=request.user, program=program, ders=ders, slot=slot,
                            gerekce=request.POST.get("gerekce", ""), request=request)
        messages.success(request, f"{ders.kod} {ders.ad} listeye eklendi"
                         + (" ve onaya gönderildi." if request.user.ogrenci_mi else "."))
    except (ValidationError, PermissionDenied) as e:
        _hata(request, e)
    return _geri(request, ogrenci_no)


@require_POST
def deneme_ekle(request, ogrenci_no):
    ogrenci, od = _ogrencinin_kaydi(request, ogrenci_no, OgrenciDersi, request.POST.get("ogrenci_dersi") or 0)
    donem = get_object_or_404(AkademikDonem, pk=_sayi(request.POST.get("donem")))
    aktarim = request.POST.get("aktarim") == "1"
    try:
        servisler.deneme_ekle(yapan=request.user, ogrenci_dersi=od, donem=donem,
                              harf_notu=request.POST.get("harf_notu", ""),
                              kaynak=Kaynak.AKTARIM if aktarim else None, request=request)
        messages.success(request, f"{od.gorunen_ad} — {donem} kaydı eklendi"
                         + (" ve onaya gönderildi." if request.user.ogrenci_mi else "."))
    except (ValidationError, PermissionDenied) as e:
        _hata(request, e)
    return _geri(request, ogrenci_no)


@require_POST
def not_gir(request, ogrenci_no, pk):
    ogrenci, deneme = _ogrencinin_kaydi(request, ogrenci_no, DersDenemesi, pk)
    try:
        servisler.not_gir(yapan=request.user, deneme=deneme, harf_notu=request.POST.get("harf_notu", ""),
                          request=request)
        messages.success(request, "Notunuz onaya gönderildi.")
    except (ValidationError, PermissionDenied) as e:
        _hata(request, e)
    return _geri(request, ogrenci_no)


@require_POST
@rol_gerekli(KOORDINATOR)
def liste_durumu(request, ogrenci_no, pk):
    ogrenci, od = _ogrencinin_kaydi(request, ogrenci_no, OgrenciDersi, pk)
    try:
        servisler.liste_durumu_degistir(yapan=request.user, ogrenci_dersi=od,
                                        yeni_durum=request.POST.get("liste_durumu", ""),
                                        gerekce=request.POST.get("gerekce", ""), request=request)
        messages.success(request, f"{od.gorunen_ad} için ders listesi güncellendi.")
    except (ValidationError, PermissionDenied) as e:
        _hata(request, e)
    return _geri(request, ogrenci_no)


class DuzeltmeFormu(forms.Form):
    donem = forms.ModelChoiceField(label="Dönem", queryset=AkademikDonem.objects.all())
    harf_notu = forms.ChoiceField(label="Harf notu", required=False,
                                  choices=[("", "— (henüz not yok)")] + DersDenemesi.HARF_NOTLARI)
    gerekce = forms.CharField(label="Düzeltme gerekçesi", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))


@rol_gerekli(KOORDINATOR)
def deneme_duzelt(request, ogrenci_no, pk):
    ogrenci, deneme = _ogrencinin_kaydi(request, ogrenci_no, DersDenemesi, pk)
    form = DuzeltmeFormu(request.POST or None, initial={"donem": deneme.donem, "harf_notu": deneme.harf_notu})
    if request.method == "POST" and form.is_valid():
        try:
            servisler.deneme_duzelt(yapan=request.user, deneme=deneme, request=request, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, "Kayıt düzeltildi; eski değer işlem kaydında saklandı.")
            return redirect("ogrenci_karti", ogrenci_no=ogrenci_no)
    return render(request, "dersler/deneme_duzelt.html", {"form": form, "deneme": deneme, "ogrenci": ogrenci})


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def onay_kuyrugu(request):
    b = servisler.bekleyenler()
    b["belgeler"] = list(Belge.objects.filter(onay_durumu="BEKLIYOR").select_related("ogrenci", "donem"))
    return render(request, "dersler/onay_kuyrugu.html", {"b": b, "geri": reverse("onay_kuyrugu")})
