import secrets
import string
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from denetim.kayit import istemci_ip, kaydet
from ortak.guvenlik import guvenli_yonlendir

from .forms import GirisFormu, HesapOlusturmaFormu
from .models import GirisDenemesi, Kullanici
from .yetki import KOORDINATOR, rol_gerekli


def gecici_sifre_uret(uzunluk=12):
    """Kriptografik olarak güvenli rastgele geçici şifre."""
    alfabe = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabe) for _ in range(uzunluk))


# --- Giriş / çıkış ----------------------------------------------------------

class GirisView(LoginView):
    template_name = "registration/giris.html"
    authentication_form = GirisFormu
    redirect_authenticated_user = True

    def _kilitli_mi(self, kullanici_adi):
        sinir = timezone.now() - timedelta(minutes=settings.GIRIS_KILIT_DAKIKA)
        son_denemeler = GirisDenemesi.objects.filter(
            kullanici_adi__iexact=kullanici_adi, zaman__gte=sinir
        ).order_by("-zaman")[: settings.GIRIS_MAKS_DENEME]
        return (len(son_denemeler) >= settings.GIRIS_MAKS_DENEME
                and not any(d.basarili for d in son_denemeler))

    def post(self, request, *args, **kwargs):
        kullanici_adi = request.POST.get("username", "")[:150]
        if self._kilitli_mi(kullanici_adi):
            form = self.get_form()
            form.add_error(None, (
                f"Çok fazla hatalı deneme. Lütfen {settings.GIRIS_KILIT_DAKIKA} "
                "dakika sonra tekrar deneyin."
            ))
            GirisDenemesi.objects.create(
                kullanici_adi=kullanici_adi, ip_adresi=istemci_ip(request), basarili=False
            )
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        cevap = super().form_valid(form)
        GirisDenemesi.objects.create(
            kullanici_adi=form.get_user().username,
            ip_adresi=istemci_ip(self.request), basarili=True,
        )
        kaydet(self.request, "GIRIS", nesne=form.get_user())
        return cevap

    def form_invalid(self, form):
        kullanici_adi = self.request.POST.get("username", "")[:150]
        if not form.non_field_errors() or "Çok fazla" not in str(form.non_field_errors()):
            GirisDenemesi.objects.create(
                kullanici_adi=kullanici_adi, ip_adresi=istemci_ip(self.request), basarili=False
            )
        return super().form_invalid(form)


class SifreDegistirView(PasswordChangeView):
    template_name = "registration/sifre_degistir.html"
    success_url = reverse_lazy("anasayfa")

    def form_valid(self, form):
        cevap = super().form_valid(form)
        kullanici = self.request.user
        kullanici.sifre_degistirmeli = False
        kullanici.save(update_fields=["sifre_degistirmeli"])
        update_session_auth_hash(self.request, kullanici)
        kaydet(self.request, "SIFRE_DEGISTIRILDI", nesne=kullanici)
        messages.success(self.request, "Şifreniz güncellendi.")
        return cevap


# --- Ana sayfa (role göre panel) -------------------------------------------

@login_required
def anasayfa(request):
    kullanici = request.user
    if kullanici.ogrenci_mi:
        ogrenci = getattr(kullanici, "ogrenci", None)
        if ogrenci:
            return redirect("ogrenci_karti", ogrenci_no=ogrenci.ogrenci_no)
        return render(request, "anasayfa.html")
    from ogrenciler.models import ProgramKaydi
    from belgeler.models import Belge
    from dersler.models import DersDenemesi, NotGirisi, OgrenciDersi
    acik = ProgramKaydi.objects.filter(durum__in=ProgramKaydi.ACIK_DURUMLAR)
    istatistik = {
        "cap": acik.filter(tur="CAP").count(),
        "ydp": acik.filter(tur="YDP").count(),
        "bekleyen": OgrenciDersi.objects.filter(onay_durumu="BEKLIYOR").count()
                    + DersDenemesi.objects.filter(onay_durumu="BEKLIYOR").count()
                    + NotGirisi.objects.filter(onay_durumu="BEKLIYOR").count()
                    + Belge.objects.filter(onay_durumu="BEKLIYOR").count(),
    }
    from kurallar.models import Uyari
    uyarilar = list(Uyari.objects.filter(durum__in=["ACIK", "GORULDU"], seviye__in=["KRITIK", "UYARI"],
                                         program_kaydi__durum__in=ProgramKaydi.ACIK_DURUMLAR)
                    .select_related("program_kaydi__ogrenci").order_by("-zaman"))
    uyarilar.sort(key=lambda u: 0 if u.seviye == "KRITIK" else 1)
    istatistik["kritik"] = sum(1 for u in uyarilar if u.seviye == "KRITIK")
    istatistik["uyari"] = len(uyarilar) - istatistik["kritik"]
    return render(request, "anasayfa.html", {"istatistik": istatistik, "uyarilar": uyarilar[:10],
                                             "uyari_toplam": len(uyarilar)})


