"""5-6. adım testleri: sürümlü kural ayarları, kural motoru, uyarılar, kurul kararları."""
import datetime
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.urls import reverse

from belgeler import servisler as bsv
from dersler import servisler as dsv
from dersler.models import Ders
from dersler.tests import SIFRE, Temel
from denetim.models import IslemKaydi
from ogrenciler.models import DonemKaydi
from ortak.test_yardimci import pdf

from . import motor, servisler as sv
from .models import KuralParametresi, KuralSurumu, Uyari
from .tanimlar import PARAMETRELER

BAHAR_ORTASI = datetime.date(2026, 3, 15)  # 2025-2026 Bahar dönemi içinde bir tarih


def acik(program, kural=None):
    qs = program.uyarilar.filter(durum__in=[Uyari.Durum.ACIK, Uyari.Durum.GORULDU])
    return qs.filter(kural=kural) if kural else qs


def cap_degerleri(**degisen):
    d = {p[0]: p[3] or "" for p in PARAMETRELER}
    d.update(degisen)
    return d


class KuralSurumuTestleri(Temel):
    def test_ilk_surumler_yuklenir(self):
        cap, ydp = KuralSurumu.gecerli("CAP"), KuralSurumu.gecerli("YDP")
        self.assertEqual(cap.degerler()["ana_gano_esik"], 2.72)
        self.assertEqual(ydp.degerler()["ana_gano_esik"], 2.30)
        self.assertIsNone(ydp.degerler()["azami_yariyil"])
        self.assertEqual(cap.degerler()["harf_puanlari"]["CB"], 2.5)

    def test_surum_ve_parametre_degistirilemez_silinemez(self):
        s = KuralSurumu.gecerli("CAP")
        s.ad = "Değişti"
        with self.assertRaises(PermissionDenied):
            s.save()
        p = s.parametreler.first()
        p.deger = "0"
        with self.assertRaises(PermissionDenied):
            p.save()
        with self.assertRaises(PermissionDenied):
            s.delete()
        with self.assertRaises(PermissionDenied):
            KuralParametresi.objects.all().delete()

    def test_veritabani_tetikleyicisi_dogrudan_sql_ile_degisikligi_engeller(self):
        s = KuralSurumu.gecerli("CAP")
        for sql in (f"UPDATE kurallar_kuralparametresi SET deger='0' WHERE surum_id={s.pk}",
                    f"UPDATE kurallar_kuralsurumu SET ad='x' WHERE id={s.pk}",
                    f"DELETE FROM kurallar_kuralsurumu WHERE id={s.pk}"):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as c:
                    c.execute(sql)

    def test_yeni_surum_eskisini_kapatir_eski_degerlendirme_degismez(self):
        eski_surum = KuralSurumu.gecerli("CAP")
        eski = motor.degerlendir(self.prog, "test")
        bugun = datetime.date.today()
        yeni = sv.yeni_surum(yapan=self.koord, program_turu="CAP", ad="Değişiklik", dayanak="Senato test kararı",
                             yururluk_baslangic=bugun, degerler=cap_degerleri(ana_gano_esik="3.00"))
        eski_surum.refresh_from_db()
        self.assertEqual(eski_surum.yururluk_bitis, bugun - datetime.timedelta(days=1))
        self.assertEqual(KuralSurumu.gecerli("CAP"), yeni)
        eski.refresh_from_db()
        self.assertEqual(eski.surum, eski_surum)  # geçmiş değerlendirme kendi sürümüyle kalır
        self.assertEqual(self.prog.degerlendirmeler.first().surum, yeni)  # yeniden değerlendirildi
        self.assertTrue(IslemKaydi.objects.filter(islem="KURAL_SURUMU_OLUSTURULDU", nesne_id=str(yeni.pk)).exists())

    def test_yeni_surum_yetki_ve_dogrulama(self):
        kw = dict(program_turu="CAP", ad="X", dayanak="Y", yururluk_baslangic=datetime.date.today(),
                  degerler=cap_degerleri())
        for yapan in (self.baskan, self.cap_k):
            with self.assertRaises(PermissionDenied):
                sv.yeni_surum(yapan=yapan, **kw)
        with self.assertRaises(ValidationError):
            sv.yeni_surum(yapan=self.koord, **{**kw, "degerler": cap_degerleri(ana_gano_esik="abc")})
        with self.assertRaises(ValidationError):  # mevcut sürümden önce başlayamaz
            sv.yeni_surum(yapan=self.koord, **{**kw, "yururluk_baslangic": datetime.date(2020, 1, 1)})

    def test_gecer_notlar_surumden_okunur(self):
        self.assertEqual(dsv.sonuc_hesapla("DD", "CAP"), "GECTI")
        sv.yeni_surum(yapan=self.koord, program_turu="CAP", ad="DD geçmez", dayanak="Test",
                      yururluk_baslangic=datetime.date.today(),
                      degerler=cap_degerleri(gecer_harf_notlari="AA, BA, BB, CB, CC, DC"))
        self.assertEqual(dsv.sonuc_hesapla("DD", "CAP"), "KALDI")
        self.assertEqual(dsv.sonuc_hesapla("DD", "YDP"), "GECTI")


