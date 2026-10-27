"""Sunum (demo) için zengin, tamamen SENTETİK veri kurar.

Kullanım (önerilen): demo_baslat.bat çift tıklanır. Bat dosyası ayrı bir
demo veritabanı (demo.sqlite3) açar, bu komutu çalıştırır ve siteyi başlatır.
Asıl veritabanınız (db.sqlite3) etkilenmez.

Elle: set CAPTAKIP_SQLITE=demo.sqlite3 → migrate → demo_verisi → runserver

Bütün kayıtlar ekrandaki işlemlerle aynı servislerden geçer; bu yüzden işlem
kaydı, bildirimler, onay kuyruğu ve kural uyarıları gerçek akıştaki gibi oluşur.

Senaryolar:
  231101101 Deniz   ÇAP  düzenli ilerleyen öğrenci (uyarısız)
  231101102 Elif    ÇAP  iki dönem ders almamış (KRİTİK) + GANO tolerans uyarısı, mesaj ve belge isteği
  231101103 Kerem   ÇAP  ana dal GANO'su ikinci kez sınırın altında (KRİTİK)
  231101104 Zeynep  ÇAP  onay kuyruğunda bekleyen ders seçimi, dönem kaydı, not ve transkript
  221101105 Burak   YDP  asgari ders yükü eksik (UYARI)
  221101106 Ayşe    YDP  tüm şartlar tamam, sertifika kararı işlenmeye hazır
  221101107 Mert    YDP  CSV ile aktarıldı; program ortalaması iki dönem düşük (KRİTİK)
  231101108 Selin   ÇAP  CSV ile aktarıldı; kayıt dondurma kararı işlenmiş
  231101109 Can     ÇAP  kendi isteğiyle ayrılma kararı işlenmiş (program kapalı)
"""
import os
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Kullanici
from ogrenciler.models import AkademikDonem, Bolum, Ogrenci
from ortak.modeller import Kaynak

# Yerel demoda sabit şifreler kullanılır. Canlı sitede kod herkese açık
# olduğundan şifreler ortam değişkeniyle (Render panelinde gizli) verilir.
YONETICI_SIFRESI = os.environ.get("CAPTAKIP_DEMO_YONETICI_SIFRESI") or "Selcuk.Demo.2026"
OGRENCI_SIFRESI = os.environ.get("CAPTAKIP_DEMO_OGRENCI_SIFRESI") or "Ogrenci.Demo.2026"
SIFRE_ORTAMDAN = bool(os.environ.get("CAPTAKIP_DEMO_YONETICI_SIFRESI"))
PDF_KLASORU = Path(settings.BASE_DIR) / "docs" / "ornek_dosyalar" / "demo"


def _pdf(ad):
    yol = PDF_KLASORU / ad
    if yol.is_file():
        icerik = yol.read_bytes()
    else:  # örnek PDF yoksa en küçük geçerli PDF
        from ortak.test_yardimci import GECERLI_PDF
        icerik = GECERLI_PDF
    return SimpleUploadedFile(ad, icerik, content_type="application/pdf")


def _csv(ad, metin):
    return SimpleUploadedFile(ad, ("﻿" + metin).encode("utf-8"), content_type="text/csv")