# --- Hesap yönetimi (yalnızca koordinatör) ----------------------------------

@rol_gerekli(KOORDINATOR)
def hesap_listesi(request):
    hesaplar = Kullanici.objects.exclude(rol=Kullanici.Rol.OGRENCI).order_by("rol", "username")
    return render(request, "accounts/hesap_listesi.html", {"hesaplar": hesaplar})


@rol_gerekli(KOORDINATOR)
def hesap_olustur(request):
    form = HesapOlusturmaFormu(request.POST or None)
    if request.method == "POST" and form.is_valid():
        kullanici = form.save(commit=False)
        gecici = gecici_sifre_uret()
        kullanici.set_password(gecici)
        kullanici.sifre_degistirmeli = True
        kullanici.save()
        kaydet(request, "HESAP_OLUSTURULDU", nesne=kullanici,
               yeni={"kullanici_adi": kullanici.username, "rol": kullanici.rol,
                     "email": kullanici.email})
        # Geçici şifre yalnızca bir kez gösterilir ve hiçbir yerde düz metin saklanmaz
        messages.success(
            request,
            f"Hesap oluşturuldu. Kullanıcı adı: {kullanici.username} — "
            f"Geçici şifre: {gecici} (Bu şifre bir daha gösterilmeyecek; "
            "kullanıcıya güvenli bir kanaldan iletin.)",
        )
        return redirect("hesap_listesi")
    return render(request, "accounts/hesap_olustur.html", {"form": form})


@require_POST
@rol_gerekli(KOORDINATOR)
def hesap_sifre_sifirla(request, pk):
    kullanici = get_object_or_404(Kullanici, pk=pk)
    if kullanici == request.user:
        messages.error(request, "Kendi şifrenizi buradan sıfırlayamazsınız; sağ üstteki “Şifre” bağlantısını kullanın.")
        return redirect("hesap_listesi")
    gecici = gecici_sifre_uret()
    kullanici.set_password(gecici)
    kullanici.sifre_degistirmeli = True
    kullanici.save()
    kaydet(request, "SIFRE_SIFIRLANDI", nesne=kullanici)
    messages.success(request, f"{kullanici.username} için yeni geçici şifre: {gecici}")
    return guvenli_yonlendir(request, request.POST.get("geri"), "hesap_listesi")


@require_POST
@rol_gerekli(KOORDINATOR)
def hesap_aktiflik_degistir(request, pk):
    """Hesaplar silinmez; yalnızca pasife alınır / yeniden açılır."""
    kullanici = get_object_or_404(Kullanici, pk=pk)
    if kullanici == request.user:
        messages.error(request, "Kendi hesabınızı pasife alamazsınız.")
        return redirect("hesap_listesi")
    eski = kullanici.is_active
    kullanici.is_active = not eski
    kullanici.save(update_fields=["is_active"])
    kaydet(request, "HESAP_AKTIFLIK_DEGISTI", nesne=kullanici,
           eski={"aktif": eski}, yeni={"aktif": kullanici.is_active},
           aciklama=request.POST.get("gerekce", "")[:500])
    messages.success(request, f"{kullanici.username} hesabı "
                     f"{'aktif' if kullanici.is_active else 'pasif'} yapıldı.")
    return redirect("hesap_listesi")
