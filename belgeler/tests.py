"""4. adım testleri: güvenli dosya yükleme, erişim, sürümler, istekler."""
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Kullanici
from denetim.models import IslemKaydi
from ogrenciler import servisler as osv
from ogrenciler.models import AkademikDonem, Bolum
from ortak.modeller import OnayDurumu
from ortak.test_yardimci import GECERLI_PDF, GECERLI_PNG, GeciciDosyaKlasoru, pdf

from . import servisler as sv
from .models import Belge, BelgeIstegi

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
        cls.guz = AkademikDonem.objects.get(yil="2025-2026", donem="GUZ")

    def setUp(self):
        self.a = self._ogrenci("231101001")
        self.b = self._ogrenci("231101002")

    def _ogrenci(self, no):
        o, _ = osv.ogrenci_ekle(yapan=self.koord, ogrenci_no=no, ad="Test", soyad="Öğrenci",
                                eposta=f"{no}@ornek.edu.tr", ana_dal_bolumu=Bolum.objects.get(kod="EEM"),
                                tur="CAP", kabul_donemi=self.guz)
        o.kullanici.sifre_degistirmeli = False
        o.kullanici.save()
        return o

    def yukle(self, dosya, yapan=None, ogrenci=None, tur="PROTOKOL_FORMU", **kw):
        return sv.belge_yukle(yapan=yapan or self.a.kullanici, ogrenci=ogrenci or self.a, dosya=dosya,
                              tur=tur, **kw)


class DosyaDogrulamaTestleri(Temel):
    def test_gecerli_pdf_yuklenir_ve_onay_bekler(self):
        b = self.yukle(pdf("protokol.pdf"))
        self.assertEqual(b.onay_durumu, OnayDurumu.BEKLIYOR)
        self.assertEqual(b.mime, "application/pdf")
        self.assertEqual(len(b.sha256), 64)
        self.assertTrue(sv.dosya_yolu(b).is_file())

    def test_dosya_rastgele_adla_web_koku_disinda_saklanir(self):
        b = self.yukle(pdf("protokol.pdf"))
        self.assertNotIn("protokol", b.dosya_yolu)
        yol = sv.dosya_yolu(b).resolve()
        self.assertTrue(str(yol).startswith(str(Path(settings.KORUNAN_DOSYA_KOKU).resolve())))
        self.assertFalse(str(yol).startswith(str(Path(settings.BASE_DIR, "static").resolve())))

    def test_koordinator_yukledigi_belge_dogrudan_onayli(self):
        b = self.yukle(pdf(), yapan=self.koord)
        self.assertEqual(b.onay_durumu, OnayDurumu.ONAYLANDI)

    def test_png_kabul_edilir(self):
        b = self.yukle(SimpleUploadedFile("form.png", GECERLI_PNG, "image/png"))
        self.assertEqual(b.mime, "image/png")

    def reddedilir(self, dosya, mesaj=None):
        with self.assertRaises(ValidationError) as h:
            self.yukle(dosya)
        if mesaj:
            self.assertIn(mesaj, " ".join(h.exception.messages))
        self.assertFalse(Belge.objects.exists())

    def test_izinsiz_uzanti_reddedilir(self):
        self.reddedilir(SimpleUploadedFile("virus.exe", b"MZ\x90\x00" * 20), "Yalnızca PDF")

    def test_uzantisi_pdf_olan_calistirilabilir_dosya_reddedilir(self):
        self.reddedilir(SimpleUploadedFile("transkript.pdf", b"MZ\x90\x00" + b"\x00" * 200), "uyuşmuyor")

    def test_html_pdf_gibi_gonderilirse_reddedilir(self):
        self.reddedilir(SimpleUploadedFile("a.pdf", b"<html><script>alert(1)</script></html>"), "uyuşmuyor")

    def test_javascript_iceren_pdf_reddedilir(self):
        zararli = GECERLI_PDF.replace(b"/Type/Catalog", b"/Type/Catalog/OpenAction<</S/JavaScript/JS(app.alert(1))>>")
        self.reddedilir(pdf("a.pdf", zararli), "çalıştırılabilir")

    def test_gomulu_dosya_iceren_pdf_reddedilir(self):
        self.reddedilir(pdf("a.pdf", GECERLI_PDF.replace(b"/Type/Catalog", b"/Type/Catalog/Names<</EmbeddedFiles 3 0 R>>")))

    def test_yarim_kalmis_pdf_reddedilir(self):
        self.reddedilir(pdf("a.pdf", GECERLI_PDF[:40]), "bozuk")

    def test_bos_dosya_reddedilir(self):
        self.reddedilir(SimpleUploadedFile("a.pdf", b""), "boş")

    @override_settings(BELGE_MAKS_BOYUT=1024)
    def test_boyut_siniri(self):
        self.reddedilir(pdf("a.pdf", b"%PDF-1.4\n" + b"0" * 2000 + b"\n%%EOF"), "çok büyük")

    def test_dosya_adindaki_yol_enjeksiyonu_temizlenir(self):
        b = self.yukle(pdf("../../../etc/passwd<script>.pdf"))
        self.assertNotIn("/", b.orijinal_ad)
        self.assertNotIn("<", b.orijinal_ad)
        self.assertNotIn("..", b.dosya_yolu)


