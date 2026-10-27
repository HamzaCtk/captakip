from django.contrib.auth.models import AbstractUser
from django.db import models


class Kullanici(AbstractUser):
    """Sisteme giriş yapan herkes.

    E-postadaki gibi yalnızca üç rol vardır. Öğrenciler kendi kendine kayıt
    olamaz; hesapları koordinatör açar.
    """

    class Rol(models.TextChoices):
        KOORDINATOR = "KOORDINATOR", "Koordinatör"
        OGRENCI = "OGRENCI", "Öğrenci"
        BOLUM_BASKANI = "BOLUM_BASKANI", "Bölüm Başkanı"

    rol = models.CharField("Rol", max_length=20, choices=Rol.choices)
    # Koordinatör hesabı geçici şifreyle açar; kullanıcı ilk girişte
    # kendi şifresini belirlemek zorundadır.
    sifre_degistirmeli = models.BooleanField("İlk girişte şifre değiştirmeli", default=True)

    class Meta:
        verbose_name = "Kullanıcı"
        verbose_name_plural = "Kullanıcılar"

    # Rol kontrollerini şablonlarda ve kodda okunur kılmak için kısayollar
    @property
    def koordinator_mu(self):
        return self.rol == self.Rol.KOORDINATOR

    @property
    def ogrenci_mi(self):
        return self.rol == self.Rol.OGRENCI

    @property
    def bolum_baskani_mi(self):
        return self.rol == self.Rol.BOLUM_BASKANI

    def __str__(self):
        ad = self.get_full_name() or self.username
        return f"{ad} ({self.get_rol_display()})"


class GirisDenemesi(models.Model):
    """Her giriş denemesi kaydedilir. Art arda başarısız denemelerde hesap
    geçici olarak kilitlenir (kaba kuvvet saldırısına karşı)."""

    kullanici_adi = models.CharField(max_length=150, db_index=True)
    ip_adresi = models.GenericIPAddressField(null=True, blank=True)
    basarili = models.BooleanField()
    zaman = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Giriş denemesi"
        verbose_name_plural = "Giriş denemeleri"
        ordering = ["-zaman"]
