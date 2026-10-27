"""3. adım testleri: onay mekanizması, kilitleme, red, düzeltme, iptal."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Kullanici
from denetim.models import IslemKaydi
from ogrenciler import servisler as osv
from ogrenciler.models import AkademikDonem, Bolum
from belgeler import servisler as bsv
from ortak.modeller import Kaynak, OnayDurumu
from ortak.test_yardimci import GeciciDosyaKlasoru, pdf

from . import servisler as sv
from .models import Ders, DersDenemesi, OgrenciDersi

SIFRE = "GucluSifre!2026"


def kullanici(username, rol):
    k = Kullanici(username=username, rol=rol, email=f"{username}@ornek.edu.tr", sifre_degistirmeli=False)
    k.set_password(SIFRE)
    k.save()
    return k


class Temel(GeciciDosyaKlasoru, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("baslangic_verisi", verbosity=0)
        cls.koord = kullanici("koord", Kullanici.Rol.KOORDINATOR)
        cls.baskan = kullanici("baskan", Kullanici.Rol.BOLUM_BASKANI)
        cls.eem = Bolum.objects.get(kod="EEM")
        cls.guz = AkademikDonem.objects.get(yil="2025-2026", donem="GUZ")
        cls.bahar = AkademikDonem.objects.get(yil="2025-2026", donem="BAHAR")

    def setUp(self):
        self.cap = self._ogrenci("231101001", "CAP")
        self.ydp = self._ogrenci("231101002", "YDP")
        self.cap_k = self.cap.kullanici
        self.prog = self.cap.guncel_program

    def _ogrenci(self, no, tur):
        o, _ = osv.ogrenci_ekle(yapan=self.koord, ogrenci_no=no, ad="Test", soyad="Öğrenci",
                                eposta=f"{no}@ornek.edu.tr", ana_dal_bolumu=self.eem, tur=tur,
                                kabul_donemi=self.guz)
        o.kullanici.sifre_degistirmeli = False
        o.kullanici.save()
        return o

    def transkript(self, donem=None):
        """Not girişinden önce zorunlu olan dönem transkriptini yükler."""
        return bsv.belge_yukle(yapan=self.cap_k, ogrenci=self.cap, dosya=pdf("transkript.pdf"),
                               tur="TRANSKRIPT", donem=donem or self.guz)

    def ders(self, kod, program=None):
        return (program or self.prog).dersler.get(ders__kod=kod, liste_durumu="AKTIF")

    def slot(self, yariyil=5):
        return self.prog.dersler.filter(ders__isnull=True, yariyil=yariyil, liste_durumu="AKTIF").first()


class DersSecimiTestleri(Temel):
    def test_cap_ogrencisi_slot_doldurur_onaya_kadar_bekler(self):
        od = sv.ders_ekle(yapan=self.cap_k, program=self.prog, ders=Ders.objects.get(kod="3301561"), slot=self.slot())
        self.assertEqual(od.onay_durumu, OnayDurumu.BEKLIYOR)
        self.assertEqual(od.slot_aciklama, "5. Yarıyıl Teknik Seçmeli Ders")
        self.assertEqual(self.prog.akts_ozeti()["toplam"], 135)  # bekleyen kalem toplamı değiştirmez
        sv.onayla(yapan=self.koord, kayit=od)
        od.doldurdugu_slot.refresh_from_db()
        self.assertEqual(od.doldurdugu_slot.liste_durumu, OgrenciDersi.ListeDurumu.CIKARILDI)
        self.assertEqual(self.prog.akts_ozeti()["toplam"], 135)  # slot yerine ders: toplam aynı

    def test_cap_ogrencisi_protokol_disi_ders_ekleyemez(self):
        with self.assertRaises(ValidationError):
            sv.ders_ekle(yapan=self.cap_k, program=self.prog, ders=Ders.objects.get(kod="3301561"))

    def test_slot_yalnizca_secmeli_dersle_doldurulur(self):
        with self.assertRaises(ValidationError):
            sv.ders_ekle(yapan=self.cap_k, program=self.prog, ders=Ders.objects.get(kod="3301454"), slot=self.slot())

    def test_ayni_slot_icin_ikinci_bekleyen_secim_olmaz(self):
        slot = self.slot()
        sv.ders_ekle(yapan=self.cap_k, program=self.prog, ders=Ders.objects.get(kod="3301561"), slot=slot)
        with self.assertRaises(ValidationError):
            sv.ders_ekle(yapan=self.cap_k, program=self.prog, ders=Ders.objects.get(kod="3301568"), slot=slot)

    def test_ydp_ogrencisi_havuzdan_ders_ekler(self):
        prog = self.ydp.guncel_program
        od = sv.ders_ekle(yapan=self.ydp.kullanici, program=prog, ders=Ders.objects.get(kod="3301454"))
        self.assertEqual(prog.akts_ozeti()["toplam"], 0)
        sv.onayla(yapan=self.koord, kayit=od)
        self.assertEqual(prog.akts_ozeti()["toplam"], 5)

    def test_pasif_ders_secilemez(self):
        d = Ders.objects.get(kod="3301454")
        d.aktif = False
        d.save()
        with self.assertRaises(ValidationError):
            sv.ders_ekle(yapan=self.ydp.kullanici, program=self.ydp.guncel_program, ders=d)

    def test_listede_olan_ders_tekrar_eklenemez(self):
        with self.assertRaises(ValidationError):
            sv.ders_ekle(yapan=self.koord, program=self.prog, ders=Ders.objects.get(kod="3301454"), gerekce="x")

    def test_koordinator_gerekcesiz_ders_ekleyemez(self):
        with self.assertRaises(ValidationError):
            sv.ders_ekle(yapan=self.koord, program=self.ydp.guncel_program, ders=Ders.objects.get(kod="3301454"))


class DenemeVeNotTestleri(Temel):
    def test_tam_akis_ders_kaydi_not_ve_onay(self):
        od = self.ders("3301454")
        deneme = sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=od, donem=self.guz)
        self.assertEqual((deneme.durum, deneme.onay_durumu), ("ALINDI", OnayDurumu.BEKLIYOR))
        with self.assertRaises(ValidationError):  # onaylanmadan not girilemez
            sv.not_gir(yapan=self.cap_k, deneme=deneme, harf_notu="BB")
        sv.onayla(yapan=self.koord, kayit=deneme)
        with self.assertRaises(ValidationError):  # transkript yüklenmeden not girilemez
            sv.not_gir(yapan=self.cap_k, deneme=deneme, harf_notu="BB")
        self.transkript()
        giris = sv.not_gir(yapan=self.cap_k, deneme=deneme, harf_notu="BB")
        self.assertEqual(self.prog.akts_ozeti()["tamamlanan"], 0)  # not onay bekliyor
        sv.onayla(yapan=self.koord, kayit=giris)
        deneme.refresh_from_db()
        self.assertEqual((deneme.harf_notu, deneme.durum), ("BB", "GECTI"))
        self.assertEqual(self.prog.akts_ozeti()["tamamlanan"], 5)

    def test_ff_ile_kalir_ve_tekrar_alinabilir(self):
        od = self.ders("3301352")
        d1 = sv.deneme_ekle(yapan=self.koord, ogrenci_dersi=od, donem=self.guz, harf_notu="FF")
        self.assertEqual(d1.durum, "KALDI")
        d2 = sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=od, donem=self.bahar)
        self.assertEqual(od.denemeler.count(), 2)
        self.assertEqual(d2.onay_durumu, OnayDurumu.BEKLIYOR)

    def test_gecilmis_ders_tekrar_girilemez(self):
        od = self.ders("3301352")
        sv.deneme_ekle(yapan=self.koord, ogrenci_dersi=od, donem=self.guz, harf_notu="AA")
        with self.assertRaises(ValidationError):
            sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=od, donem=self.bahar)

    def test_ayni_donemde_ayni_ders_iki_kez_girilemez(self):
        od = self.ders("3301352")
        sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=od, donem=self.guz)
        with self.assertRaises(ValidationError):
            sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=od, donem=self.guz)

    def test_koordinator_gecmis_veri_aktarir_onay_kilidine_takilmaz(self):
        d = sv.deneme_ekle(yapan=self.koord, ogrenci_dersi=self.ders("3301156"), donem=self.guz,
                           harf_notu="CB", kaynak=Kaynak.AKTARIM)
        self.assertEqual((d.onay_durumu, d.kaynak, d.durum), (OnayDurumu.ONAYLANDI, Kaynak.AKTARIM, "GECTI"))
        self.assertTrue(IslemKaydi.objects.filter(islem="DERS_DENEMESI_EKLENDI", aciklama="İlk kurulum aktarımı").exists())


class KilitVeYetkiTestleri(Temel):
    def setUp(self):
        super().setUp()
        self.deneme = sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=self.ders("3301352"), donem=self.guz)

    def test_ogrenci_bekleyen_kaydini_geri_cekebilir(self):
        sv.geri_cek(yapan=self.cap_k, kayit=self.deneme)
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.IPTAL)

    def test_onaylanan_kayit_kilitlenir(self):
        sv.onayla(yapan=self.koord, kayit=self.deneme)
        self.deneme.refresh_from_db()
        self.assertTrue(self.deneme.kilitli_mi)
        with self.assertRaises(PermissionDenied):
            sv.geri_cek(yapan=self.cap_k, kayit=self.deneme)
        with self.assertRaises(ValidationError):
            sv.onayla(yapan=self.koord, kayit=self.deneme)

    def test_ogrenci_onaylayamaz(self):
        with self.assertRaises(PermissionDenied):
            sv.onayla(yapan=self.cap_k, kayit=self.deneme)

    def test_baska_ogrencinin_kaydina_dokunamaz(self):
        with self.assertRaises(PermissionDenied):
            sv.geri_cek(yapan=self.ydp.kullanici, kayit=self.deneme)
        with self.assertRaises(PermissionDenied):
            sv.deneme_ekle(yapan=self.ydp.kullanici, ogrenci_dersi=self.ders("3301351"), donem=self.guz)

    def test_red_gerekce_ister_ve_kayit_silinmez(self):
        with self.assertRaises(ValidationError):
            sv.reddet(yapan=self.koord, kayit=self.deneme, gerekce="  ")
        sv.reddet(yapan=self.koord, kayit=self.deneme, gerekce="Ders kayıt formuyla uyuşmuyor")
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.REDDEDILDI)
        self.assertEqual(self.deneme.gerekce, "Ders kayıt formuyla uyuşmuyor")
        self.assertTrue(DersDenemesi.objects.filter(pk=self.deneme.pk).exists())

    def test_koordinator_duzeltmesi_eski_degeri_saklar(self):
        sv.onayla(yapan=self.koord, kayit=self.deneme)
        sv.deneme_duzelt(yapan=self.koord, deneme=self.deneme, donem=self.bahar, harf_notu="CC",
                         gerekce="Transkriptte bahar dönemi görünüyor")
        k = IslemKaydi.objects.get(islem="KAYIT_DUZELTILDI")
        self.assertEqual(k.eski_deger["donem"], "2025-2026 Güz")
        self.assertEqual(k.yeni_deger["donem"], "2025-2026 Bahar")
        self.assertEqual(k.yeni_deger["harf_notu"], "CC")

    def test_iptal_edilen_kayit_hesaptan_cikar(self):
        sv.onayla(yapan=self.koord, kayit=self.deneme)
        self.transkript()
        giris = sv.not_gir(yapan=self.cap_k, deneme=self.deneme, harf_notu="AA")
        sv.onayla(yapan=self.koord, kayit=giris)
        self.assertEqual(self.prog.akts_ozeti()["tamamlanan"], 4)
        sv.iptal_et(yapan=self.koord, kayit=self.deneme, gerekce="Yanlış öğrenciye girilmiş")
        self.assertEqual(self.prog.akts_ozeti()["tamamlanan"], 0)

    def test_gecilmis_ders_listeden_cikarilamaz(self):
        sv.onayla(yapan=self.koord, kayit=self.deneme)
        self.transkript()
        sv.onayla(yapan=self.koord, kayit=sv.not_gir(yapan=self.cap_k, deneme=self.deneme, harf_notu="AA"))
        with self.assertRaises(ValidationError):
            sv.liste_durumu_degistir(yapan=self.koord, ogrenci_dersi=self.ders("3301352"),
                                     yeni_durum="CIKARILDI", gerekce="deneme")


class EkranTestleri(Temel):
    def setUp(self):
        super().setUp()
        self.deneme = sv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=self.ders("3301352"), donem=self.guz)

    def url(self, no, eylem, pk=None):
        return reverse("kayit_islemi", args=[no, "deneme", pk or self.deneme.pk, eylem])

    def test_koordinator_ekrandan_onaylar(self):
        self.client.force_login(self.koord)
        self.client.post(self.url("231101001", "onayla"))
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.ONAYLANDI)

    def test_bolum_baskani_onaylayamaz(self):
        self.client.force_login(self.baskan)
        self.assertEqual(self.client.post(self.url("231101001", "onayla")).status_code, 403)
        self.assertEqual(self.client.get(reverse("onay_kuyrugu")).status_code, 200)

    def test_ogrenci_ekrandan_onaylayamaz(self):
        self.client.force_login(self.cap_k)
        self.client.post(self.url("231101001", "onayla"))
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.BEKLIYOR)

    def test_baska_ogrenci_url_ile_kayda_ulasamaz(self):
        self.client.force_login(self.ydp.kullanici)
        # Başkasının numarasıyla: 403
        self.assertEqual(self.client.post(self.url("231101001", "geri-cek")).status_code, 403)
        # Kendi numarası + başkasının kayıt kimliği: 404 (kayıt bu öğrenciye ait değil)
        self.assertEqual(self.client.post(self.url("231101002", "geri-cek")).status_code, 404)
        self.deneme.refresh_from_db()
        self.assertEqual(self.deneme.onay_durumu, OnayDurumu.BEKLIYOR)

    def test_onay_kuyrugu_bekleyeni_listeler(self):
        self.client.force_login(self.koord)
        self.assertContains(self.client.get(reverse("onay_kuyrugu")), "İşletim Sistemleri")

    def test_serbest_metin_ders_eklenemez(self):
        self.client.force_login(self.ydp.kullanici)
        self.client.post(reverse("ders_sec", args=["231101002"]), {"ders_kodu": "UYDURMA 101"})
        self.assertEqual(self.ydp.guncel_program.dersler.count(), 0)

    def test_gecersiz_kimlik_sunucu_hatasi_vermez(self):
        self.client.force_login(self.cap_k)
        cevap = self.client.post(reverse("deneme_ekle", args=["231101001"]), {"ogrenci_dersi": "abc", "donem": "x"})
        self.assertEqual(cevap.status_code, 404)
