"""CSV dosyasını güvenli biçimde okur ve sütunları tanır.

- Kodlama: UTF-8 (BOM'lu veya BOM'suz) denenir, olmazsa Windows-1254
  (Excel'in Türkçe Windows'ta kaydettiği biçim).
- Ayırıcı: noktalı virgül, virgül veya sekme kendiliğinden bulunur.
- Sütun adları esnektir: "Öğrenci No", "OGRENCI_NO", "ogrno" aynı sütun
  sayılır. OBİS'ten alınan dökümlerin sütun adları farklıysa yalnızca
  aşağıdaki SUTUNLAR sözlüğüne yeni ad eklemek yeterlidir (OBİS'e hazırlık).
"""
import csv
import io
import re

from django.core.exceptions import ValidationError

MAKS_BOYUT = 2 * 1024 * 1024   # 2 MB
MAKS_SATIR = 2000

# tür → [(anahtar, zorunlu mu, kabul edilen sütun adları)]
SUTUNLAR = {
    "OGRENCI": [
        ("ogrenci_no", True, ["ogrenci_no", "ogrenci_numarasi", "ogrno", "numara", "no"]),
        ("ad", True, ["ad", "adi"]),
        ("soyad", True, ["soyad", "soyadi"]),
        ("eposta", True, ["eposta", "e_posta", "email", "e_mail", "mail"]),
        ("ana_dal", True, ["ana_dal", "ana_dal_bolumu", "anadal", "bolum", "bolum_kodu"]),
        ("program", True, ["program", "program_turu", "tur"]),
        ("kabul_donemi", True, ["kabul_donemi", "kabul_yariyili", "kayit_donemi", "giris_donemi"]),
    ],
    "NOT": [
        ("ogrenci_no", True, ["ogrenci_no", "ogrenci_numarasi", "ogrno", "numara", "no"]),
        ("ders_kodu", True, ["ders_kodu", "ders_kod", "dersin_kodu", "kod"]),
        ("donem", True, ["donem", "akademik_donem", "ogretim_donemi", "yariyil_donem"]),
        ("harf_notu", False, ["harf_notu", "harf", "basari_notu", "not"]),
    ],
    "ANA_DAL": [
        ("ogrenci_no", True, ["ogrenci_no", "ogrenci_numarasi", "ogrno", "numara", "no"]),
        ("donem", True, ["donem", "akademik_donem", "ogretim_donemi"]),
        ("gano", True, ["gano", "agno", "genel_ortalama", "ana_dal_gano"]),
        ("ana_dal_durumu", False, ["ana_dal_durumu", "durum"]),
        ("kaynak", False, ["kaynak", "aciklama"]),
    ],
}

# İndirilebilir örnek şablonlar (tamamen sentetik veri)
SABLONLAR = {
    "OGRENCI": [
        ["ogrenci_no", "ad", "soyad", "eposta", "ana_dal", "program", "kabul_donemi"],
        ["231101011", "Ayşe", "Örnekçi", "231101011@ornek.edu.tr", "EEM", "ÇAP", "2025-2026 Güz"],
        ["221101012", "Mert", "Sentetikoğlu", "221101012@ornek.edu.tr", "EEM", "YDP", "2025-2026 Bahar"],
    ],
    "NOT": [
        ["ogrenci_no", "ders_kodu", "donem", "harf_notu"],
        ["231101011", "3301156", "2025-2026 Güz", "BA"],
        ["231101011", "3301352", "2025-2026 Bahar", "FF"],
        ["231101011", "3301352", "2026-2027 Güz", ""],
    ],
    "ANA_DAL": [
        ["ogrenci_no", "donem", "gano", "ana_dal_durumu", "kaynak"],
        ["231101011", "2025-2026 Bahar", "3,05", "Aktif", "Ana dal transkripti (sentetik)"],
    ],
}

_TR = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")


def sade(metin):
    """Sütun adını karşılaştırma için sadeleştirir: 'Öğrenci No' → 'ogrenci_no'."""
    metin = str(metin or "").strip().translate(_TR).lower()
    return re.sub(r"[^a-z0-9]+", "_", metin).strip("_")


def _coz(icerik):
    if b"\x00" in icerik:
        raise ValidationError("Dosya metin (CSV) değil.")
    for kodlama in ("utf-8-sig", "cp1254"):
        try:
            return icerik.decode(kodlama), kodlama
        except UnicodeDecodeError:
            continue
    raise ValidationError("Dosyanın karakter kodlaması tanınmadı. UTF-8 olarak kaydedin.")


def oku(icerik, tur):
    """Döndürür: {"kodlama", "ayirac", "satirlar": [(satir_no, {anahtar: değer})]}"""
    if tur not in SUTUNLAR:
        raise ValidationError("Geçersiz aktarım türü.")
    if not icerik:
        raise ValidationError("Dosya boş.")
    if len(icerik) > MAKS_BOYUT:
        raise ValidationError(f"Dosya en fazla {MAKS_BOYUT // (1024 * 1024)} MB olabilir.")
    metin, kodlama = _coz(icerik)
    ilk = metin.splitlines()[0] if metin.strip() else ""
    ayirac = max([";", ",", "\t"], key=ilk.count)
    if not ilk.count(ayirac):
        raise ValidationError("Sütunlar ayrılamadı. Noktalı virgül (;) veya virgülle ayrılmış CSV yükleyin.")

    okuyucu = csv.reader(io.StringIO(metin, newline=""), delimiter=ayirac)
    try:
        basliklar = [sade(b) for b in next(okuyucu)]
    except (StopIteration, csv.Error):
        raise ValidationError("Başlık satırı okunamadı.")

    konum, eksik = {}, []
    for anahtar, zorunlu, adlar in SUTUNLAR[tur]:
        bulunan = next((basliklar.index(a) for a in adlar if a in basliklar), None)
        if bulunan is None:
            if zorunlu:
                eksik.append(adlar[0])
        else:
            konum[anahtar] = bulunan
    if eksik:
        raise ValidationError("Eksik sütun: " + ", ".join(eksik) + ". Örnek şablonu indirip ona göre hazırlayın.")

    satirlar = []
    try:
        for hucreler in okuyucu:
            if not any(h.strip() for h in hucreler):
                continue  # boş satır
            if len(satirlar) >= MAKS_SATIR:
                raise ValidationError(f"Bir dosyada en fazla {MAKS_SATIR} satır olabilir; dosyayı bölün.")
            veri = {a: (hucreler[i].strip() if i < len(hucreler) else "") for a, i in konum.items()}
            satirlar.append((okuyucu.line_num, veri))
    except csv.Error as e:
        raise ValidationError(f"CSV satır {okuyucu.line_num}: biçim hatası ({e}).")
    if not satirlar:
        raise ValidationError("Dosyada başlık dışında satır yok.")
    return {"kodlama": kodlama, "ayirac": ayirac, "satirlar": satirlar}


def sablon_metni(tur):
    """Excel'in Türkçe Windows'ta doğru açması için UTF-8 BOM ve noktalı virgül."""
    cikti = io.StringIO()
    yazici = csv.writer(cikti, delimiter=";", lineterminator="\r\n")
    yazici.writerows(SABLONLAR[tur])
    return "﻿" + cikti.getvalue()
