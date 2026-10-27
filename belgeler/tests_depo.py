"""Canlı ortam: dosyaların veritabanında saklanması (Render'da disk kalıcı değil)."""
import os
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from aktarim import servisler as asv
from dersler.tests import SIFRE, Temel
from mesajlar import servisler as msv
from ortak import depo
from ortak.test_yardimci import GECERLI_PDF, pdf

from . import servisler as sv
from .models import DepolananDosya


@override_settings(DOSYA_DEPOSU="veritabani")
class VeritabaniDeposuTestleri(Temel):
    def setUp(self):
        super().setUp()
        self.cap_k.set_password(SIFRE)
        self.cap_k.save()

    def diskte_dosya_yok(self):
        kok = Path(self._klasor)
        return not any(p.is_file() for p in kok.rglob("*"))

    def test_belge_veritabanina_yazilir_ve_indirilir(self):
        b = sv.belge_yukle(yapan=self.cap_k, ogrenci=self.cap, dosya=pdf("transkript.pdf"), tur="TRANSKRIPT",
                           donem=self.guz)
        kayit = DepolananDosya.objects.get(yol=b.dosya_yolu)
        self.assertEqual((bytes(kayit.icerik), kayit.sha256), (GECERLI_PDF, b.sha256))
        self.assertTrue(self.diskte_dosya_yok())
        self.client.login(username=self.cap_k.username, password=SIFRE)
        r = self.client.get(reverse("belge_indir", args=[self.cap.ogrenci_no, b.pk]))
        self.assertEqual(b"".join(r.streaming_content), GECERLI_PDF)
        self.assertIn("attachment", r["Content-Disposition"])

    def test_mesaj_eki_ve_csv_veritabaninda(self):
        m = msv.mesaj_gonder(yapan=self.cap_k, ogrenci=self.cap, metin="ekli", ek=pdf("ek.pdf"))
        self.assertEqual(depo.oku(m.ek_yolu), GECERLI_PDF)
        metin = "Öğrenci No;Adı;Soyadı;E-posta;Bölüm;Program;Kabul Dönemi\n" \
                "231101091;Ada;Deneme;a@ornek.edu.tr;EEM;YDP;2025-2026 Güz\n"
        islem = asv.yukle(yapan=self.koord, tur="OGRENCI",
                          dosya=SimpleUploadedFile("o.csv", metin.encode(), content_type="text/csv"))
        asv.uygula(yapan=self.koord, islem=islem)  # dosyayı depodan yeniden okur ve özetini doğrular
        self.assertTrue(self.diskte_dosya_yok())
        self.assertEqual(DepolananDosya.objects.count(), 2)

    def test_depolanan_dosya_degistirilemez_silinemez(self):
        depo.kaydet("2026/10/deneme.pdf", GECERLI_PDF)
        d = DepolananDosya.objects.get()
        with self.assertRaises(PermissionDenied):
            d.save()
        with self.assertRaises(PermissionDenied):
            d.delete()
        self.assertIsNone(depo.oku("2026/10/yok.pdf"))


class DiskDeposuTestleri(Temel):
    def test_kok_disina_cikilamaz(self):
        with self.assertRaises(ValueError):
            depo.kaydet("../../disari.pdf", GECERLI_PDF)


class CanliKurulumTestleri(Temel):
    def test_demo_verisi_bos_ise_atlar(self):
        # Temel sınıfı zaten öğrenci ekledi: --bos-ise hata vermeden geçmeli
        call_command("demo_verisi", "--bos-ise", verbosity=0, stdout=open(os.devnull, "w"))


class CanliSifreTestleri(TestCase):
    """Boş veritabanı: canlıda şifre ortam değişkenleri yoksa demo verisi kurulmaz."""

    @override_settings(CANLI=True)
    def test_canlida_sifre_ortam_degiskeni_zorunlu(self):
        from unittest import mock
        from django.core.management.base import CommandError
        from ogrenciler.models import Ogrenci
        with mock.patch.dict(os.environ, {"CAPTAKIP_DEMO_YONETICI_SIFRESI": "", "CAPTAKIP_DEMO_OGRENCI_SIFRESI": ""}):
            with self.assertRaisesMessage(CommandError, "ortam değişkenleri zorunludur"):
                call_command("demo_verisi", "--bos-ise", verbosity=0)
        self.assertFalse(Ogrenci.objects.exists())
