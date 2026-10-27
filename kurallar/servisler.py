"""Kural ayarları, ana dal bilgisi, uyarılar ve kurul kararları servisleri.

Tüm yazma işlemleri buradan geçer: önce yetki denetlenir, sonra değişiklik
yapılır, işlem kaydı yazılır ve gerekiyorsa kurallar yeniden değerlendirilir.
"""
import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Kullanici
from denetim.kayit import kaydet
from ortak.modeller import Kaynak, OnayDurumu

from . import motor
from .models import KuralParametresi, KuralSurumu, Uyari
from .tanimlar import ILK_SURUM, PARAMETRELER, dogrula

KOORD = Kullanici.Rol.KOORDINATOR


def _koordinator_mu(yapan):
    if yapan is None or yapan.rol != KOORD:
        raise PermissionDenied("Bu işlem yalnızca koordinatör tarafından yapılabilir.")


def _acik_programlar(program_turu):
    from ogrenciler.models import ProgramKaydi
    return ProgramKaydi.objects.filter(tur=program_turu, durum__in=ProgramKaydi.ACIK_DURUMLAR)


# --- Kural sürümleri --------------------------------------------------------------

def _surum_olustur(*, yapan, program_turu, ad, dayanak, yururluk_baslangic, degerler):
    surum = KuralSurumu.objects.create(program_turu=program_turu, ad=ad, dayanak=dayanak,
                                       yururluk_baslangic=yururluk_baslangic, olusturan=yapan)
    for anahtar, *_ in PARAMETRELER:
        KuralParametresi.objects.create(surum=surum, anahtar=anahtar, deger=(degerler.get(anahtar) or "").strip())
    return surum


@transaction.atomic
def yeni_surum(*, yapan, program_turu, ad, dayanak, yururluk_baslangic, degerler, request=None):
    """Yönerge değişince yeni kural sürümü açar. Eski sürüm silinmez; geçerliliği
    yeni sürümün başlangıcından bir gün önce kapanır. Geçmiş değerlendirmeler
    kendi sürümleriyle kalır."""
    _koordinator_mu(yapan)
    if program_turu not in ("CAP", "YDP"):
        raise ValidationError("Geçersiz program türü.")
    if not (ad or "").strip() or not (dayanak or "").strip():
        raise ValidationError("Sürüm adı ve dayanak (yönerge / senato kararı) zorunludur.")
    hatalar = []
    for anahtar, etiket, *_ in PARAMETRELER:
        hata = dogrula(anahtar, degerler.get(anahtar))
        if hata:
            hatalar.append(f"{etiket}: {hata}")
    if hatalar:
        raise ValidationError(hatalar)

    onceki = KuralSurumu.gecerli(program_turu, yururluk_baslangic)
    sonraki_var = KuralSurumu.objects.filter(program_turu=program_turu,
                                             yururluk_baslangic__gte=yururluk_baslangic).exists()
    if sonraki_var:
        raise ValidationError("Bu tarihte veya sonrasında başlayan bir sürüm zaten var. "
                              "Yeni sürüm en son sürümden sonra başlamalıdır.")
    if onceki:
        onceki = KuralSurumu.objects.select_for_update().get(pk=onceki.pk)
        onceki.kapat(yururluk_baslangic - datetime.timedelta(days=1))

    surum = _surum_olustur(yapan=yapan, program_turu=program_turu, ad=ad.strip(), dayanak=dayanak.strip(),
                           yururluk_baslangic=yururluk_baslangic, degerler=degerler)
    kaydet(request, "KURAL_SURUMU_OLUSTURULDU", nesne=surum, yapan=yapan,
           eski=onceki.degerler() if onceki else None, yeni=surum.degerler(),
           aciklama=f"{surum.dayanak}. Önceki sürüm: {onceki.ad if onceki else '—'}")

    # Bugün yürürlükteyse açık programlar yeni sürümle yeniden değerlendirilir
    if yururluk_baslangic <= timezone.localdate():
        for program in _acik_programlar(program_turu):
            motor.degerlendir(program, "Yeni kural sürümü", yapan)
    return surum


def ilk_surumleri_olustur(yapan=None):
    """Başlangıç verisi: yürürlükteki yönergelerin ilk kural sürümleri.
    Tekrar çalıştırılırsa yeni sürüm açmaz."""
    olusan = []
    for tur, (ad, tarih) in ILK_SURUM.items():
        if KuralSurumu.objects.filter(program_turu=tur).exists():
            continue
        sutun = 3 if tur == "CAP" else 4
        degerler = {p[0]: p[sutun] for p in PARAMETRELER}
        surum = _surum_olustur(yapan=yapan, program_turu=tur, ad=ad, dayanak=ad,
                               yururluk_baslangic=datetime.date.fromisoformat(tarih), degerler=degerler)
        kaydet(None, "KURAL_SURUMU_OLUSTURULDU", nesne=surum, yapan=yapan, yeni=surum.degerler(),
               aciklama="İlk kurulum")
        olusan.append(surum)
    return olusan


