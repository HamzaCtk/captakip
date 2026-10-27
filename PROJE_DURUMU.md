# ÇAP / YDP Takip Sistemi: Proje Durumu (devir notu)

Son güncelleme: 15 Ekim 2026. Bu dosya, projeye yeni bir sohbette (Claude Projeler) kaldığı yerden devam edebilmek için yazıldı.

## Öğrenci ve ders
- Hamza Çeliktürk, 213301056
- Bilgisayar Mühendisliği Uygulamaları, Selçuk Üniversitesi Teknoloji Fakültesi Bilgisayar Mühendisliği
- Ara sunum (demo): **30 Ekim 2026 Cuma**, çalışan kodla bilgisayar üzerinde
- Konu: ÇAP (Çift Ana Dal) ve YDP (Yan Dal) öğrencilerini izleyen web otomasyonu
- Temel: hocanın e-postası. E-posta ile yönerge çelişirse **yönerge esas alınır**.
- Hocanın şartları:
  - Sisteme yalnızca **sentetik** (uydurma) veri girilir.
  - Sızma testleri yalnızca kendi uygulamamız üzerinde ve kendi test ortamımızda yapılır.
- Üniversitenin resmi logosu kullanılmıyor; uygulamanın kendi "ÇY" işareti var.
- Renkler Selçuk sarısı ve lacivert (#ffc90d, #1c458b, #0d2d5e). Yazı tipi Montserrat, çevrimdışı olarak projede.
- Hamza başlangıç seviyesinde. Açıklamalar **Türkçe ve basit** olmalı.

## Kodun yeri
- Asıl kopya: `C:\Users\celik\source\captakip` (Windows, PyCharm ile açılıyor).
- Teknoloji: Django 5.2, Python 3.13, SQLite (`CAPTAKIP_DB=postgres` ile PostgreSQL'e hazır).
- Kurulum: `KURULUM.md`. Device Guard yüzünden pip şöyle çalıştırılmalı: `python -m pip install -r requirements.txt`.
- Çalıştırma: `python manage.py runserver`, ardından tarayıcıda http://127.0.0.1:8000
- Testler: `python manage.py test` (198 test, SQLite ve PostgreSQL'de hepsi geçiyor; `testleri_calistir.bat`)
- Başlangıç verisi: `python manage.py baslangic_verisi --ornek`
  - Bölümler, dönemler (2022–2028), 25 derslik katalog ve EEM→BM ÇAP protokolünü (28 kalem, 135 AKTS) kurar.
  - Kural sürümlerini oluşturur.
  - Üç sentetik öğrenci ekler: 231101001 ÇAP, 231101002 ÇAP, 221101003 YDP.
- Koordinatör hesabı `python manage.py koordinator_olustur` ile açılır. Öğrenci şifresi `python manage.py changepassword <no>` ile sıfırlanır.

## Mimari kuralları (yeni kod da bunlara uymalı)
- **Servis katmanı:** Tüm yazma işlemleri `<app>/servisler.py` içinden yapılır. Ekranlar (views) sadece servis çağırır. Servis önce yetkiyi denetler, sonra işlemi yapar, sonra işlem kaydı yazar.
- **Silinmezlik:** `ortak/modeller.py` içinde `SilinemezModel` var. Hiçbir kayıt silinmez; kayıtlar iptal/red durumuna geçer.
- **Onay mantığı:** `OnayliKayit` alanları: `onay_durumu` (BEKLIYOR, ONAYLANDI, REDDEDILDI, IPTAL), `kaynak`, `olusturan`, `onaylayan`, `onay_zamani`, `gerekce`.
  - Öğrencinin girdiği kayıt BEKLIYOR başlar, koordinatörün girdiği ONAYLI başlar.
  - Hesaplara yalnızca onaylı kayıtlar girer.
- **İşlem kaydı:** `denetim.kayit.kaydet(request, "KOD", nesne=..., eski=..., yeni=..., ogrenci_no=..., yapan=...)`
  - Kayıtlar değiştirilemez; bunu veritabanı tetikleyicileri (trigger) de garanti eder.
  - Yeni işlem kodlarının Türkçe adı `dersler/templatetags/takip.py` içindeki `_ISLEMLER` sözlüğüne eklenir.
- **Roller:** KOORDINATOR, OGRENCI, BOLUM_BASKANI.
  - Bölüm başkanı salt okunurdur; bir ara katman (middleware) onun POST isteklerini engeller.
  - İlk girişte şifre değiştirmek zorunludur.
  - 5 hatalı denemeden sonra giriş 15 dakika kilitlenir.
- **IDOR koruması:** `ogrenciler.views.erisilebilir_ogrenci(request, ogrenci_no)`. Öğrenci başka bir öğrencinin numarasını açarsa 403 alır. Başka öğrenciye ait bir pk'ya 404 döner.
- **Eşzamanlılık:** Servisler kaydı `select_for_update()` ile yeniden okur.
- **Güvenli dosya yükleme (belgeler):**
  - Uzantı beyaz listesi ve magic byte denetimi; dosya bütünlüğü kontrolü.
  - JavaScript veya gömülü dosya içeren PDF reddedilir. Sınır 10 MB.
  - Dosyalar `korunan_dosyalar/` altında rastgele adla saklanır.
  - İndirme ek olarak verilir; `nosniff` ve CSP sandbox başlıkları eklenir.

## Uygulamalar (Django app)
- `accounts`: kullanıcı, giriş, şifre, hesap yönetimi.
- `denetim`: değiştirilemez işlem kaydı.
- `ogrenciler`: Bolum, AkademikDonem, Ogrenci, ProgramKaydi (ÇAP/YDP, durum), DonemKaydi, AnaDalKaydi, KoordinatorNotu, Karar.
- `dersler`:
  - Modeller: Ders kataloğu, ProtokolSablonu/Kalemi, OgrenciDersi (ders listesi ve seçmeli slotları), DersDenemesi, NotGirisi.
  - Onay kuyruğu da bu uygulamada.
- `belgeler`: Belge (sürümlü), BelgeIstegi, güvenli yükleme ve indirme. Not girmeden önce o döneme ait transkriptin yüklenmiş olması zorunludur.
- `kurallar`: kural motoru, sürümlü kural ayarları ve uyarılar (5–6. adım, aşağıda).
- `mesajlar`: Mesaj (öğrenci–koordinatör yazışması, ek dosya) ve Bildirim (7. adım, aşağıda).
- `aktarim`: CSV ile geçmiş veri aktarımı, AktarimIslemi (8. adım, aşağıda).

## Biten adımlar
1. Kurulum, roller, giriş güvenliği, işlem kaydı
2. Öğrenci kaydı, ders kataloğu, protokol, öğrenci kartı
3. Onay mekanizması: ders seçimi, deneme ve not; onay, red, geri çekme, iptal ve düzeltme
4. Belge yönetimi: güvenli yükleme, sürümleme, belge isteği, transkript zorunluluğu
5. ve 6. Kural motoru ve uyarılar:
   - **Sürümlü kural ayarları** (`/kurallar/`):
     - KuralSurumu ve KuralParametresi değiştirilemez. Yeni sürüm açılınca eski sürüm kapanır.
     - Eşikler `kurallar/tanimlar.py` içindeki PARAMETRELER listesinden ilk sürüme yüklenir.
   - **Motor** (`kurallar/motor.py`):
     - `degerlendir(program, tetikleyen, yapan, tarih)` sadece onaylı veriyle çalışır.
     - Sonuç donmuş bir KuralDegerlendirmesi olarak saklanır ve uyarılar eşitlenir. Aynı uyarı tekrar açılmaz; koşul ortadan kalkan uyarı GECERSIZ olur.
     - Kurallar: ana dal GANO (ÇAP 2,72, 2,50 toleransıyla bir defalık hak; YDP 2,30), program not ortalaması, iki dönem ders almama, azami süre ve ek süre, YDP asgari yükü (6 ders / 30 AKTS), ana dalda dondurma, tamamlama ve mezuniyet koşulu.
   - **Tetikleme:** onay, iptal, düzeltme, ders listesi değişikliği, ders ekleme, öğrenci ekleme, ana dal bilgisi girişi ve karar işleme.
   - **Ekranlar:**
     - Öğrenci kartında "Durum ve uyarılar" sekmesi.
     - Ana dal bilgisi formu, "Kuralları şimdi değerlendir" düğmesi, uyarıyı "görüldü" veya "karara bağlandı" yapma.
     - Kurul kararı işleme sayfası. Onaylı bir KURUL_KARARI belgesi seçmek zorunlu. Mezuniyet, sertifika, kayıt silme ve ayrılma kararları programı sonuçlandırır.
     - Ana sayfada açık uyarılar, listede uyarı sütunu ve filtresi.
   - Test ipucu: 231101002 numaralı öğrencide "Son 2 dönem üst üste ders alınmadı" KRİTİK uyarısı görünür.
7. Mesajlaşma ve bildirim (`mesajlar` uygulaması):
   - Her öğrencinin tek konuşması var; öğrenci kartında **Mesajlar** sekmesi (`/ogrenciler/<no>/mesajlar/`).
     Koordinatörün konuşma listesi `/mesajlar/`. Öğrenci yalnızca kendi konuşmasını görür (IDOR → 403).
     Bölüm başkanı okur, yazamaz; onun okuması "okundu" sayılmaz.
   - Mesajlar silinemez, metni değiştirilemez (yalnızca `okunma_zamani`/`okuyan` güncellenir).
     Gönderim `MESAJ_GONDERILDI` olarak işlem kaydına düşer.
   - Ek dosya: belgelerle aynı `dogrula()` denetimi; `korunan_dosyalar/mesaj/` altında rastgele adla.
     İndirme ek olarak, `nosniff` + CSP sandbox başlıklarıyla.
   - Bildirim (`mesajlar/bildirim.py`): onay, red, iptal, düzeltme, ders listesi değişikliği,
     belge onay/red, belge isteği → öğrenciye. Yeni UYARI/KRİTİK uyarı → öğrenciye ve
     (işlemi yapan hariç) tüm koordinatörlere; aynı uyarı tekrar bildirilmez, BİLGİ bildirilmez.
     Bildirim işlemle aynı transaction'da yazılır. `/bildirimler/`, tıklayınca okundu olur
     (yalnızca site içi adrese yönlendirir), "Tümünü okundu yap".
   - Üst çubukta zarf (okunmamış mesaj) ve zil (okunmamış bildirim) simgeleri, sayaçlarıyla.
   - Yeni kurulumda `python manage.py migrate` gerekir (mesajlar/0001_initial).
8. CSV ile geçmiş veri aktarımı (`aktarim` uygulaması, `/aktarim/`):
   - Üç tür: öğrenci kayıtları, ders ve not geçmişi, ana dal GANO bilgisi. Örnek şablonlar sayfadan indirilir;
     denemelik sentetik dosyalar `docs/ornek_dosyalar/` içinde (1_ogrenciler, 2_notlar, 2_notlar_hatali, 3_ana_dal).
   - `aktarim/okuyucu.py`: UTF-8/Windows-1254, `;` `,` veya sekme, en fazla 2 MB / 2000 satır.
     Sütun adları esnek (SUTUNLAR sözlüğü); OBİS dökümü için yalnızca yeni ad eklemek yeterli.
     Dönem `2025-2026 Güz` veya `2025-2026/1`. `= + - @` ile başlayan metin hücreleri reddedilir (formül enjeksiyonu).
   - `aktarim/servisler.py`: satırlar ekrandakiyle AYNI servislerden geçer (ogrenci_ekle, ders_ekle, deneme_ekle,
     ana_dal_kaydi_ekle), kaynak AKTARIM. ÇAP'ta seçmeli ders boş slota yerleşir; YDP'de listeye eklenir.
   - **Önizleme:** her şey gerçek servislerle bir transaction içinde denenir, sonra geri alınır; satır sonuçları saklanır.
   - **Uygulama:** yalnızca hatasız önizlemede, tek transaction'da ya hep ya hiç. Aynı dosya (SHA-256) ikinci kez
     uygulanamaz. Önizlemeden sonra veri değiştiyse hiçbir satır yazılmaz. Geçici şifreler yalnızca sonuç ekranında
     bir kez gösterilir.
   - `kurallar.motor.toplu_islem()`: aktarımda kurallar satır başına değil, sonunda her program için bir kez çalışır.
   - AktarimIslemi silinmez; dosya `korunan_dosyalar/aktarim/` altında saklanır. İşlem kodları AKTARIM_YUKLENDI,
     AKTARIM_UYGULANDI, AKTARIM_VAZGECILDI. Bölüm başkanı görür, yükleyemez.
9. Güvenlik testleri ve tasarım açıklaması:
   - `accounts/tests_guvenlik.py` (24 test): rol matrisi, IDOR, toplu atama, kalıcı XSS, SQL enjeksiyonu, CSRF, HTTP yöntemi,
     güvenlik başlıkları, çerez bayrakları, hata sayfası, açık yönlendirme, zayıf şifre, kendi şifresini sıfırlama,
     `geri` parametresi (ZAP'ın bulduğu 500 hatası ve şifre sıfırlamadaki açık yönlendirme → `ortak.guvenlik.guvenli_yonlendir`).
   - `ortak/guvenlik.py`: CSP (betik yok, `unsafe-inline` yok), Permissions-Policy, CORP, oturum açık sayfalarda `no-store`.
     Satır içi stil kaldırıldı (ilerleme çubuğu `<progress>`). `CSRF_COOKIE_HTTPONLY`, COOP, özel 404/500, hata günlüğü.
   - SQLite: WAL + `transaction_mode=IMMEDIATE` + timeout 20 (eşzamanlı yazmada kilit hatası olmasın).
   - `CAPTAKIP_HTTPS=1` ile güvenli çerez/HSTS/yönlendirme (DEBUG'dan ayrıldı; yerel demo http ile çalışır).
   - OWASP ZAP 2.16.1 ile anonim + koordinatör oturumlu aktif tarama (yalnızca yerel demo ortamı, sentetik veri).
     Rapor: `docs/guvenlik/Guvenlik_ve_Tasarim_Raporu.pdf`, ZAP HTML raporları `docs/guvenlik/`.
10. Demo hazırlığı:
   - `python manage.py demo_verisi` (boş veritabanında): 9 sentetik öğrenci, her senaryo için (bkz. komutun başı).
     Şifreler: koordinator/baskan `Selcuk.Demo.2026`, öğrenciler `Ogrenci.Demo.2026`.
   - `demo_baslat.bat`: `demo.sqlite3` + `korunan_dosyalar_demo` (asıl veriye dokunmaz), DEBUG=0, her açılışta sıfırdan.
     `baslat.bat` (asıl veritabanı), `testleri_calistir.bat`.
   - Demo PDF'leri `docs/ornek_dosyalar/demo/` (sentetik, "SENTETİK ÖRNEK" filigranlı).
   - `DEMO_SENARYOSU.md` (+ PDF): 12 dakikalık akış, olası sorular, sorun giderme. Akış tarayıcıda baştan sona prova edildi.

## Rapor
`docs/CAP_YDP_Takip_Sistemi_Tasarim_Raporu.pdf`:
- 17 sayfa, Selçuk renklerinde kapak (ad, numara, ders adı; hoca adı yok).
- Yönergeye dayalı. Çelişki bölümü yok, takvim yok.

## Canlı ortam (ara sınav, son teslim 30.10.2026 23.59)
Hoca e-postası: uygulama internetten erişilebilir olmalı (Railway/Vercel/Neon vb.). Gönderilecekler: canlı adres,
koordinatör/öğrenci/bölüm başkanı test hesapları, kaynak kod (GitHub), geliştirme durumu.
Seçim: **Render (web, ücretsiz) + Neon (PostgreSQL, ücretsiz, süresiz)**, kod Hamza'nın GitHub hesabında (herkese açık).
- Adım adım rehber: `CANLIYA_ALMA.md`. Blueprint: `render.yaml` (build: pip + collectstatic; start: migrate →
  `demo_verisi --bos-ise` → gunicorn 1 işlem 4 iş parçacığı; sağlık: `/saglik/`).
- `config/settings.py`: `CANLI` (RENDER/RAILWAY_ENVIRONMENT değişkeni) → DEBUG kapalı, HTTPS + proxy başlığı + HSTS,
  WhiteNoise (sıkıştırılmış, manifestli statik), `DATABASE_URL` (dj-database-url), Render alan adı ALLOWED_HOSTS ve
  CSRF_TRUSTED_ORIGINS'e kendiliğinden eklenir, gizli anahtar zorunlu.
- `ortak/depo.py`: dosya deposu `disk` (yerel) / `veritabani` (canlı; `belgeler.DepolananDosya`, silinemez/değiştirilemez).
  Render ücretsiz planda disk kalıcı değil.
- Canlı şifreler yalnızca Render ortam değişkeninde: `CAPTAKIP_DEMO_YONETICI_SIFRESI`, `CAPTAKIP_DEMO_OGRENCI_SIFRESI`
  (yoksa canlıda demo kurulmaz). Koddaki `Selcuk.Demo.2026` / `Ogrenci.Demo.2026` yalnızca yerel demo içindir.
- PostgreSQL ile bulunan hata düzeltildi: önizleme içindeki geri alınan programlar dıştaki toplu değerlendirmeye
  sızıyordu (`toplu_islem(..., ayri=True)` + yalnızca var olan programlar değerlendirilir).
- `README.md`: GitHub ana sayfası (özellik/durum tablosu).

## Sıradaki adımlar (yapılacaklar)
- Hamza'nın incelemesi ve eksik listesi.
- İsteğe bağlı: ana Proje ve Tasarım Raporu'nu güncellemek (rapor "17 test" diyor, şu an 198; bazı güvenlik maddeleri
  "uygulanacak" yazıyor ama yapıldı). Gövdenin kaynak HTML'i kayıp; güncellemek için yeniden yazılması gerekir.

## Bilinen notlar
- ÇAP yönergesi 20.05.2026'da yürürlüğe girdi; bu tarihten önceki tarihlerle ÇAP değerlendirmesi yapılmaz.
- ÇAP program not ortalaması eşiği (100 üzerinden 70'in 4'lük karşılığı) bilerek boş bırakıldı. Koordinatör "Kurallar" sayfasından yeni sürümle girer; o zamana kadar BİLGİ uyarısı çıkar.
