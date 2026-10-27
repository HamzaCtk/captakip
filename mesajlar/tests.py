"""7. adım testleri: mesajlaşma, mesaj ekleri, okundu bilgisi ve bildirimler."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from belgeler import servisler as bsv
from denetim.models import IslemKaydi
from dersler import servisler as dsv
from accounts.models import Kullanici
from dersler.tests import Temel, kullanici
from kurallar import motor
from ortak.test_yardimci import pdf

from . import servisler as sv
from .models import Bildirim, Mesaj


class MesajServisTestleri(Temel):
    def test_ogrenci_kendi_konusmasina_yazar_islem_kaydi_dusulur(self):
        m = sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="  Protokolüm hakkında bir sorum var.  ")
        self.assertEqual(m.metin, "Protokolüm hakkında bir sorum var.")
        self.assertTrue(m.ogrenciden_mi)
        k = IslemKaydi.objects.get(islem="MESAJ_GONDERILDI")
        self.assertEqual(k.ogrenci_no, self.cap.ogrenci_no)
        self.assertEqual(k.yapan, self.cap_k)

    def test_ogrenci_baska_ogrenciye_yazamaz(self):
        with self.assertRaises(PermissionDenied):
            sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.ydp, metin="Merhaba")

    def test_bolum_baskani_yazamaz_koordinator_herkese_yazar(self):
        with self.assertRaises(PermissionDenied):
            sv.mesaj_gonder(yapan=self.baskan, ogrenci=self.cap, metin="Merhaba")
        sv.mesaj_gonder(yapan=self.koord, ogrenci=self.ydp, metin="Ders listenizi kontrol ettim.")
        self.assertEqual(self.ydp.mesajlar.count(), 1)

    def test_bos_veya_cok_uzun_mesaj_reddedilir(self):
        for metin in ("", "   ", "x" * (sv.MAKS_UZUNLUK + 1)):
            with self.assertRaises(ValidationError):
                sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin=metin)

    def test_mesaj_silinemez_ve_degistirilemez(self):
        m = sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="İlk metin")
        with self.assertRaises(PermissionDenied):
            m.delete()
        with self.assertRaises(PermissionDenied):
            Mesaj.objects.filter(pk=m.pk).delete()
        m.metin = "Değiştirilmiş metin"
        with self.assertRaises(PermissionDenied):
            m.save()
        with self.assertRaises(PermissionDenied):
            m.save(update_fields=["metin", "okunma_zamani"])
        m.refresh_from_db()
        self.assertEqual(m.metin, "İlk metin")

    def test_okundu_bilgisi_karsi_tarafta_isaretlenir(self):
        m = sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="Soru")
        self.assertEqual(sv.okunmamis_mesaj_sayisi(self.koord), 1)
        sv.okundu_isaretle(okuyan=self.cap_k, ogrenci=self.cap)  # kendi mesajını okuması sayılmaz
        sv.okundu_isaretle(okuyan=self.baskan, ogrenci=self.cap)  # bölüm başkanı tarafı değil
        m.refresh_from_db()
        self.assertIsNone(m.okunma_zamani)
        sv.okundu_isaretle(okuyan=self.koord, ogrenci=self.cap)
        m.refresh_from_db()
        self.assertIsNotNone(m.okunma_zamani)
        self.assertEqual(m.okuyan, self.koord)
        self.assertEqual(sv.okunmamis_mesaj_sayisi(self.koord), 0)

        sv.mesaj_gonder(yapan=self.koord, ogrenci=self.cap, metin="Cevap")
        self.assertEqual(sv.okunmamis_mesaj_sayisi(self.cap_k), 1)
        self.assertEqual(sv.okunmamis_mesaj_sayisi(self.ydp.kullanici), 0)  # başkasının mesajı sayılmaz
        sv.okundu_isaretle(okuyan=self.cap_k, ogrenci=self.cap)
        self.assertEqual(sv.okunmamis_mesaj_sayisi(self.cap_k), 0)


class MesajEkiTestleri(Temel):
    def test_gecerli_ek_korunan_klasore_rastgele_adla_yazilir(self):
        m = sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="Formum ekte", ek=pdf("form.pdf"))
        self.assertTrue(m.ek_var_mi)
        self.assertEqual(m.ek_adi, "form.pdf")
        self.assertEqual(m.ek_mime, "application/pdf")
        self.assertNotIn("form", m.ek_yolu)
        self.assertTrue(sv.ek_yolu(m).is_file())

    def test_sahte_veya_zararli_ek_reddedilir_mesaj_olusmaz(self):
        sahte = SimpleUploadedFile("odev.pdf", b"MZ\x90\x00 calistirilabilir", "application/pdf")
        js = SimpleUploadedFile("x.pdf", b"%PDF-1.4\n/JavaScript (alert(1))\n%%EOF\n", "application/pdf")
        exe = SimpleUploadedFile("x.exe", b"MZ\x90\x00", "application/octet-stream")
        for dosya in (sahte, js, exe):
            with self.assertRaises(ValidationError):
                sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="Ek", ek=dosya)
        self.assertFalse(Mesaj.objects.exists())

    def test_ek_yalnizca_yetkili_kisiye_guvenli_basliklarla_indirilir(self):
        m = sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="Ek", ek=pdf("form.pdf"))
        adres = reverse("mesaj_ek_indir", args=[self.cap.ogrenci_no, m.pk])
        self.client.force_login(self.cap_k)
        cevap = self.client.get(adres)
        self.assertEqual(cevap.status_code, 200)
        self.assertIn("attachment", cevap["Content-Disposition"])
        self.assertEqual(cevap["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", cevap["Content-Security-Policy"])
        b"".join(cevap.streaming_content)
        # Başka öğrenci: kendi numarasıyla başkasının ekini açamaz, başkasının numarasını da deneyemez
        self.client.force_login(self.ydp.kullanici)
        self.assertEqual(self.client.get(adres).status_code, 403)
        yanlis = reverse("mesaj_ek_indir", args=[self.ydp.ogrenci_no, m.pk])
        self.assertEqual(self.client.get(yanlis).status_code, 404)


class MesajEkranTestleri(Temel):
    def giris(self, kullanici_adi):
        self.client.force_login(Kullanici.objects.get(username=kullanici_adi))

    def test_ogrenci_mesaj_kutusundan_kendi_konusmasina_gider(self):
        self.giris(self.cap.ogrenci_no)
        cevap = self.client.get(reverse("mesaj_kutusu"))
        self.assertRedirects(cevap, reverse("konusma", args=[self.cap.ogrenci_no]))

    def test_ogrenci_baskasinin_konusmasini_goremez_yazamaz(self):
        sv.mesaj_gonder(yapan=self.koord, ogrenci=self.ydp, metin="Gizli içerik")
        self.giris(self.cap.ogrenci_no)
        self.assertEqual(self.client.get(reverse("konusma", args=[self.ydp.ogrenci_no])).status_code, 403)
        cevap = self.client.post(reverse("mesaj_gonder", args=[self.ydp.ogrenci_no]), {"metin": "Merhaba"})
        self.assertEqual(cevap.status_code, 403)
        self.assertEqual(self.ydp.mesajlar.count(), 1)

    def test_ekrandan_mesaj_gonderilir_ve_koordinator_okuyunca_okundu_olur(self):
        self.giris(self.cap.ogrenci_no)
        self.client.post(reverse("mesaj_gonder", args=[self.cap.ogrenci_no]),
                         {"metin": "Ders kayıt formumu yükledim.", "ek": pdf("kayit.pdf")})
        m = self.cap.mesajlar.get()
        self.assertTrue(m.ek_var_mi)
        self.giris("koord")
        cevap = self.client.get(reverse("mesaj_kutusu"))
        self.assertContains(cevap, self.cap.ogrenci_no)
        self.assertContains(cevap, "1 yeni")
        cevap = self.client.get(reverse("konusma", args=[self.cap.ogrenci_no]))
        self.assertContains(cevap, "Ders kayıt formumu yükledim.")
        m.refresh_from_db()
        self.assertIsNotNone(m.okunma_zamani)

    def test_bolum_baskani_okur_ama_yazamaz(self):
        sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="Soru")
        self.giris("baskan")
        cevap = self.client.get(reverse("konusma", args=[self.cap.ogrenci_no]))
        self.assertContains(cevap, "Soru")
        self.assertNotContains(cevap, 'name="metin"')
        cevap = self.client.post(reverse("mesaj_gonder", args=[self.cap.ogrenci_no]), {"metin": "Cevap"})
        self.assertEqual(cevap.status_code, 403)
        self.assertIsNone(self.cap.mesajlar.get().okunma_zamani)  # bölüm başkanı okuması sayılmaz

    def test_mesajdaki_html_calistirilmaz(self):
        sv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="<script>alert('xss')</script>")
        self.giris("koord")
        cevap = self.client.get(reverse("konusma", args=[self.cap.ogrenci_no]))
        self.assertNotContains(cevap, "<script>alert")
        self.assertContains(cevap, "&lt;script&gt;")

    def test_menude_okunmamis_mesaj_sayaci(self):
        sv.mesaj_gonder(yapan=self.koord, ogrenci=self.cap, metin="Bilgi")
        self.giris(self.cap.ogrenci_no)
        cevap = self.client.get(reverse("bildirimler"))
        self.assertEqual(cevap.context["okunmamis_mesaj"], 1)


class BildirimTestleri(Temel):
    def bildirimler(self, kullanici, tur=None):
        qs = Bildirim.objects.filter(alici=kullanici)
        return qs.filter(tur=tur) if tur else qs

    def test_onay_ve_red_ogrenciye_bildirilir(self):
        deneme = dsv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=self.ders("3301156"), donem=self.bahar)
        dsv.onayla(yapan=self.koord, kayit=deneme)
        self.assertIn("onaylandı", self.bildirimler(self.cap_k, "ONAY").get().metin)
        baska = self.prog.dersler.filter(ders__isnull=False, liste_durumu="AKTIF").exclude(ders__kod="3301156").first()
        guz = dsv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=baska, donem=self.guz)
        dsv.reddet(yapan=self.koord, kayit=guz, gerekce="Ders kayıt formu eksik")
        red = self.bildirimler(self.cap_k, "RED").get()
        self.assertIn("Ders kayıt formu eksik", red.metin)
        self.assertEqual(red.baglanti, reverse("ogrenci_karti", args=[self.cap.ogrenci_no]))
        self.assertFalse(self.bildirimler(self.ydp.kullanici).filter(tur__in=["ONAY", "RED"]).exists())

    def test_iptal_ve_duzeltme_bildirilir(self):
        deneme = dsv.deneme_ekle(yapan=self.koord, ogrenci_dersi=self.ders("3301156"), donem=self.bahar)
        dsv.deneme_duzelt(yapan=self.koord, deneme=deneme, donem=self.bahar, harf_notu="BA", gerekce="Not hatası")
        self.assertTrue(self.bildirimler(self.cap_k, "DUZELTME").exists())
        dsv.iptal_et(yapan=self.koord, kayit=deneme, gerekce="Yanlış öğrenciye girildi")
        self.assertIn("Yanlış öğrenciye girildi", self.bildirimler(self.cap_k, "IPTAL").get().metin)

    def test_belge_red_ve_istek_bildirilir(self):
        b = bsv.belge_yukle(yapan=self.cap_k, ogrenci=self.cap, dosya=pdf(), tur="PROTOKOL_FORMU")
        bsv.belge_reddet(yapan=self.koord, belge=b, gerekce="İmza eksik")
        red = self.bildirimler(self.cap_k, "RED").get()
        self.assertIn("İmza eksik", red.metin)
        self.assertEqual(red.baglanti, reverse("belgeler", args=[self.cap.ogrenci_no]))
        bsv.istek_olustur(yapan=self.koord, ogrenci=self.cap, tur="MUAFIYET_FORMU", aciklama="Lütfen yükleyin")
        self.assertTrue(self.bildirimler(self.cap_k, "BELGE_ISTEGI").exists())

    def test_yeni_kritik_uyari_ogrenciye_ve_diger_koordinatorlere_bir_kez_bildirilir(self):
        # Öğrenci eklenirken motor çalıştı: "2 dönem ders almama" KRİTİK uyarısı açık.
        # İşlemi yapan koordinatör uyarıyı zaten ekranda görür; ona ayrıca bildirim gitmez.
        self.assertEqual(self.bildirimler(self.cap_k, "UYARI").count(), 1)
        self.assertIn("Kritik", self.bildirimler(self.cap_k, "UYARI").get().metin)
        self.assertFalse(self.bildirimler(self.koord, "UYARI").exists())
        ikinci = kullanici("koord2", Kullanici.Rol.KOORDINATOR)
        yeni = self._ogrenci("231101009", "CAP")
        self.assertEqual(self.bildirimler(ikinci, "UYARI").filter(ogrenci_no=yeni.ogrenci_no).count(), 1)
        self.assertFalse(self.bildirimler(self.baskan).exists())  # bölüm başkanına bildirim gitmez
        for _ in range(3):  # aynı uyarı tekrar bildirilmez
            motor.degerlendir(self.prog, "test")
        self.assertEqual(self.bildirimler(self.cap_k, "UYARI").count(), 1)

    def test_bildirim_yalnizca_sahibi_tarafindan_acilir_ve_okundu_olur(self):
        b = self.bildirimler(self.cap_k, "UYARI").get()
        self.client.force_login(self.ydp.kullanici)
        self.assertEqual(self.client.get(reverse("bildirim_ac", args=[b.pk])).status_code, 404)
        self.client.force_login(self.cap_k)
        cevap = self.client.get(reverse("bildirim_ac", args=[b.pk]))
        self.assertRedirects(cevap, reverse("ogrenci_durum", args=[self.cap.ogrenci_no]))
        b.refresh_from_db()
        self.assertTrue(b.okundu_mu)

    def test_dis_adrese_yonlendirme_yapilmaz(self):
        b = Bildirim.objects.create(alici=self.cap_k, tur="ONAY", metin="x", baglanti="//kotu.example.com/")
        self.client.force_login(self.cap_k)
        self.assertRedirects(self.client.get(reverse("bildirim_ac", args=[b.pk])), reverse("bildirimler"))

    def test_tumunu_okundu_yap_ve_sayac(self):
        self.client.force_login(self.cap_k)
        cevap = self.client.get(reverse("bildirimler"))
        self.assertEqual(cevap.context["okunmamis_bildirim"], 1)
        self.client.post(reverse("bildirim_tumunu_okundu"))
        self.assertFalse(self.bildirimler(self.cap_k).filter(okunma_zamani__isnull=True).exists())

    def test_bildirim_silinemez_ve_metni_degismez(self):
        b = self.bildirimler(self.cap_k).first()
        with self.assertRaises(PermissionDenied):
            b.delete()
        b.metin = "değişti"
        with self.assertRaises(PermissionDenied):
            b.save()