# --- Değerlendirme ve uyarılar ----------------------------------------------------

@transaction.atomic
def simdi_degerlendir(*, yapan, program, request=None):
    _koordinator_mu(yapan)
    kayit = motor.degerlendir(program, "Koordinatör isteği", yapan)
    if kayit is None:
        raise ValidationError("Program sonuçlanmış veya bu program türü için yürürlükte kural sürümü yok.")
    return kayit


@transaction.atomic
def uyari_kapat(*, yapan, uyari, durum, notu="", request=None):
    """Koordinatör uyarıyı 'görüldü' veya 'karara bağlandı' olarak işaretler."""
    _koordinator_mu(yapan)
    uyari = Uyari.objects.select_for_update().get(pk=uyari.pk)
    if durum not in (Uyari.Durum.GORULDU, Uyari.Durum.KARARA_BAGLANDI):
        raise ValidationError("Geçersiz durum.")
    if uyari.durum not in (Uyari.Durum.ACIK, Uyari.Durum.GORULDU) or uyari.durum == durum:
        raise ValidationError("Bu uyarının durumu değiştirilemez.")
    if durum == Uyari.Durum.KARARA_BAGLANDI and not (notu or "").strip():
        raise ValidationError("Karara bağlarken karar bilgisini (kurul, tarih, sayı) not olarak yazın.")
    eski = uyari.durum
    uyari.durum, uyari.kapatan, uyari.kapatma_zamani = durum, yapan, timezone.now()
    uyari.kapatma_notu = (notu or "").strip()
    uyari.save(update_fields=["durum", "kapatan", "kapatma_zamani", "kapatma_notu"])
    kaydet(request, "UYARI_DURUMU_DEGISTI", nesne=uyari, yapan=yapan,
           ogrenci_no=uyari.program_kaydi.ogrenci.ogrenci_no,
           eski={"durum": eski}, yeni={"durum": durum, "mesaj": uyari.mesaj}, aciklama=uyari.kapatma_notu)
    return uyari


# --- Ana dal bilgisi ----------------------------------------------------------------

@transaction.atomic
def ana_dal_kaydi_ekle(*, yapan, program, donem, gano, ana_dal_durumu, kaynak_aciklama, request=None):
    """Ana dal GANO'su ve durumu. Sistem ana dal derslerini izlemez; bilgiyi
    koordinatör kaynağıyla (öğrenci işleri yazısı, transkript) girer. Düzeltme
    gerekirse yeni kayıt girilir, eskisi geçmişte kalır."""
    from ogrenciler.models import AnaDalKaydi
    _koordinator_mu(yapan)
    if not (kaynak_aciklama or "").strip():
        raise ValidationError("Bilginin kaynağını yazın (ör. ana dal transkripti).")
    if program.durum not in ("AKTIF", "DONDURULDU"):
        raise ValidationError("Sonuçlanmış programa ana dal bilgisi girilemez.")
    kayit = AnaDalKaydi(program_kaydi=program, donem=donem, gano=gano, ana_dal_durumu=ana_dal_durumu,
                        kaynak_aciklama=kaynak_aciklama.strip(), giren=yapan)
    kayit.full_clean()
    kayit.save()
    kaydet(request, "ANA_DAL_BILGISI_GIRILDI", nesne=kayit, yapan=yapan, ogrenci_no=program.ogrenci.ogrenci_no,
           yeni={"donem": str(donem), "gano": str(gano), "durum": ana_dal_durumu}, aciklama=kayit.kaynak_aciklama)
    motor.guvenli_degerlendir(program, "Ana dal bilgisi girildi", yapan)
    return kayit


# --- Kurul kararları ------------------------------------------------------------------

SONUC_DURUMU = {"MEZUNIYET": "MEZUN", "SERTIFIKA": "SERTIFIKA", "KAYIT_SILME": "SILINDI", "AYRILMA": "AYRILDI"}