class KuralMotoruTestleri(Temel):
    def test_iki_donem_ders_almayan_ogrenci_kritik_uyari_alir(self):
        motor.degerlendir(self.prog, "test")
        u = acik(self.prog, "ders_almama").get()
        self.assertEqual(u.seviye, Uyari.Seviye.KRITIK)
        self.assertIn("2 dönem", u.mesaj)
        self.assertEqual(u.dayanak, "ÇAP Md. 9/d")

    def test_bir_donem_ders_almayan_ogrenci_on_uyari_alir(self):
        ydp = self.ydp.guncel_program  # YDP yönergesi bu tarihte yürürlükte
        motor.degerlendir(ydp, "test", tarih=BAHAR_ORTASI)
        u = acik(ydp, "ders_almama").get()
        self.assertEqual(u.seviye, Uyari.Seviye.UYARI)
        self.assertEqual(u.dayanak, "YDP Md. 7/4")

    def test_yururlukten_once_kural_uygulanmaz(self):
        self.assertIsNone(motor.degerlendir(self.prog, "test", tarih=BAHAR_ORTASI))  # ÇAP yön. 20.05.2026

    def test_yalnizca_onayli_kayitlar_hesaba_girer(self):
        motor.degerlendir(self.prog, "test")
        deneme = dsv.deneme_ekle(yapan=self.cap_k, ogrenci_dersi=self.ders("3301156"), donem=self.bahar)
        motor.degerlendir(self.prog, "test")
        self.assertEqual(acik(self.prog, "ders_almama").get().seviye, Uyari.Seviye.KRITIK)  # bekleyen sayılmaz
        dsv.onayla(yapan=self.koord, kayit=deneme)  # onay kuralları kendiliğinden çalıştırır
        self.assertFalse(acik(self.prog, "ders_almama").exists())
        eski = self.prog.uyarilar.get(kural="ders_almama")
        self.assertEqual(eski.durum, Uyari.Durum.GECERSIZ)  # silinmez, koşul kalktı olarak kapanır

    def test_ayni_uyari_tekrar_acilmaz(self):
        for _ in range(3):
            motor.degerlendir(self.prog, "test")
        self.assertEqual(self.prog.uyarilar.filter(kural="ders_almama").count(), 1)
        self.assertEqual(self.prog.degerlendirmeler.count(), 4)  # ekleme anı + 3

    def test_cap_ana_dal_gano_bir_defalik_hak_sonra_kritik(self):
        sv.ana_dal_kaydi_ekle(yapan=self.koord, program=self.prog, donem=self.guz, gano=Decimal("2.60"),
                              ana_dal_durumu="AKTIF", kaynak_aciklama="Transkript")
        ilk = acik(self.prog, "ana_dal_gano").get()
        self.assertEqual(ilk.seviye, Uyari.Seviye.UYARI)
        self.assertIn("toleransı içinde", ilk.mesaj)
        sv.ana_dal_kaydi_ekle(yapan=self.koord, program=self.prog, donem=self.bahar, gano=Decimal("2.40"),
                              ana_dal_durumu="AKTIF", kaynak_aciklama="Transkript")
        self.assertEqual(acik(self.prog, "ana_dal_gano").get().seviye, Uyari.Seviye.KRITIK)
        ilk.refresh_from_db()
        self.assertEqual(ilk.durum, Uyari.Durum.GECERSIZ)

    def test_ana_dal_gano_duzelince_uyari_kapanir(self):
        sv.ana_dal_kaydi_ekle(yapan=self.koord, program=self.prog, donem=self.guz, gano=Decimal("2.60"),
                              ana_dal_durumu="AKTIF", kaynak_aciklama="Transkript")
        sv.ana_dal_kaydi_ekle(yapan=self.koord, program=self.prog, donem=self.bahar, gano=Decimal("3.00"),
                              ana_dal_durumu="AKTIF", kaynak_aciklama="Transkript")
        self.assertFalse(acik(self.prog, "ana_dal_gano").exists())

    def test_ydp_ana_dal_gano_ilk_dususte_kritik(self):
        ydp = self.ydp.guncel_program
        sv.ana_dal_kaydi_ekle(yapan=self.koord, program=ydp, donem=self.bahar, gano=Decimal("2.20"),
                              ana_dal_durumu="AKTIF", kaynak_aciklama="Öğrenci işleri yazısı")
        u = acik(ydp, "ana_dal_gano").get()
        self.assertEqual(u.seviye, Uyari.Seviye.KRITIK)
        self.assertEqual(u.dayanak, "YDP Md. 7/5")

    def test_ydp_asgari_ders_yuku(self):
        ydp = self.ydp.guncel_program
        motor.degerlendir(ydp, "test")
        self.assertEqual(acik(ydp, "asgari_yuk").get().seviye, Uyari.Seviye.UYARI)

    def test_ydp_program_ortalamasi_iki_donem_dusuk_kritik(self):
        ydp = self.ydp.guncel_program
        d1, d2 = Ders.objects.get(kod="3301351"), Ders.objects.get(kod="3301352")
        for ders, donem in ((d1, self.guz), (d2, self.bahar)):
            od = dsv.ders_ekle(yapan=self.koord, program=ydp, ders=ders, gerekce="Yan dal ders seçimi")
            dsv.deneme_ekle(yapan=self.koord, ogrenci_dersi=od, donem=donem, harf_notu="DD")
        u = acik(ydp, "program_gano").get()
        self.assertEqual(u.seviye, Uyari.Seviye.KRITIK)
        self.assertIn("2 dönem", u.mesaj)

    def test_ana_dal_bilgisini_yalnizca_koordinator_girer(self):
        for yapan in (self.baskan, self.cap_k):
            with self.assertRaises(PermissionDenied):
                sv.ana_dal_kaydi_ekle(yapan=yapan, program=self.prog, donem=self.guz, gano=Decimal("3"),
                                      ana_dal_durumu="AKTIF", kaynak_aciklama="x")
        with self.assertRaises(ValidationError):
            sv.ana_dal_kaydi_ekle(yapan=self.koord, program=self.prog, donem=self.guz, gano=Decimal("5"),
                                  ana_dal_durumu="AKTIF", kaynak_aciklama="x")


