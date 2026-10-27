from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.yetki import BOLUM_BASKANI, KOORDINATOR, OGRENCI, rol_gerekli
from ogrenciler.views import erisilebilir_ogrenci

from . import servisler
from .forms import AnaDalFormu, KararFormu, SurumFormu
from .models import KuralSurumu, Uyari
from .tanimlar import TANIM


def _hata(request, e):
    messages.error(request, " ".join(e.messages) if hasattr(e, "messages") else str(e))


def _program_gerekli(request, ogrenci):
    program = ogrenci.guncel_program
    if program is None:
        messages.error(request, "Öğrencinin program kaydı yok.")
    return program


# --- Kural ayarları ------------------------------------------------------------------

def _dayanak(metin, tur):
    """Dayanak metninden yalnızca ilgili program türüne ait kısmı gösterir."""
    diger = "YDP" if tur == "CAP" else "ÇAP"
    parcalar = [p for p in metin.split(" · ") if not p.startswith(diger)]
    return " · ".join(parcalar) or metin


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def kural_ayarlari(request):
    gruplar = []
    for tur, ad in (("CAP", "Çift Ana Dal (ÇAP)"), ("YDP", "Yan Dal (YDP)")):
        surumler = list(KuralSurumu.objects.filter(program_turu=tur).prefetch_related("parametreler")
                        .select_related("olusturan"))
        gecerli = KuralSurumu.gecerli(tur)
        satirlar = []
        if gecerli:
            degerler = {p.anahtar: p.deger for p in gecerli.parametreler.all()}
            satirlar = [(TANIM[a][1], degerler.get(a) or "—", _dayanak(TANIM[a][5], tur)) for a in TANIM]
        gruplar.append({"tur": tur, "ad": ad, "gecerli": gecerli, "satirlar": satirlar,
                        "gecmis": [s for s in surumler if s != gecerli]})
    return render(request, "kurallar/ayarlar.html", {"gruplar": gruplar})


@rol_gerekli(KOORDINATOR)
def surum_yeni(request, tur):
    if tur not in ("CAP", "YDP"):
        return redirect("kural_ayarlari")
    onceki = KuralSurumu.objects.filter(program_turu=tur).order_by("-yururluk_baslangic", "-id").first()
    form = SurumFormu(request.POST or None, onceki=onceki)
    if request.method == "POST" and form.is_valid():
        try:
            surum = servisler.yeni_surum(yapan=request.user, request=request, program_turu=tur,
                                         ad=form.cleaned_data["ad"], dayanak=form.cleaned_data["dayanak"],
                                         yururluk_baslangic=form.cleaned_data["yururluk_baslangic"],
                                         degerler=form.degerler())
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, f"Yeni kural sürümü kaydedildi: {surum.ad}. Önceki sürüm geçmişte korunuyor.")
            return redirect("kural_ayarlari")
    return render(request, "kurallar/surum_yeni.html", {"form": form, "tur": tur, "onceki": onceki})


# --- Öğrencinin durum sekmesi ------------------------------------------------------

