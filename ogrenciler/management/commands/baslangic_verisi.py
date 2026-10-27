"""Başlangıç verisini yükler: bölümler, akademik dönemler, ders kataloğu ve
EEM → Bilgisayar Mühendisliği ÇAP protokolü.

Kullanım:
    python manage.py baslangic_verisi              # yalnız tanım verisi
    python manage.py baslangic_verisi --ornek      # + sentetik örnek öğrenciler

Komut tekrar çalıştırılabilir; var olan kayıtlar çoğaltılmaz.
Not: Tüm öğrenci verileri sentetiktir (gerçek kişilere ait değildir).
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Kullanici
from dersler.models import Ders, DersDenemesi, ProtokolKalemi, ProtokolSablonu
from ogrenciler.models import AkademikDonem, Bolum, Ogrenci
from ortak.modeller import Kaynak, OnayDurumu

BOLUMLER = [
    ("BM", "Bilgisayar Mühendisliği", "Teknoloji Fakültesi"),
    ("EEM", "Elektrik-Elektronik Mühendisliği", "Teknoloji Fakültesi"),
]

# (kod, ad, akts, yarıyıl, tür) — Çift Anadal Kabul ve Ders Protokol Formu'ndan
KATALOG = [
    ("3301156", "Bilgisayar Mühendisliğine Giriş", 4, 1, "ZORUNLU"),
    ("3301351", "Nesneye Yönelik Programlama Dili", 4, 3, "ZORUNLU"),
    ("3301352", "İşletim Sistemleri", 4, 3, "ZORUNLU"),
    ("3301354", "Veri Yapıları ve Uygulamaları", 4, 3, "ZORUNLU"),
    ("3301452", "Programlama Dili-2", 4, 4, "ZORUNLU"),
    ("3301454", "Veri Tabanı Yönetim Sistemleri", 5, 4, "ZORUNLU"),
    ("3301455", "Yazılım Mühendisliği", 4, 4, "ZORUNLU"),
    ("3301456", "Mobil Programlama", 4, 4, "ZORUNLU"),
    ("3301552", "Programlama Dili-3", 5, 5, "ZORUNLU"),
    ("3301553", "Veri Haberleşmesi ve Ağlar", 5, 5, "ZORUNLU"),
    ("3301651", "Yapay Zeka", 4, 6, "ZORUNLU"),
    ("3301652", "Otomata Teorisi ve Biçimsel Diller", 4, 6, "ZORUNLU"),
    ("3301653", "Görüntü İşleme", 4, 6, "ZORUNLU"),
    ("3301654", "Mühendislik Tasarımı", 6, 6, "ZORUNLU"),
    ("3301751", "Bilgisayar Mühendisliği Uygulamaları", 4, 7, "ZORUNLU"),
    ("3301752", "Bilgisayar Mimarisi ve Organizasyonu", 4, 7, "ZORUNLU"),
    ("3301753", "Veri Bilimi", 4, 7, "ZORUNLU"),
    ("3301851", "İşletmede Mesleki Eğitim", 20, 8, "ZORUNLU"),
    ("3301852", "Staj 1", 5, 8, "ZORUNLU"),
    ("3301853", "Staj 2", 5, 8, "ZORUNLU"),
    # Protokoldeki özel şartlarda adı geçen teknik seçmeliler
    ("3301561", "Sinyal İşleme", 4, 5, "SECMELI"),
    ("3301568", "Veri Madenciliği", 4, 5, "SECMELI"),
    ("3301663", "Gömülü Sistemler", 4, 6, "SECMELI"),
    ("3301665", "Robotik", 4, 6, "SECMELI"),
    ("3301770", "Veri İletişim Teknikleri", 4, 7, "SECMELI"),
]

OZEL = {
    1: "EEM 3302458 Veri Yapıları (4. yy teknik seçmeli) alınırsa muaf sayılır.",
    2: "EEM 3302758 Sayısal Sinyal İşleme alınırsa 3301561 Sinyal İşleme'den muaf sayılır.",
    3: "EEM 3302459 Mühendislik Veri Madenciliği alınırsa 3301568 Veri Madenciliği'nden muaf sayılır.",
    4: "EEM 3302561 Makine Öğrenmesi ve Yapay Zekâ alınırsa muaf sayılır.",
    5: "EEM 3302659 Görüntü İşleme alınırsa muaf sayılır.",
    6: "EEM 3302656 Gömülü Sistemler alınırsa 3301663 Gömülü Sistemler'den muaf sayılır.",
    7: "EEM 3302563 Robotik Sistemlere Giriş alınırsa 3301665 Robotik'ten muaf sayılır.",
    8: "EEM 3302556 Veri İletişim Teknikleri alınırsa 3301770 Veri İletişim Teknikleri'nden muaf sayılır.",
}

# Protokol kalemleri sırasıyla: ders kodu veya (slot açıklaması, yarıyıl), akts, özel şart no
PROTOKOL_EEM = [
    ("3301156", 4, None), ("3301351", 4, None), ("3301352", 4, None), ("3301354", 4, 1),
    ("3301452", 4, None), ("3301454", 5, None), ("3301455", 4, None), ("3301456", 4, None),
    ("3301552", 5, None), ("3301553", 5, None),
    (("5. Yarıyıl Teknik Seçmeli Ders", 5), 4, 2), (("5. Yarıyıl Teknik Seçmeli Ders", 5), 4, 3),
    (("5. Yarıyıl Teknik Seçmeli Ders", 5), 4, None),
    ("3301651", 4, 4), ("3301652", 4, None), ("3301653", 4, 5), ("3301654", 6, None),
    (("6. Yarıyıl Teknik Seçmeli Ders", 6), 4, 6), (("6. Yarıyıl Teknik Seçmeli Ders", 6), 4, 7),
    (("6. Yarıyıl Teknik Seçmeli Ders", 6), 4, None),
    ("3301751", 4, None), ("3301752", 4, None), ("3301753", 4, None),
    (("7. Yarıyıl Teknik Seçmeli Ders", 7), 4, 8), (("7. Yarıyıl Teknik Seçmeli Ders", 7), 4, None),
    ("3301851", 20, None), ("3301852", 5, None), ("3301853", 5, None),
]


class Command(BaseCommand):
    help = "Bölüm, dönem, ders kataloğu ve EEM protokolünü yükler."

    def add_arguments(self, parser):
        parser.add_argument("--ornek", action="store_true", help="Sentetik örnek öğrenciler de ekle")

    @transaction.atomic
    def handle(self, *args, **o):
        bolumler = {}
        for kod, ad, fak in BOLUMLER:
            bolumler[kod], _ = Bolum.objects.get_or_create(kod=kod, defaults={"ad": ad, "fakulte": fak})

        for yil in range(2022, 2029):
            for d in ("GUZ", "BAHAR", "YAZ"):
                AkademikDonem.objects.get_or_create(yil=f"{yil}-{yil + 1}", donem=d)

        dersler = {}
        for kod, ad, akts, yy, tur in KATALOG:
            dersler[kod], _ = Ders.objects.get_or_create(
                kod=kod, defaults={"ad": ad, "akts": akts, "yariyil": yy, "tur": tur})

        sablon, yeni = ProtokolSablonu.objects.get_or_create(
            program_turu="CAP", ana_dal_bolumu=bolumler["EEM"],
            defaults={"ad": "EEM → Bilgisayar Mühendisliği ÇAP Protokolü"})
        if yeni:
            for sira, (kalem, akts, ozel) in enumerate(PROTOKOL_EEM, start=1):
                if isinstance(kalem, tuple):
                    ProtokolKalemi.objects.create(sablon=sablon, sira=sira, slot_aciklama=kalem[0],
                                                  yariyil=kalem[1], akts=akts, ozel_sart=OZEL.get(ozel, ""))
                else:
                    ProtokolKalemi.objects.create(sablon=sablon, sira=sira, ders=dersler[kalem],
                                                  yariyil=dersler[kalem].yariyil, akts=akts,
                                                  ozel_sart=OZEL.get(ozel, ""))
        toplam = sablon.toplam_akts()
        if toplam != 135:
            raise CommandError(f"Protokol toplamı 135 AKTS olmalı, {toplam} bulundu.")
        if o["verbosity"]:
            self.stdout.write(self.style.SUCCESS(
                f"Tanım verisi hazır: {Ders.objects.count()} ders, {sablon.kalemler.count()} protokol kalemi ({toplam} AKTS)."))

        from kurallar.servisler import ilk_surumleri_olustur
        yeni_surumler = ilk_surumleri_olustur()
        if o["verbosity"] and yeni_surumler:
            self.stdout.write(self.style.SUCCESS(
                "Kural sürümleri oluşturuldu: " + ", ".join(s.ad for s in yeni_surumler)))

        self.verbosity = o["verbosity"]
        if o["ornek"]:
            self._ornek_ogrenciler(bolumler)

    def _ornek_ogrenciler(self, bolumler):
        from ogrenciler import servisler
        koord = Kullanici.objects.filter(rol=Kullanici.Rol.KOORDINATOR).first()
        if koord is None:
            raise CommandError("Önce koordinatör hesabı oluşturun (koordinator_olustur).")
        guz25 = AkademikDonem.objects.get(yil="2025-2026", donem="GUZ")
        bahar26 = AkademikDonem.objects.get(yil="2025-2026", donem="BAHAR")
        guz26 = AkademikDonem.objects.get(yil="2026-2027", donem="GUZ")
        ornekler = [
            ("231101001", "Deniz", "Örnekoğlu", "CAP", bolumler["EEM"], guz25),
            ("231101002", "Elif", "Denemeci", "CAP", bolumler["EEM"], guz25),
            ("221101003", "Kerem", "Sentetik", "YDP", bolumler["EEM"], guz25),
        ]
        for no, ad, soyad, tur, bolum, donem in ornekler:
            if Ogrenci.objects.filter(ogrenci_no=no).exists():
                continue
            ogrenci, sifre = servisler.ogrenci_ekle(
                yapan=koord, ogrenci_no=no, ad=ad, soyad=soyad, eposta=f"{no}@ornek.edu.tr",
                ana_dal_bolumu=bolum, tur=tur, kabul_donemi=donem, kaynak=Kaynak.AKTARIM)
            self.stdout.write(f"  {no} {ad} {soyad} ({tur}) — geçici şifre: {sifre}")

        # İlk öğrenciye geçmiş dönem notları (ilk kurulum aktarımı gibi)
        program = Ogrenci.objects.get(ogrenci_no="231101001").guncel_program
        if not DersDenemesi.objects.filter(ogrenci_dersi__program_kaydi=program).exists():
            simdi = timezone.now()
            def deneme(kod, donem, durum, notu, onay=OnayDurumu.ONAYLANDI):
                od = program.dersler.get(ders__kod=kod)
                DersDenemesi.objects.create(
                    ogrenci_dersi=od, donem=donem, durum=durum, harf_notu=notu, onay_durumu=onay,
                    kaynak=Kaynak.AKTARIM if onay == OnayDurumu.ONAYLANDI else Kaynak.OGRENCI,
                    olusturan=koord if onay == OnayDurumu.ONAYLANDI else program.ogrenci.kullanici,
                    onaylayan=koord if onay == OnayDurumu.ONAYLANDI else None,
                    onay_zamani=simdi if onay == OnayDurumu.ONAYLANDI else None)
            deneme("3301156", guz25, "GECTI", "CB")
            deneme("3301351", guz25, "GECTI", "BA")
            deneme("3301352", bahar26, "KALDI", "FF")
            deneme("3301352", guz26, "ALINDI", "")
            deneme("3301452", guz26, "ALINDI", "", onay=OnayDurumu.BEKLIYOR)
            vy = program.dersler.get(ders__kod="3301354")
            vy.liste_durumu = vy.ListeDurumu.MUAF
            vy.save(update_fields=["liste_durumu"])

        # Ana dal bilgileri (sentetik) ve ilk kural değerlendirmesi
        from kurallar import motor
        from ogrenciler.models import AnaDalKaydi, ProgramKaydi
        bahar26 = AkademikDonem.objects.get(yil="2025-2026", donem="BAHAR")
        for no, gano in (("231101001", "3.12"), ("231101002", "2.61"), ("221101003", "2.45")):
            prg = Ogrenci.objects.get(ogrenci_no=no).guncel_program
            if prg and not prg.ana_dal_kayitlari.exists():
                AnaDalKaydi.objects.create(program_kaydi=prg, donem=bahar26, gano=gano,
                                           kaynak_aciklama="Sentetik örnek veri", giren=koord)
        for prg in ProgramKaydi.objects.filter(durum__in=ProgramKaydi.ACIK_DURUMLAR):
            motor.degerlendir(prg, "Başlangıç verisi", koord)
        if self.verbosity:
            self.stdout.write(self.style.SUCCESS("Sentetik örnek öğrenciler hazır; kurallar değerlendirildi."))
