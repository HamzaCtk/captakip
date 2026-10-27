"""1. adım testleri: roller, giriş güvenliği, işlem kaydı.

Çalıştırmak için:  python manage.py test
"""
from django.db import connection, IntegrityError, DatabaseError
from django.test import TestCase
from django.urls import reverse

from denetim.models import IslemKaydi

from .models import Kullanici

SIFRE = "GucluSifre!2026"


def kullanici_olustur(username, rol, sifre_degistirmeli=False):
    k = Kullanici(username=username, rol=rol, email=f"{username}@ornek.edu.tr",
                  sifre_degistirmeli=sifre_degistirmeli)
    k.set_password(SIFRE)
    k.save()
    return k


class GirisTestleri(TestCase):
    def setUp(self):
        self.koord = kullanici_olustur("koord", Kullanici.Rol.KOORDINATOR)

    def test_dogru_sifreyle_giris(self):
        cevap = self.client.post(reverse("giris"), {"username": "koord", "password": SIFRE})
        self.assertRedirects(cevap, reverse("anasayfa"))
        self.assertTrue(IslemKaydi.objects.filter(islem="GIRIS").exists())

    def test_giris_yapmadan_sayfa_acilmaz(self):
        cevap = self.client.get(reverse("anasayfa"))
        self.assertEqual(cevap.status_code, 302)
        self.assertIn(reverse("giris"), cevap.url)

    def test_bes_hatali_denemeden_sonra_kilit(self):
        for _ in range(5):
            self.client.post(reverse("giris"), {"username": "koord", "password": "yanlis"})
        # Doğru şifre bile artık kabul edilmez
        cevap = self.client.post(reverse("giris"), {"username": "koord", "password": SIFRE})
        self.assertEqual(cevap.status_code, 200)
        self.assertContains(cevap, "Çok fazla hatalı deneme")

    def test_hata_mesaji_kullanici_varligini_sizdirmaz(self):
        c1 = self.client.post(reverse("giris"), {"username": "koord", "password": "yanlis"})
        c2 = self.client.post(reverse("giris"), {"username": "olmayan", "password": "yanlis"})
        self.assertContains(c1, "Kullanıcı adı veya şifre hatalı.")
        self.assertContains(c2, "Kullanıcı adı veya şifre hatalı.")

    def test_cikis_get_ile_yapilamaz(self):
        # GET ile çıkış CSRF benzeri saldırılara açık olurdu
        self.client.force_login(self.koord)
        cevap = self.client.get(reverse("cikis"))
        self.assertEqual(cevap.status_code, 405)


class SifreDegistirmeZorunluluguTestleri(TestCase):
    def test_gecici_sifreli_kullanici_yonlendirilir(self):
        k = kullanici_olustur("yeni", Kullanici.Rol.BOLUM_BASKANI, sifre_degistirmeli=True)
        self.client.force_login(k)
        cevap = self.client.get(reverse("anasayfa"))
        self.assertRedirects(cevap, reverse("sifre_degistir"))

    def test_sifre_degisince_serbest_kalir(self):
        k = kullanici_olustur("yeni", Kullanici.Rol.BOLUM_BASKANI, sifre_degistirmeli=True)
        self.client.force_login(k)
        self.client.post(reverse("sifre_degistir"), {
            "old_password": SIFRE,
            "new_password1": "YeniGucluSifre#77",
            "new_password2": "YeniGucluSifre#77",
        })
        k.refresh_from_db()
        self.assertFalse(k.sifre_degistirmeli)
        self.assertEqual(self.client.get(reverse("anasayfa")).status_code, 200)


class RolYetkiTestleri(TestCase):
    def setUp(self):
        self.koord = kullanici_olustur("koord", Kullanici.Rol.KOORDINATOR)
        self.baskan = kullanici_olustur("baskan", Kullanici.Rol.BOLUM_BASKANI)
        self.ogrenci = kullanici_olustur("231101001", Kullanici.Rol.OGRENCI)

    def test_hesap_listesi_sadece_koordinator(self):
        url = reverse("hesap_listesi")
        self.client.force_login(self.koord)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.ogrenci)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.baskan)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_bolum_baskani_hicbir_sey_degistiremez(self):
        self.client.force_login(self.baskan)
        cevap = self.client.post(reverse("hesap_olustur"), {
            "username": "x", "email": "x@ornek.edu.tr", "rol": "KOORDINATOR"})
        self.assertEqual(cevap.status_code, 403)
        self.assertFalse(Kullanici.objects.filter(username="x").exists())

    def test_ogrenci_hesap_acamaz(self):
        self.client.force_login(self.ogrenci)
        cevap = self.client.post(reverse("hesap_olustur"), {
            "username": "x", "email": "x@ornek.edu.tr", "rol": "KOORDINATOR"})
        self.assertEqual(cevap.status_code, 403)

    def test_koordinator_hesap_acar_ve_islem_kaydi_dusulur(self):
        self.client.force_login(self.koord)
        self.client.post(reverse("hesap_olustur"), {
            "username": "baskan2", "first_name": "Ayşe", "last_name": "Yılmaz",
            "email": "baskan2@ornek.edu.tr", "rol": "BOLUM_BASKANI"})
        yeni = Kullanici.objects.get(username="baskan2")
        self.assertTrue(yeni.sifre_degistirmeli)
        self.assertTrue(yeni.has_usable_password())
        kayit = IslemKaydi.objects.get(islem="HESAP_OLUSTURULDU", nesne_id=str(yeni.pk))
        self.assertEqual(kayit.yapan, self.koord)

    def test_koordinator_ogrenci_rolunde_hesap_acamaz_bu_formdan(self):
        # Öğrenci hesapları yalnızca öğrenci kartıyla açılır
        self.client.force_login(self.koord)
        self.client.post(reverse("hesap_olustur"), {
            "username": "ogr", "email": "ogr@ornek.edu.tr", "rol": "OGRENCI"})
        self.assertFalse(Kullanici.objects.filter(username="ogr").exists())


class IslemKaydiDegistirilemezTestleri(TestCase):
    def setUp(self):
        self.kayit = IslemKaydi.objects.create(islem="TEST")

    def test_python_ile_guncellenemez(self):
        self.kayit.islem = "DEGISTI"
        with self.assertRaises(Exception):
            self.kayit.save()

    def test_python_ile_silinemez(self):
        with self.assertRaises(Exception):
            self.kayit.delete()

    def test_dogrudan_sql_ile_guncellenemez(self):
        with self.assertRaises((IntegrityError, DatabaseError)):
            with connection.cursor() as c:
                c.execute("UPDATE denetim_islemkaydi SET islem='X' WHERE id=%s", [self.kayit.pk])

    def test_dogrudan_sql_ile_silinemez(self):
        with self.assertRaises((IntegrityError, DatabaseError)):
            with connection.cursor() as c:
                c.execute("DELETE FROM denetim_islemkaydi WHERE id=%s", [self.kayit.pk])

    def test_toplu_queryset_silme_de_engellenir(self):
        with self.assertRaises((IntegrityError, DatabaseError)):
            IslemKaydi.objects.all().delete()