@transaction.atomic
def karar_isle(*, yapan, program, tur, kurul, karar_tarihi, karar_sayisi, gerekce, dayanak_belge,
               donem=None, request=None):
    """Kurulun verdiği kararı sisteme işler. Sistem karar vermez; koordinatör
    karar yazısını (yüklenmiş ve onaylı kurul kararı belgesi) dayanak gösterir."""
    from belgeler.models import BelgeTuru
    from ogrenciler.models import DonemKaydi, Karar, ProgramKaydi
    _koordinator_mu(yapan)
    program = ProgramKaydi.objects.select_for_update().get(pk=program.pk)
    if tur not in Karar.Tur.values:
        raise ValidationError("Geçersiz karar türü.")
    if program.durum not in ProgramKaydi.ACIK_DURUMLAR:
        raise ValidationError("Bu program kaydı sonuçlanmış; yeni karar işlenemez.")
    if not all((s or "").strip() for s in (kurul, karar_sayisi, gerekce)) or not karar_tarihi:
        raise ValidationError("Kurul, karar tarihi, karar sayısı ve gerekçe zorunludur.")
    if karar_tarihi > timezone.localdate():
        raise ValidationError("Karar tarihi ileri bir tarih olamaz.")
    if dayanak_belge is None or dayanak_belge.ogrenci_id != program.ogrenci_id \
            or dayanak_belge.tur != BelgeTuru.KURUL_KARARI or dayanak_belge.onay_durumu != OnayDurumu.ONAYLANDI:
        raise ValidationError("Dayanak olarak bu öğrenciye ait, onaylı bir 'Kurul kararı' belgesi seçilmelidir.")
    if tur == Karar.Tur.SERTIFIKA and program.tur != "YDP":
        raise ValidationError("Sertifika kararı yalnızca yan dal programı için işlenir.")
    if tur == Karar.Tur.MEZUNIYET and program.tur != "CAP":
        raise ValidationError("Mezuniyet (diploma) kararı yalnızca ÇAP için işlenir.")
    if tur == Karar.Tur.DONDURMA and donem is None:
        raise ValidationError("Kayıt dondurma kararı için dönem seçilmelidir.")

    eski_durum = program.durum
    karar = Karar.objects.create(program_kaydi=program, tur=tur, kurul=kurul.strip(), karar_tarihi=karar_tarihi,
                                 karar_sayisi=karar_sayisi.strip(), gerekce=gerekce.strip(),
                                 dayanak_belge=dayanak_belge, isleyen=yapan)
    simdi = timezone.now()
    if tur == Karar.Tur.DONDURMA:
        dk, yeni = DonemKaydi.objects.select_for_update().get_or_create(
            program_kaydi=program, donem=donem,
            defaults=dict(kayit_durumu=DonemKaydi.KayitDurumu.DONDURULDU, onay_durumu=OnayDurumu.ONAYLANDI,
                          kaynak=Kaynak.KOORDINATOR, olusturan=yapan, onaylayan=yapan, onay_zamani=simdi,
                          gerekce=f"{karar.kurul} {karar.karar_tarihi:%d.%m.%Y} / {karar.karar_sayisi}"))
        if not yeni:
            dk.kayit_durumu, dk.onay_durumu = DonemKaydi.KayitDurumu.DONDURULDU, OnayDurumu.ONAYLANDI
            dk.onaylayan, dk.onay_zamani = yapan, simdi
            dk.gerekce = f"{karar.kurul} {karar.karar_tarihi:%d.%m.%Y} / {karar.karar_sayisi}"
            dk.save()
    elif tur in SONUC_DURUMU:
        program.durum = SONUC_DURUMU[tur]
        program.save(update_fields=["durum"])

    kaydet(request, "KARAR_ISLENDI", nesne=karar, yapan=yapan, ogrenci_no=program.ogrenci.ogrenci_no,
           eski={"program_durumu": eski_durum},
           yeni={"tur": tur, "kurul": karar.kurul, "tarih": str(karar_tarihi), "sayi": karar.karar_sayisi,
                 "program_durumu": program.durum, "donem": str(donem) if donem else None},
           aciklama=karar.gerekce)

    if program.durum in ProgramKaydi.ACIK_DURUMLAR:
        motor.degerlendir(program, f"Karar işlendi: {karar.get_tur_display()}", yapan)
    else:
        # Program sonuçlandı: açık uyarılar bu kararla kapanır
        for u in program.uyarilar.filter(durum__in=[Uyari.Durum.ACIK, Uyari.Durum.GORULDU]):
            u.durum, u.kapatan, u.kapatma_zamani = Uyari.Durum.KARARA_BAGLANDI, yapan, simdi
            u.kapatma_notu = f"{karar.get_tur_display()}: {karar.kurul} {karar.karar_tarihi:%d.%m.%Y} / " \
                             f"{karar.karar_sayisi}"
            u.save(update_fields=["durum", "kapatan", "kapatma_zamani", "kapatma_notu"])
    return karar
