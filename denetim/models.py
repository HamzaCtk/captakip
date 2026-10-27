from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models


class IslemKaydi(models.Model):
    """Değiştirilemez ve silinemez işlem kaydı (denetim izi).

    E-posta: "Sistemde yapılan her işlem kayıt altına alınır: kim, ne zaman,
    neyi, eski ve yeni değeriyle ne yaptı. Bu kayıt değiştirilemez ve
    silinemez."

    Koruma iki katmanlıdır:
      1) Python tarafında: save() yalnızca yeni kayıt oluşturur, delete() hata verir.
      2) Veritabanı tarafında: UPDATE/DELETE engelleyen tetikleyiciler
         (bkz. migrations/0002_degistirilemez_tetikleyiciler.py).
    """

    zaman = models.DateTimeField(auto_now_add=True, db_index=True)
    yapan = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
        help_text="Boşsa işlemi sistem yapmıştır.",
    )
    islem = models.CharField("İşlem", max_length=60, db_index=True)
    # Hangi kayıt üzerinde işlem yapıldı? (ör. "Kullanici", 12)
    nesne_turu = models.CharField(max_length=60, blank=True)
    nesne_id = models.CharField(max_length=40, blank=True)
    nesne_metni = models.CharField(max_length=255, blank=True)
    # İlgili öğrenci (öğrenci kartında geçmişi göstermek için)
    ogrenci_no = models.CharField(max_length=20, blank=True, db_index=True)
    eski_deger = models.JSONField(null=True, blank=True)
    yeni_deger = models.JSONField(null=True, blank=True)
    aciklama = models.TextField("Açıklama / gerekçe", blank=True)
    ip_adresi = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "İşlem kaydı"
        verbose_name_plural = "İşlem kayıtları"
        ordering = ["-zaman", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied("İşlem kaydı değiştirilemez.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("İşlem kaydı silinemez.")

    def __str__(self):
        return f"{self.zaman:%d.%m.%Y %H:%M} {self.yapan} {self.islem}"
