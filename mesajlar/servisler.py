"""Mesaj ve bildirim servisleri.

Kurallar (koordinatörün proje e-postası, "MESAJLAŞMA"):
- Öğrenci yalnızca koordinatörle yazışır ve yalnızca kendi mesajlarını görür.
- Koordinatör tüm öğrencilerle yazışır. Bölüm başkanı yazışmaları okur, yazamaz.
- Mesajlar silinemez ve değiştirilemez; ek dosya alabilir.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Kullanici
from belgeler.dogrulama import dogrula, guvenli_ad
from denetim.kayit import kaydet
from ortak import depo

from .models import Bildirim, Mesaj

KOORD = Kullanici.Rol.KOORDINATOR
OGR = Kullanici.Rol.OGRENCI
MAKS_UZUNLUK = 4000


def _kendi_konusmasi_mi(kullanici, ogrenci):
    return kullanici.rol == OGR and getattr(kullanici, "ogrenci", None) == ogrenci


def ek_yolu(mesaj):
    return Path(settings.KORUNAN_DOSYA_KOKU) / mesaj.ek_yolu


@transaction.atomic
def mesaj_gonder(*, yapan, ogrenci, metin, ek=None, request=None):
    """Koordinatör herhangi bir öğrenciye, öğrenci yalnızca kendi konuşmasına yazar."""
    if not (yapan.rol == KOORD or _kendi_konusmasi_mi(yapan, ogrenci)):
        raise PermissionDenied("Bu konuşmaya mesaj yazamazsınız.")
    metin = (metin or "").strip()
    if not metin:
        raise ValidationError("Mesaj boş olamaz.")
    if len(metin) > MAKS_UZUNLUK:
        raise ValidationError(f"Mesaj en fazla {MAKS_UZUNLUK} karakter olabilir.")

    ek_alanlari = {}
    if ek is not None:
        mime, uzanti, ozet, icerik = dogrula(ek)
        goreli = f"mesaj/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{uzanti}"
        depo.kaydet(goreli, icerik)
        ek_alanlari = dict(ek_yolu=goreli, ek_adi=guvenli_ad(ek.name), ek_boyut=len(icerik),
                           ek_sha256=ozet, ek_mime=mime)

    mesaj = Mesaj.objects.create(ogrenci=ogrenci, gonderen=yapan, metin=metin, **ek_alanlari)
    kaydet(request, "MESAJ_GONDERILDI", nesne=mesaj, yapan=yapan, ogrenci_no=ogrenci.ogrenci_no,
           yeni={"uzunluk": len(metin), "ek": mesaj.ek_adi or None,
                 "ek_sha256": mesaj.ek_sha256[:16] or None})
    return mesaj


def okundu_isaretle(*, okuyan, ogrenci):
    """Konuşmayı açan tarafın, karşı taraftan gelen okunmamış mesajlarını okundu yapar.
    Bölüm başkanı okumakla mesajı 'okundu' yapmaz (yazışmanın tarafı değildir)."""
    qs = Mesaj.objects.filter(ogrenci=ogrenci, okunma_zamani__isnull=True)
    if okuyan.rol == KOORD:
        qs = qs.filter(gonderen=ogrenci.kullanici)
    elif _kendi_konusmasi_mi(okuyan, ogrenci):
        qs = qs.exclude(gonderen=okuyan)
    else:
        return 0
    return qs.update(okunma_zamani=timezone.now(), okuyan=okuyan)


def okunmamis_mesaj_sayisi(kullanici):
    if kullanici.rol == KOORD:
        return Mesaj.objects.filter(okunma_zamani__isnull=True, gonderen__rol=OGR).count()
    if kullanici.rol == OGR:
        ogrenci = getattr(kullanici, "ogrenci", None)
        if ogrenci is None:
            return 0
        return Mesaj.objects.filter(ogrenci=ogrenci, okunma_zamani__isnull=True) \
            .exclude(gonderen=kullanici).count()
    return 0


def bildirim_okundu(*, kullanici, bildirim):
    if bildirim.alici_id != kullanici.id:
        raise PermissionDenied
    if bildirim.okunma_zamani is None:
        bildirim.okunma_zamani = timezone.now()
        bildirim.save(update_fields=["okunma_zamani"])
    return bildirim


def tumunu_okundu_yap(*, kullanici):
    return Bildirim.objects.filter(alici=kullanici, okunma_zamani__isnull=True) \
        .update(okunma_zamani=timezone.now())
