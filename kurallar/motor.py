"""Kural motoru.

degerlendir(program) çağrıldığında:
1. Program türü için o tarihte geçerli kural sürümü seçilir.
2. Yalnızca ONAYLI kayıtlardan girdi verisi toplanır.
3. Her kural fonksiyonu bulgu (seviye + mesaj + dayanak) üretir.
4. Girdi, bulgular ve kullanılan sürüm donmuş bir KuralDegerlendirmesi olarak
   saklanır (sonradan değiştirilemez).
5. Uyarılar güncellenir: yeni bulgu → yeni uyarı; ortadan kalkan bulgu →
   uyarı "koşul ortadan kalktı" olarak kapanır (silinmez).

Uyarı karar değildir; kararı koordinatör kurul kararına dayanarak işler.
"""
import contextlib
import contextvars

from django.db import transaction
from django.utils import timezone

from ortak.modeller import OnayDurumu

from .models import KuralDegerlendirmesi, KuralSurumu, Uyari

BILGI, UYARI, KRITIK = Uyari.Seviye.BILGI, Uyari.Seviye.UYARI, Uyari.Seviye.KRITIK


def _virgul(x):
    return f"{x:.2f}".replace(".", ",") if x is not None else "—"


# --- Girdi toplama ------------------------------------------------------------

def _girdi_topla(program, p, tarih):
    from ogrenciler.models import AkademikDonem, DonemKaydi
    from dersler.models import OgrenciDersi

    guncel = AkademikDonem.guncel(tarih)
    # Ana dal kayıtları: her dönem için son girilen kayıt
    ana = {}
    for k in program.ana_dal_kayitlari.select_related("donem").order_by("donem__sira", "zaman", "id"):
        ana[k.donem.sira] = k
    ana_liste = [ana[s] for s in sorted(ana)]

    dersler = list(program.dersler.filter(onay_durumu=OnayDurumu.ONAYLANDI)
                   .exclude(liste_durumu=OgrenciDersi.ListeDurumu.CIKARILDI)
                   .prefetch_related("denemeler__donem"))
    onayli_denemeler = [d for od in dersler for d in od.denemeler.all() if d.onay_durumu == OnayDurumu.ONAYLANDI]

    # Ders alınan dönemler ve kayıt durumu özel dönemler
    ders_alinan = {d.donem.sira for d in onayli_denemeler}
    ozel = {dk.donem.sira: dk.kayit_durumu for dk in DonemKaydi.objects.filter(
        program_kaydi=program, onay_durumu=OnayDurumu.ONAYLANDI).select_related("donem")}

    # Kabulden bugüne normal dönemler (Güz/Bahar)
    donemler = list(AkademikDonem.objects.filter(sira__gte=program.kabul_donemi.sira)
                    .exclude(donem="YAZ").order_by("sira"))
    if guncel:
        donemler = [d for d in donemler if d.sira <= guncel.sira]

    # Dönem sonu itibarıyla kümülatif program not ortalaması (yalnızca not
    # alınan dönemler için hesaplanır; içinde bulunulan dönem notlanmadan sayılmaz)
    puanlar = p.get("harf_puanlari") or {}
    notlu_donemler = {d.donem.sira for d in onayli_denemeler if d.harf_notu}
    ortalamalar = []
    for d in donemler:
        if d.sira not in notlu_donemler:
            continue
        top_puan = top_akts = 0
        for od in dersler:
            if od.liste_durumu != OgrenciDersi.ListeDurumu.AKTIF:
                continue
            notlu = [x for x in od.denemeler.all() if x.onay_durumu == OnayDurumu.ONAYLANDI
                     and x.harf_notu and x.donem.sira <= d.sira]
            if notlu:  # tekrar alınan derste son onaylı deneme sayılır
                son = sorted(notlu, key=lambda x: (x.donem.sira, x.id))[-1]
                if son.harf_notu in puanlar:
                    top_puan += puanlar[son.harf_notu] * od.akts
                    top_akts += od.akts
        if top_akts:
            ortalamalar.append({"donem": str(d), "sira": d.sira, "gano": round(top_puan / top_akts, 2)})

    ozet = program.akts_ozeti()
    aktif_kalemler = [od for od in dersler if od.liste_durumu != OgrenciDersi.ListeDurumu.CIKARILDI]
    return {
        "tarih": str(tarih), "guncel_donem": str(guncel) if guncel else None,
        "guncel_sira": guncel.sira if guncel else None,
        "program_durumu": program.durum, "tur": program.tur,
        "ana_dal": [{"donem": str(k.donem), "sira": k.donem.sira, "gano": float(k.gano),
                     "durum": k.ana_dal_durumu} for k in ana_liste],
        "donemler": [{"donem": str(d), "sira": d.sira,
                      "ders_alindi": d.sira in ders_alinan, "ozel": ozel.get(d.sira)} for d in donemler],
        "program_gano": ortalamalar,
        "akts": ozet,
        "ders_sayisi": len(aktif_kalemler),
    }


