"""Belge servisleri: yükleme, onay/red, ek belge istekleri, transkript kontrolü.

Kurallar (koordinatörün proje e-postası, "BELGE YÖNETİMİ"):
- Öğrenci yalnızca kendi kartına yükler ve yalnızca kendi belgelerini görür.
- Koordinatör her türlü belgeyi yükleyebilir.
- Dönem sonunda ÇAP/YDP transkripti yüklenmeden notlar onaya gönderilemez.
- Reddedilen veya yenilenen belgenin eski sürümü silinmez. Öğrenci belge silemez.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Kullanici
from django.urls import reverse

from denetim.kayit import kaydet
from ortak import depo
from mesajlar.bildirim import ogrenciye_bildir
from ortak.modeller import Kaynak, OnayDurumu

from .dogrulama import dogrula, guvenli_ad
from .models import DONEMLI_TURLER, Belge, BelgeIstegi, BelgeTuru

KOORD = Kullanici.Rol.KOORDINATOR
OGR = Kullanici.Rol.OGRENCI


def _ozet(b):
    return {"tur": b.tur, "donem": str(b.donem) if b.donem_id else None, "dosya": b.orijinal_ad,
            "sha256": b.sha256[:16], "onay": b.onay_durumu}


def _yetki(yapan, ogrenci):
    if yapan.rol == KOORD:
        return
    if yapan.rol == OGR and getattr(yapan, "ogrenci", None) == ogrenci:
        return
    raise PermissionDenied("Bu öğrencinin kartına belge yükleyemezsiniz.")


def _bildir(ogrenci, tur, metin):
    ogrenciye_bildir(ogrenci, tur, metin, baglanti=reverse("belgeler", args=[ogrenci.ogrenci_no]))


def dosya_yolu(belge):
    return Path(settings.KORUNAN_DOSYA_KOKU) / belge.dosya_yolu


@transaction.atomic
def belge_yukle(*, yapan, ogrenci, dosya, tur, donem=None, aciklama="", istek=None, onceki=None, request=None):
    _yetki(yapan, ogrenci)
    if tur not in BelgeTuru.values:
        raise ValidationError("Geçersiz belge türü.")
    if tur in DONEMLI_TURLER and donem is None:
        raise ValidationError("Bu belge türü için dönem seçmelisiniz.")
    if yapan.rol == OGR and tur == BelgeTuru.KURUL_KARARI:
        raise PermissionDenied("Kurul kararlarını yalnızca koordinatör yükler.")
    if istek is not None:
        istek = BelgeIstegi.objects.select_for_update().get(pk=istek.pk)
        if istek.ogrenci_id != ogrenci.id or not istek.acik_mi:
            raise ValidationError("Bu istek için belge yüklenemez.")
        tur = istek.tur
    if onceki is not None:
        onceki = Belge.objects.select_for_update().get(pk=onceki.pk)
        if onceki.ogrenci_id != ogrenci.id or not onceki.guncel_mi:
            raise ValidationError("Yalnızca bu öğrencinin güncel belgesi yenilenebilir.")
        tur, donem = onceki.tur, onceki.donem

    mime, uzanti, ozet, icerik = dogrula(dosya)

    # Diske rastgele adla yaz (orijinal ad diskte hiç kullanılmaz)
    goreli = f"{timezone.now():%Y/%m}/{uuid.uuid4().hex}{uzanti}"
    depo.kaydet(goreli, icerik)

    baslangic = (dict(onay_durumu=OnayDurumu.ONAYLANDI, onaylayan=yapan, onay_zamani=timezone.now(),
                      kaynak=Kaynak.KOORDINATOR)
                 if yapan.rol == KOORD else dict(onay_durumu=OnayDurumu.BEKLIYOR, kaynak=Kaynak.OGRENCI))
    belge = Belge.objects.create(
        ogrenci=ogrenci, tur=tur, donem=donem, aciklama=(aciklama or "")[:300], dosya_yolu=goreli,
        orijinal_ad=guvenli_ad(dosya.name), boyut=len(icerik), sha256=ozet, mime=mime,
        onceki_surum=onceki, istek=istek, olusturan=yapan, **baslangic)

    if onceki is not None and onceki.onay_durumu == OnayDurumu.BEKLIYOR:
        # Henüz incelenmemiş eski sürüm kuyruktan çıkar; silinmez, gerekçesiyle iptal olur
        onceki.onay_durumu, onceki.gerekce = OnayDurumu.IPTAL, "Yerine yeni sürüm yüklendi."
        onceki.save(update_fields=["onay_durumu", "gerekce"])

    if istek is not None:
        istek.durum = (BelgeIstegi.Durum.ONAYLANDI if belge.onayli_mi else BelgeIstegi.Durum.YUKLENDI)
        istek.save(update_fields=["durum"])

    kaydet(request, "BELGE_YUKLENDI", nesne=belge, yapan=yapan, ogrenci_no=ogrenci.ogrenci_no, yeni=_ozet(belge),
           aciklama=(f"Önceki sürüm #{onceki.pk} yenilendi" if onceki else "")
           + (f" İstek #{istek.pk} için" if istek else ""))
    return belge


@transaction.atomic
def belge_onayla(*, yapan, belge, request=None):
    if yapan.rol != KOORD:
        raise PermissionDenied("Belgeleri yalnızca koordinatör onaylar.")
    belge = Belge.objects.select_for_update().get(pk=belge.pk)
    if belge.onay_durumu != OnayDurumu.BEKLIYOR:
        raise ValidationError("Yalnızca onay bekleyen belgeler onaylanabilir.")
    eski = _ozet(belge)
    belge.onay_durumu, belge.onaylayan, belge.onay_zamani = OnayDurumu.ONAYLANDI, yapan, timezone.now()
    belge.save()
    if belge.istek_id:
        BelgeIstegi.objects.filter(pk=belge.istek_id).update(durum=BelgeIstegi.Durum.ONAYLANDI)
    kaydet(request, "BELGE_ONAYLANDI", nesne=belge, yapan=yapan, ogrenci_no=belge.ogrenci.ogrenci_no,
           eski=eski, yeni=_ozet(belge))
    _bildir(belge.ogrenci, "ONAY", f"Belgeniz onaylandı: {belge}.")
    return belge


@transaction.atomic
def belge_reddet(*, yapan, belge, gerekce, request=None):
    if yapan.rol != KOORD:
        raise PermissionDenied("Belgeleri yalnızca koordinatör reddeder.")
    if not (gerekce or "").strip():
        raise ValidationError("Reddetmek için gerekçe yazmalısınız.")
    belge = Belge.objects.select_for_update().get(pk=belge.pk)
    if belge.onay_durumu != OnayDurumu.BEKLIYOR:
        raise ValidationError("Yalnızca onay bekleyen belgeler reddedilebilir.")
    eski = _ozet(belge)
    belge.onay_durumu, belge.gerekce = OnayDurumu.REDDEDILDI, gerekce.strip()
    belge.onaylayan, belge.onay_zamani = yapan, timezone.now()
    belge.save()
    if belge.istek_id:
        BelgeIstegi.objects.filter(pk=belge.istek_id).update(durum=BelgeIstegi.Durum.REDDEDILDI)
    kaydet(request, "BELGE_REDDEDILDI", nesne=belge, yapan=yapan, ogrenci_no=belge.ogrenci.ogrenci_no,
           eski=eski, yeni=_ozet(belge), aciklama=gerekce)
    _bildir(belge.ogrenci, "RED", f"Belgeniz reddedildi: {belge}. Gerekçe: {belge.gerekce} "
                                  "Yeni sürüm yükleyebilirsiniz.")
    return belge


@transaction.atomic
def istek_olustur(*, yapan, ogrenci, tur, aciklama, son_tarih=None, request=None):
    if yapan.rol != KOORD:
        raise PermissionDenied("Ek belge isteğini yalnızca koordinatör oluşturur.")
    if not (aciklama or "").strip():
        raise ValidationError("İsteğin açıklamasını yazın.")
    istek = BelgeIstegi.objects.create(ogrenci=ogrenci, isteyen=yapan, tur=tur, aciklama=aciklama.strip(),
                                       son_tarih=son_tarih)
    kaydet(request, "BELGE_ISTENDI", nesne=istek, yapan=yapan, ogrenci_no=ogrenci.ogrenci_no,
           yeni={"tur": tur, "aciklama": istek.aciklama, "son_tarih": str(son_tarih) if son_tarih else None})
    _bildir(ogrenci, "BELGE_ISTEGI", f"Koordinatör sizden belge istedi: {istek.get_tur_display()}"
                                     + (f" (son tarih {son_tarih:%d.%m.%Y})" if son_tarih else "") + ".")
    return istek


def transkript_yuklendi_mi(ogrenci, donem):
    """Dönem sonu not girişi için o döneme ait ÇAP/YDP not belgesi yüklenmiş mi?
    (Onay bekleyen de kabul edilir; reddedilen veya iptal edilen sayılmaz.)"""
    return Belge.objects.filter(ogrenci=ogrenci, tur=BelgeTuru.TRANSKRIPT, donem=donem) \
        .exclude(onay_durumu__in=[OnayDurumu.REDDEDILDI, OnayDurumu.IPTAL]).exists()
