# ÇAP / YDP Takip Sistemi — Kurulum (Windows)

## 1. Python'u kontrol et
PowerShell'i aç ve yaz:

```powershell
python --version
```

`Python 3.11` veya daha yenisi görünmeli. Görünmüyorsa https://www.python.org/downloads/ adresinden kur
ve kurulumda **"Add python.exe to PATH"** kutusunu işaretle.

## 2. Proje klasörüne gir ve sanal ortam kur

```powershell
cd $HOME\source\captakip
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

> `Activate.ps1` için "running scripts is disabled" hatası alırsan bir kez şunu çalıştır:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Sanal ortam etkinken satırın başında `(.venv)` yazar. Her yeni PowerShell penceresinde
`.\.venv\Scripts\Activate.ps1` komutunu tekrar çalıştırman gerekir.

## 3. Veritabanını oluştur

```powershell
python manage.py migrate
```

## 4. İlk koordinatör hesabını aç

```powershell
python manage.py koordinator_olustur --kullanici-adi koordinator --email koordinator@ornek.edu.tr --ad Demo --soyad Koordinator
```

Senden şifre ister (en az 10 karakter, çok basit olmamalı). Yazarken ekranda görünmez, bu normal.

## 5. Başlangıç verisini yükle

```powershell
python manage.py baslangic_verisi --ornek
```

Bölümleri, akademik dönemleri, ders kataloğunu ve EEM → Bilgisayar ÇAP protokolünü (28 kalem, 135 AKTS) yükler.
`--ornek` üç sentetik öğrenci ekler ve geçici şifrelerini ekrana yazar. Komut tekrar çalıştırılabilir.

## 6. Sunucuyu çalıştır

```powershell
python manage.py runserver
```

Tarayıcıda **http://127.0.0.1:8000** adresini aç ve koordinatör hesabıyla giriş yap.

## 7. Testleri çalıştır

```powershell
python manage.py test
```

Tüm testlerin `OK` ile bitmesi gerekir.

## 8. Kısayol dosyaları (çift tıkla çalışır)

Proje klasöründe üç `.bat` dosyası vardır. Sanal ortamı (`.venv`) kendileri etkinleştirir.

| Dosya | Ne yapar |
|---|---|
| `baslat.bat` | Asıl veritabanıyla (`db.sqlite3`) siteyi açar ve tarayıcıyı başlatır. |
| `demo_baslat.bat` | **Sunum için.** Ayrı bir demo veritabanını (`demo.sqlite3`) her seferinde sıfırdan kurar, 9 sentetik öğrenci yükler ve siteyi açar. Asıl verilere dokunmaz. Giriş bilgileri pencerede yazar; ayrıntılar `DEMO_SENARYOSU.md` dosyasında. |
| `testleri_calistir.bat` | Bütün otomatik testleri (güvenlik testleri dahil) çalıştırır. |

## 9. Ortam değişkenleri (yayına alırken)

| Değişken | Açıklama |
|---|---|
| `CAPTAKIP_SECRET_KEY` | Gizli anahtar (yayında zorunlu, rastgele ve uzun) |
| `CAPTAKIP_DEBUG` | `0` = hata ayıklama kapalı (yayında `0`) |
| `CAPTAKIP_HTTPS` | `1` = güvenli çerez, HTTPS yönlendirme, HSTS |
| `CAPTAKIP_ALLOWED_HOSTS` | Alan adları, virgülle ayrılmış |
| `CAPTAKIP_DB` | `postgres` = PostgreSQL kullan (`PGHOST`, `PGUSER`… ile) |
| `CAPTAKIP_SQLITE` | SQLite dosya adı (varsayılan `db.sqlite3`; demo `demo.sqlite3`) |
| `CAPTAKIP_DOSYA_KLASORU` | Yüklenen belgelerin klasörü (varsayılan `korunan_dosyalar`) |
| `DATABASE_URL` | PostgreSQL bağlantı adresi (canlıda Neon) |
| `CAPTAKIP_DOSYA_DEPOSU` | `disk` veya `veritabani` (canlıda kendiliğinden `veritabani`) |

Güvenlik ayrıntıları için `docs/guvenlik/` klasöründeki rapora bakın. İnternete (Render + Neon) yayınlamak için `CANLIYA_ALMA.md` dosyasına bakın.