class ErisimTestleri(Temel):
    def setUp(self):
        super().setUp()
        self.belge = self.yukle(pdf("gizli.pdf"))
        self.url = reverse("belge_indir", args=["231101001", self.belge.pk])

    def test_ogrenci_kendi_belgesini_indirir(self):
        self.client.force_login(self.a.kullanici)
        cevap = self.client.get(self.url)
        self.assertEqual(cevap.status_code, 200)
        self.assertIn("attachment", cevap["Content-Disposition"])
        self.assertEqual(cevap["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(cevap.streaming_content), GECERLI_PDF)

    def test_baska_ogrenci_indiremez(self):
        self.client.force_login(self.b.kullanici)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        # kendi numarasıyla başkasının belge kimliğini denerse 404
        self.assertEqual(self.client.get(reverse("belge_indir", args=["231101002", self.belge.pk])).status_code, 404)

    def test_giris_yapmadan_indirilemez(self):
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_bolum_baskani_indirir_ama_yukleyemez(self):
        self.client.force_login(self.baskan)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        cevap = self.client.post(reverse("belge_yukle", args=["231101001"]),
                                 {"tur": "DIGER", "dosya": pdf()})
        self.assertEqual(cevap.status_code, 403)

    def test_ogrenci_baskasinin_kartina_yukleyemez(self):
        with self.assertRaises(PermissionDenied):
            self.yukle(pdf(), yapan=self.b.kullanici, ogrenci=self.a)
        self.client.force_login(self.b.kullanici)
        cevap = self.client.post(reverse("belge_yukle", args=["231101001"]), {"tur": "DIGER", "dosya": pdf()})
        self.assertEqual(cevap.status_code, 403)

    def test_ogrenci_baskasinin_belge_listesini_goremez(self):
        self.client.force_login(self.b.kullanici)
        self.assertEqual(self.client.get(reverse("belgeler", args=["231101001"])).status_code, 403)

    def test_ogrenci_kurul_karari_yukleyemez(self):
        with self.assertRaises(PermissionDenied):
            self.yukle(pdf(), tur="KURUL_KARARI")

    def test_ekrandan_yukleme_ve_islem_kaydi(self):
        self.client.force_login(self.a.kullanici)
        self.client.post(reverse("belge_yukle", args=["231101001"]),
                         {"tur": "TRANSKRIPT", "donem": self.guz.pk, "dosya": pdf("t.pdf")})
        self.assertTrue(Belge.objects.filter(tur="TRANSKRIPT").exists())
        self.assertEqual(IslemKaydi.objects.filter(islem="BELGE_YUKLENDI").count(), 2)

    def test_transkript_donemsiz_yuklenemez(self):
        with self.assertRaises(ValidationError):
            self.yukle(pdf(), tur="TRANSKRIPT")


class SurumVeIstekTestleri(Temel):
    def test_reddedilen_belge_silinmez_yeni_surum_eskiyi_saklar(self):
        v1 = self.yukle(pdf("v1.pdf"))
        sv.belge_reddet(yapan=self.koord, belge=v1, gerekce="İmza eksik")
        v2 = self.yukle(pdf("v2.pdf"), onceki=v1)
        v1.refresh_from_db()
        self.assertEqual(v1.onay_durumu, OnayDurumu.REDDEDILDI)
        self.assertFalse(v1.guncel_mi)
        self.assertTrue(v2.guncel_mi)
        self.assertEqual(v2.surum_no, 2)
        self.assertTrue(sv.dosya_yolu(v1).is_file())  # eski dosya diskte duruyor

    def test_eski_surum_tekrar_yenilenemez(self):
        v1 = self.yukle(pdf())
        self.yukle(pdf(), onceki=v1)
        with self.assertRaises(ValidationError):
            self.yukle(pdf(), onceki=v1)

    def test_bekleyen_belgenin_yeni_surumu_eskiyi_kuyruktan_cikarir(self):
        v1 = self.yukle(pdf("v1.pdf"))
        v2 = self.yukle(pdf("v2.pdf"), onceki=v1)
        v1.refresh_from_db()
        self.assertEqual(v1.onay_durumu, OnayDurumu.IPTAL)
        self.assertEqual(v2.onay_durumu, OnayDurumu.BEKLIYOR)
        self.assertEqual(Belge.objects.filter(onay_durumu=OnayDurumu.BEKLIYOR).count(), 1)
        self.assertTrue(sv.dosya_yolu(v1).is_file())

    def test_belge_silinemez(self):
        b = self.yukle(pdf())
        with self.assertRaises(PermissionDenied):
            b.delete()
        with self.assertRaises(PermissionDenied):
            Belge.objects.all().delete()

    def test_ogrenci_belgeyi_geri_cekemez(self):
        b = self.yukle(pdf())
        self.client.force_login(self.a.kullanici)
        self.client.post(reverse("kayit_islemi", args=["231101001", "belge", b.pk, "geri-cek"]))
        b.refresh_from_db()
        self.assertEqual(b.onay_durumu, OnayDurumu.BEKLIYOR)

    def test_red_gerekce_ister(self):
        b = self.yukle(pdf())
        with self.assertRaises(ValidationError):
            sv.belge_reddet(yapan=self.koord, belge=b, gerekce="")

    def test_ek_belge_istegi_tam_akis(self):
        istek = sv.istek_olustur(yapan=self.koord, ogrenci=self.a, tur="MUAFIYET_FORMU",
                                 aciklama="Veri Yapıları muafiyeti için imzalı form")
        self.assertEqual(istek.durum, BelgeIstegi.Durum.BEKLIYOR)
        b1 = self.yukle(pdf(), tur="DIGER", istek=istek)
        self.assertEqual(b1.tur, "MUAFIYET_FORMU")  # tür istekten gelir
        istek.refresh_from_db()
        self.assertEqual(istek.durum, BelgeIstegi.Durum.YUKLENDI)
        sv.belge_reddet(yapan=self.koord, belge=b1, gerekce="Danışman imzası yok")
        istek.refresh_from_db()
        self.assertEqual(istek.durum, BelgeIstegi.Durum.REDDEDILDI)
        b2 = self.yukle(pdf(), istek=istek)
        sv.belge_onayla(yapan=self.koord, belge=b2)
        istek.refresh_from_db()
        self.assertEqual(istek.durum, BelgeIstegi.Durum.ONAYLANDI)
        with self.assertRaises(ValidationError):  # kapanan isteğe yükleme yapılamaz
            self.yukle(pdf(), istek=istek)

    def test_ogrenci_istek_olusturamaz(self):
        with self.assertRaises(PermissionDenied):
            sv.istek_olustur(yapan=self.a.kullanici, ogrenci=self.a, tur="DIGER", aciklama="x")

    def test_baska_ogrencinin_istegine_yuklenemez(self):
        istek = sv.istek_olustur(yapan=self.koord, ogrenci=self.b, tur="DIGER", aciklama="x")
        with self.assertRaises(ValidationError):
            self.yukle(pdf(), istek=istek)