# --- Kurallar -----------------------------------------------------------------

def k_ana_dal_gano(g, p, ad):
    esik = p.get("ana_gano_esik")
    if esik is None or not g["ana_dal"]:
        return []
    son = g["ana_dal"][-1]
    if son["gano"] >= esik:
        return []
    dusus = sum(1 for k in g["ana_dal"] if k["gano"] < esik)
    izin = p.get("ana_gano_izin_sayisi") or 0
    tol = p.get("ana_gano_tolerans_esik")
    if dusus > izin:
        return [(KRITIK, f"Ana dal GANO {_virgul(son['gano'])} — {dusus}. kez {_virgul(esik)} sınırının altında. "
                         "Kayıt silme koşulu oluştu; kurul kararı gerekir.", ad)]
    ek = f" ({_virgul(tol)} toleransı içinde)" if tol is not None and son["gano"] >= tol else ""
    return [(UYARI, f"Ana dal GANO {_virgul(son['gano'])} — {_virgul(esik)} sınırının altında{ek}. "
                    f"Bir defalık hak kullanıldı ({dusus}/{izin}); tekrarı kayıt silme koşuludur.", ad)]


def k_program_gano(g, p, ad):
    esik = p.get("program_gano_esik")
    if esik is None:
        if g["tur"] == "CAP" and g["program_gano"]:
            return [(BILGI, "ÇAP not ortalaması sınırının (100 üzerinden 70) 4'lük karşılığı kural ayarlarına "
                            "girilmedi; bu kural kontrol edilmedi.", ad)]
        return []
    if not g["program_gano"]:
        return []
    son = g["program_gano"][-1]
    if son["gano"] >= esik:
        return []
    ardisik = 0
    for kayit in reversed(g["program_gano"]):
        if kayit["gano"] < esik:
            ardisik += 1
        else:
            break
    sinir = p.get("program_gano_ardisik_donem") or 1
    if ardisik >= sinir:
        return [(KRITIK, f"Program not ortalaması {_virgul(son['gano'])} — {ardisik} dönem üst üste "
                         f"{_virgul(esik)} altında. Kayıt silme koşulu oluştu.", ad)]
    return [(UYARI, f"Program not ortalaması {_virgul(son['gano'])}, {_virgul(esik)} altında "
                    f"({ardisik}/{sinir} dönem).", ad)]


def k_ders_almama(g, p, ad):
    sinir = p.get("ders_almama_donem")
    if not sinir or g["guncel_sira"] is None:
        return []
    gecmis = [d for d in g["donemler"] if d["sira"] < g["guncel_sira"]]
    dondurulmus = {k["sira"] for k in g["ana_dal"] if k["durum"] == "DONDURULDU"}
    seri = 0
    for d in reversed(gecmis):
        if d["ders_alindi"] or d["ozel"] in ("DONDURULDU", "IZINLI") or d["sira"] in dondurulmus:
            break
        seri += 1
    if seri >= sinir:
        return [(KRITIK, f"Son {seri} dönem üst üste ders alınmadı (kayıt dondurma/izin yok). "
                         "Kayıt silme koşulu oluştu.", ad)]
    if seri == sinir - 1 and seri > 0:
        return [(UYARI, "Geçen dönem ders alınmadı. Bu dönem de ders alınmazsa kayıt silme koşulu oluşur.", ad)]
    return []


def k_sure(g, p, ad):
    bulgular = []
    azami = p.get("azami_yariyil")
    yariyil = len(g["donemler"])
    if azami:
        if yariyil > azami:
            bulgular.append((KRITIK, f"Azami öğrenim süresi aşıldı ({yariyil}/{azami} yarıyıl).", ad))
        elif yariyil >= azami - 1:
            bulgular.append((UYARI, f"Azami öğrenim süresine yaklaşıldı ({yariyil}/{azami} yarıyıl).", ad))
    ek = p.get("ek_sure_yariyil")
    mezun = next((k for k in g["ana_dal"] if k["durum"] == "MEZUN"), None)
    if ek is not None and mezun and g["guncel_sira"] is not None:
        gecen = sum(1 for d in g["donemler"] if d["sira"] > mezun["sira"])
        if gecen > ek:
            bulgular.append((KRITIK, f"Ana dal mezuniyetinden sonraki ek süre aşıldı ({gecen}/{ek} yarıyıl).", ad))
        else:
            bulgular.append((BILGI, f"Ana daldan mezun; ek süre kullanılıyor ({gecen}/{ek} yarıyıl).", ad))
    return bulgular


