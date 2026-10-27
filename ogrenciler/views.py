from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.yetki import BOLUM_BASKANI, KOORDINATOR, OGRENCI, rol_gerekli
from denetim.models import IslemKaydi
from dersler import servisler as dsv
from dersler.models import Ders, DersDenemesi, OgrenciDersi
from ortak.modeller import OnayDurumu

from . import servisler
from .forms import KoordinatorNotuFormu, OgrenciEkleFormu
from .models import AkademikDonem, Ogrenci, ProgramKaydi


def erisilebilir_ogrenci(request, ogrenci_no):
    """Öğrenci kaydını yetki kontrolüyle getirir.

    Öğrenci yalnızca kendi kaydına erişebilir. Başka bir öğrencinin numarası
    denenirse (IDOR) 404 değil 403 döner ve kayıt varlığı sızdırılmaz.
    """
    kullanici = request.user
    if kullanici.rol == OGRENCI:
        if getattr(getattr(kullanici, "ogrenci", None), "ogrenci_no", None) != ogrenci_no:
            raise PermissionDenied("Yalnızca kendi kaydınızı görebilirsiniz.")
    elif kullanici.rol not in (KOORDINATOR, BOLUM_BASKANI):
        raise PermissionDenied
    return get_object_or_404(Ogrenci, ogrenci_no=ogrenci_no)


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def ogrenci_listesi(request):
    q = request.GET.get("q", "").strip()
    tur = request.GET.get("tur", "")
    uyari = request.GET.get("uyari", "")
    acik = Q(uyarilar__durum__in=["ACIK", "GORULDU"])
    programlar = ProgramKaydi.objects.annotate(
        kritik_sayisi=Count("uyarilar", filter=acik & Q(uyarilar__seviye="KRITIK"), distinct=True),
        uyari_sayisi=Count("uyarilar", filter=acik & Q(uyarilar__seviye="UYARI"), distinct=True),
    ).select_related("ogrenci", "kabul_donemi", "ogrenci__ana_dal_bolumu") \
        .prefetch_related(Prefetch("dersler", queryset=OgrenciDersi.objects.prefetch_related("denemeler")))
    if q:
        programlar = programlar.filter(Q(ogrenci__ogrenci_no__icontains=q) | Q(ogrenci__ad__icontains=q) |
                                       Q(ogrenci__soyad__icontains=q))
    if tur in ("CAP", "YDP"):
        programlar = programlar.filter(tur=tur)
    if uyari == "kritik":
        programlar = programlar.filter(kritik_sayisi__gt=0)
    elif uyari == "var":
        programlar = programlar.filter(Q(kritik_sayisi__gt=0) | Q(uyari_sayisi__gt=0))
    return render(request, "ogrenciler/liste.html", {"programlar": programlar, "q": q, "tur": tur, "uyari": uyari})


