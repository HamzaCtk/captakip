"""Bulut servisinin "site ayakta mı?" kontrolü için sade adres.

Veritabanına basit bir sorgu atar; bağlantı yoksa 503 döner. Kişisel veri
veya sürüm bilgisi göstermez.
"""
from django.db import connection
from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def saglik(request):
    try:
        with connection.cursor() as imlec:
            imlec.execute("SELECT 1")
    except Exception:
        return HttpResponse("veritabani yok", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
