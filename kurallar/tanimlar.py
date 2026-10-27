"""Yönerge kurallarının parametre tanımları.

Buradaki değerler yalnızca İLK kural sürümünü oluşturmak için kullanılır.
Sistem çalışırken eşikler veritabanındaki kural sürümünden okunur ve
koordinatör tarafından "Kural ayarları" ekranından değiştirilir. Böylece
yönerge değişince kod değişmez; yeni bir kural sürümü girilir.

Her tanım: (anahtar, etiket, tip, ÇAP varsayılanı, YDP varsayılanı, dayanak)
tip: "sayi" (ondalık), "tam" (tam sayı), "liste" (virgüllü), "harf" (harf=puan)
None = bu program türünde kural uygulanmaz.
"""

HARF_PUANLARI = "AA=4.00, BA=3.50, BB=3.00, CB=2.50, CC=2.00, DC=1.50, DD=1.00, FD=0.50, FF=0.00"
GECER_NOTLAR = "AA, BA, BB, CB, CC, DC, DD"

PARAMETRELER = [
    ("ana_gano_esik", "Ana dal GANO alt sınırı", "sayi", "2.72", "2.30",
     "ÇAP Md. 9/e (2,72) · YDP Md. 7/5 (2,30)"),
    ("ana_gano_tolerans_esik", "Bir defaya mahsus izin verilen alt sınır", "sayi", "2.50", None,
     "ÇAP Md. 9/e: bir defaya mahsus 2,50'nin altına düşebilir"),
    ("ana_gano_izin_sayisi", "Sınırın altına düşme izni (kez)", "tam", "1", "0",
     "ÇAP Md. 9/e: ikinci kez düşerse kayıt silinir · YDP Md. 7/5: ilk düşüşte silinir"),
    ("program_gano_esik", "Program not ortalaması alt sınırı (4'lük)", "sayi", None, "2.00",
     "ÇAP: Y.Ö.K. Yön. Md. 17/4 (100 üzerinden 70; 4'lük karşılığı koordinatörce girilir) · YDP Md. 7/6"),
    ("program_gano_ardisik_donem", "Program ortalaması kaç dönem üst üste düşük olursa", "tam", "2", "2",
     "ÇAP: bir defaya mahsus izin · YDP Md. 7/6: üst üste iki dönem"),
    ("ders_almama_donem", "Üst üste ders alınmayan dönem sınırı", "tam", "2", "2",
     "ÇAP Md. 9/d · YDP Md. 7/4"),
    ("azami_yariyil", "Azami öğrenim süresi (yarıyıl)", "tam", "14", None,
     "ÇAP Md. 8/d · 2547 s. Kanun Md. 44/c (lisans: 7 yıl)"),
    ("ek_sure_yariyil", "Ana dal mezuniyetinden sonra ek süre (yarıyıl)", "tam", None, "2",
     "YDP Md. 7/9"),
    ("mezuniyet_ana_gano", "Diploma için ana dal mezuniyet GANO'su", "sayi", "2.72", None,
     "ÇAP Md. 8/c"),
    ("bitirme_program_gano", "Sertifika için yan dal not ortalaması", "sayi", None, "2.00",
     "YDP Md. 7/8"),
    ("asgari_ders", "Asgari ders sayısı", "tam", None, "6", "YDP Md. 5/g"),
    ("asgari_akts", "Asgari AKTS", "tam", None, "30", "YDP Md. 5/g"),
    ("gecer_harf_notlari", "Geçer harf notları", "liste", GECER_NOTLAR, GECER_NOTLAR,
     "Selçuk Üniversitesi Ön Lisans ve Lisans Eğitim-Öğretim ve Sınav Yönetmeliği"),
    ("harf_puanlari", "Harf notlarının 4'lük karşılıkları", "harf", HARF_PUANLARI, HARF_PUANLARI,
     "Selçuk Üniversitesi Ön Lisans ve Lisans Eğitim-Öğretim ve Sınav Yönetmeliği"),
]

TANIM = {p[0]: p for p in PARAMETRELER}

ILK_SURUM = {
    "CAP": ("Çift Ana Dal Yönergesi (Senato 20.05.2026, 2026-20)", "2026-05-20"),
    "YDP": ("Yan Dal Yönergesi (Senato 26.10.2023, 2023-131)", "2023-10-26"),
}


def coz(anahtar, metin):
    """Saklanan metin değeri tipine göre Python değerine çevirir."""
    if metin in (None, ""):
        return None
    tip = TANIM[anahtar][2]
    if tip == "sayi":
        return float(str(metin).replace(",", "."))
    if tip == "tam":
        return int(metin)
    if tip == "liste":
        return [p.strip().upper() for p in str(metin).split(",") if p.strip()]
    if tip == "harf":
        sonuc = {}
        for parca in str(metin).split(","):
            harf, _, puan = parca.partition("=")
            sonuc[harf.strip().upper()] = float(puan.strip().replace(",", "."))
        return sonuc
    return metin


def dogrula(anahtar, metin):
    """Koordinatörün girdiği değerin biçimini denetler; hata metni döndürür."""
    if metin in (None, ""):
        return None
    try:
        deger = coz(anahtar, metin)
    except (ValueError, TypeError):
        return "Geçersiz değer biçimi."
    tip = TANIM[anahtar][2]
    if tip == "sayi" and not (0 <= deger <= 100):
        return "Değer 0 ile 100 arasında olmalı."
    if tip == "tam" and deger < 0:
        return "Değer negatif olamaz."
    if tip == "harf" and not deger:
        return "En az bir harf notu girin (ör. AA=4.00)."
    return None
