"""CSV aktarım servisleri.

Satırlar ekrandan girişle AYNI servisler üzerinden işlenir (ogrenci_ekle,
ders_ekle, deneme_ekle, ana_dal_kaydi_ekle). Böylece yetki, iş kuralları,
işlem kaydı ve kural değerlendirmesi aktarımda da aynen uygulanır. Aktarılan
her kaydın kaynağı "Geçmiş veri aktarımı" (AKTARIM) olur.
"""
import hashlib
import re
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Kullanici
from belgeler.dogrulama import guvenli_ad
from denetim.kayit import kaydet
from ortak import depo
from ortak.modeller import Kaynak, OnayDurumu

from . import okuyucu
from .models import AktarimIslemi

KOORD = Kullanici.Rol.KOORDINATOR
_DONEM_ADLARI = {"guz": "GUZ", "1": "GUZ", "bahar": "BAHAR", "2": "BAHAR", "yaz": "YAZ", "3": "YAZ"}
_PROGRAM_ADLARI = {"cap": "CAP", "cift_ana_dal": "CAP", "cift_anadal": "CAP",
                   "ydp": "YDP", "yan_dal": "YDP", "yandal": "YDP"}
_ANA_DAL_DURUMLARI = {"": "AKTIF", "aktif": "AKTIF", "dondurulmus": "DONDURULDU", "donduruldu": "DONDURULDU",
                      "kaydi_dondurulmus": "DONDURULDU", "mezun": "MEZUN", "ana_daldan_mezun": "MEZUN"}


class _GeriAl(Exception):
    """Önizlemede yapılan her şeyi geri almak için kullanılır."""


def _koordinator_mu(yapan):
    if yapan is None or yapan.rol != KOORD:
        raise PermissionDenied("Veri aktarımını yalnızca koordinatör yapabilir.")


# --- Hücre çözümleyiciler -------------------------------------------------------

def _metin(deger, ad, uzunluk=80):
    deger = (deger or "").strip()
    if not deger:
        raise ValidationError(f"{ad} boş.")
    if deger[0] in "=+-@\t\r":
        # CSV/formül enjeksiyonu: bu karakterle başlayan hücreler kabul edilmez
        raise ValidationError(f"{ad} '{deger[0]}' ile başlayamaz.")
    if len(deger) > uzunluk:
        raise ValidationError(f"{ad} en fazla {uzunluk} karakter olabilir.")
    return deger


def _donem(deger):
    from ogrenciler.models import AkademikDonem
    m = re.fullmatch(r"(\d{4})\s*[-/]\s*(\d{4})\s*[ /\-]?\s*([^\d\s]+|\d)(?:\s+yar[ıi]y[ıi]l[ıi])?",
                     (deger or "").strip(), flags=re.IGNORECASE)
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        raise ValidationError(f"Dönem anlaşılamadı: '{deger}'. Örnek: 2025-2026 Güz")
    donem = _DONEM_ADLARI.get(okuyucu.sade(m.group(3)))
    if donem is None:
        raise ValidationError(f"Dönem adı Güz, Bahar veya Yaz olmalı: '{deger}'.")
    try:
        return AkademikDonem.objects.get(yil=f"{m.group(1)}-{m.group(2)}", donem=donem)
    except AkademikDonem.DoesNotExist:
        raise ValidationError(f"{deger} dönemi sistemde tanımlı değil.")


def _gecmis_donem(deger):
    from ogrenciler.models import AkademikDonem
    donem = _donem(deger)
    guncel = AkademikDonem.guncel()
    if guncel and donem.sira > guncel.sira:
        raise ValidationError(f"{donem} henüz başlamadı; gelecek dönem aktarılamaz.")
    return donem


def _program_donemi(program, deger):
    donem = _gecmis_donem(deger)
    if donem.sira < program.kabul_donemi.sira:
        raise ValidationError(f"{donem}, öğrencinin kabul döneminden ({program.kabul_donemi}) önce.")
    return donem


def _ogrenci(no):
    from ogrenciler.models import Ogrenci
    no = (no or "").strip()
    try:
        ogrenci = Ogrenci.objects.get(ogrenci_no=no)
    except Ogrenci.DoesNotExist:
        raise ValidationError(f"{no or '(boş)'} numaralı öğrenci sistemde yok. Önce öğrenci kayıtlarını aktarın.")
    program = ogrenci.guncel_program
    if program is None or program.durum not in program.ACIK_DURUMLAR:
        raise ValidationError(f"{no} öğrencisinin açık bir ÇAP/YDP kaydı yok.")
    return ogrenci, program