def ogrenci_durum(request, ogrenci_no):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    program = ogrenci.guncel_program
    koordinator = request.user.rol == KOORDINATOR
    yonetici = request.user.rol in (KOORDINATOR, BOLUM_BASKANI)
    baglam = {"ogrenci": ogrenci, "program": program, "sekme": "durum", "koordinator": koordinator,
              "yonetici": yonetici, "ogrenci_kendisi": request.user.rol == OGRENCI,
              "acik_istek": ogrenci.belge_istekleri.filter(durum__in=["BEKLIYOR", "REDDEDILDI"]).count()}
    if program:
        uyarilar = list(program.uyarilar.select_related("kapatan"))
        baglam["acik_uyarilar"] = [u for u in uyarilar if u.durum in (Uyari.Durum.ACIK, Uyari.Durum.GORULDU)]
        baglam["kapali_uyarilar"] = [u for u in uyarilar if u not in baglam["acik_uyarilar"]]
        baglam["ana_dal"] = program.ana_dal_kayitlari.select_related("donem", "giren")
        baglam["kararlar"] = program.kararlar.select_related("isleyen", "dayanak_belge")
        baglam["surum"] = KuralSurumu.gecerli(program.tur)
        son = program.degerlendirmeler.select_related("surum", "yapan").first()
        baglam["son_degerlendirme"] = son
        if son:
            baglam["program_gano"] = son.girdi.get("program_gano", [])
            baglam["son_ana_gano"] = (son.girdi.get("ana_dal") or [None])[-1]
        if yonetici:
            baglam["degerlendirmeler"] = program.degerlendirmeler.select_related("surum", "yapan")[:20]
        if koordinator and program.durum in ("AKTIF", "DONDURULDU"):
            baglam["ana_dal_formu"] = AnaDalFormu(program=program)
    return render(request, "kurallar/durum.html", baglam)


@require_POST
@rol_gerekli(KOORDINATOR)
def ana_dal_ekle(request, ogrenci_no):
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    program = _program_gerekli(request, ogrenci)
    if program:
        form = AnaDalFormu(request.POST, program=program)
        if form.is_valid():
            try:
                servisler.ana_dal_kaydi_ekle(yapan=request.user, request=request, program=program,
                                             **form.cleaned_data)
                messages.success(request, "Ana dal bilgisi kaydedildi; kurallar yeniden değerlendirildi.")
            except ValidationError as e:
                _hata(request, e)
        else:
            messages.error(request, "Ana dal bilgisi kaydedilemedi: " +
                           " ".join(f"{form.fields[a].label if a in form.fields else ''}: {' '.join(h)}"
                                    for a, h in form.errors.items()))
    return redirect("ogrenci_durum", ogrenci_no=ogrenci_no)


@require_POST
@rol_gerekli(KOORDINATOR)
def simdi_degerlendir(request, ogrenci_no):
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    program = _program_gerekli(request, ogrenci)
    if program:
        try:
            kayit = servisler.simdi_degerlendir(yapan=request.user, program=program, request=request)
            messages.success(request, f"Kurallar değerlendirildi ({len(kayit.sonuc)} bulgu).")
        except ValidationError as e:
            _hata(request, e)
    return redirect("ogrenci_durum", ogrenci_no=ogrenci_no)


@require_POST
@rol_gerekli(KOORDINATOR)
def uyari_durumu(request, ogrenci_no, pk):
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    uyari = get_object_or_404(Uyari, pk=pk, program_kaydi__ogrenci=ogrenci)
    try:
        servisler.uyari_kapat(yapan=request.user, request=request, uyari=uyari,
                              durum=request.POST.get("durum", ""), notu=request.POST.get("notu", ""))
        messages.success(request, "Uyarı güncellendi.")
    except ValidationError as e:
        _hata(request, e)
    return redirect("ogrenci_durum", ogrenci_no=ogrenci_no)


@rol_gerekli(KOORDINATOR)
def karar_isle(request, ogrenci_no):
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    program = _program_gerekli(request, ogrenci)
    if program is None or program.durum not in ("AKTIF", "DONDURULDU"):
        if program:
            messages.error(request, "Program kaydı sonuçlanmış; yeni karar işlenemez.")
        return redirect("ogrenci_durum", ogrenci_no=ogrenci_no)
    form = KararFormu(request.POST or None, program=program)
    if request.method == "POST" and form.is_valid():
        try:
            karar = servisler.karar_isle(yapan=request.user, request=request, program=program, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, f"Karar işlendi: {karar.get_tur_display()}.")
            return redirect("ogrenci_durum", ogrenci_no=ogrenci_no)
    return render(request, "kurallar/karar.html", {"form": form, "ogrenci": ogrenci, "program": program})
