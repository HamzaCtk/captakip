"""Ders takibi ve onay servisleri.

Kurallar (koordinatörün proje e-postası, "ONAY MANTIĞI"):
- Öğrencinin girdiği ders, deneme ve not BEKLİYOR durumunda başlar.
- Koordinatör onaylayana kadar kesinleşmez ve hesaplara girmez.
- Onaylanan kayıt kilitlenir; öğrenci değiştiremez.
- Hatayı yalnızca koordinatör gerekçeyle düzeltir; düzeltme kaydedilir.
- Reddedilen veya iptal edilen kayıt silinmez, o durumuyla kalır.

Her fonksiyon önce yetkiyi denetler (ekranda bir kontrol unutulsa bile
servis izin vermez), sonra değişikliği yapar ve işlem kaydı yazar.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Kullanici
from denetim.kayit import kaydet
from mesajlar.bildirim import ogrenciye_bildir
from ortak.modeller import Kaynak, OnayDurumu

from .models import Ders, DersDenemesi, NotGirisi, OgrenciDersi

KOORD = Kullanici.Rol.KOORDINATOR
OGR = Kullanici.Rol.OGRENCI


# --- Yardımcılar ---------------------------------------------------------------

def _ogrenci_no(kayit):
    if isinstance(kayit, OgrenciDersi):
        return kayit.program_kaydi.ogrenci.ogrenci_no
    if isinstance(kayit, DersDenemesi):
        return kayit.ogrenci_dersi.program_kaydi.ogrenci.ogrenci_no
    if isinstance(kayit, NotGirisi):
        return kayit.deneme.ogrenci_dersi.program_kaydi.ogrenci.ogrenci_no
    raise TypeError(kayit)


def _program(kayit):
    if isinstance(kayit, OgrenciDersi):
        return kayit.program_kaydi
    if isinstance(kayit, DersDenemesi):
        return kayit.ogrenci_dersi.program_kaydi
    return kayit.deneme.ogrenci_dersi.program_kaydi


def _ozet(kayit):
    """İşlem kaydına yazılacak okunabilir değerler."""
    if isinstance(kayit, OgrenciDersi):
        return {"ders": kayit.ders.kod if kayit.ders else kayit.slot_aciklama, "akts": kayit.akts,
                "liste_durumu": kayit.liste_durumu, "onay": kayit.onay_durumu}
    if isinstance(kayit, DersDenemesi):
        return {"ders": str(kayit.ogrenci_dersi.gorunen_ad), "donem": str(kayit.donem),
                "durum": kayit.durum, "harf_notu": kayit.harf_notu, "onay": kayit.onay_durumu}
    return {"deneme": str(kayit.deneme), "harf_notu": kayit.harf_notu, "onay": kayit.onay_durumu}


def _kayit_adi(kayit):
    """Bildirimde gösterilecek kısa ad."""
    if isinstance(kayit, OgrenciDersi):
        return f"Ders listesi: {kayit.gorunen_ad}"
    if isinstance(kayit, DersDenemesi):
        return f"{kayit.ogrenci_dersi.gorunen_ad} ({kayit.donem}) dönem kaydı"
    return f"{kayit.deneme.ogrenci_dersi.gorunen_ad} ({kayit.deneme.donem}) notu {kayit.harf_notu}"


def _bildir(kayit, tur, olay, gerekce=""):
    """Kaydın sahibi öğrenciye onay, red, iptal veya düzeltme bildirimi."""
    metin = f"{_kayit_adi(kayit)} {olay}." + (f" Gerekçe: {gerekce.strip()}" if gerekce else "")
    ogrenciye_bildir(_program(kayit).ogrenci, tur, metin)


def _koordinator_mu(yapan):
    if yapan.rol != KOORD:
        raise PermissionDenied("Bu işlem yalnızca koordinatör tarafından yapılabilir.")


def _ogrencinin_kendi_programi(yapan, program):
    """Öğrenci yalnızca kendi açık program kaydı üzerinde işlem yapabilir."""
    if yapan.rol != OGR or getattr(yapan, "ogrenci", None) != program.ogrenci:
        raise PermissionDenied("Yalnızca kendi kaydınız üzerinde işlem yapabilirsiniz.")
    if program.durum != program.Durum.AKTIF:
        raise ValidationError("Program kaydınız aktif değil; yeni kayıt giremezsiniz.")


def _baslangic_durumu(yapan, kaynak):
    """Öğrencinin girdiği kayıt BEKLİYOR, koordinatörünki doğrudan ONAYLI başlar."""
    if yapan.rol == KOORD:
        return dict(onay_durumu=OnayDurumu.ONAYLANDI, onaylayan=yapan, onay_zamani=timezone.now(),
                    kaynak=kaynak or Kaynak.KOORDINATOR, olusturan=yapan)
    return dict(onay_durumu=OnayDurumu.BEKLIYOR, kaynak=Kaynak.OGRENCI, olusturan=yapan)


def gecer_notlar(program_turu=None):
    """Geçer harf notları yürürlükteki kural sürümünden okunur; sürüm yoksa ayarlardaki liste."""
    if program_turu:
        from kurallar.models import KuralSurumu
        surum = KuralSurumu.gecerli(program_turu)
        if surum:
            liste = surum.degerler().get("gecer_harf_notlari")
            if liste:
                return liste
    return settings.GECER_HARF_NOTLARI


def sonuc_hesapla(harf_notu, program_turu=None):
    return DersDenemesi.Durum.GECTI if harf_notu in gecer_notlar(program_turu) else DersDenemesi.Durum.KALDI


def _kurallari_calistir(program, neden, yapan):
    """Onaylı veri değişince kural motoru yeniden çalışır (uyarılar güncellenir)."""
    from kurallar.motor import guvenli_degerlendir
    guvenli_degerlendir(program, neden, yapan)


# --- Ders listesine ekleme -----------------------------------------------------

@transaction.atomic
def ders_ekle(*, yapan, program, ders, slot=None, gerekce="", kaynak=None, request=None):
    """Ders listesine katalogdan ders ekler.

    - ÇAP öğrencisi yalnızca seçmeli slotunu doldurabilir (ÇAP Md. 7/2).
    - YDP öğrencisi ilan edilen havuzdan (katalog) ders seçer (YDP Md. 5/g).
    - Koordinatör gerekçeyle her iki türde ders ekleyebilir.
    Serbest metinle ders girilemez; ders katalogdaki aktif bir ders olmalıdır.
    """
    if yapan.rol == OGR:
        _ogrencinin_kendi_programi(yapan, program)
        if program.tur == "CAP" and slot is None:
            raise ValidationError("ÇAP'ta ders listesi protokolle belirlenir; yalnızca seçmeli slotlarını doldurabilirsiniz.")
    else:
        _koordinator_mu(yapan)
        if not gerekce.strip():
            raise ValidationError("Koordinatörün ders listesi değişikliği için gerekçe zorunludur.")

    if not isinstance(ders, Ders) or not ders.aktif:
        raise ValidationError("Ders katalogda bulunamadı veya pasif durumda.")
    if program.dersler.filter(ders=ders).exclude(onay_durumu__in=[OnayDurumu.REDDEDILDI, OnayDurumu.IPTAL]) \
            .exclude(liste_durumu=OgrenciDersi.ListeDurumu.CIKARILDI).exists():
        raise ValidationError(f"{ders.kod} zaten ders listenizde.")

    if slot is not None:
        slot = OgrenciDersi.objects.select_for_update().get(pk=slot.pk)
        if slot.program_kaydi_id != program.id or slot.ders_id is not None or \
                slot.liste_durumu != OgrenciDersi.ListeDurumu.AKTIF or not slot.onayli_mi:
            raise ValidationError("Geçersiz seçmeli slotu.")
        if ders.tur != Ders.Tur.SECMELI:
            raise ValidationError("Seçmeli slotu yalnızca seçmeli bir dersle doldurulabilir.")
        if slot.dolduranlar.filter(onay_durumu=OnayDurumu.BEKLIYOR).exists():
            raise ValidationError("Bu slot için onay bekleyen bir seçiminiz var.")

    od = OgrenciDersi.objects.create(
        program_kaydi=program, ders=ders, yariyil=slot.yariyil if slot else ders.yariyil,
        slot_aciklama=slot.slot_aciklama if slot else "",
        akts=slot.akts if slot else ders.akts, sira=slot.sira if slot else 900,
        protokol_kalemi=slot.protokol_kalemi if slot else None, doldurdugu_slot=slot,
        gerekce=gerekce, **_baslangic_durumu(yapan, kaynak))
    if od.onayli_mi and slot:
        _slotu_kapat(slot, od, yapan)
    kaydet(request, "DERS_LISTEYE_EKLENDI", nesne=od, yapan=yapan, ogrenci_no=program.ogrenci.ogrenci_no,
           yeni=_ozet(od), aciklama=gerekce)
    if od.onayli_mi:
        _kurallari_calistir(program, "Ders listesine ders eklendi", yapan)
    return od


def _slotu_kapat(slot, dolduran, yapan):
    slot.liste_durumu = OgrenciDersi.ListeDurumu.CIKARILDI
    slot.gerekce = f"Seçmeli slotu {dolduran.ders.kod} ile dolduruldu."
    slot.save(update_fields=["liste_durumu", "gerekce"])


# --- Dönem dersi (deneme) ve not girişi -----------------------------------------

@transaction.atomic
def deneme_ekle(*, yapan, ogrenci_dersi, donem, durum=None, harf_notu="", kaynak=None, request=None):
    """Öğrenci o dönem aldığı dersi girer (ALINDI, onay bekler).
    Koordinatör geçmiş dönem dersini notuyla birlikte doğrudan girebilir."""
    ogrenci_dersi = OgrenciDersi.objects.select_for_update().get(pk=ogrenci_dersi.pk)
    program = ogrenci_dersi.program_kaydi
    if yapan.rol == OGR:
        _ogrencinin_kendi_programi(yapan, program)
        durum, harf_notu = DersDenemesi.Durum.ALINDI, ""
    else:
        _koordinator_mu(yapan)
        if harf_notu:
            durum = sonuc_hesapla(harf_notu, program.tur)
        durum = durum or DersDenemesi.Durum.ALINDI

    if not ogrenci_dersi.onayli_mi or ogrenci_dersi.liste_durumu != OgrenciDersi.ListeDurumu.AKTIF:
        raise ValidationError("Yalnızca ders listenizde onaylı ve aktif olan dersler için dönem kaydı girilebilir.")
    if ogrenci_dersi.ders_id is None:
        raise ValidationError("Önce seçmeli slotu için bir ders seçilmelidir.")
    gecerli = ogrenci_dersi.denemeler.exclude(onay_durumu__in=[OnayDurumu.REDDEDILDI, OnayDurumu.IPTAL])
    if gecerli.filter(durum=DersDenemesi.Durum.GECTI, onay_durumu=OnayDurumu.ONAYLANDI).exists():
        raise ValidationError("Bu dersi zaten geçtiniz.")
    if gecerli.filter(donem=donem).exists():
        raise ValidationError(f"Bu ders için {donem} döneminde zaten bir kayıt var.")

    deneme = DersDenemesi.objects.create(ogrenci_dersi=ogrenci_dersi, donem=donem, durum=durum,
                                         harf_notu=harf_notu, **_baslangic_durumu(yapan, kaynak))
    kaydet(request, "DERS_DENEMESI_EKLENDI", nesne=deneme, yapan=yapan,
           ogrenci_no=program.ogrenci.ogrenci_no, yeni=_ozet(deneme),
           aciklama="İlk kurulum aktarımı" if kaynak == Kaynak.AKTARIM else "")
    if deneme.onayli_mi:
        _kurallari_calistir(program, "Dönem ders kaydı girildi", yapan)
    return deneme


@transaction.atomic
def not_gir(*, yapan, deneme, harf_notu, request=None):
    """Öğrenci dönem sonu notunu girer; koordinatör onaylayınca işlenir."""
    deneme = DersDenemesi.objects.select_for_update().get(pk=deneme.pk)  # güncel hâli
    _ogrencinin_kendi_programi(yapan, deneme.ogrenci_dersi.program_kaydi)
    if harf_notu not in dict(DersDenemesi.HARF_NOTLARI):
        raise ValidationError("Geçersiz harf notu.")
    if not deneme.not_girilebilir_mi:
        raise ValidationError("Bu ders için şu anda not girilemez.")
    from belgeler.servisler import transkript_yuklendi_mi
    if not transkript_yuklendi_mi(deneme.ogrenci_dersi.program_kaydi.ogrenci, deneme.donem):
        raise ValidationError(f"Notunuzu göndermeden önce {deneme.donem} dönemine ait ÇAP/YDP not belgesini "
                              "(transkript) Belgeler sayfasından yüklemelisiniz.")
    giris = NotGirisi.objects.create(deneme=deneme, harf_notu=harf_notu, **_baslangic_durumu(yapan, None))
    kaydet(request, "NOT_GIRILDI", nesne=giris, yapan=yapan, ogrenci_no=_ogrenci_no(deneme), yeni=_ozet(giris))
    return giris


# --- Onay, red, geri çekme, iptal ---------------------------------------------

@transaction.atomic
def onayla(*, yapan, kayit, request=None):
    _koordinator_mu(yapan)
    kayit = type(kayit).objects.select_for_update().get(pk=kayit.pk)
    if kayit.onay_durumu != OnayDurumu.BEKLIYOR:
        raise ValidationError("Yalnızca onay bekleyen kayıtlar onaylanabilir.")
    eski = _ozet(kayit)
    kayit.onay_durumu = OnayDurumu.ONAYLANDI
    kayit.onaylayan, kayit.onay_zamani = yapan, timezone.now()
    kayit.save()

    # Onayın yan etkileri
    if isinstance(kayit, OgrenciDersi) and kayit.doldurdugu_slot_id:
        _slotu_kapat(kayit.doldurdugu_slot, kayit, yapan)
    if isinstance(kayit, NotGirisi):
        deneme = kayit.deneme
        deneme.harf_notu = kayit.harf_notu
        deneme.durum = sonuc_hesapla(kayit.harf_notu, _program(kayit).tur)
        deneme.save(update_fields=["harf_notu", "durum"])

    kaydet(request, "KAYIT_ONAYLANDI", nesne=kayit, yapan=yapan, ogrenci_no=_ogrenci_no(kayit),
           eski=eski, yeni=_ozet(kayit))
    _bildir(kayit, "ONAY", "onaylandı")
    _kurallari_calistir(_program(kayit), "Kayıt onaylandı", yapan)
    return kayit


@transaction.atomic
def reddet(*, yapan, kayit, gerekce, request=None):
    _koordinator_mu(yapan)
    if not (gerekce or "").strip():
        raise ValidationError("Reddetmek için gerekçe yazmalısınız.")
    kayit = type(kayit).objects.select_for_update().get(pk=kayit.pk)
    if kayit.onay_durumu != OnayDurumu.BEKLIYOR:
        raise ValidationError("Yalnızca onay bekleyen kayıtlar reddedilebilir.")
    eski = _ozet(kayit)
    kayit.onay_durumu, kayit.gerekce = OnayDurumu.REDDEDILDI, gerekce.strip()
    kayit.onaylayan, kayit.onay_zamani = yapan, timezone.now()
    kayit.save()
    kaydet(request, "KAYIT_REDDEDILDI", nesne=kayit, yapan=yapan, ogrenci_no=_ogrenci_no(kayit),
           eski=eski, yeni=_ozet(kayit), aciklama=gerekce)
    _bildir(kayit, "RED", "reddedildi", gerekce)
    return kayit


@transaction.atomic
def geri_cek(*, yapan, kayit, request=None):
    """Öğrenci, henüz onaylanmamış kendi kaydını geri çeker (silinmez, iptal olur)."""
    kayit = type(kayit).objects.select_for_update().get(pk=kayit.pk)
    _ogrencinin_kendi_programi(yapan, _program(kayit))
    if kayit.olusturan_id != yapan.id or kayit.onay_durumu != OnayDurumu.BEKLIYOR:
        raise PermissionDenied("Yalnızca onay bekleyen kendi kayıtlarınızı geri çekebilirsiniz.")
    eski = _ozet(kayit)
    kayit.onay_durumu, kayit.gerekce = OnayDurumu.IPTAL, "Öğrenci tarafından geri çekildi."
    kayit.save()
    kaydet(request, "KAYIT_GERI_CEKILDI", nesne=kayit, yapan=yapan, ogrenci_no=_ogrenci_no(kayit),
           eski=eski, yeni=_ozet(kayit))
    return kayit


@transaction.atomic
def iptal_et(*, yapan, kayit, gerekce, request=None):
    """Koordinatör, şartlara uymayan veya hatalı bir kaydı gerekçesiyle iptal eder."""
    _koordinator_mu(yapan)
    if not (gerekce or "").strip():
        raise ValidationError("İptal için gerekçe yazmalısınız.")
    kayit = type(kayit).objects.select_for_update().get(pk=kayit.pk)
    if kayit.onay_durumu == OnayDurumu.IPTAL:
        raise ValidationError("Kayıt zaten iptal edilmiş.")
    eski = _ozet(kayit)
    kayit.onay_durumu, kayit.gerekce = OnayDurumu.IPTAL, gerekce.strip()
    kayit.save()
    kaydet(request, "KAYIT_IPTAL_EDILDI", nesne=kayit, yapan=yapan, ogrenci_no=_ogrenci_no(kayit),
           eski=eski, yeni=_ozet(kayit), aciklama=gerekce)
    _bildir(kayit, "IPTAL", "iptal edildi", gerekce)
    if eski["onay"] == OnayDurumu.ONAYLANDI:
        _kurallari_calistir(_program(kayit), "Onaylı kayıt iptal edildi", yapan)
    return kayit


# --- Koordinatör düzeltmeleri ---------------------------------------------------

@transaction.atomic
def deneme_duzelt(*, yapan, deneme, donem, harf_notu, gerekce, request=None):
    """Onaylı bir denemedeki hatayı koordinatör düzeltir. Eski değer işlem
    kaydında kalır."""
    _koordinator_mu(yapan)
    if not (gerekce or "").strip():
        raise ValidationError("Düzeltme için gerekçe yazmalısınız.")
    deneme = DersDenemesi.objects.select_for_update().get(pk=deneme.pk)
    if deneme.onay_durumu != OnayDurumu.ONAYLANDI:
        raise ValidationError("Yalnızca onaylı kayıtlar düzeltilir; bekleyen kaydı onaylayın veya reddedin.")
    eski = _ozet(deneme)
    deneme.donem = donem
    deneme.harf_notu = harf_notu or ""
    deneme.durum = sonuc_hesapla(harf_notu, _program(deneme).tur) if harf_notu else DersDenemesi.Durum.ALINDI
    deneme.save()
    kaydet(request, "KAYIT_DUZELTILDI", nesne=deneme, yapan=yapan, ogrenci_no=_ogrenci_no(deneme),
           eski=eski, yeni=_ozet(deneme), aciklama=gerekce)
    _bildir(deneme, "DUZELTME", "koordinatör tarafından düzeltildi", gerekce)
    _kurallari_calistir(_program(deneme), "Kayıt düzeltildi", yapan)
    return deneme


@transaction.atomic
def liste_durumu_degistir(*, yapan, ogrenci_dersi, yeni_durum, gerekce, request=None):
    """Dersi listeden çıkarır, muaf sayar ya da listeye geri alır.
    Geçilmiş dersler ve notlar bundan etkilenmez."""
    _koordinator_mu(yapan)
    if not (gerekce or "").strip():
        raise ValidationError("Ders listesi değişikliği için gerekçe yazmalısınız.")
    if yeni_durum not in OgrenciDersi.ListeDurumu.values:
        raise ValidationError("Geçersiz durum.")
    od = OgrenciDersi.objects.select_for_update().get(pk=ogrenci_dersi.pk)
    if not od.onayli_mi:
        raise ValidationError("Yalnızca onaylı ders listesi kalemleri değiştirilebilir.")
    if yeni_durum == OgrenciDersi.ListeDurumu.CIKARILDI and od.tamamlandi_mi:
        raise ValidationError("Geçilmiş bir ders listeden çıkarılamaz.")
    eski = _ozet(od)
    od.liste_durumu, od.gerekce = yeni_durum, gerekce.strip()
    od.save(update_fields=["liste_durumu", "gerekce"])
    kaydet(request, "DERS_LISTESI_DEGISTI", nesne=od, yapan=yapan, ogrenci_no=_ogrenci_no(od),
           eski=eski, yeni=_ozet(od), aciklama=gerekce)
    _bildir(od, "DUZELTME", f"durumu değişti: {od.get_liste_durumu_display()}", gerekce)
    _kurallari_calistir(od.program_kaydi, "Ders listesi değişti", yapan)
    return od


# --- Onay kuyruğu ---------------------------------------------------------------

def bekleyenler(program=None):
    """Onay bekleyen tüm kayıtlar (koordinatör kuyruğu)."""
    od = OgrenciDersi.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).select_related(
        "ders", "program_kaydi__ogrenci")
    dn = DersDenemesi.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).select_related(
        "donem", "ogrenci_dersi__ders", "ogrenci_dersi__program_kaydi__ogrenci")
    ng = NotGirisi.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).select_related(
        "deneme__donem", "deneme__ogrenci_dersi__ders", "deneme__ogrenci_dersi__program_kaydi__ogrenci")
    if program is not None:
        od = od.filter(program_kaydi=program)
        dn = dn.filter(ogrenci_dersi__program_kaydi=program)
        ng = ng.filter(deneme__ogrenci_dersi__program_kaydi=program)
    return {"dersler": list(od), "denemeler": list(dn), "notlar": list(ng)}