# --- Satır işleyiciler -----------------------------------------------------------

def _ogrenci_satiri(veri, yapan, islem):
    from ogrenciler.models import Bolum, ogrenci_no_dogrulayici
    from ogrenciler.servisler import ogrenci_ekle
    no = (veri["ogrenci_no"] or "").strip()
    ogrenci_no_dogrulayici(no)
    eposta = (veri["eposta"] or "").strip().lower()
    validate_email(eposta)
    bolum_metni = (veri["ana_dal"] or "").strip()
    bolum = Bolum.objects.filter(kod__iexact=bolum_metni).first() or \
        Bolum.objects.filter(ad__iexact=bolum_metni).first()
    if bolum is None:
        raise ValidationError(f"Ana dal bölümü tanınmadı: '{bolum_metni}' (bölüm kodu yazın, ör. EEM).")
    tur = _PROGRAM_ADLARI.get(okuyucu.sade(veri["program"]))
    if tur is None:
        raise ValidationError(f"Program ÇAP veya YDP olmalı: '{veri['program']}'.")
    kabul = _gecmis_donem(veri["kabul_donemi"])
    if kabul.donem == "YAZ":
        raise ValidationError("Kabul dönemi yaz okulu olamaz.")
    ogrenci, sifre = ogrenci_ekle(yapan=yapan, ogrenci_no=no, ad=_metin(veri["ad"], "Ad"),
                                  soyad=_metin(veri["soyad"], "Soyad"), eposta=eposta, ana_dal_bolumu=bolum,
                                  tur=tur, kabul_donemi=kabul, kaynak=Kaynak.AKTARIM)
    return f"{no} {ogrenci.ad_soyad} ({tur}, {kabul})", {"ogrenci_no": no, "ad_soyad": ogrenci.ad_soyad,
                                                          "sifre": sifre}


def _ders_listesi_kalemi(program, ders, yapan, islem):
    """Ders öğrencinin listesinde yoksa yönergeye uygun şekilde eklenir."""
    from dersler.models import Ders, OgrenciDersi
    from dersler.servisler import ders_ekle
    od = program.dersler.filter(ders=ders, liste_durumu=OgrenciDersi.ListeDurumu.AKTIF,
                                onay_durumu=OnayDurumu.ONAYLANDI).first()
    if od:
        return od, ""
    gerekce = f"Geçmiş veri aktarımı #{islem.pk}"
    if program.tur == "YDP":
        return ders_ekle(yapan=yapan, program=program, ders=ders, gerekce=gerekce, kaynak=Kaynak.AKTARIM), \
            " · yan dal listesine eklendi"
    if ders.tur == Ders.Tur.SECMELI:
        bos = list(program.dersler.filter(ders__isnull=True, liste_durumu=OgrenciDersi.ListeDurumu.AKTIF,
                                          onay_durumu=OnayDurumu.ONAYLANDI).order_by("sira", "id"))
        slot = next((s for s in bos if s.yariyil == ders.yariyil), None) or (bos[0] if bos else None)
        if slot is None:
            raise ValidationError(f"{ders.kod} seçmeli bir ders ama öğrencinin boş seçmeli slotu kalmadı.")
        return ders_ekle(yapan=yapan, program=program, ders=ders, slot=slot, gerekce=gerekce,
                         kaynak=Kaynak.AKTARIM), f" · {slot.slot_aciklama} slotuna yerleşti"
    raise ValidationError(f"{ders.kod} öğrencinin ÇAP ders listesinde (protokolde) yok.")


def _not_satiri(veri, yapan, islem):
    from dersler.models import Ders, DersDenemesi
    from dersler.servisler import deneme_ekle
    ogrenci, program = _ogrenci(veri["ogrenci_no"])
    kod = (veri["ders_kodu"] or "").strip()
    ders = Ders.objects.filter(kod=kod).first()
    if ders is None:
        raise ValidationError(f"{kod or '(boş)'} kodlu ders katalogda yok.")
    donem = _program_donemi(program, veri["donem"])
    harf = (veri.get("harf_notu") or "").strip().upper().replace("İ", "I")
    if harf and harf not in dict(DersDenemesi.HARF_NOTLARI):
        raise ValidationError(f"Geçersiz harf notu: '{harf}'.")
    od, ek = _ders_listesi_kalemi(program, ders, yapan, islem)
    deneme = deneme_ekle(yapan=yapan, ogrenci_dersi=od, donem=donem, harf_notu=harf, kaynak=Kaynak.AKTARIM)
    return f"{ogrenci.ogrenci_no} · {ders.kod} {ders.ad} · {donem} · " \
           f"{harf or 'devam ediyor'} ({deneme.get_durum_display()}){ek}", None


