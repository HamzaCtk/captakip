"""Yüklenen dosyaların güvenlik kontrolü.

Kontroller (hepsi sunucuda yapılır, tarayıcıya güvenilmez):
1. Boş dosya ve boyut sınırı (varsayılan 10 MB)
2. Uzantı beyaz listesi: .pdf, .png, .jpg, .jpeg
3. İçerik imzası ("magic bytes"): dosyanın gerçek türü uzantısıyla aynı olmalı
   (ör. adı .pdf olan bir .exe reddedilir)
4. Bütünlük: PDF '%%EOF', PNG 'IEND', JPEG 'FFD9' ile bitmeli (yarım/bozuk dosya)
5. Etkin içerik: JavaScript, otomatik çalıştırma veya gömülü dosya içeren PDF reddedilir
6. Dosya adı: yol bileşenleri ve tehlikeli karakterler temizlenir; diskte
   orijinal ad hiç kullanılmaz (rastgele ad verilir)
"""
import hashlib
import os
import re
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError

IZINLI_TURLER = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}

IMZALAR = {
    "application/pdf": [b"%PDF-"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
}

# PDF içinde kod çalıştırabilen veya dosya taşıyan anahtarlar
PDF_TEHLIKELI = [rb"/JavaScript", rb"/JS\b", rb"/Launch", rb"/EmbeddedFile", rb"/OpenAction\s*<<[^>]*?/JS",
                 rb"/RichMedia", rb"/XFA"]


def guvenli_ad(ad):
    """Dosya adını yalnızca görüntülemek için temizler."""
    ad = os.path.basename(str(ad).replace("\\", "/"))
    ad = unicodedata.normalize("NFC", ad)
    ad = re.sub(r"[^\w.\- ()]", "_", ad, flags=re.UNICODE).strip(" .")
    return (ad or "belge")[:120]


def dogrula(dosya):
    """Dosyayı doğrular. Geçerliyse (mime, uzantı, sha256, içerik) döndürür,
    değilse ValidationError fırlatır."""
    maks = getattr(settings, "BELGE_MAKS_BOYUT", 10 * 1024 * 1024)
    if dosya is None or dosya.size == 0:
        raise ValidationError("Dosya boş.")
    if dosya.size > maks:
        raise ValidationError(f"Dosya çok büyük. En fazla {maks // (1024 * 1024)} MB yükleyebilirsiniz.")

    uzanti = os.path.splitext(dosya.name or "")[1].lower()
    if uzanti not in IZINLI_TURLER:
        raise ValidationError("Yalnızca PDF, PNG ve JPEG dosyaları yüklenebilir.")
    mime = IZINLI_TURLER[uzanti]

    icerik = b"".join(dosya.chunks())
    if len(icerik) > maks:
        raise ValidationError("Dosya çok büyük.")
    if not any(icerik.startswith(imza) for imza in IMZALAR[mime]):
        raise ValidationError("Dosyanın içeriği uzantısıyla uyuşmuyor. Dosya bozuk ya da farklı türde olabilir.")

    son = icerik[-2048:]
    if mime == "application/pdf":
        if b"%%EOF" not in son:
            raise ValidationError("PDF dosyası eksik veya bozuk görünüyor.")
        for desen in PDF_TEHLIKELI:
            if re.search(desen, icerik):
                raise ValidationError("PDF dosyası çalıştırılabilir içerik (JavaScript, gömülü dosya vb.) "
                                      "barındırıyor. Lütfen belgeyi yazdır → PDF olarak kaydet ile yeniden oluşturun.")
    elif mime == "image/png" and b"IEND" not in son:
        raise ValidationError("PNG dosyası eksik veya bozuk görünüyor.")
    elif mime == "image/jpeg" and b"\xff\xd9" not in son:
        raise ValidationError("JPEG dosyası eksik veya bozuk görünüyor.")

    return mime, uzanti, hashlib.sha256(icerik).hexdigest(), icerik