@rol_gerekli(KOORDINATOR)
def ogrenci_ekle(request):
    form = OgrenciEkleFormu(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            ogrenci, gecici = servisler.ogrenci_ekle(yapan=request.user, request=request, **form.cleaned_data)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            messages.success(request, f"{ogrenci.ad_soyad} eklendi. Kullanıcı adı: {ogrenci.ogrenci_no} — "
                                      f"Geçici şifre: {gecici} (bir daha gösterilmeyecek).")
            return redirect("ogrenci_karti", ogrenci_no=ogrenci.ogrenci_no)
    return render(request, "ogrenciler/ekle.html", {"form": form})


def ogrenci_karti(request, ogrenci_no):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    ogrenci = erisilebilir_ogrenci(request, ogrenci_no)
    program = ogrenci.guncel_program
    yonetici = request.user.rol in (KOORDINATOR, BOLUM_BASKANI)
    baglam = {"ogrenci": ogrenci, "program": program, "yonetici": yonetici, "sekme": "dersler",
              "acik_istek": ogrenci.belge_istekleri.filter(durum__in=["BEKLIYOR", "REDDEDILDI"]).count(),
              "koordinator": request.user.rol == KOORDINATOR, "ogrenci_kendisi": request.user.rol == OGRENCI,
              "dersler": [], "arsiv": [], "ozet": {"toplam": 0, "tamamlanan": 0, "kalan": 0}, "bekleyen": 0,
              "harf_notlari": DersDenemesi.HARF_NOTLARI}

    if program:
        tum = list(program.dersler.select_related("ders", "protokol_kalemi").prefetch_related(
            Prefetch("denemeler", queryset=DersDenemesi.objects.select_related("donem")
                     .prefetch_related("not_girisleri"))))
        gorunur = [d for d in tum if d.liste_durumu != OgrenciDersi.ListeDurumu.CIKARILDI
                   and d.onay_durumu not in (OnayDurumu.REDDEDILDI, OnayDurumu.IPTAL)]
        baglam["dersler"] = sorted(gorunur, key=lambda d: (d.sira, d.id))
        baglam["arsiv"] = [d for d in tum if d not in gorunur]
        baglam["ozet"] = program.akts_ozeti()
        baglam["acik_uyarilar"] = list(program.uyarilar.filter(durum__in=["ACIK", "GORULDU"])
                                       .order_by("seviye", "-zaman"))
        _sira = {"KRITIK": 0, "UYARI": 1, "BILGI": 2}
        baglam["acik_uyarilar"].sort(key=lambda u: _sira.get(u.seviye, 3))
        b = dsv.bekleyenler(program)
        baglam["bekleyen"] = len(b["dersler"]) + len(b["denemeler"]) + len(b["notlar"]) \
            + ogrenci.belgeler.filter(onay_durumu=OnayDurumu.BEKLIYOR).count()
        from belgeler.models import BelgeTuru
        baglam["transkript_donemleri"] = set(ogrenci.belgeler.filter(tur=BelgeTuru.TRANSKRIPT).exclude(
            onay_durumu__in=[OnayDurumu.REDDEDILDI, OnayDurumu.IPTAL]).values_list("donem_id", flat=True))

        listedeki = {d.ders_id for d in gorunur if d.ders_id}
        baglam["secmeliler"] = Ders.objects.filter(aktif=True, tur=Ders.Tur.SECMELI).exclude(id__in=listedeki)
        baglam["katalog"] = Ders.objects.filter(aktif=True).exclude(id__in=listedeki)
        # Dönem kaydı girilebilecek dersler: onaylı, aktif, ders seçilmiş, henüz geçilmemiş
        baglam["deneme_dersleri"] = [d for d in gorunur if d.onayli_mi and d.ders_id
                                     and d.liste_durumu == OgrenciDersi.ListeDurumu.AKTIF and not d.tamamlandi_mi]
        guncel = AkademikDonem.guncel()
        if request.user.rol == OGRENCI and guncel:
            # Öğrenci: bu dönem zaten kaydı olan dersleri listeleme
            baglam["deneme_dersleri"] = [d for d in baglam["deneme_dersleri"]
                                         if not any(x.donem_id == guncel.id for x in d.gecerli_denemeler)]
        donemler = AkademikDonem.objects.filter(sira__gte=program.kabul_donemi.sira)
        if guncel:
            donemler = donemler.filter(sira__lte=guncel.sira)
        if request.user.rol == OGRENCI and guncel:
            donemler = donemler.filter(sira__gte=guncel.sira - 10)  # öğrenci: içinde bulunulan yıl
        baglam["donemler"] = donemler.order_by("-sira")
        baglam["guncel_donem"] = guncel

    if ozet := baglam["ozet"]:
        baglam["yuzde"] = round(100 * ozet["tamamlanan"] / ozet["toplam"]) if ozet["toplam"] else 0
    if yonetici:
        # Koordinatör notları ve işlem geçmişi öğrenciye gösterilmez
        baglam["notlar"] = ogrenci.koordinator_notlari.select_related("yazan")
        baglam["gecmis"] = IslemKaydi.objects.filter(ogrenci_no=ogrenci.ogrenci_no).select_related("yapan")[:50]
        baglam["not_formu"] = KoordinatorNotuFormu()
    return render(request, "ogrenciler/kart.html", baglam)


@require_POST
@rol_gerekli(KOORDINATOR)
def koordinator_notu_ekle(request, ogrenci_no):
    ogrenci = get_object_or_404(Ogrenci, ogrenci_no=ogrenci_no)
    form = KoordinatorNotuFormu(request.POST)
    if form.is_valid():
        servisler.koordinator_notu_ekle(yapan=request.user, request=request, ogrenci=ogrenci,
                                        metin=form.cleaned_data["metin"])
        messages.success(request, "Not eklendi.")
    else:
        messages.error(request, "Not eklenemedi: " + " ".join(form.errors.get("metin", [])))
    return redirect("ogrenci_karti", ogrenci_no=ogrenci_no)
