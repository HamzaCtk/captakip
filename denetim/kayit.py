"""İşlem kaydı yazmak için tek giriş noktası.

Kullanım:
    from denetim.kayit import kaydet
    kaydet(request, "KULLANICI_OLUSTURULDU", nesne=kullanici,
           yeni={"rol": "OGRENCI"}, aciklama="...")
"""
from .models import IslemKaydi


def istemci_ip(request):
    if request is None:
        return None
    # Not: Ters vekil (proxy) arkasında çalışırken X-Forwarded-For
    # yalnızca güvenilen vekilden geliyorsa kullanılmalıdır.
    return request.META.get("REMOTE_ADDR")


def kaydet(request, islem, nesne=None, eski=None, yeni=None,
           aciklama="", ogrenci_no="", yapan=None):
    if yapan is None and request is not None and request.user.is_authenticated:
        yapan = request.user
    return IslemKaydi.objects.create(
        yapan=yapan,
        islem=islem,
        nesne_turu=type(nesne).__name__ if nesne is not None else "",
        nesne_id=str(nesne.pk) if nesne is not None else "",
        nesne_metni=str(nesne)[:255] if nesne is not None else "",
        ogrenci_no=ogrenci_no,
        eski_deger=eski,
        yeni_deger=yeni,
        aciklama=aciklama,
        ip_adresi=istemci_ip(request),
    )
