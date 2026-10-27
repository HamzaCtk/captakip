# Canlıya alma: GitHub + Neon + Render

Toplam süre yaklaşık 30–40 dakika. Üç ücretsiz hesap gerekir: **GitHub**, **Neon** (veritabanı) ve **Render** (web sunucusu).
Neon ve Render'a "GitHub ile giriş" yaparsan ayrıca şifre oluşturman gerekmez.

> ⚠️ Canlı sitede **yalnızca sentetik veri** kullanılır. Gerçek öğrenci bilgisi ya da belge yükleme.
> ⚠️ Bu depo herkese açık olacak. **Şifreleri ve veritabanı adresini hiçbir dosyaya yazma.** Bunları yalnızca Render panelindeki "Environment" alanına gir.

---

## 1. Kodu GitHub'a yükle (GitHub Desktop ile)

1. https://github.com adresinde hesabın yoksa aç.
2. https://desktop.github.com adresinden **GitHub Desktop**'ı indir, kur ve GitHub hesabınla giriş yap.
3. **File → Add local repository…** menüsüne gir ve klasör olarak `C:\Users\celik\source\captakip` seç.
4. "This directory does not appear to be a Git repository" uyarısı çıkar. Altındaki **create a repository** bağlantısına tıkla.
   - Name: `captakip`
   - **Git ignore** ve **License** alanlarını **None** bırak; projede zaten `.gitignore` var.
   - **Create repository** düğmesine bas.
5. Soldaki **Changes** listesinde `.venv`, `db.sqlite3`, `demo.sqlite3` ve `korunan_dosyalar` **görünmemeli**. `.gitignore` bunları dışarıda bırakır.
6. Üstteki **Publish repository** düğmesine bas.
   - **Keep this code private** kutusundaki işareti **kaldır**. Hocanın kodu görebilmesi için depo herkese açık olmalı.
   - **Publish repository** düğmesine bas.
7. Depo adresin artık şöyle: `https://github.com/KULLANICI_ADIN/captakip`

## 2. Veritabanını oluştur (Neon)

1. https://neon.com adresinde **Sign up** düğmesine bas ve **GitHub ile** giriş yap. Kredi kartı istenmez.
2. **Create project** düğmesine bas:
   - Project name: `captakip`
   - Region: **AWS Europe Central 1 (Frankfurt)**
   - Diğer ayarları olduğu gibi bırak ve **Create** düğmesine bas.
3. Proje açılınca **Connect** düğmesine bas. **Connection string** alanında `postgresql://...` ile başlayan adresi gör ve **Copy** ile kopyala.
   - Bu adres veritabanının şifresini de içerir. Bir yere kaydet ama **kimseyle paylaşma, hiçbir dosyaya yazma.**

## 3. Web sitesini kur (Render)

1. https://render.com adresinde **Get Started** düğmesine bas ve **GitHub ile** giriş yap.
2. Sağ üstteki **New +** menüsünden **Blueprint** seç.
3. **Connect GitHub** düğmesine bas. GitHub'ın izin ekranında **Only select repositories → captakip** seç ve onayla.
4. Listede `captakip` deposunun yanındaki **Connect** düğmesine bas. Render, depodaki `render.yaml` dosyasını okur.
   - Blueprint Name: `captakip`
5. Render senden üç değer ister:

   | Alan | Ne yazacaksın |
   |---|---|
   | `DATABASE_URL` | Neon'dan kopyaladığın `postgresql://...` adresi |
   | `CAPTAKIP_DEMO_YONETICI_SIFRESI` | Koordinatör ve bölüm başkanı hesaplarının şifresi (en az 10 karakter) |
   | `CAPTAKIP_DEMO_OGRENCI_SIFRESI` | Öğrenci hesaplarının şifresi (en az 10 karakter) |

   `CAPTAKIP_SECRET_KEY` alanını Render kendisi üretir; boş bırak.
6. **Apply** (Deploy Blueprint) düğmesine bas.
7. Servise tıklayıp **Logs** sekmesini aç. İlk kurulum 3–6 dakika sürer. Sırasıyla şunları görmelisin:
   - `Applying ... OK` (tablolar kuruluyor)
   - `Demo verisi hazır.`
   - `Booting worker` / `Your service is live 🎉`
8. Sitenin adresi sayfanın üstünde yazar: `https://captakip-xxxx.onrender.com`

### Blueprint seçeneği çıkmazsa (elle kurulum)
**New + → Web Service** menüsünden `captakip` deposunu seç, sonra şu ayarları gir:

| Alan | Değer |
|---|---|
| Language / Runtime | Python 3 |
| Region | Frankfurt |
| Build Command | `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| Start Command | `python manage.py migrate --noinput && python manage.py demo_verisi --bos-ise && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120` |
| Instance Type | **Free** |
| Health Check Path (Advanced) | `/saglik/` |

**Environment Variables** bölümüne 3. adımın 5. maddesindeki üç değeri gir. Ek olarak şunları ekle:
- `CAPTAKIP_SECRET_KEY`: **Generate** düğmesiyle üret.
- `PYTHON_VERSION`: `3.13.5`

## 4. Kontrol et

1. Site adresini aç. Ücretsiz planda site 15 dakika kullanılmazsa uykuya geçer; ilk açılış **yaklaşık 1 dakika** sürebilir.
2. `koordinator` kullanıcı adı ve Render'a girdiğin yönetici şifresiyle giriş yap. Ana sayfada uyarılar görünmeli.
3. Öğrenci olarak giriş yap (ör. `231101104` ve öğrenci şifresi).
4. Bölüm başkanı için `baskan` kullanıcı adı ve yönetici şifresiyle giriş yap; hiçbir şeyi değiştirememeli.

## 5. Sonradan kod değişirse

GitHub Desktop'ta değişiklikleri gör, alttaki **Summary** kutusuna kısa bir açıklama yaz, **Commit to main** düğmesine bas, sonra **Push origin** düğmesine bas. Render yeni sürümü birkaç dakika içinde kendiliğinden yayına alır.
Veritabanındaki veriler korunur. Demo verisi yalnızca veritabanı boşken bir kez kurulur.

## Nasıl çalışıyor? (sunumda sorulursa)

- **Render** her açılışta `migrate` ile tabloları günceller. Veritabanı boşsa `demo_verisi --bos-ise` ile sentetik demo verisini kurar, sonra `gunicorn` ile siteyi başlatır.
- **Neon** PostgreSQL veritabanıdır. Ücretsiz plan süresizdir; kullanılmayınca uyur, ilk istekte uyanır.
- Render'ın ücretsiz planında sunucu diski kalıcı değildir. Bu yüzden canlıda yüklenen belgeler, mesaj ekleri ve CSV dosyaları **veritabanında** saklanır (`ortak/depo.py`).
- Canlı ortam kendiliğinden algılanır (`config/settings.py` → `CANLI`):
  - hata ayıklama kapalı
  - HTTPS zorunlu, HSTS açık, güvenli çerezler
  - statik dosyaları WhiteNoise sunar
  - gizli anahtar ve şifreler yalnızca ortam değişkenlerinden okunur
- `/saglik/` adresi, Render'ın "site ayakta mı" kontrolü içindir; sadece `ok` döner.
