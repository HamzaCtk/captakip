"""Her sayfada menüde gösterilen onay bekleyen kayıt sayısı."""


def onay_sayaci(request):
    kullanici = getattr(request, "user", None)
    if not kullanici or not kullanici.is_authenticated or kullanici.rol not in ("KOORDINATOR", "BOLUM_BASKANI"):
        return {}
    from ortak.modeller import OnayDurumu
    from belgeler.models import Belge
    from .models import DersDenemesi, NotGirisi, OgrenciDersi
    sayi = sum(m.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).count()
               for m in (OgrenciDersi, DersDenemesi, NotGirisi, Belge))
    return {"onay_bekleyen_sayisi": sayi}
