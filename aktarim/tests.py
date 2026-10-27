"""8. adım testleri: CSV ile geçmiş veri aktarımı."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.models import Kullanici
from denetim.models import IslemKaydi
from dersler.models import DersDenemesi
from dersler import servisler as dsv
from dersler.tests import SIFRE, Temel
from kurallar.models import Uyari
from ogrenciler.models import Ogrenci
from ortak.modeller import Kaynak

from . import okuyucu, servisler as sv
from .models import AktarimIslemi

OGRENCI_CSV = """Öğrenci No;Adı;Soyadı;E-posta;Bölüm;Program;Kabul Dönemi
231101051;Ayşe;Örnekçi;231101051@ornek.edu.tr;EEM;ÇAP;2025-2026 Güz
221101052;Mert;Sentetikoğlu;221101052@ornek.edu.tr;eem;Yan Dal;2025-2026/2
"""


def csv_dosya(metin, ad="veri.csv", kodlama="utf-8"):
    return SimpleUploadedFile(ad, metin.encode(kodlama), content_type="text/csv")


class OkuyucuTestleri(Temel):
    def test_sutun_adlari_esnek_kodlama_ve_ayirici_bulunur(self):
        metin = "OGRENCI_NO,Ders Kodu,Akademik Dönem,Başarı Notu\n231101001,3301156,2025-2026 Güz,BA\n"
        sonuc = okuyucu.oku(metin.encode("cp1254"), "NOT")
        self.assertEqual(sonuc["kodlama"], "cp1254")
        self.assertEqual(sonuc["ayirac"], ",")
        self.assertEqual(sonuc["satirlar"][0][1], {"ogrenci_no": "231101001", "ders_kodu": "3301156",
                                                   "donem": "2025-2026 Güz", "harf_notu": "BA"})

    def test_bicim_hatalari(self):
        for icerik, beklenen in ((b"", "boş"), (b"\x89PNG\r\n\x00\x00", "metin"),
                                 ("ogrenci_no;donem\n1;2\n".encode(), "Eksik sütun"),
                                 ("ogrenci_no;ders_kodu;donem\n".encode(), "satır yok")):
            with self.subTest(beklenen=beklenen), self.assertRaisesMessage(ValidationError, beklenen):
                okuyucu.oku(icerik, "NOT")
        cok = "ogrenci_no;ders_kodu;donem\n" + "1;2;3\n" * (okuyucu.MAKS_SATIR + 1)
        with self.assertRaisesMessage(ValidationError, "en fazla"):
            okuyucu.oku(cok.encode(), "NOT")

    def test_sablonlar_excel_uyumlu_ve_okunabilir(self):
        for tur in okuyucu.SABLONLAR:
            metin = okuyucu.sablon_metni(tur)
            self.assertTrue(metin.startswith("﻿"))
            self.assertEqual(okuyucu.oku(metin.encode("utf-8"), tur)["ayirac"], ";")


class OgrenciAktarimiTestleri(Temel):
    def test_onizleme_veritabanina_hicbir_sey_yazmaz(self):
        ogrenci_sayisi, kullanici_sayisi = Ogrenci.objects.count(), Kullanici.objects.count()
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        self.assertEqual((islem.satir_sayisi, islem.hata_sayisi), (2, 0))
        self.assertTrue(islem.uygulanabilir_mi)
        self.assertEqual(Ogrenci.objects.count(), ogrenci_sayisi)
        self.assertEqual(Kullanici.objects.count(), kullanici_sayisi)
        self.assertFalse(IslemKaydi.objects.filter(islem="OGRENCI_EKLENDI", ogrenci_no="231101051").exists())
        self.assertIn("231101051 Ayşe Örnekçi (CAP", islem.onizleme[0]["mesaj"])

    def test_uygulama_ogrencileri_aktarim_kaynagiyla_ekler(self):
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        islem, sifreler = sv.uygula(yapan=self.koord, islem=islem)
        self.assertEqual(islem.durum, AktarimIslemi.Durum.UYGULANDI)
        self.assertEqual([s["ogrenci_no"] for s in sifreler], ["231101051", "221101052"])
        ydp = Ogrenci.objects.get(ogrenci_no="221101052").guncel_program
        self.assertEqual((ydp.tur, str(ydp.kabul_donemi)), ("YDP", "2025-2026 Bahar"))
        cap = Ogrenci.objects.get(ogrenci_no="231101051").guncel_program
        self.assertEqual(cap.dersler.count(), 28)
        self.assertTrue(all(d.kaynak == Kaynak.AKTARIM for d in cap.dersler.all()))
        self.assertTrue(IslemKaydi.objects.filter(islem="AKTARIM_UYGULANDI", nesne_id=str(islem.pk)).exists())
        # Aynı dosya ikinci kez uygulanamaz
        ikinci = sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        self.assertFalse(ikinci.uygulanabilir_mi)
        self.assertIn("daha önce uygulandı", ikinci.onizleme[0]["mesaj"])

    def test_hatali_satir_varsa_hicbir_satir_yazilmaz(self):
        metin = OGRENCI_CSV + ("231101053;=HYPERLINK(\"x\");Kişi;x@ornek.edu.tr;EEM;ÇAP;2025-2026 Güz\n"
                               "231101054;Ali;Veli;gecersiz-eposta;EEM;ÇAP;2025-2026 Güz\n"
                               "231101055;Can;Can;c@ornek.edu.tr;MAK;ÇAP;2025-2026 Güz\n"
                               "231101051;Ayşe;Tekrar;a@ornek.edu.tr;EEM;ÇAP;2025-2026 Güz\n"
                               "231101056;Ece;Ece;e@ornek.edu.tr;EEM;ÇAP;2030-2031 Güz\n")
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(metin), tur="OGRENCI")
        hatalar = {s["satir"]: s["mesaj"] for s in islem.onizleme if s["durum"] == "HATA"}
        self.assertEqual(set(hatalar), {4, 5, 6, 7, 8})
        self.assertIn("'=' ile başlayamaz", hatalar[4])  # formül enjeksiyonu
        self.assertIn("tanınmadı", hatalar[6])
        self.assertIn("zaten kayıtlı", hatalar[7])         # dosya içi tekrar da yakalanır
        self.assertFalse(islem.uygulanabilir_mi)
        with self.assertRaises(ValidationError):
            sv.uygula(yapan=self.koord, islem=islem)
        self.assertFalse(Ogrenci.objects.filter(ogrenci_no="231101051").exists())

    def test_yalnizca_koordinator_aktarim_yapar(self):
        for yapan in (self.baskan, self.cap_k):
            with self.assertRaises(PermissionDenied):
                sv.yukle(yapan=yapan, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        with self.assertRaises(PermissionDenied):
            sv.uygula(yapan=self.baskan, islem=islem)

    def test_aktarim_kaydi_degistirilemez_silinemez(self):
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        islem.dosya_adi = "baska.csv"
        with self.assertRaises(PermissionDenied):
            islem.save(update_fields=["dosya_adi"])
        with self.assertRaises(PermissionDenied):
            islem.delete()

    def test_csv_disi_dosya_reddedilir(self):
        with self.assertRaisesMessage(ValidationError, ".csv"):
            sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV, ad="veri.xlsx"), tur="OGRENCI")
        self.assertFalse(AktarimIslemi.objects.exists())


class NotVeAnaDalAktarimiTestleri(Temel):
    def test_not_gecmisi_aktarimi(self):
        metin = ("ogrenci_no;ders_kodu;donem;harf_notu\n"
                 "231101001;3301156;2025-2026 Güz;BA\n"
                 "231101001;3301352;2025-2026/2;ff\n"
                 "231101001;3301561;2025-2026 Bahar;CC\n"     # seçmeli → boş slota yerleşir
                 "231101002;3301351;2025-2026 Güz;AA\n")      # YDP → yan dal listesine eklenir
        once = self.prog.degerlendirmeler.count()
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(metin), tur="NOT")
        self.assertEqual(islem.hata_sayisi, 0, islem.onizleme)
        self.assertEqual(self.prog.degerlendirmeler.count(), once)  # önizleme değerlendirme de yazmaz
        sv.uygula(yapan=self.koord, islem=islem)
        d = DersDenemesi.objects.get(ogrenci_dersi__program_kaydi=self.prog, ogrenci_dersi__ders__kod="3301156")
        self.assertEqual((d.durum, d.harf_notu, d.kaynak), ("GECTI", "BA", Kaynak.AKTARIM))
        self.assertEqual(DersDenemesi.objects.get(ogrenci_dersi__ders__kod="3301352",
                                                  ogrenci_dersi__program_kaydi=self.prog).durum, "KALDI")
        secmeli = self.prog.dersler.get(ders__kod="3301561")
        self.assertIsNotNone(secmeli.doldurdugu_slot)
        self.assertTrue(self.ydp.guncel_program.dersler.filter(ders__kod="3301351").exists())
        # Kurallar her program için bir kez değerlendirildi (satır başına değil)
        self.assertEqual(self.prog.degerlendirmeler.count(), once + 1)
        self.assertFalse(self.prog.uyarilar.filter(kural="ders_almama", durum="ACIK").exists())

    def test_not_satiri_hatalari(self):
        metin = ("ogrenci_no;ders_kodu;donem;harf_notu\n"
                 "999999999;3301156;2025-2026 Güz;BA\n"
                 "231101001;9999999;2025-2026 Güz;BA\n"
                 "231101001;3301156;2025-2026 Kış;BA\n"
                 "231101001;3301156;2025-2026 Güz;XY\n"
                 "231101001;3301156;2027-2028 Güz;BA\n"
                 "231101001;3301156;2024-2025 Güz;BA\n"
                 "231101001;3301156;2025-2026 Güz;BA\n"
                 "231101001;3301156;2025-2026 Bahar;BB\n")  # aynı ders geçildikten sonra tekrar
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(metin), tur="NOT")
        hatalar = {s["satir"]: s["mesaj"] for s in islem.onizleme if s["durum"] == "HATA"}
        self.assertEqual(set(hatalar), {2, 3, 4, 5, 6, 7, 9})
        self.assertIn("sistemde yok", hatalar[2])
        self.assertIn("katalogda yok", hatalar[3])
        self.assertIn("Güz, Bahar veya Yaz", hatalar[4])
        self.assertIn("harf notu", hatalar[5])
        self.assertIn("henüz başlamadı", hatalar[6])
        self.assertIn("kabul döneminden", hatalar[7])
        self.assertIn("zaten geçtiniz", hatalar[9])

    def test_onizlemeden_sonra_veri_degisirse_hicbir_satir_yazilmaz(self):
        metin = "ogrenci_no;ders_kodu;donem;harf_notu\n231101001;3301156;2025-2026 Güz;BA\n" \
                "231101001;3301351;2025-2026 Güz;BB\n"
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(metin), tur="NOT")
        self.assertTrue(islem.uygulanabilir_mi)
        dsv.deneme_ekle(yapan=self.koord, ogrenci_dersi=self.ders("3301351"), donem=self.guz, harf_notu="CC")
        with self.assertRaisesMessage(ValidationError, "Hiçbir satır yazılmadı"):
            sv.uygula(yapan=self.koord, islem=islem)
        islem.refresh_from_db()
        self.assertEqual((islem.durum, islem.hata_sayisi), ("ONIZLENDI", 1))
        self.assertFalse(DersDenemesi.objects.filter(ogrenci_dersi__ders__kod="3301156",
                                                     ogrenci_dersi__program_kaydi=self.prog).exists())

    def test_ana_dal_aktarimi_kurallari_calistirir(self):
        metin = "Öğrenci No;Dönem;AGNO;Durum;Kaynak\n231101001;2025-2026 Güz;2,60;Aktif;\n" \
                "231101001;2025-2026 Bahar;2.40;;Öğrenci işleri yazısı\n231101002;2025-2026 Bahar;5;Aktif;\n"
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(metin), tur="ANA_DAL")
        self.assertEqual([s["satir"] for s in islem.onizleme if s["durum"] == "HATA"], [4])
        metin = "\n".join(metin.splitlines()[:3]) + "\n"
        islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(metin), tur="ANA_DAL")
        sv.uygula(yapan=self.koord, islem=islem)
        self.assertEqual(self.prog.ana_dal_kayitlari.count(), 2)
        self.assertEqual(self.prog.ana_dal_kayitlari.get(gano="2.60").kaynak_aciklama, f"CSV aktarımı #{islem.pk}")
        u = self.prog.uyarilar.get(kural="ana_dal_gano", durum=Uyari.Durum.ACIK)
        self.assertEqual(u.seviye, Uyari.Seviye.KRITIK)


class EkranTestleri(Temel):
    def setUp(self):
        super().setUp()
        self.cap_k.set_password(SIFRE)
        self.cap_k.save()

    def test_ogrenci_aktarim_ekranini_acamaz(self):
        self.client.login(username=self.cap_k.username, password=SIFRE)
        self.assertEqual(self.client.get(reverse("aktarim_listesi")).status_code, 403)

    def test_bolum_baskani_gorur_yukleyemez(self):
        self.client.login(username="baskan", password=SIFRE)
        r = self.client.get(reverse("aktarim_listesi"))
        self.assertContains(r, "Aktarım geçmişi")
        self.assertNotContains(r, "Yükle ve önizle")
        self.client.post(reverse("aktarim_listesi"), {"tur": "OGRENCI", "dosya": csv_dosya(OGRENCI_CSV)})
        self.assertFalse(AktarimIslemi.objects.exists())

    def test_koordinator_yukler_onizler_uygular(self):
        self.client.login(username="koord", password=SIFRE)
        r = self.client.post(reverse("aktarim_listesi"), {"tur": "OGRENCI", "dosya": csv_dosya(OGRENCI_CSV)},
                             follow=True)
        self.assertContains(r, "hiçbir şey yazılmadı")
        islem = AktarimIslemi.objects.get()
        r = self.client.post(reverse("aktarim_uygula", args=[islem.pk]))
        self.assertContains(r, "Geçici şifreler yalnızca şimdi gösteriliyor")
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertContains(self.client.get(reverse("aktarim_detay", args=[islem.pk])), "Uygulandı")
        r = self.client.get(reverse("aktarim_sablon", args=["NOT"]))
        self.assertEqual(r["Content-Type"], "text/csv; charset=utf-8")

    def test_bicim_hatasi_formda_gosterilir(self):
        self.client.login(username="koord", password=SIFRE)
        r = self.client.post(reverse("aktarim_listesi"),
                             {"tur": "NOT", "dosya": csv_dosya("a;b\n1;2\n")})
        self.assertContains(r, "Eksik sütun")
        self.assertFalse(AktarimIslemi.objects.exists())


class TopluIslemIcindeOnizlemeTestleri(Temel):
    """PostgreSQL'de bulunan hata: dışta bir toplu işlem varken yapılan önizleme,
    geri alınan program kayıtlarını dıştaki değerlendirme listesine sızdırıyordu."""

    def test_onizleme_geri_alinan_kayitlari_sizdirmaz(self):
        from kurallar.motor import toplu_islem
        with toplu_islem("test", self.koord):
            islem = sv.yukle(yapan=self.koord, dosya=csv_dosya(OGRENCI_CSV), tur="OGRENCI")
        self.assertEqual(islem.hata_sayisi, 0)
        self.assertFalse(Ogrenci.objects.filter(ogrenci_no="231101051").exists())
