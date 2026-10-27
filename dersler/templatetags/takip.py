"""Şablonlarda kullanılan küçük yardımcılar."""
from django import template

register = template.Library()

_RENKLER = {
    "Geçti": "yesil", "Muaf": "gri", "Kaldı": "kirmizi", "Alındı": "mavi",
    "Planlandı": "mavi", "Henüz alınmadı": "gri", "Ders seçilmedi": "gri",
    "Listeden çıkarıldı": "gri",
    "Onay bekliyor": "sari", "Onaylandı": "yesil", "Reddedildi": "kirmizi", "İptal": "gri",
    "Aktif": "yesil", "Dondurulmuş": "sari", "Mezun (diploma)": "mavi",
    "Sertifika aldı": "mavi", "Kaydı silindi": "kirmizi", "Kendi isteğiyle ayrıldı": "gri",
}


@register.filter
def durum_rengi(metin):
    return _RENKLER.get(str(metin), "gri")


_ISLEMLER = {
    "GIRIS": "Sisteme giriş", "SIFRE_DEGISTIRILDI": "Şifre değiştirildi", "SIFRE_SIFIRLANDI": "Şifre sıfırlandı",
    "HESAP_OLUSTURULDU": "Hesap oluşturuldu", "HESAP_AKTIFLIK_DEGISTI": "Hesap aktif/pasif yapıldı",
    "OGRENCI_EKLENDI": "Öğrenci sisteme eklendi", "KOORDINATOR_NOTU_EKLENDI": "Koordinatör notu eklendi",
    "DERS_EKLENDI": "Kataloğa ders eklendi", "DERS_GUNCELLENDI": "Katalogda ders güncellendi",
    "DERS_AKTIFLIK_DEGISTI": "Ders aktif/pasif yapıldı",
    "DERS_LISTEYE_EKLENDI": "Ders listesine ders eklendi", "DERS_LISTESI_DEGISTI": "Ders listesi değişti",
    "DERS_DENEMESI_EKLENDI": "Dönem ders kaydı girildi", "NOT_GIRILDI": "Not girildi",
    "KAYIT_ONAYLANDI": "Kayıt onaylandı", "KAYIT_REDDEDILDI": "Kayıt reddedildi",
    "KAYIT_GERI_CEKILDI": "Kayıt geri çekildi", "KAYIT_IPTAL_EDILDI": "Kayıt iptal edildi",
    "KAYIT_DUZELTILDI": "Kayıt düzeltildi",
}


@register.filter
def islem_adi(kod):
    return _ISLEMLER.get(kod, kod)


_ISLEMLER.update({
    "KURAL_SURUMU_OLUSTURULDU": "Kural sürümü oluşturuldu", "UYARI_DURUMU_DEGISTI": "Uyarı durumu değişti",
    "ANA_DAL_BILGISI_GIRILDI": "Ana dal bilgisi girildi", "KARAR_ISLENDI": "Kurul kararı işlendi",
    "BELGE_YUKLENDI": "Belge yüklendi", "BELGE_ONAYLANDI": "Belge onaylandı", "BELGE_REDDEDILDI": "Belge reddedildi",
    "BELGE_ISTENDI": "Belge istendi", "BELGE_INDIRILDI": "Belge indirildi",
    "MESAJ_GONDERILDI": "Mesaj gönderildi",
    "AKTARIM_YUKLENDI": "CSV aktarım dosyası yüklendi", "AKTARIM_UYGULANDI": "CSV aktarımı uygulandı",
    "AKTARIM_VAZGECILDI": "CSV aktarımından vazgeçildi",
})
_RENKLER.update({"Kritik": "kirmizi", "Uyarı": "sari", "Bilgi": "mavi", "Açık": "sari", "Görüldü": "mavi",
                 "Karara bağlandı": "yesil", "Koşul ortadan kalktı": "gri"})


@register.simple_tag
def acik_uyari_sayisi(program):
    """Programın açık (ACIK/GÖRÜLDÜ) uyarı sayısı ve en yüksek seviyesi."""
    if program is None:
        return {"sayi": 0, "seviye": ""}
    uyarilar = list(program.uyarilar.filter(durum__in=["ACIK", "GORULDU"]).values_list("seviye", flat=True))
    seviye = "KRITIK" if "KRITIK" in uyarilar else "UYARI" if "UYARI" in uyarilar else \
        "BILGI" if uyarilar else ""
    return {"sayi": len(uyarilar), "seviye": seviye}
