"""Testlerde kullanılan ortak yardımcılar (sentetik dosyalar, geçici klasör)."""
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

GECERLI_PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
               b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
GECERLI_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32 + b"IEND\xaeB`\x82"


def pdf(ad="belge.pdf", icerik=GECERLI_PDF):
    return SimpleUploadedFile(ad, icerik, content_type="application/pdf")


class GeciciDosyaKlasoru:
    """Test sınıfına karıştırılır: yüklenen dosyalar geçici klasöre yazılır,
    test bitince silinir (gerçek arşive dokunulmaz)."""

    @classmethod
    def setUpClass(cls):
        cls._klasor = tempfile.mkdtemp(prefix="captakip_test_")
        cls._ayar = override_settings(KORUNAN_DOSYA_KOKU=cls._klasor)
        cls._ayar.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._ayar.disable()
        shutil.rmtree(cls._klasor, ignore_errors=True)
