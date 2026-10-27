"""Her sayfada menüde gösterilen okunmamış mesaj ve bildirim sayıları."""


def sayaclar(request):
    kullanici = getattr(request, "user", None)
    if not kullanici or not kullanici.is_authenticated or kullanici.sifre_degistirmeli:
        return {}
    from .servisler import okunmamis_mesaj_sayisi
    return {
        "okunmamis_mesaj": okunmamis_mesaj_sayisi(kullanici),
        "okunmamis_bildirim": kullanici.bildirimler.filter(okunma_zamani__isnull=True).count(),
    }
