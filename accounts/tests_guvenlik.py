"""9. adım: güvenlik test paketi (OWASP Top 10 odaklı).

Bu testler sızma testinde elle denenecek saldırıların otomatik hâlidir ve
yalnızca kendi uygulamamız üzerinde, test veritabanında çalışır.

A01 Erişim kontrolü ......... rol matrisi, IDOR, salt okunur rol, toplu atama
A03 Enjeksiyon .............. SQL enjeksiyonu, XSS (kalıcı), CSV formül enjeksiyonu
A04 Güvensiz tasarım ........ CSRF, HTTP yöntemi kısıtları
A05 Yanlış yapılandırma ..... güvenlik başlıkları, çerez bayrakları, hata sayfaları
A07 Kimlik doğrulama ........ açık yönlendirme, zayıf şifre
A08 Veri bütünlüğü .......... işlem kaydının değiştirilemezliği (denetim/tests.py)
"""
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse

from belgeler import servisler as bsv
from belgeler.dogrulama import guvenli_ad
from dersler.models import DersDenemesi
from dersler.tests import SIFRE, Temel
from mesajlar.models import Bildirim, Mesaj
from ogrenciler import servisler as osv
from ortak.modeller import OnayDurumu
from ortak.test_yardimci import pdf

XSS = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
XSS_KACIS = "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"


class GuvenlikTemel(Temel):
    def setUp(self):
        super().setUp()
        for k in (self.cap_k, self.ydp.kullanici):
            k.set_password(SIFRE)
            k.save()

    def giris(self, kullanici, istemci=None):
        istemci = istemci or self.client
        self.assertTrue(istemci.login(username=kullanici.username, password=SIFRE))
        return istemci