class UyariVeKararTestleri(Temel):
    def setUp(self):
        super().setUp()
        motor.degerlendir(self.prog, "test")
        self.uyari = acik(self.prog, "ders_almama").get()

    def karar_belgesi(self, ogrenci=None):
        return bsv.belge_yukle(yapan=self.koord, ogrenci=ogrenci or self.cap, dosya=pdf("karar.pdf"),
                               tur="KURUL_KARARI", aciklama="Yönetim kurulu kararı")

    def karar(self, **kw):
        veri = dict(yapan=self.koord, program=self.prog, tur="KAYIT_SILME", kurul="Fakülte Yönetim Kurulu",
                    karar_tarihi=datetime.date(2026, 9, 1), karar_sayisi="2026/45-3",
                    gerekce="İki dönem ders almadı", dayanak_belge=None)
        veri.update(kw)
        return sv.karar_isle(**veri)

    def test_uyari_gorulur_ve_karara_baglanir(self):
        with self.assertRaises(PermissionDenied):
            sv.uyari_kapat(yapan=self.cap_k, uyari=self.uyari, durum="GORULDU")
        sv.uyari_kapat(yapan=self.koord, uyari=self.uyari, durum="GORULDU")
        with self.assertRaises(ValidationError):  # karar bilgisi zorunlu
            sv.uyari_kapat(yapan=self.koord, uyari=self.uyari, durum="KARARA_BAGLANDI")
        sv.uyari_kapat(yapan=self.koord, uyari=self.uyari, durum="KARARA_BAGLANDI", notu="FYK 2026/45-3")
        motor.degerlendir(self.prog, "test")  # karara bağlanan uyarı yeniden açılmaz
        self.assertEqual(self.prog.uyarilar.filter(kural="ders_almama").count(), 1)
        with self.assertRaises(PermissionDenied):
            self.uyari.delete()

    def test_karar_dayanak_belge_olmadan_islenemez(self):
        with self.assertRaises(ValidationError):
            self.karar()
        baska = self._ogrenci("231101099", "CAP")
        with self.assertRaises(ValidationError):
            self.karar(dayanak_belge=self.karar_belgesi(baska))
        self.prog.refresh_from_db()
        self.assertEqual(self.prog.durum, "AKTIF")

    def test_karar_yalnizca_koordinator(self):
        for yapan in (self.baskan, self.cap_k):
            with self.assertRaises(PermissionDenied):
                self.karar(yapan=yapan, dayanak_belge=self.karar_belgesi())

    def test_kayit_silme_karari_programi_sonuclandirir(self):
        k = self.karar(dayanak_belge=self.karar_belgesi())
        self.prog.refresh_from_db()
        self.assertEqual(self.prog.durum, "SILINDI")
        self.uyari.refresh_from_db()
        self.assertEqual(self.uyari.durum, Uyari.Durum.KARARA_BAGLANDI)
        self.assertIn("2026/45-3", self.uyari.kapatma_notu)
        self.assertIsNone(motor.degerlendir(self.prog, "test"))  # sonuçlanan program değerlendirilmez
        self.assertTrue(IslemKaydi.objects.filter(islem="KARAR_ISLENDI", nesne_id=str(k.pk)).exists())
        with self.assertRaises(ValidationError):  # ikinci karar işlenemez
            self.karar(dayanak_belge=self.karar_belgesi(), tur="AYRILMA")

    def test_dondurma_karari_donemi_ders_almama_kuralindan_cikarir(self):
        self.karar(tur="DONDURMA", donem=self.bahar, dayanak_belge=self.karar_belgesi())
        self.assertEqual(DonemKaydi.objects.get(program_kaydi=self.prog, donem=self.bahar).kayit_durumu,
                         "DONDURULDU")
        self.assertFalse(acik(self.prog, "ders_almama").exists())
        self.prog.refresh_from_db()
        self.assertEqual(self.prog.durum, "AKTIF")

    def test_sertifika_karari_capta_islenemez(self):
        with self.assertRaises(ValidationError):
            self.karar(tur="SERTIFIKA", dayanak_belge=self.karar_belgesi())


