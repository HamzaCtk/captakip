"""Servis katmanı: veriyi değiştiren tüm işlemler buradan geçer.

Ekrandan giriş, CSV aktarımı ve ileride OBİS adaptörü aynı fonksiyonları
çağırır. Böylece işlem kaydı, onay durumu ve kural kontrolleri hiçbir
yoldan atlanamaz.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import Kullanici
from accounts.views import gecici_sifre_uret
from denetim.kayit import kaydet
from dersler.models import OgrenciDersi, ProtokolSablonu
from ortak.modeller import Kaynak, OnayDurumu

from .models import KoordinatorNotu, Ogrenci, ProgramKaydi


def uygun_protokol(ana_dal_bolumu, tur):
    return ProtokolSablonu.objects.filter(
        program_turu=tur, ana_dal_bolumu=ana_dal_bolumu, aktif=True
    ).first()


@transaction.atomic
def ogrenci_ekle(*, yapan, request=None, ogrenci_no, ad, soyad, eposta,
                 ana_dal_bolumu, tur, kabul_donemi, kaynak=Kaynak.KOORDINATOR):
    """Dekanlıktan/yönetim kurulundan kabul bildirilen öğrenciyi sisteme ekler.

    Öğrenci kartı, kullanıcı hesabı ve program kaydı birlikte oluşur.
    ÇAP'ta öğrencinin ana dalına ait protokol şablonu ders listesine
    kopyalanır (ÇAP Md. 7/2: dersleri bölüm belirler).

    Döndürür: (ogrenci, gecici_sifre)
    """
    if Ogrenci.objects.filter(ogrenci_no=ogrenci_no).exists() or \
            Kullanici.objects.filter(username=ogrenci_no).exists():
        raise ValidationError("Bu öğrenci numarası zaten kayıtlı.")

    protokol = None
    if tur == ProgramKaydi.Tur.CAP:
        protokol = uygun_protokol(ana_dal_bolumu, tur)
        if protokol is None:
            raise ValidationError(
                f"{ana_dal_bolumu} için tanımlı bir ÇAP protokol şablonu yok. "
                "Önce protokolü tanımlayın.")

    gecici = gecici_sifre_uret()
    kullanici = Kullanici(username=ogrenci_no, first_name=ad, last_name=soyad,
                          email=eposta, rol=Kullanici.Rol.OGRENCI, sifre_degistirmeli=True)
    kullanici.set_password(gecici)
    kullanici.save()

    ogrenci = Ogrenci.objects.create(kullanici=kullanici, ogrenci_no=ogrenci_no, ad=ad,
                                     soyad=soyad, eposta=eposta, ana_dal_bolumu=ana_dal_bolumu)
    program = ProgramKaydi.objects.create(ogrenci=ogrenci, tur=tur, kabul_donemi=kabul_donemi,
                                          protokol=protokol)

    if protokol:
        simdi = timezone.now()
        OgrenciDersi.objects.bulk_create([
            OgrenciDersi(
                program_kaydi=program, ders=k.ders, slot_aciklama=k.slot_aciklama,
                yariyil=k.yariyil, akts=k.akts, protokol_kalemi=k, sira=k.sira,
                # Protokol imzalı formdan geldiği için doğrudan onaylıdır
                onay_durumu=OnayDurumu.ONAYLANDI, kaynak=kaynak,
                olusturan=yapan, onaylayan=yapan, onay_zamani=simdi,
            )
            for k in protokol.kalemler.all()
        ])

    kaydet(request, "OGRENCI_EKLENDI", nesne=ogrenci, yapan=yapan, ogrenci_no=ogrenci_no,
           yeni={"ad_soyad": ogrenci.ad_soyad, "eposta": eposta, "tur": tur,
                 "kabul_donemi": str(kabul_donemi), "ana_dal": str(ana_dal_bolumu),
                 "protokol": str(protokol) if protokol else None,
                 "ders_sayisi": program.dersler.count()})
    from kurallar.motor import guvenli_degerlendir
    guvenli_degerlendir(program, "Öğrenci eklendi", yapan)
    return ogrenci, gecici


def koordinator_notu_ekle(*, yapan, request=None, ogrenci, metin):
    metin = (metin or "").strip()
    if not metin:
        raise ValidationError("Not boş olamaz.")
    not_ = KoordinatorNotu.objects.create(ogrenci=ogrenci, yazan=yapan, metin=metin)
    kaydet(request, "KOORDINATOR_NOTU_EKLENDI", nesne=not_, yapan=yapan,
           ogrenci_no=ogrenci.ogrenci_no, yeni={"metin": metin})
    return not_
