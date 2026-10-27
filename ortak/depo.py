"""Yüklenen dosyaların saklandığı yer (tek giriş noktası).

İki depo vardır; ayar ile seçilir (settings.DOSYA_DEPOSU):
- "disk" (yerel geliştirme ve demo): korunan_dosyalar/ klasörü. Web'den
  doğrudan erişilemez; yalnızca yetki denetimi yapan indirme görünümüyle verilir.
- "veritabani" (canlı ortam): içerik belgeler.DepolananDosya tablosunda
  tutulur. Sunucu diski kalıcı olmayan bulut servislerinde dosyalar kaybolmaz
  ve kayıtla aynı veritabanı işleminde (transaction) yazılır.

Her iki depoda da dosyanın yolu ("2026/10/<rastgele>.pdf") sistem tarafından
üretilir; kullanıcıdan gelen dosya adı hiçbir zaman yol olarak kullanılmaz.
"""
import hashlib
import io
from pathlib import Path

from django.conf import settings


def _veritabani_mi():
    return getattr(settings, "DOSYA_DEPOSU", "disk") == "veritabani"


def _disk_yolu(goreli):
    kok = Path(settings.KORUNAN_DOSYA_KOKU).resolve()
    yol = (kok / goreli).resolve()
    if kok not in yol.parents:  # ek güvenlik: kök dışına çıkılamaz
        raise ValueError("Geçersiz dosya yolu.")
    return yol


def kaydet(goreli, icerik):
    """Yeni dosyayı yazar. Aynı yolda dosya varsa hata verir (üzerine yazılmaz)."""
    if _veritabani_mi():
        from belgeler.models import DepolananDosya
        DepolananDosya.objects.create(yol=goreli, icerik=icerik, boyut=len(icerik),
                                      sha256=hashlib.sha256(icerik).hexdigest())
        return
    hedef = _disk_yolu(goreli)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    with open(hedef, "xb") as f:
        f.write(icerik)


def oku(goreli):
    """Dosyanın içeriğini döndürür; yoksa None."""
    if _veritabani_mi():
        from belgeler.models import DepolananDosya
        kayit = DepolananDosya.objects.filter(yol=goreli).only("icerik").first()
        return bytes(kayit.icerik) if kayit else None
    yol = _disk_yolu(goreli)
    return yol.read_bytes() if yol.is_file() else None


def ac(goreli):
    """İndirme için dosya nesnesi (FileResponse'a verilir); yoksa None."""
    if _veritabani_mi():
        icerik = oku(goreli)
        return io.BytesIO(icerik) if icerik is not None else None
    yol = _disk_yolu(goreli)
    return open(yol, "rb") if yol.is_file() else None
