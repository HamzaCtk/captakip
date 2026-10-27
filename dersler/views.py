from django import forms
from django.contrib import messages
from django.db.models import Q
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.yetki import BOLUM_BASKANI, KOORDINATOR, rol_gerekli
from denetim.kayit import kaydet

from .models import Ders, ProtokolSablonu


class DersFormu(forms.ModelForm):
    gerekce = forms.CharField(label="Değişiklik gerekçesi", required=False, max_length=500,
                              help_text="Mevcut bir dersi düzenlerken zorunludur.")

    class Meta:
        model = Ders
        fields = ["kod", "ad", "akts", "yariyil", "tur"]

    def clean(self):
        temiz = super().clean()
        if self.instance.pk and not temiz.get("gerekce"):
            self.add_error("gerekce", "Düzenleme için gerekçe yazın.")
        return temiz


def _degerler(ders):
    return {k: v for k, v in model_to_dict(ders, fields=["kod", "ad", "akts", "yariyil", "tur", "aktif"]).items()}


@rol_gerekli(KOORDINATOR, BOLUM_BASKANI)
def katalog(request):
    q = request.GET.get("q", "").strip()
    dersler = Ders.objects.all()
    if q:
        dersler = dersler.filter(Q(kod__icontains=q) | Q(ad__icontains=q))
    protokoller = ProtokolSablonu.objects.prefetch_related("kalemler__ders").select_related("ana_dal_bolumu")
    return render(request, "dersler/katalog.html", {"dersler": dersler, "q": q, "protokoller": protokoller})


@rol_gerekli(KOORDINATOR)
def ders_formu(request, pk=None):
    ders = get_object_or_404(Ders, pk=pk) if pk else None
    eski = _degerler(ders) if ders else None
    form = DersFormu(request.POST or None, instance=ders)
    if request.method == "POST" and form.is_valid():
        ders = form.save()
        kaydet(request, "DERS_GUNCELLENDI" if eski else "DERS_EKLENDI", nesne=ders,
               eski=eski, yeni=_degerler(ders), aciklama=form.cleaned_data.get("gerekce", ""))
        messages.success(request, f"{ders.kod} kaydedildi. Öğrencilerin daha önce geçtiği dersler etkilenmez.")
        return redirect("katalog")
    return render(request, "dersler/ders_formu.html", {"form": form, "ders": ders})


@require_POST
@rol_gerekli(KOORDINATOR)
def ders_aktiflik(request, pk):
    ders = get_object_or_404(Ders, pk=pk)
    gerekce = request.POST.get("gerekce", "").strip()[:500]
    if not gerekce:
        messages.error(request, "Pasife alma / aktif etme için gerekçe yazın.")
        return redirect("katalog")
    eski = ders.aktif
    ders.aktif = not eski
    ders.save(update_fields=["aktif"])
    kaydet(request, "DERS_AKTIFLIK_DEGISTI", nesne=ders, eski={"aktif": eski},
           yeni={"aktif": ders.aktif}, aciklama=gerekce)
    messages.success(request, f"{ders.kod} {'aktif' if ders.aktif else 'pasif'} yapıldı.")
    return redirect("katalog")