def k_asgari_yuk(g, p, ad):
    ders, akts = p.get("asgari_ders"), p.get("asgari_akts")
    if not ders and not akts:
        return []
    if (ders and g["ders_sayisi"] < ders) or (akts and g["akts"]["toplam"] < akts):
        return [(UYARI, f"Ders listesi asgari şartı karşılamıyor: {g['ders_sayisi']} ders, "
                        f"{g['akts']['toplam']} AKTS (en az {ders} ders ve {akts} AKTS).", ad)]
    return []


def k_ana_dal_dondurma(g, p, ad):
    if g["ana_dal"] and g["ana_dal"][-1]["durum"] == "DONDURULDU" and g["program_durumu"] == "AKTIF":
        return [(UYARI, "Ana dalda kayıt dondurulmuş; bu programda da dondurulmuş sayılır. "
                        "İlgili kurul kararını sisteme işleyin.", ad)]
    return []


def k_tamamlama(g, p, ad):
    a = g["akts"]
    if not a["toplam"] or a["tamamlanan"] < a["toplam"]:
        return []
    son_ana = g["ana_dal"][-1] if g["ana_dal"] else None
    mezun = son_ana and son_ana["durum"] == "MEZUN"
    if g["tur"] == "CAP":
        esik = p.get("mezuniyet_ana_gano")
        if not mezun:
            return [(BILGI, "Tüm ÇAP dersleri tamamlandı. Diploma için ana dal mezuniyeti bekleniyor.", ad)]
        if esik is not None and son_ana["gano"] < esik:
            return [(UYARI, f"Dersler tamam, ancak ana dal mezuniyet GANO'su {_virgul(son_ana['gano'])} "
                            f"< {_virgul(esik)}; diploma koşulu sağlanmıyor.", ad)]
        return [(BILGI, "Diploma koşulları sağlanıyor. Mezuniyet kararını işleyebilirsiniz.", ad)]
    esik = p.get("bitirme_program_gano")
    pg = g["program_gano"][-1]["gano"] if g["program_gano"] else None
    if esik is not None and pg is not None and pg < esik:
        return [(UYARI, f"Yan dal dersleri tamam, ancak not ortalaması {_virgul(pg)} < {_virgul(esik)}.", ad)]
    if not mezun:
        return [(BILGI, "Tüm yan dal dersleri tamamlandı. Sertifika için ana dal mezuniyeti bekleniyor.", ad)]
    return [(BILGI, "Sertifika koşulları sağlanıyor. Sertifika kararını işleyebilirsiniz.", ad)]


KURALLAR = [
    ("ana_dal_gano", k_ana_dal_gano, {"CAP": "ÇAP Md. 9/e", "YDP": "YDP Md. 7/5"}),
    ("program_gano", k_program_gano, {"CAP": "Y.Ö.K. Yön. Md. 17/4", "YDP": "YDP Md. 7/6"}),
    ("ders_almama", k_ders_almama, {"CAP": "ÇAP Md. 9/d", "YDP": "YDP Md. 7/4"}),
    ("sure", k_sure, {"CAP": "ÇAP Md. 8/d · 2547 s. K. Md. 44/c", "YDP": "YDP Md. 7/9"}),
    ("asgari_yuk", k_asgari_yuk, {"CAP": "", "YDP": "YDP Md. 5/g"}),
    ("ana_dal_dondurma", k_ana_dal_dondurma, {"CAP": "ÇAP Md. 9/ç", "YDP": "YDP Md. 7/2"}),
    ("tamamlama", k_tamamlama, {"CAP": "ÇAP Md. 8/c-ç", "YDP": "YDP Md. 7/8"}),
]


# --- Değerlendirme --------------------------------------------------------------

@transaction.atomic
def degerlendir(program, tetikleyen, yapan=None, tarih=None):
    """Programı geçerli kural sürümüyle değerlendirir; donmuş kaydı döndürür."""
    if program.durum not in ("AKTIF", "DONDURULDU"):
        return None  # sonuçlanmış programlar değerlendirilmez
    tarih = tarih or timezone.localdate()
    surum = KuralSurumu.gecerli(program.tur, tarih)
    if surum is None:
        return None
    p = surum.degerler()
    g = _girdi_topla(program, p, tarih)
    bulgular = []
    for anahtar, fonk, dayanaklar in KURALLAR:
        for seviye, mesaj, dayanak in fonk(g, p, dayanaklar.get(program.tur, "")):
            bulgular.append({"kural": anahtar, "seviye": seviye, "mesaj": mesaj, "dayanak": dayanak})

    kayit = KuralDegerlendirmesi.objects.create(program_kaydi=program, surum=surum, tetikleyen=tetikleyen,
                                                yapan=yapan, girdi=g, sonuc=bulgular)
    _uyarilari_esitle(program, kayit, bulgular, yapan)
    return kayit