def _ana_dal_satiri(veri, yapan, islem):
    from kurallar.servisler import ana_dal_kaydi_ekle
    ogrenci, program = _ogrenci(veri["ogrenci_no"])
    donem = _gecmis_donem(veri["donem"])
    try:
        gano = Decimal((veri["gano"] or "").strip().replace(",", "."))
    except InvalidOperation:
        raise ValidationError(f"GANO sayı olmalı: '{veri['gano']}'.")
    if not (0 <= gano <= 4):
        raise ValidationError("GANO 0 ile 4 arasında olmalı.")
    durum = _ANA_DAL_DURUMLARI.get(okuyucu.sade(veri.get("ana_dal_durumu")))
    if durum is None:
        raise ValidationError(f"Ana dal durumu Aktif, Dondurulmuş veya Mezun olmalı: '{veri['ana_dal_durumu']}'.")
    kaynak = veri.get("kaynak") or ""
    kaynak = _metin(kaynak, "Kaynak", 150) if kaynak.strip() else f"CSV aktarımı #{islem.pk}"
    ana_dal_kaydi_ekle(yapan=yapan, program=program, donem=donem, gano=gano.quantize(Decimal("0.01")),
                       ana_dal_durumu=durum, kaynak_aciklama=kaynak)
    return f"{ogrenci.ogrenci_no} · {donem} · GANO {gano} · {durum.title()}", None


ISLEYICILER = {"OGRENCI": _ogrenci_satiri, "NOT": _not_satiri, "ANA_DAL": _ana_dal_satiri}


def _hata_metni(e):
    if isinstance(e, ValidationError):
        return " ".join(e.messages)
    return str(e) or e.__class__.__name__


def _satirlari_isle(islem, yapan, satirlar):
    """Her satır kendi kayıt noktasında (savepoint) işlenir; hatalı satır
    diğerlerini bozmaz. Döndürür: (sonuçlar, ek bilgiler)"""
    isleyici = ISLEYICILER[islem.tur]
    sonuclar, ekler = [], []
    for satir_no, veri in satirlar:
        try:
            with transaction.atomic():
                ozet, ek = isleyici(veri, yapan, islem)
            sonuclar.append({"satir": satir_no, "durum": "TAMAM", "mesaj": ozet})
            if ek:
                ekler.append(ek)
        except (ValidationError, ObjectDoesNotExist, ValueError, IntegrityError) as e:
            ozet = " · ".join(v for v in list(veri.values())[:3] if v)[:80]
            sonuclar.append({"satir": satir_no, "durum": "HATA", "mesaj": _hata_metni(e), "veri": ozet})
    return sonuclar, ekler


def _dosyayi_oku(islem):
    icerik = depo.oku(islem.dosya_yolu)
    if icerik is None or hashlib.sha256(icerik).hexdigest() != islem.sha256:
        raise ValidationError("Saklanan dosya değişmiş (özet tutmuyor); aktarım uygulanamaz.")
    return okuyucu.oku(icerik, islem.tur)["satirlar"]


def _onizle(islem, yapan, satirlar):
    """Satırları gerçek servislerle işler, sonra her şeyi geri alır."""
    from kurallar.motor import toplu_islem
    sonuc = {}
    try:
        with transaction.atomic(), toplu_islem("CSV önizleme", yapan, ayri=True):
            sonuc["satirlar"], _ = _satirlari_isle(islem, yapan, satirlar)
            raise _GeriAl
    except _GeriAl:
        pass
    return sonuc["satirlar"]


# --- Dış servisler -------------------------------------------------------------------