class EkranTestleri(Temel):
    def giris(self, k):
        self.client.login(username=k.username, password=SIFRE)

    def setUp(self):
        super().setUp()
        self.cap_k.set_password(SIFRE)
        self.cap_k.save()
        self.ydp.kullanici.set_password(SIFRE)
        self.ydp.kullanici.save()
        motor.degerlendir(self.prog, "test")

    def test_ogrenci_kendi_uyarilarini_gorur_baskasini_goremez(self):
        self.giris(self.cap_k)
        r = self.client.get(reverse("ogrenci_durum", args=["231101001"]))
        self.assertContains(r, "üst üste ders alınmadı")
        self.assertNotContains(r, "Kuralları şimdi değerlendir")
        self.assertNotContains(r, "Değerlendirme geçmişi")
        self.assertEqual(self.client.get(reverse("ogrenci_durum", args=["231101002"])).status_code, 403)
        r = self.client.post(reverse("ana_dal_ekle", args=["231101001"]),
                             {"donem": self.guz.pk, "gano": "3.50", "ana_dal_durumu": "AKTIF", "kaynak_aciklama": "x"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self.prog.ana_dal_kayitlari.exists())
        self.assertEqual(self.client.get(reverse("kural_ayarlari")).status_code, 403)

    def test_koordinator_ana_dal_girer_ve_uyarilar_gorunur(self):
        self.giris(self.koord)
        r = self.client.post(reverse("ana_dal_ekle", args=["231101001"]),
                             {"donem": self.guz.pk, "gano": "2.60", "ana_dal_durumu": "AKTIF",
                              "kaynak_aciklama": "Ana dal transkripti"}, follow=True)
        self.assertContains(r, "Ana dal GANO 2,60")
        self.assertContains(self.client.get(reverse("ogrenci_listesi") + "?uyari=kritik"), "231101001")
        self.assertContains(self.client.get(reverse("anasayfa")), "Açık uyarılar")
        self.assertContains(self.client.get(reverse("ogrenci_karti", args=["231101001"])), "Açık uyarılar")

    def test_baska_ogrencinin_uyarisi_kapatilamaz(self):
        self.giris(self.koord)
        u = acik(self.prog).first()
        r = self.client.post(reverse("uyari_durumu", args=["231101002", u.pk]), {"durum": "GORULDU"})
        self.assertEqual(r.status_code, 404)
        u.refresh_from_db()
        self.assertEqual(u.durum, Uyari.Durum.ACIK)

    def test_bolum_baskani_kural_ayarlarini_gorur_degistiremez(self):
        self.giris(self.baskan)
        r = self.client.get(reverse("kural_ayarlari"))
        self.assertContains(r, "Yürürlükte")
        self.assertNotContains(r, "+ Yeni sürüm")
        sayi = KuralSurumu.objects.count()
        self.client.post(reverse("surum_yeni", args=["CAP"]), {"ad": "x", "dayanak": "y",
                                                                "yururluk_baslangic": "2026-12-01"})
        self.assertEqual(KuralSurumu.objects.count(), sayi)

    def test_koordinator_ekrandan_yeni_surum_girer(self):
        self.giris(self.koord)
        r = self.client.get(reverse("surum_yeni", args=["YDP"]))
        self.assertContains(r, 'value="2.30"')  # önceki sürümden dolu gelir
        veri = {"ad": "YDP değişikliği", "dayanak": "Senato 2026/99", "yururluk_baslangic": str(datetime.date.today())}
        veri.update({f"p_{a}": (v or "") for a, _e, _t, _c, v, _d in PARAMETRELER})
        veri["p_asgari_akts"] = "24"
        r = self.client.post(reverse("surum_yeni", args=["YDP"]), veri, follow=True)
        self.assertContains(r, "Yeni kural sürümü kaydedildi")
        self.assertEqual(KuralSurumu.gecerli("YDP").degerler()["asgari_akts"], 24)

    def test_karar_ekrani(self):
        self.giris(self.koord)
        belge = bsv.belge_yukle(yapan=self.koord, ogrenci=self.cap, dosya=pdf("karar.pdf"), tur="KURUL_KARARI")
        r = self.client.get(reverse("karar_isle", args=["231101001"]))
        self.assertContains(r, "Kurul kararı işle")
        self.assertNotContains(r, "Yan dal sertifikası")  # ÇAP öğrencisine sertifika seçeneği yok
        r = self.client.post(reverse("karar_isle", args=["231101001"]), {
            "tur": "DONDURMA", "kurul": "FYK", "karar_tarihi": "2026-09-01", "karar_sayisi": "2026/1",
            "donem": self.bahar.pk, "dayanak_belge": belge.pk, "gerekce": "Sağlık mazereti"}, follow=True)
        self.assertContains(r, "Karar işlendi")
        self.assertContains(r, "Sağlık mazereti")
