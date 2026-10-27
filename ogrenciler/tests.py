"""2. adım testleri: öğrenci ekleme, protokol yükleme, erişim, AKTS hesabı."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from accounts.models import Kullanici
from denetim.models import IslemKaydi
from dersler.models import Ders, DersDenemesi, OgrenciDersi
from ortak.modeller import OnayDurumu

from . import servisler
from .models import AkademikDonem, Bolum, Ogrenci, ProgramKaydi

SIFRE = "GucluSifre!2026"


def kullanici(username, rol):
    k = Kullanici(username=username, rol=rol, email=f"{username}@ornek.edu.tr", sifre_degistirmeli=False)
    k.set_password(SIFRE)
    k.save()
    return k


class TemelVeri(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("baslangic_verisi", verbosity=0)
        cls.koord = kullanici("koord", Kullanici.Rol.KOORDINATOR)
        cls.baskan = kullanici("baskan", Kullanici.Rol.BOLUM_BASKANI)
        cls.eem = Bolum.objects.get(kod="EEM")
        cls.bm = Bolum.objects.get(kod="BM")
        cls.guz = AkademikDonem.objects.get(yil="2025-2026", donem="GUZ")

    def ogrenci_ekle(self, no="231101001", tur="CAP", bolum=None):
        return servisler.ogrenci_ekle(yapan=self.koord, ogrenci_no=no, ad="Deneme", soyad="Öğrenci",
                                      eposta=f"{no}@ornek.edu.tr", ana_dal_bolumu=bolum or self.eem,
                                      tur=tur, kabul_donemi=self.guz)


class OgrenciEklemeTestleri(TemelVeri):
    def test_cap_ogrencisine_protokol_yuklenir(self):
        ogrenci, gecici = self.ogrenci_ekle()
        program = ogrenci.guncel_program
        self.assertEqual(program.dersler.count(), 28)
        self.assertEqual(program.akts_ozeti()["toplam"], 135)
        self.assertEqual(program.dersler.filter(ders__isnull=True).count(), 8)  # seçmeli slotları
        self.assertTrue(all(d.onay_durumu == OnayDurumu.ONAYLANDI for d in program.dersler.all()))

    def test_ogrenci_hesabi_gecici_sifreyle_acilir(self):
        ogrenci, gecici = self.ogrenci_ekle()
        k = ogrenci.kullanici
        self.assertEqual(k.username, "231101001")
        self.assertEqual(k.rol, Kullanici.Rol.OGRENCI)
        self.assertTrue(k.sifre_degistirmeli)
        self.assertTrue(k.check_password(gecici))

    def test_islem_kaydi_dusulur(self):
        self.ogrenci_ekle()
        kayit = IslemKaydi.objects.get(islem="OGRENCI_EKLENDI")
        self.assertEqual(kayit.ogrenci_no, "231101001")
        self.assertEqual(kayit.yeni_deger["ders_sayisi"], 28)

    def test_ydp_ogrencisinin_listesi_bos_baslar(self):
        ogrenci, _ = self.ogrenci_ekle(tur="YDP")
        self.assertEqual(ogrenci.guncel_program.dersler.count(), 0)

    def test_protokolu_olmayan_bolumden_cap_eklenemez(self):
        with self.assertRaises(ValidationError):
            self.ogrenci_ekle(bolum=self.bm)
        self.assertFalse(Ogrenci.objects.exists())
        self.assertFalse(Kullanici.objects.filter(username="231101001").exists())  # işlem geri alındı

    def test_ayni_numara_iki_kez_eklenemez(self):
        self.ogrenci_ekle()
        with self.assertRaises(ValidationError):
            self.ogrenci_ekle()

    def test_ikinci_acik_program_acilamaz(self):
        ogrenci, _ = self.ogrenci_ekle()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProgramKaydi.objects.create(ogrenci=ogrenci, tur="YDP", kabul_donemi=self.guz)

    def test_koordinator_ekrandan_ogrenci_ekler(self):
        self.client.force_login(self.koord)
        cevap = self.client.post(reverse("ogrenci_ekle"), {
            "ogrenci_no": "231101009", "ad": "Ali", "soyad": "Veli", "eposta": "ali@ornek.edu.tr",
            "ana_dal_bolumu": self.eem.pk, "tur": "CAP", "kabul_donemi": self.guz.pk})
        self.assertRedirects(cevap, reverse("ogrenci_karti", args=["231101009"]))

    def test_gecersiz_ogrenci_numarasi_reddedilir(self):
        self.client.force_login(self.koord)
        cevap = self.client.post(reverse("ogrenci_ekle"), {
            "ogrenci_no": "12ab", "ad": "Ali", "soyad": "Veli", "eposta": "ali@ornek.edu.tr",
            "ana_dal_bolumu": self.eem.pk, "tur": "CAP", "kabul_donemi": self.guz.pk})
        self.assertEqual(cevap.status_code, 200)
        self.assertFalse(Ogrenci.objects.exists())


class ErisimTestleri(TemelVeri):
    def setUp(self):
        self.a, _ = self.ogrenci_ekle("231101001")
        self.b, _ = self.ogrenci_ekle("231101002")
        for o in (self.a, self.b):
            o.kullanici.sifre_degistirmeli = False
            o.kullanici.save()

    def test_ogrenci_kendi_kartini_gorur(self):
        self.client.force_login(self.a.kullanici)
        self.assertEqual(self.client.get(reverse("ogrenci_karti", args=["231101001"])).status_code, 200)

    def test_ogrenci_baskasinin_kartini_goremez_idor(self):
        self.client.force_login(self.a.kullanici)
        self.assertEqual(self.client.get(reverse("ogrenci_karti", args=["231101002"])).status_code, 403)
        # Var olmayan numara da aynı cevabı alır (kayıt varlığı sızdırılmaz)
        self.assertEqual(self.client.get(reverse("ogrenci_karti", args=["999999999"])).status_code, 403)

    def test_ogrenci_listeyi_ve_katalog_duzenlemeyi_goremez(self):
        self.client.force_login(self.a.kullanici)
        self.assertEqual(self.client.get(reverse("ogrenci_listesi")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ders_ekle")).status_code, 403)

    def test_ogrenci_ana_sayfada_kendi_kartina_yonlendirilir(self):
        self.client.force_login(self.a.kullanici)
        self.assertRedirects(self.client.get(reverse("anasayfa")), reverse("ogrenci_karti", args=["231101001"]))

    def test_koordinator_notunu_ogrenci_goremez(self):
        servisler.koordinator_notu_ekle(yapan=self.koord, ogrenci=self.a, metin="GİZLİ-NOT-123")
        self.client.force_login(self.a.kullanici)
        self.assertNotContains(self.client.get(reverse("ogrenci_karti", args=["231101001"])), "GİZLİ-NOT-123")
        self.client.force_login(self.baskan)
        self.assertContains(self.client.get(reverse("ogrenci_karti", args=["231101001"])), "GİZLİ-NOT-123")

    def test_bolum_baskani_gorur_ama_ekleyemez(self):
        self.client.force_login(self.baskan)
        self.assertEqual(self.client.get(reverse("ogrenci_listesi")).status_code, 200)
        self.assertEqual(self.client.get(reverse("ogrenci_karti", args=["231101001"])).status_code, 200)
        cevap = self.client.post(reverse("koordinator_notu_ekle", args=["231101001"]), {"metin": "x"})
        self.assertEqual(cevap.status_code, 403)

    def test_not_alaninda_xss_kacisi(self):
        servisler.koordinator_notu_ekle(yapan=self.koord, ogrenci=self.a, metin="<script>alert(1)</script>")
        self.client.force_login(self.koord)
        cevap = self.client.get(reverse("ogrenci_karti", args=["231101001"]))
        self.assertNotContains(cevap, "<script>alert(1)</script>")
        self.assertContains(cevap, "&lt;script&gt;")


class AktsVeSilinmezlikTestleri(TemelVeri):
    def setUp(self):
        self.ogrenci, _ = self.ogrenci_ekle()
        self.program = self.ogrenci.guncel_program

    def deneme(self, kod, durum, onay):
        od = self.program.dersler.get(ders__kod=kod)
        return DersDenemesi.objects.create(ogrenci_dersi=od, donem=self.guz, durum=durum, onay_durumu=onay)

    def test_yalnizca_onayli_gecme_akts_ye_sayilir(self):
        self.deneme("3301156", "GECTI", OnayDurumu.ONAYLANDI)   # 4 AKTS
        self.deneme("3301351", "GECTI", OnayDurumu.BEKLIYOR)    # sayılmaz
        self.deneme("3301352", "KALDI", OnayDurumu.ONAYLANDI)   # sayılmaz
        self.assertEqual(self.program.akts_ozeti()["tamamlanan"], 4)

    def test_muaf_ders_tamamlanmis_sayilir(self):
        od = self.program.dersler.get(ders__kod="3301354")
        od.liste_durumu = OgrenciDersi.ListeDurumu.MUAF
        od.save()
        self.assertEqual(self.program.akts_ozeti()["tamamlanan"], 4)

    def test_cikarilan_ders_toplamdan_duser(self):
        od = self.program.dersler.get(ders__kod="3301456")
        od.liste_durumu = OgrenciDersi.ListeDurumu.CIKARILDI
        od.save()
        self.assertEqual(self.program.akts_ozeti()["toplam"], 131)

    def test_katalog_degisikligi_ogrenci_aktsini_bozmaz(self):
        Ders.objects.filter(kod="3301454").update(akts=8)
        self.assertEqual(self.program.dersler.get(ders__kod="3301454").akts, 5)

    def test_kayitlar_silinemez(self):
        with self.assertRaises(PermissionDenied):
            self.program.dersler.first().delete()
        with self.assertRaises(PermissionDenied):
            OgrenciDersi.objects.all().delete()
        with self.assertRaises(PermissionDenied):
            self.ogrenci.delete()


class KatalogTestleri(TemelVeri):
    def test_ders_duzenleme_gerekce_ister_ve_eski_degeri_kaydeder(self):
        ders = Ders.objects.get(kod="3301456")
        self.client.force_login(self.koord)
        veri = {"kod": "3301456", "ad": "Mobil Uygulama Geliştirme", "akts": 4, "yariyil": 4, "tur": "ZORUNLU"}
        cevap = self.client.post(reverse("ders_duzenle", args=[ders.pk]), veri)
        self.assertEqual(cevap.status_code, 200)  # gerekçesiz reddedildi
        veri["gerekce"] = "Müfredat güncellemesi"
        self.client.post(reverse("ders_duzenle", args=[ders.pk]), veri)
        kayit = IslemKaydi.objects.get(islem="DERS_GUNCELLENDI")
        self.assertEqual(kayit.eski_deger["ad"], "Mobil Programlama")
        self.assertEqual(kayit.yeni_deger["ad"], "Mobil Uygulama Geliştirme")
        self.assertEqual(kayit.aciklama, "Müfredat güncellemesi")