def yukle(*, yapan, dosya, tur, request=None):
    """Dosyayı doğrular, saklar ve önizlemesini çıkarır (veritabanına veri yazmaz)."""
    _koordinator_mu(yapan)
    if not dosya.name.lower().endswith(".csv"):
        raise ValidationError("Yalnızca .csv uzantılı dosya yüklenebilir.")
    if dosya.size > okuyucu.MAKS_BOYUT:
        raise ValidationError("Dosya çok büyük (en fazla 2 MB).")
    icerik = dosya.read(okuyucu.MAKS_BOYUT + 1)
    okunan = okuyucu.oku(icerik, tur)  # başlık/biçim hatasında burada durur, hiçbir şey saklanmaz
    ozet = hashlib.sha256(icerik).hexdigest()

    goreli = f"aktarim/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.csv"
    depo.kaydet(goreli, icerik)

    islem = AktarimIslemi.objects.create(
        tur=tur, dosya_adi=guvenli_ad(dosya.name), dosya_yolu=goreli, boyut=len(icerik), sha256=ozet,
        kodlama=okunan["kodlama"], ayirac={"\t": "TAB"}.get(okunan["ayirac"], okunan["ayirac"]),
        yukleyen=yapan, satir_sayisi=len(okunan["satirlar"]))
    sonuclar = _onizle(islem, yapan, okunan["satirlar"])
    if AktarimIslemi.objects.filter(sha256=ozet, tur=tur, durum=AktarimIslemi.Durum.UYGULANDI).exists():
        sonuclar.insert(0, {"satir": 1, "durum": "HATA", "mesaj": "Bu dosyanın aynısı daha önce uygulandı."})
    islem.onizleme = sonuclar
    islem.hata_sayisi = sum(1 for s in sonuclar if s["durum"] == "HATA")
    islem.save(update_fields=["onizleme", "hata_sayisi"])
    kaydet(request, "AKTARIM_YUKLENDI", nesne=islem, yapan=yapan,
           yeni={"tur": tur, "dosya": islem.dosya_adi, "sha256": ozet[:16], "satir": islem.satir_sayisi,
                 "hata": islem.hata_sayisi})
    return islem


def uygula(*, yapan, islem, request=None):
    """Önizlemesi hatasız olan aktarımı tek işlemde uygular.
    Döndürür: (islem, ekler) — ekler: öğrenci aktarımında bir kez gösterilecek geçici şifreler."""
    from kurallar.motor import toplu_islem
    _koordinator_mu(yapan)
    sonuclar = None
    try:
        with transaction.atomic():
            islem = AktarimIslemi.objects.select_for_update().get(pk=islem.pk)
            if not islem.uygulanabilir_mi:
                raise ValidationError("Bu aktarım uygulanamaz (hatalı satır var ya da zaten sonuçlandı).")
            if AktarimIslemi.objects.filter(sha256=islem.sha256, tur=islem.tur,
                                            durum=AktarimIslemi.Durum.UYGULANDI).exists():
                raise ValidationError("Bu dosyanın aynısı daha önce uygulandı.")
            with toplu_islem(f"CSV aktarımı #{islem.pk}", yapan):
                sonuclar, ekler = _satirlari_isle(islem, yapan, _dosyayi_oku(islem))
                if any(s["durum"] == "HATA" for s in sonuclar):
                    raise _GeriAl  # önizlemeden sonra veri değişmiş: hiçbir satır yazılmaz
            islem.durum, islem.uygulayan, islem.uygulama_zamani = \
                AktarimIslemi.Durum.UYGULANDI, yapan, timezone.now()
            islem.onizleme = sonuclar
            islem.save(update_fields=["durum", "uygulayan", "uygulama_zamani", "onizleme"])
            kaydet(request, "AKTARIM_UYGULANDI", nesne=islem, yapan=yapan,
                   yeni={"tur": islem.tur, "dosya": islem.dosya_adi, "satir": len(sonuclar)})
            return islem, ekler
    except _GeriAl:
        islem.refresh_from_db()
        islem.onizleme = sonuclar
        islem.hata_sayisi = sum(1 for s in sonuclar if s["durum"] == "HATA")
        islem.save(update_fields=["onizleme", "hata_sayisi"])
        raise ValidationError("Önizlemeden sonra veriler değişmiş; bazı satırlar artık hata veriyor. "
                              "Hiçbir satır yazılmadı. Hataları düzeltip dosyayı yeniden yükleyin.")


@transaction.atomic
def vazgec(*, yapan, islem, request=None):
    _koordinator_mu(yapan)
    islem = AktarimIslemi.objects.select_for_update().get(pk=islem.pk)
    if islem.durum != AktarimIslemi.Durum.ONIZLENDI:
        raise ValidationError("Bu aktarım zaten sonuçlanmış.")
    islem.durum = AktarimIslemi.Durum.VAZGECILDI
    islem.save(update_fields=["durum"])
    kaydet(request, "AKTARIM_VAZGECILDI", nesne=islem, yapan=yapan)
    return islem