class Command(BaseCommand):
    help = "Sunum için sentetik demo verisi kurar (boş bir veritabanında)."

    def add_arguments(self, parser):
        parser.add_argument("--bos-ise", action="store_true",
                            help="Veritabanında öğrenci varsa hata vermeden atla (canlı ortamın her açılışı için).")

    def handle(self, *args, **o):
        if o["bos_ise"] and Ogrenci.objects.exists():
            self.stdout.write("Demo verisi zaten kurulu; atlandı.")
            return
        if getattr(settings, "CANLI", False) and not (os.environ.get("CAPTAKIP_DEMO_YONETICI_SIFRESI")
                                                       and os.environ.get("CAPTAKIP_DEMO_OGRENCI_SIFRESI")):
            # Kod herkese açık: canlıda koddaki yerel demo şifreleri kullanılamaz
            raise CommandError("Canlı ortamda CAPTAKIP_DEMO_YONETICI_SIFRESI ve CAPTAKIP_DEMO_OGRENCI_SIFRESI "
                               "ortam değişkenleri zorunludur (Render → Environment).")
        if Ogrenci.objects.exists():
            raise CommandError("Bu komut yalnızca BOŞ bir demo veritabanında çalışır. "
                               "demo_baslat.bat dosyasını kullanın (asıl veritabanınıza dokunmaz).")
        call_command("baslangic_verisi", verbosity=0)
        with transaction.atomic():
            self._kur()
        self.stdout.write(self.style.SUCCESS("\nDemo verisi hazır. Giriş bilgileri:"))
        yon, ogr = ("(ortam değişkeninde)", "(ortam değişkeninde)") if SIFRE_ORTAMDAN else \
            (YONETICI_SIFRESI, OGRENCI_SIFRESI)
        self.stdout.write(f"  Koordinatör    : koordinator / {yon}")
        self.stdout.write(f"  Bölüm başkanı  : baskan / {yon}")
        self.stdout.write(f"  Öğrenciler     : öğrenci numarası / {ogr}")
        self.stdout.write("  (231101101 … 231101109, 221101105 … 221101107)")

    # ------------------------------------------------------------------
    def _kur(self):
        from aktarim import servisler as asv
        from belgeler import servisler as bsv
        from dersler import servisler as dsv
        from dersler.models import Ders
        from kurallar import servisler as ksv
        from kurallar.motor import toplu_islem
        from mesajlar import servisler as msv
        from ogrenciler import servisler as osv

        K = self.koord = self._kullanici("koordinator", "Demo", "Koordinatör", Kullanici.Rol.KOORDINATOR)
        self._kullanici("baskan", "Demo", "Bölüm Başkanı", Kullanici.Rol.BOLUM_BASKANI)
        eem = Bolum.objects.get(kod="EEM")
        d = {k: AkademikDonem.objects.get(yil=y, donem=t) for k, y, t in (
            ("g24", "2024-2025", "GUZ"), ("b25", "2024-2025", "BAHAR"), ("g25", "2025-2026", "GUZ"),
            ("b26", "2025-2026", "BAHAR"), ("g26", "2026-2027", "GUZ"))}
        ders = {x.kod: x for x in Ders.objects.all()}

        def ogrenci(no, ad, soyad, tur, kabul):
            o, _ = osv.ogrenci_ekle(yapan=K, ogrenci_no=no, ad=ad, soyad=soyad, eposta=f"{no}@ornek.edu.tr",
                                    ana_dal_bolumu=eem, tur=tur, kabul_donemi=d[kabul], kaynak=Kaynak.AKTARIM)
            return o, o.guncel_program

        def liste_kalemi(program, kod):
            return program.dersler.get(ders__kod=kod, liste_durumu="AKTIF")

        def gecmis(program, satirlar):
            """(kod, dönem, harf) — koordinatör girişi, geçmiş veri aktarımı olarak."""
            for kod, donem, harf in satirlar:
                dsv.deneme_ekle(yapan=K, ogrenci_dersi=liste_kalemi(program, kod), donem=d[donem], harf_notu=harf,
                                kaynak=Kaynak.AKTARIM)

        def ydp_listesi(program, kodlar):
            for kod in kodlar:
                dsv.ders_ekle(yapan=K, program=program, ders=ders[kod], gerekce="Yan dal ders seçimi (kayıt formu)",
                              kaynak=Kaynak.AKTARIM)

        def ana_dal(program, donem, gano, durum="AKTIF", kaynak="Ana dal transkripti (sentetik)"):
            ksv.ana_dal_kaydi_ekle(yapan=K, program=program, donem=d[donem], gano=Decimal(gano),
                                   ana_dal_durumu=durum, kaynak_aciklama=kaynak)

        def slot(program, yariyil):
            return program.dersler.filter(ders__isnull=True, yariyil=yariyil, liste_durumu="AKTIF").first()

        with toplu_islem("Demo verisi kurulumu", K):
            # 1) Deniz — düzenli ilerleyen ÇAP öğrencisi
            deniz, p = ogrenci("231101101", "Deniz", "Örnekoğlu", "CAP", "g24")
            gecmis(p, [("3301156", "g24", "BA"), ("3301351", "g24", "BB"), ("3301352", "b25", "CB"),
                       ("3301354", "b25", "AA"), ("3301452", "g25", "BA"), ("3301454", "g25", "CC"),
                       ("3301455", "g25", "BB"), ("3301456", "b26", "AA")])
            dsv.ders_ekle(yapan=K, program=p, ders=ders["3301561"], slot=slot(p, 5), gerekce="Seçmeli ders seçimi",
                          kaynak=Kaynak.AKTARIM)
            gecmis(p, [("3301561", "b26", "BB"), ("3301552", "g26", ""), ("3301553", "g26", "")])
            ana_dal(p, "b26", "3.21")

            # 2) Elif — iki dönem ders almamış, GANO tolerans aralığında
            elif_, p = ogrenci("231101102", "Elif", "Denemeci", "CAP", "g25")
            ana_dal(p, "b26", "2.61")
            bsv.istek_olustur(yapan=K, ogrenci=elif_, tur="DIGER",
                              aciklama="Ders alamadığınız dönemler için mazeret belgesi (sağlık raporu vb.) yükleyin.")

            # 3) Kerem — ana dal GANO'su ikinci kez sınırın altında
            kerem, p = ogrenci("231101103", "Kerem", "Sentetik", "CAP", "g25")
            gecmis(p, [("3301156", "g25", "CC"), ("3301351", "g25", "DC"), ("3301352", "b26", "FF"),
                       ("3301354", "b26", "CB"), ("3301352", "g26", "")])
            ana_dal(p, "g25", "2.60")
            ana_dal(p, "b26", "2.45")
            osv.koordinator_notu_ekle(yapan=K, ogrenci=kerem, metin="Ana dal GANO düşüşü hakkında öğrenciyle "
                                      "görüşüldü; bir sonraki dönem sonu yakından izlenecek. (sentetik)")

            # 4) Zeynep — onay kuyruğunda bekleyen kayıtlar
            zeynep, p = ogrenci("231101104", "Zeynep", "Örnekçi", "CAP", "b26")
            gecmis(p, [("3301156", "b26", "BA"), ("3301352", "b26", "")])
            ana_dal(p, "b26", "3.05")

            # 5) Burak — YDP, asgari ders yükü eksik
            burak, p = ogrenci("221101105", "Burak", "Denemeoğlu", "YDP", "g25")
            ydp_listesi(p, ["3301351", "3301352", "3301354"])
            gecmis(p, [("3301351", "g25", "BB"), ("3301352", "b26", "BA"), ("3301354", "g26", "")])
            ana_dal(p, "b26", "2.95")

            # 6) Ayşe — YDP tamamlandı, sertifika kararına hazır
            ayse, p = ogrenci("221101106", "Ayşe", "Yandal", "YDP", "g24")
            kodlar = ["3301156", "3301351", "3301352", "3301354", "3301452", "3301454", "3301455", "3301456"]
            ydp_listesi(p, kodlar)
            gecmis(p, list(zip(kodlar, ["g24", "g24", "b25", "b25", "g25", "g25", "b26", "b26"],
                               ["BA", "BB", "AA", "CB", "BB", "BA", "CC", "AA"])))
            ana_dal(p, "b26", "3.40", "MEZUN", "Mezuniyet belgesi (sentetik)")
            bsv.belge_yukle(yapan=K, ogrenci=ayse, dosya=_pdf("kurul_karari_sertifika.pdf"), tur="KURUL_KARARI",
                            aciklama="FYK 2026/41-7 sertifika kararı")

            # 7-8) Mert ve Selin — CSV aktarımıyla gelen öğrenciler
            ogr = asv.yukle(yapan=K, tur="OGRENCI", dosya=_csv("eski_kayitlar.csv", (
                "Öğrenci No;Adı;Soyadı;E-posta;Bölüm;Program;Kabul Dönemi\n"
                "221101107;Mert;Notlu;221101107@ornek.edu.tr;EEM;YDP;2025-2026 Güz\n"
                "231101108;Selin;Dondurmacı;231101108@ornek.edu.tr;EEM;ÇAP;2025-2026 Güz\n")))
            asv.uygula(yapan=K, islem=ogr)
            mert = Ogrenci.objects.get(ogrenci_no="221101107")
            ydp_listesi(mert.guncel_program, ["3301351", "3301352", "3301354"])
            notlar = asv.yukle(yapan=K, tur="NOT", dosya=_csv("eski_notlar.csv", (
                "ogrenci_no;ders_kodu;donem;harf_notu\n"
                "221101107;3301351;2025-2026 Güz;DD\n"
                "221101107;3301352;2025-2026 Bahar;FD\n"
                "221101107;3301354;2025-2026 Bahar;FF\n"
                "231101108;3301156;2025-2026 Güz;BB\n"
                "231101108;3301351;2025-2026 Güz;CB\n"
                "231101108;3301352;2026-2027 Güz;\n")))
            asv.uygula(yapan=K, islem=notlar)
            anadal = asv.yukle(yapan=K, tur="ANA_DAL", dosya=_csv("eski_ana_dal.csv", (
                "ogrenci_no;donem;gano;ana_dal_durumu;kaynak\n"
                "221101107;2025-2026 Bahar;2,85;Aktif;Öğrenci işleri listesi (sentetik)\n"
                "231101108;2025-2026 Bahar;2,90;Aktif;Öğrenci işleri listesi (sentetik)\n")))
            asv.uygula(yapan=K, islem=anadal)
            selin = Ogrenci.objects.get(ogrenci_no="231101108")
            karar_belgesi = bsv.belge_yukle(yapan=K, ogrenci=selin, dosya=_pdf("kurul_karari_dondurma.pdf"),
                                            tur="KURUL_KARARI", aciklama="FYK 2026/08-4 kayıt dondurma")
            ksv.karar_isle(yapan=K, program=selin.guncel_program, tur="DONDURMA", kurul="Fakülte Yönetim Kurulu",
                           karar_tarihi=self._tarih(2026, 2, 20), karar_sayisi="2026/08-4",
                           gerekce="Sağlık mazereti nedeniyle 2025-2026 Bahar yarıyılı için kayıt dondurma.",
                           dayanak_belge=karar_belgesi, donem=d["b26"])

            # 9) Can — kendi isteğiyle ayrıldı
            can, p = ogrenci("231101109", "Can", "Ayrılmaz", "CAP", "g25")
            gecmis(p, [("3301156", "g25", "CC")])
            belge = bsv.belge_yukle(yapan=K, ogrenci=can, dosya=_pdf("kurul_karari_ayrilma.pdf"), tur="KURUL_KARARI",
                                    aciklama="FYK 2026/37-2 ayrılma")
            ksv.karar_isle(yapan=K, program=p, tur="AYRILMA", kurul="Fakülte Yönetim Kurulu",
                           karar_tarihi=self._tarih(2026, 9, 10), karar_sayisi="2026/37-2",
                           gerekce="Öğrencinin kendi isteğiyle programdan ayrılma talebi kabul edildi.",
                           dayanak_belge=belge)

        # Tüm öğrencilere demo şifresi (ilk girişte şifre değiştirme istenmez)
        # Şifre özeti bir kez hesaplanır (canlıdaki düşük işlemcide ilk açılış hızlansın)
        from django.contrib.auth.hashers import make_password
        Kullanici.objects.filter(rol=Kullanici.Rol.OGRENCI).update(password=make_password(OGRENCI_SIFRESI),
                                                                  sifre_degistirmeli=False)

        # Öğrencinin kendi yaptığı işlemler (onay kuyruğuna düşer)
        zk = zeynep.kullanici
        p = zeynep.guncel_program
        dsv.ders_ekle(yapan=zk, program=p, ders=ders["3301568"], slot=slot(p, 5))
        dsv.deneme_ekle(yapan=zk, ogrenci_dersi=liste_kalemi(p, "3301351"), donem=d["g26"])
        bsv.belge_yukle(yapan=zk, ogrenci=zeynep, dosya=_pdf("transkript_2025_bahar.pdf"), tur="TRANSKRIPT",
                        donem=d["b26"], aciklama="2025-2026 Bahar ÇAP not belgesi")
        dsv.not_gir(yapan=zk, deneme=liste_kalemi(p, "3301352").denemeler.get(donem=d["b26"]), harf_notu="BB")

        # Mesajlar
        msv.mesaj_gonder(yapan=elif_.kullanici, ogrenci=elif_, metin=(
            "Merhaba hocam, geçen iki dönem sağlık sorunlarım nedeniyle ÇAP derslerine kayıt olamadım. "
            "Programdan çıkarılmamak için ne yapmam gerekiyor?"))
        msv.mesaj_gonder(yapan=K, ogrenci=kerem, metin=(
            "Merhaba Kerem, ana dal ortalaman ikinci kez 2,72'nin altına düştü. Bu hafta ofis saatinde görüşelim."))
        msv.mesaj_gonder(yapan=kerem.kullanici, ogrenci=kerem, metin="Tamam hocam, perşembe 14.00'te gelirim.")
        msv.mesaj_gonder(yapan=zk, ogrenci=zeynep, metin=(
            "Hocam 2025-2026 Bahar transkriptimi yükledim, İşletim Sistemleri notumu da girdim. Onayınızı bekliyorum."))
        msv.okundu_isaretle(okuyan=K, ogrenci=kerem)

    def _kullanici(self, kadi, ad, soyad, rol):
        k = Kullanici(username=kadi, first_name=ad, last_name=soyad, email=f"{kadi}@ornek.edu.tr", rol=rol,
                      sifre_degistirmeli=False)
        k.set_password(YONETICI_SIFRESI)
        k.save()
        return k

    @staticmethod
    def _tarih(y, a, g):
        import datetime
        return datetime.date(y, a, g)
