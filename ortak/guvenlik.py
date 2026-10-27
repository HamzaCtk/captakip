"""HTTP güvenlik başlıkları (OWASP Secure Headers önerileri).

Django'nun SecurityMiddleware'i X-Content-Type-Options, Referrer-Policy ve
Cross-Origin-Opener-Policy başlıklarını ekler. Bu ara katman ayrıca:
- Content-Security-Policy: Sayfa yalnızca kendi sunucumuzdaki CSS, yazı tipi
  ve görselleri yükleyebilir. Hiçbir betik (JavaScript) çalıştırılmaz. Bir
  XSS açığı olsa bile enjekte edilen betik tarayıcıda çalışmaz.
- Permissions-Policy: kamera, mikrofon, konum gibi özellikler kapalıdır.
- Giriş yapmış kullanıcıya giden sayfalar tarayıcıda/proxy'de saklanmaz
  (ortak bilgisayarda "geri" tuşuyla not bilgisi görünmesin).
"""
from django.utils.cache import add_never_cache_headers

CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
IZINLER = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


class GuvenlikBasliklariMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cevap = self.get_response(request)
        # Dosya indirmeleri kendi (daha sıkı) CSP'sini koyar; ona dokunulmaz
        cevap.headers.setdefault("Content-Security-Policy", CSP)
        cevap.headers.setdefault("Permissions-Policy", IZINLER)
        cevap.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if getattr(request, "user", None) is not None and request.user.is_authenticated \
                and "Cache-Control" not in cevap:
            add_never_cache_headers(cevap)
            cevap["Cache-Control"] += ", private"
        return cevap


def guvenli_yonlendir(request, hedef, varsayilan, *args, **kwargs):
    """Kullanıcıdan gelen 'geri dön' adresine yalnızca site içi bir yolsa yönlendirir.

    Dış siteye (açık yönlendirme / open redirect) veya anlamsız bir değere
    gelen istekler varsayılan sayfaya döner.
    """
    from django.http import HttpResponseRedirect
    from django.shortcuts import redirect
    from django.utils.http import url_has_allowed_host_and_scheme
    if hedef and hedef.startswith("/") and url_has_allowed_host_and_scheme(
            hedef, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return HttpResponseRedirect(hedef)
    return redirect(varsayilan, *args, **kwargs)