def _uyarilari_esitle(program, kayit, bulgular, yapan):
    mevcut = list(program.uyarilar.exclude(durum=Uyari.Durum.GECERSIZ))
    gorulen = set()
    for b in bulgular:
        ayni = next((u for u in mevcut if u.kural == b["kural"] and u.seviye == b["seviye"]), None)
        if ayni:
            gorulen.add(ayni.pk)
            if ayni.mesaj != b["mesaj"] and ayni.durum == Uyari.Durum.ACIK:
                # Aynı uyarının güncel değerlerle yeni kaydı açılır; eskisi kapanır
                _gecersiz(ayni, yapan, "Değerler güncellendi")
            else:
                continue
        u = Uyari.objects.create(program_kaydi=program, degerlendirme=kayit, kural=b["kural"],
                                 seviye=b["seviye"], mesaj=b["mesaj"], dayanak=b["dayanak"])
        gorulen.add(u.pk)
        if ayni is None:  # yalnızca gerçekten yeni (veya seviyesi değişen) uyarı bildirilir
            _uyari_bildir(program, u, yapan)
        # Seviye değişen eski uyarılar (ör. UYARI → KRITIK) kapanır
        for eski in mevcut:
            if eski.kural == b["kural"] and eski.pk not in gorulen and eski.durum != Uyari.Durum.KARARA_BAGLANDI:
                _gecersiz(eski, yapan, "Yerine yeni seviye uyarı açıldı")
                gorulen.add(eski.pk)
    for u in mevcut:
        if u.pk not in gorulen and u.durum in (Uyari.Durum.ACIK, Uyari.Durum.GORULDU):
            _gecersiz(u, yapan, "Koşul ortadan kalktı")


def _uyari_bildir(program, uyari, yapan):
    """Yeni UYARI ve KRİTİK seviyeli uyarılar öğrenciye ve koordinatörlere bildirilir.
    BİLGİ seviyesi yalnızca "Durum ve uyarılar" sekmesinde görünür."""
    if uyari.seviye == BILGI:
        return
    from django.urls import reverse
    from mesajlar.bildirim import koordinatorlere_bildir, ogrenciye_bildir
    ogrenci = program.ogrenci
    baglanti = reverse("ogrenci_durum", args=[ogrenci.ogrenci_no])
    metin = f"{uyari.get_seviye_display()}: {uyari.mesaj}"
    ogrenciye_bildir(ogrenci, "UYARI", metin, baglanti)
    koordinatorlere_bildir("UYARI", f"{ogrenci.ogrenci_no} {ogrenci.ad_soyad} · {metin}", baglanti,
                           ogrenci.ogrenci_no, haric=yapan if getattr(yapan, "rol", None) == "KOORDINATOR" else None)


def _gecersiz(uyari, yapan, notu):
    uyari.durum = Uyari.Durum.GECERSIZ
    uyari.kapatma_zamani, uyari.kapatma_notu = timezone.now(), notu
    uyari.save(update_fields=["durum", "kapatma_zamani", "kapatma_notu"])


_ertelenen = contextvars.ContextVar("kural_ertele", default=None)


@contextlib.contextmanager
def toplu_islem(tetikleyen, yapan=None, ayri=False):
    """Toplu işlemlerde (CSV aktarımı) her satırda değil, sonunda her program
    için bir kez değerlendirme yapılır.

    ayri=True: dışarıda başka bir toplu işlem olsa bile kendi listesini tutar.
    Önizleme gibi sonunda geri alınan işlemler bunu kullanır; geri alınan
    kayıtlar dıştaki listeye sızmaz.
    """
    if _ertelenen.get() is not None and not ayri:  # iç içe çağrı: dıştaki toplar
        yield
        return
    bekleyen = {}
    belirtec = _ertelenen.set(bekleyen)
    try:
        yield
    finally:
        _ertelenen.reset(belirtec)
    # Hata olursa buraya gelinmez (değerlendirme yapılmaz). Bu arada silinmiş
    # ya da geri alınmış kayıtlar atlanır.
    from ogrenciler.models import ProgramKaydi
    for program in ProgramKaydi.objects.filter(pk__in=list(bekleyen)).order_by("pk"):
        degerlendir(program, tetikleyen, yapan)


def guvenli_degerlendir(program, tetikleyen, yapan=None):
    """Başka bir işlemin sonunda çağrılır. Program yoksa sessizce geçer."""
    if program is None:
        return None
    bekleyen = _ertelenen.get()
    if bekleyen is not None:
        bekleyen[program.pk] = program
        return None
    return degerlendir(program, tetikleyen, yapan)
