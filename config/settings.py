"""
ÇAP / YDP Takip Sistemi - Django ayarları.

Not: Gizli anahtar ve DEBUG gibi değerler ortam değişkenlerinden okunur.
Geliştirme ortamında varsayılanlar kullanılır; canlıya alırken mutlaka değiştirin.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Canlı ortam (bulut) algılama -------------------------------------------
# Render ve Railway kendi ortam değişkenlerini verir. Canlıda varsayılanlar
# güvenli tarafa çekilir: hata ayıklama kapalı, HTTPS zorunlu, dosyalar
# veritabanında.
CANLI = bool(os.environ.get("RENDER") or os.environ.get("RAILWAY_ENVIRONMENT"))

# --- Temel güvenlik ayarları ---------------------------------------------
SECRET_KEY = os.environ.get("CAPTAKIP_SECRET_KEY", "")
if not SECRET_KEY:
    if CANLI:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured("Canlı ortamda CAPTAKIP_SECRET_KEY ortam değişkeni zorunludur.")
    SECRET_KEY = "gelistirme-icin-gecici-anahtar-canlida-mutlaka-degistirin"
DEBUG = os.environ.get("CAPTAKIP_DEBUG", "0" if CANLI else "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("CAPTAKIP_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
                 if h.strip()]
# Bulut servisinin verdiği alan adı kendiliğinden eklenir
for _degisken in ("RENDER_EXTERNAL_HOSTNAME", "RAILWAY_PUBLIC_DOMAIN"):
    if os.environ.get(_degisken):
        ALLOWED_HOSTS.append(os.environ[_degisken])
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("127.0.0.1", "localhost")]

# --- Uygulamalar ------------------------------------------------------------
INSTALLED_APPS = [
    # Django'nun hazır parçaları (admin bilerek eklenmedi: tüm işlemler
    # işlem kaydına düşsün diye sadece kendi ekranlarımızdan yapılır)
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Bizim uygulamalarımız
    "accounts",
    "denetim",
    "ogrenciler",
    "dersler",
    "kurallar",
    "belgeler",
    "mesajlar",
    "aktarim",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "ortak.guvenlik.GuvenlikBasliklariMiddleware",
    # Bizim güvenlik katmanlarımız
    "accounts.middleware.SifreDegistirmeZorunluMiddleware",
    "accounts.middleware.SaltOkunurRolMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dersler.baglam.onay_sayaci",
                "mesajlar.baglam.sayaclar",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Veritabanı -------------------------------------------------------------
# Geliştirmede SQLite (kurulum gerektirmez). Canlıda DATABASE_URL verilir
# (Neon / Render / Railway PostgreSQL bağlantı adresi).
if os.environ.get("DATABASE_URL"):
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"], conn_max_age=60,
                                                  conn_health_checks=True)}
elif os.environ.get("CAPTAKIP_DB") == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("PGDATABASE", "captakip"),
            "USER": os.environ.get("PGUSER", "captakip"),
            "PASSWORD": os.environ.get("PGPASSWORD", ""),
            "HOST": os.environ.get("PGHOST", "localhost"),
            "PORT": os.environ.get("PGPORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            # Demo için ayrı veritabanı: CAPTAKIP_SQLITE=demo.sqlite3
            "NAME": BASE_DIR / os.environ.get("CAPTAKIP_SQLITE", "db.sqlite3"),
            # Eşzamanlı yazmalarda "database is locked" hatasını önler: yazma
            # işlemi kilidi baştan alır, meşgulse 20 saniyeye kadar bekler.
            "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20,
                        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"},
        }
    }

# --- Kullanıcı modeli ve giriş ---------------------------------------------
AUTH_USER_MODEL = "accounts.Kullanici"
LOGIN_URL = "giris"
LOGIN_REDIRECT_URL = "anasayfa"
LOGOUT_REDIRECT_URL = "giris"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Başarısız giriş denemesi sınırı (kaba kuvvet saldırısına karşı)
GIRIS_MAKS_DENEME = 5
GIRIS_KILIT_DAKIKA = 15

# --- Oturum ve çerez güvenliği ---------------------------------------------
SESSION_COOKIE_HTTPONLY = True          # JavaScript çerezi okuyamaz
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True             # sitede JavaScript yok; CSRF çerezini betik okuyamaz (ZAP bulgusu)
SESSION_COOKIE_AGE = 60 * 60 * 2        # 2 saat hareketsizlikte oturum düşer
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
X_FRAME_OPTIONS = "DENY"                # clickjacking koruması
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# HTTPS ile yayına alındığında CAPTAKIP_HTTPS=1 verilir. (Yerel demo ve
# yerel güvenlik taraması http://127.0.0.1 üzerinden yapılır.)
if os.environ.get("CAPTAKIP_HTTPS", "1" if CANLI else "0") == "1":
    # Bulut servisleri HTTPS'i önlerindeki vekil sunucuda (proxy) sonlandırır
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^saglik/$"]  # bulut servisinin iç sağlık kontrolü
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

if not DEBUG and SECRET_KEY.startswith("gelistirme-"):
    import warnings
    warnings.warn("CAPTAKIP_SECRET_KEY ayarlanmadı: canlı ortamda mutlaka gizli bir anahtar verin.")

# --- Dil, saat ---------------------------------------------------------------
LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

# --- Statik ve yüklenen dosyalar -------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise: canlıda statik dosyaları (CSS, yazı tipi) uygulamanın kendisi
# sıkıştırarak ve önbellek başlıklarıyla sunar (yerelde runserver sunar).
if CANLI or os.environ.get("CAPTAKIP_WHITENOISE") == "1":
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

    def _statik_basliklari(basliklar, yol, adres):
        basliklar["X-Content-Type-Options"] = "nosniff"  # ZAP bulgusu (statik dosyalar)
    WHITENOISE_ADD_HEADERS_FUNCTION = _statik_basliklari

# Yüklenen belgeler web'den doğrudan erişilemeyen bir klasörde tutulur;
# sadece yetki kontrolü yapan bir görünüm üzerinden indirilebilir.
KORUNAN_DOSYA_KOKU = BASE_DIR / os.environ.get("CAPTAKIP_DOSYA_KLASORU", "korunan_dosyalar")
# Dosya deposu: "disk" (yerel) veya "veritabani" (canlı; sunucu diski kalıcı değil)
DOSYA_DEPOSU = os.environ.get("CAPTAKIP_DOSYA_DEPOSU", "veritabani" if CANLI else "disk")
BELGE_MAKS_BOYUT = 10 * 1024 * 1024  # 10 MB
# Yükleme isteğinin toplam boyut sınırı (dosya + form alanları)
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Hata günlüğü ---------------------------------------------------------------
# DEBUG kapalıyken de sunucu hataları (500) ayrıntısıyla konsola yazılır;
# kullanıcıya ise iç bilgi içermeyen sade bir hata sayfası gösterilir.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"konsol": {"class": "logging.StreamHandler"}},
    "loggers": {"django.request": {"handlers": ["konsol"], "level": "ERROR", "propagate": False}},
}

# --- Not sistemi -------------------------------------------------------------
# Geçer kabul edilen harf notları. 6. adımda kural ayarlarına taşınacaktır.
GECER_HARF_NOTLARI = ["AA", "BA", "BB", "CB", "CC", "DC", "DD"]