class ErisimKontroluTestleri(GuvenlikTemel):
    """A01: Her rol yalnızca kendisine açık sayfaları görebilir."""

    YONETICI = ["ogrenci_listesi", "onay_kuyrugu", "kural_ayarlari", "aktarim_listesi", "katalog"]
    YALNIZ_KOORDINATOR = ["hesap_listesi", "hesap_olustur", "ogrenci_ekle", "ders_ekle"]

    def test_giris_yapmayan_hicbir_sayfayi_goremez(self):
        adresler = [reverse(a) for a in self.YONETICI + self.YALNIZ_KOORDINATOR + ["anasayfa", "bildirimler",
                                                                                   "mesaj_kutusu"]]
        adresler += [reverse(a, args=["231101001"]) for a in ("ogrenci_karti", "ogrenci_durum", "belgeler",
                                                               "konusma")]
        for adres in adresler:
            with self.subTest(adres=adres):
                r = self.client.get(adres)
                self.assertEqual(r.status_code, 302)
                self.assertTrue(r["Location"].startswith(reverse("giris")))

    def test_ogrenci_yonetim_sayfalarini_acamaz(self):
        self.giris(self.cap_k)
        for ad in self.YONETICI + self.YALNIZ_KOORDINATOR:
            if ad == "katalog":
                continue
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 403)
        self.assertEqual(self.client.get(reverse("surum_yeni", args=["CAP"])).status_code, 403)
        self.assertEqual(self.client.get(reverse("karar_isle", args=["231101001"])).status_code, 403)

    def test_bolum_baskani_okur_degistiremez(self):
        self.giris(self.baskan)
        for ad in self.YONETICI:
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 200)
        for ad in self.YALNIZ_KOORDINATOR:
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 403)
        r = self.client.post(reverse("mesaj_gonder", args=["231101001"]), {"metin": "deneme"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Mesaj.objects.exists())

    def test_idor_baska_ogrencinin_sayfalari(self):
        self.giris(self.cap_k)
        for ad in ("ogrenci_karti", "ogrenci_durum", "belgeler", "konusma"):
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad, args=["231101001"])).status_code, 200)
                self.assertEqual(self.client.get(reverse(ad, args=["231101002"])).status_code, 403)

    def test_idor_baska_ogrencinin_kayitlarina_yazamaz(self):
        self.giris(self.cap_k)
        hedef = "231101002"
        istekler = [
            ("mesaj_gonder", {"metin": "başkasının konuşması"}),
            ("ders_sec", {"ders_kodu": "3301351"}),
            ("deneme_ekle", {"ogrenci_dersi": 1, "donem": self.guz.pk}),
            ("belge_yukle", {"tur": "DIGER", "dosya": pdf()}),
        ]
        for ad, veri in istekler:
            with self.subTest(islem=ad):
                self.assertEqual(self.client.post(reverse(ad, args=[hedef]), veri).status_code, 403)
        self.assertFalse(Mesaj.objects.exists())
        self.assertFalse(self.ydp.belgeler.exists())

    def test_idor_belge_indirme(self):
        belge = bsv.belge_yukle(yapan=self.koord, ogrenci=self.ydp, dosya=pdf("gizli.pdf"), tur="DIGER")
        self.giris(self.cap_k)
        # Başkasının numarasıyla: 403; kendi numarasıyla başkasının belge kimliği: 404
        self.assertEqual(self.client.get(reverse("belge_indir", args=["231101002", belge.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("belge_indir", args=["231101001", belge.pk])).status_code, 404)

    def test_toplu_atama_ogrenci_onay_durumunu_belirleyemez(self):
        self.giris(self.cap_k)
        od = self.ders("3301156")
        self.client.post(reverse("deneme_ekle", args=["231101001"]), {
            "ogrenci_dersi": od.pk, "donem": self.guz.pk,
            # Formda olmayan alanlar gönderilse de dikkate alınmamalı
            "onay_durumu": "ONAYLANDI", "harf_notu": "AA", "durum": "GECTI", "kaynak": "KOORDINATOR"})
        d = DersDenemesi.objects.get(ogrenci_dersi=od)
        self.assertEqual((d.onay_durumu, d.durum, d.harf_notu, d.kaynak),
                         (OnayDurumu.BEKLIYOR, "ALINDI", "", "OGRENCI"))


class EnjeksiyonTestleri(GuvenlikTemel):
    """A03: Kullanıcı girdisi hiçbir yerde kod olarak çalışmaz."""

    def test_kalici_xss_mesaj_ve_not(self):
        self.giris(self.cap_k)
        self.client.post(reverse("mesaj_gonder", args=["231101001"]), {"metin": XSS})
        r = self.client.get(reverse("konusma", args=["231101001"]))
        self.assertNotContains(r, "<script>alert")
        self.assertNotContains(r, "<img src=x")
        self.assertContains(r, XSS_KACIS)
        self.client.logout()
        self.giris(self.koord)
        self.client.post(reverse("koordinator_notu_ekle", args=["231101001"]), {"metin": XSS})
        for adres in (reverse("ogrenci_karti", args=["231101001"]), reverse("mesaj_kutusu")):
            with self.subTest(adres=adres):
                r = self.client.get(adres)
                self.assertNotContains(r, "<script>alert")

    def test_kalici_xss_ogrenci_adi_ve_dosya_adi(self):
        o, _ = osv.ogrenci_ekle(yapan=self.koord, ogrenci_no="231101077", ad=XSS, soyad="Test",
                                eposta="x@ornek.edu.tr", ana_dal_bolumu=self.eem, tur="YDP",
                                kabul_donemi=self.guz)
        bsv.belge_yukle(yapan=self.koord, ogrenci=o, dosya=pdf('<svg onload=alert(1)>.pdf'), tur="DIGER")
        self.giris(self.koord)
        for adres in (reverse("ogrenci_listesi"), reverse("ogrenci_karti", args=["231101077"]),
                      reverse("belgeler", args=["231101077"]), reverse("anasayfa")):
            with self.subTest(adres=adres):
                r = self.client.get(adres)
                self.assertNotContains(r, "<script>alert")
                self.assertNotContains(r, "<svg onload")

    def test_sql_enjeksiyonu_arama_ve_adres(self):
        self.giris(self.koord)
        for yuk in ("' OR '1'='1", "%' OR 1=1 --", "1; DROP TABLE ogrenciler_ogrenci; --", "\" OR \"\"=\""):
            with self.subTest(yuk=yuk):
                r = self.client.get(reverse("ogrenci_listesi"), {"q": yuk})
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "231101001")  # filtre atlatılıp tüm kayıtlar dökülmedi
        self.assertEqual(self.client.get("/ogrenciler/1' OR '1'='1/").status_code, 404)
        self.assertEqual(self.client.get(reverse("ogrenci_listesi")).status_code, 200)  # tablo yerinde

    def test_dosya_adi_ile_dizin_atlama_yapilamaz(self):
        self.assertEqual(guvenli_ad("../../etc/passwd"), "passwd")
        self.assertEqual(guvenli_ad("..\\..\\windows\\win.ini"), "win.ini")
        self.assertNotIn("/", guvenli_ad("a/../../b.pdf"))


class CsrfVeYontemTestleri(GuvenlikTemel):
    """A01/A04: Siteler arası istek sahteciliği ve yöntem kısıtları."""

    def test_csrf_jetonu_olmadan_istek_reddedilir(self):
        istemci = self.giris(self.cap_k, Client(enforce_csrf_checks=True))
        r = istemci.post(reverse("mesaj_gonder", args=["231101001"]), {"metin": "CSRF denemesi"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Mesaj.objects.exists())

    def test_degistiren_islemler_get_ile_yapilamaz(self):
        self.giris(self.koord)
        for adres in (reverse("mesaj_gonder", args=["231101001"]), reverse("cikis"),
                      reverse("simdi_degerlendir", args=["231101001"]), reverse("bildirim_tumunu_okundu")):
            with self.subTest(adres=adres):
                self.assertEqual(self.client.get(adres).status_code, 405)


class YapilandirmaTestleri(GuvenlikTemel):
    """A05: Güvenlik başlıkları, çerezler ve hata sayfaları."""

    def test_guvenlik_basliklari(self):
        self.giris(self.koord)
        r = self.client.get(reverse("anasayfa"))
        csp = r["Content-Security-Policy"]
        for parca in ("default-src 'self'", "script-src 'self'", "object-src 'none'", "frame-ancestors 'none'",
                      "form-action 'self'"):
            self.assertIn(parca, csp)
        self.assertNotIn("unsafe-inline", csp)
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["Referrer-Policy"], "same-origin")
        self.assertEqual(r["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("camera=()", r["Permissions-Policy"])
        self.assertIn("no-store", r["Cache-Control"])  # kişisel veri tarayıcıda saklanmaz

    def test_sayfalarda_satir_ici_betik_ve_stil_yok(self):
        self.giris(self.koord)
        for adres in (reverse("anasayfa"), reverse("ogrenci_listesi"), reverse("ogrenci_karti", args=["231101001"])):
            with self.subTest(adres=adres):
                icerik = self.client.get(adres).content.decode()
                self.assertNotIn("<script", icerik)
                self.assertNotIn("style=", icerik)
                self.assertNotIn("onclick=", icerik)

    def test_oturum_cerezi_bayraklari(self):
        r = self.client.post(reverse("giris"), {"username": "koord", "password": SIFRE})
        cerez = r.cookies["sessionid"]
        self.assertTrue(cerez["httponly"])
        self.assertEqual(cerez["samesite"], "Lax")

    @override_settings(DEBUG=False)
    def test_hata_sayfasi_ic_bilgi_sizdirmaz(self):
        self.giris(self.koord)
        r = self.client.get("/boyle-bir-sayfa-yok/")
        self.assertEqual(r.status_code, 404)
        self.assertContains(r, "Sayfa bulunamadı", status_code=404)
        self.assertNotContains(r, "URLconf", status_code=404)
        self.assertNotContains(r, "settings", status_code=404)


class KimlikDogrulamaTestleri(GuvenlikTemel):
    """A07: Açık yönlendirme ve şifre politikası."""

    def test_giriste_acik_yonlendirme_yok(self):
        r = self.client.post(reverse("giris") + "?next=https://kotu-site.example/", {"username": "koord",
                                                                                      "password": SIFRE})
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("kotu-site", r["Location"])

    def test_bildirimde_acik_yonlendirme_yok(self):
        self.giris(self.cap_k)
        for baglanti in ("https://kotu-site.example/", "//kotu-site.example/x", "/\\kotu-site.example"):
            with self.subTest(baglanti=baglanti):
                b = Bildirim.objects.create(alici=self.cap_k, tur="ONAY", metin="x", baglanti=baglanti)
                r = self.client.get(reverse("bildirim_ac", args=[b.pk]))
                self.assertEqual(r["Location"], reverse("bildirimler"))

    def test_baskasinin_bildirimi_acilamaz(self):
        b = Bildirim.objects.create(alici=self.koord, tur="UYARI", metin="koordinatöre özel")
        self.giris(self.cap_k)
        self.assertEqual(self.client.get(reverse("bildirim_ac", args=[b.pk])).status_code, 404)

    def test_zayif_sifre_kabul_edilmez(self):
        for zayif in ("12345678", "sifre123", "qwertyuiop", "231101001x"):
            with self.subTest(sifre=zayif), self.assertRaises(ValidationError):
                validate_password(zayif, user=self.cap_k)


class HesapYonetimiTestleri(GuvenlikTemel):
    """ZAP taramasında görülen durum: koordinatör kendi şifresini 'sıfırla' ile sıfırlayıp oturumunu düşürmemeli."""

    def test_koordinator_kendi_sifresini_sifirlayamaz(self):
        self.giris(self.koord)
        r = self.client.post(reverse("hesap_sifre_sifirla", args=[self.koord.pk]), follow=True)
        self.assertContains(r, "Kendi şifrenizi buradan sıfırlayamazsınız")
        self.koord.refresh_from_db()
        self.assertFalse(self.koord.sifre_degistirmeli)
        self.assertTrue(self.koord.check_password(SIFRE))


class YonlendirmeTestleri(GuvenlikTemel):
    """ZAP aktif taramasında bulunan iki sorun için kalıcı testler."""

    def test_onay_sonrasi_geri_adresi_yalnizca_site_ici(self):
        from dersler import servisler as dsv
        self.giris(self.koord)
        kart = reverse("ogrenci_karti", args=["231101001"])
        for geri, beklenen in (("zApPX1117sS", kart),              # önceden 500 hatası veriyordu
                               ("https://kotu-site.example/", kart),
                               ("//kotu-site.example/", kart),
                               ("/onay/", "/onay/")):
            with self.subTest(geri=geri):
                d = dsv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=self.ders("3301156"), donem=self.guz)
                r = self.client.post(reverse("kayit_islemi", args=["231101001", "deneme", d.pk, "reddet"]),
                                     {"gerekce": "test", "geri": geri})
                self.assertEqual((r.status_code, r["Location"]), (302, beklenen))

    def test_sifre_sifirlamada_acik_yonlendirme_yok(self):
        self.giris(self.koord)
        r = self.client.post(reverse("hesap_sifre_sifirla", args=[self.baskan.pk]),
                             {"geri": "https://kotu-site.example/"})
        self.assertEqual(r["Location"], reverse("hesap_listesi"))
        r = self.client.post(reverse("hesap_sifre_sifirla", args=[self.baskan.pk]), {"geri": "bozuk-deger"})
        self.assertEqual(r["Location"], reverse("hesap_listesi"))
