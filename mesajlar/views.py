from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.yetki import BOLUM_BASKANI, KOORDINATOR, OGRENCI
from ogrenciler.models import Ogrenci
from ogrenciler.views import erisilebilir_ogrenci
from ortak import depo

from . import servisler
from .models import Bildirim, Mesaj


class MesajFormu(forms.Form):
    metin = forms.CharField(label="Mesajınız", max_length=servisler.MAKS_UZUNLUK,
                            widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Mesajınızı yazın…"}))
    ek = forms.FileField(label="Ek dosya (isteğe bağlı)", required=False,
                         help_text="PDF, PNG veya JPEG · en fazla 10 MB",
                         widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg"}))


def _giris_gerekli(request):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    return None


def mesaj_kutusu(request):
    """Öğrenci kendi konuşmasına gider; koordinatör ve bölüm başkanı konuşma listesini görür."""
    if (yonlendir := _giris_gerekli(request)) is not None:
        return yonlendir
    if request.user.rol == OGRENCI:
        ogrenci = getattr(request.user, "ogrenci", None)
        if ogrenci is None:
            raise PermissionDenied
        return redirect("konusma", ogrenci_no=ogrenci.ogrenci_no)
    if request.user.rol not in (KOORDINATOR, BOLUM_BASKANI):
        raise PermissionDenied
    konusmalar = Ogrenci.objects.filter(mesajlar__isnull=False).annotate(
        son_zaman=Max("mesajlar__zaman"),
        mesaj_sayisi=Count("mesajlar", distinct=True),
        okunmamis=Count("mesajlar", distinct=True, filter=Q(mesajlar__okunma_zamani__isnull=True,
                                                            mesajlar__gonderen__rol=OGRENCI)),
    ).order_by("-son_zaman")
    return render(request, "mesajlar/kutu.html", {"konusmalar": konusmalar})


def konusma(request, ogrenci_no):
    if (yonlendir := _giris_gerekli(request)) is not None:
        return yonlendir
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    servisler.okundu_isaretle(okuyan=request.user, ogrenci=ogrenci)
    yazabilir = request.user.rol == KOORDINATOR or request.user.rol == OGRENCI
    return render(request, "mesajlar/konusma.html", {
        "ogrenci": ogrenci, "program": ogrenci.guncel_program, "sekme": "mesajlar",
        "mesajlar": ogrenci.mesajlar.select_related("gonderen", "okuyan"),
        "form": MesajFormu() if yazabilir else None,
        "acik_istek": ogrenci.belge_istekleri.filter(durum__in=["BEKLIYOR", "REDDEDILDI"]).count(),
    })


@require_POST
def mesaj_gonder(request, ogrenci_no):
    if not request.user.is_authenticated:
        raise PermissionDenied
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    form = MesajFormu(request.POST, request.FILES)
    if not form.is_valid():
        hatalar = " ".join(" ".join(v) for v in form.errors.values())
        messages.error(request, f"Mesaj gönderilemedi. {hatalar}")
        return redirect("konusma", ogrenci_no=ogrenci_no)
    try:
        servisler.mesaj_gonder(yapan=request.user, ogrenci=ogrenci, metin=form.cleaned_data["metin"],
                               ek=form.cleaned_data.get("ek"), request=request)
        messages.success(request, "Mesaj gönderildi.")
    except ValidationError as e:
        messages.error(request, "Mesaj gönderilemedi: " + " ".join(e.messages))
    return redirect("konusma", ogrenci_no=ogrenci_no)


def ek_indir(request, ogrenci_no, pk):
    """Mesaj eki yalnızca konuşmayı görebilen kişiye, belgelerle aynı güvenlik başlıklarıyla verilir."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    mesaj = get_object_or_404(Mesaj, pk=pk, ogrenci=ogrenci)
    if not mesaj.ek_var_mi:
        raise Http404
    dosya = depo.ac(mesaj.ek_yolu)
    if dosya is None:
        raise Http404("Dosya bulunamadı.")
    cevap = FileResponse(dosya, as_attachment=True, filename=mesaj.ek_adi, content_type=mesaj.ek_mime)
    cevap["X-Content-Type-Options"] = "nosniff"
    cevap["Content-Security-Policy"] = "default-src 'none'; sandbox"
    cevap["Cache-Control"] = "private, no-store"
    return cevap


# --- Bildirimler ----------------------------------------------------------------

def bildirimler(request):
    if (yonlendir := _giris_gerekli(request)) is not None:
        return yonlendir
    liste = request.user.bildirimler.all()[:100]
    return render(request, "mesajlar/bildirimler.html", {"bildirimler": liste})


def bildirim_ac(request, pk):
    """Bildirimi okundu yapar ve ilgili sayfaya götürür. Yalnızca kendi bildirimi açılabilir."""
    if (yonlendir := _giris_gerekli(request)) is not None:
        return yonlendir
    bildirim = get_object_or_404(Bildirim, pk=pk, alici=request.user)
    servisler.bildirim_okundu(kullanici=request.user, bildirim=bildirim)
    hedef = bildirim.baglanti
    # Açık yönlendirme (open redirect) olmasın: yalnızca site içi yollar kabul edilir
    if not hedef or not hedef.startswith("/") or \
            not url_has_allowed_host_and_scheme(hedef, allowed_hosts={request.get_host()}):
        hedef = "bildirimler"
    return redirect(hedef)


@require_POST
def tumunu_okundu(request):
    if not request.user.is_authenticated:
        raise PermissionDenied
    servisler.tumunu_okundu_yap(kullanici=request.user)
    messages.success(request, "Tüm bildirimler okundu olarak işaretlendi.")
    return redirect("bildirimler")
