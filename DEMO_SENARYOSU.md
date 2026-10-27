# ÇAP / YDP Takip Sistemi: Demo Senaryosu

**Ara sunum:** 30 Ekim 2026 Cuma · **Süre:** yaklaşık 12 dakika ve sorular
**Sunan:** Hamza Çeliktürk (213301056) · Bilgisayar Mühendisliği Uygulamaları

Sistemdeki bütün kişiler, notlar ve belgeler **sentetik** (uydurma) veridir.

---

## 1. Hazırlık

### Sunumdan bir gün önce
1. Proje klasöründe **`testleri_calistir.bat`** dosyasına çift tıkla. Sonunda `OK` yazmalı. Test sayısını not al (sunumda söyleyeceksin).
2. **`demo_baslat.bat`** dosyasına çift tıkla ve senaryoyu baştan sona bir kez prova et.
3. `docs` klasöründeki güvenlik raporunu (PDF) ve ZAP raporunu aç, göz gezdir.

### Sunumdan 10 dakika önce
1. Açık siteyi kapat ve **`demo_baslat.bat`** dosyasını yeniden çalıştır. Demo her açılışta sıfırdan kurulur, yani provada yaptığın değişiklikler silinir.
2. Tarayıcıda iki pencere aç:
   - **Normal pencere:** koordinatör girişi.
   - **Gizli pencere** (Ctrl+Shift+N): öğrenci girişi. Gizli pencere ayrı oturum tutar, iki kullanıcı aynı anda açık kalır.
3. Yazılar arkadan okunsun diye tarayıcı yakınlaştırmasını **%125** yap (Ctrl ve +).
4. `docs\ornek_dosyalar\demo\notlar_hatali_demo.csv` dosyasının yerini bil.

### Giriş bilgileri

| Rol | Kullanıcı adı | Şifre |
|---|---|---|
| Koordinatör | `koordinator` | `Selcuk.Demo.2026` |
| Bölüm başkanı (salt okunur) | `baskan` | `Selcuk.Demo.2026` |
| Öğrenciler | öğrenci numarası | `Ogrenci.Demo.2026` |

### Demodaki öğrenciler

| No | Ad | Program | Neyi göstermek için |
|---|---|---|---|
| 231101101 | Deniz Örnekoğlu | ÇAP | Düzenli ilerleyen, uyarısız öğrenci |
| 231101102 | Elif Denemeci | ÇAP | **KRİTİK:** iki dönem ders almamış; ayrıca mesaj ve belge isteği var |
| 231101103 | Kerem Sentetik | ÇAP | **KRİTİK:** ana dal GANO'su ikinci kez 2,72'nin altında |
| 231101104 | Zeynep Örnekçi | ÇAP | **Onay kuyruğu:** bekleyen 4 kaydı var (seçmeli ders, dönem kaydı, not, transkript) |
| 221101105 | Burak Denemeoğlu | YDP | **UYARI:** asgari ders yükü (6 ders / 30 AKTS) eksik |
| 221101106 | Ayşe Yandal | YDP | Bütün şartlar tamam; **sertifika kararı** canlı işlenecek |
| 221101107 | Mert Notlu | YDP | CSV ile aktarıldı; program ortalaması iki dönem 2,00'ın altında |
| 231101108 | Selin Dondurmacı | ÇAP | CSV ile aktarıldı; kayıt dondurma kararı işlenmiş |
| 231101109 | Can Ayrılmaz | ÇAP | Kendi isteğiyle ayrıldı (program kapalı) |

---

## 2. Akış

### 0. Açılış (30 sn)
> "Bölümümüzde ÇAP ve yan dal öğrencilerinin dersleri, notları, belgeleri ve yönerge şartları şu an elle takip ediliyor. Bu sistem bu takibi tek yerde topluyor. Yönergedeki kuralları kendisi kontrol ediyor ve sorun gördüğünde koordinatörü uyarıyor. Kararı her zaman kurul veriyor; sistem sadece uyarıyor ve kararı kayda geçiriyor."

### 1. Koordinatör ana sayfası (1 dk)
**Normal pencere:** `koordinator` olarak giriş yap.
- Üstteki kutular: aktif ÇAP/YDP sayısı, onay bekleyen kayıt, kritik ve uyarı sayısı.
- **Açık uyarılar** tablosu: her uyarının yanında dayandığı yönerge maddesi var (ör. *ÇAP Md. 9/d*).
> "Bu uyarıları ben elle girmedim. Kural motoru yönergeye göre kendisi üretti ve sadece onaylanmış verilere bakıyor."

### 2. Öğrenci listesi ve filtre (45 sn)
**Öğrenciler** menüsüne gir. Uyarı filtresinden **Kritik uyarısı olanlar**'ı seç.
- Elif, Kerem ve Mert listelenir. Can'ın durumu "Kendi isteğiyle ayrıldı".

### 3. Elif'in kartı (1,5 dk)
**231101102** numarasına tıkla.
- **Durum ve uyarılar** sekmesi:
  - KRİTİK: "Son 2 dönem üst üste ders alınmadı."
  - UYARI: ana dal GANO'su 2,61; 2,50 toleransı içinde, bir defalık hak kullanıldı.
> "Uyarı bir karar değil. Kayıt silme ancak kurul kararı sisteme işlendiğinde olur."
- **Belgeler** sekmesi: koordinatörün açtığı "mazeret belgesi" isteği burada.
- **Mesajlar** sekmesi: Elif'in mesajı var. Kısa bir cevap yazıp gönder.
> "Mesajlar silinemez ve değiştirilemez. Öğrenci sadece kendi yazışmasını görebilir."

### 4. Öğrencinin gözünden (2 dk)
**Gizli pencere:** `231101104` (Zeynep) olarak giriş yap.
- Kart doğrudan açılır. Bekleyen kayıtlarda **"Onay bekliyor"** etiketi var ve bunlar AKTS hesabına girmez.
- Adres çubuğuna başka bir öğrencinin adresini yaz: `127.0.0.1:8000/ogrenciler/231101101/` → **Erişim engellendi**.
> "Bu IDOR denen saldırıya karşı koruma. Öğrenci numarayı değiştirerek başkasının bilgisini göremez."

### 5. Onay kuyruğu (2 dk)
**Normal pencere:** **Onay kuyruğu** menüsüne gir. Zeynep'in 4 kaydı orada.
1. Transkript belgesini **onayla**.
2. *İşletim Sistemleri* için girilen BB notunu **onayla**.
3. Seçmeli ders seçimini (Veri Madenciliği) **onayla**.
4. *Nesneye Yönelik Programlama* dönem kaydını gerekçe yazarak **reddet**, örneğin: "Ders kayıt formu yüklenmedi."

**Gizli pencere:** sayfayı yenile. Zil simgesinde bildirimler görünür; red bildiriminde gerekçe yazıyor.
> "Onaylanan kayıt kilitlenir, öğrenci değiştiremez. Reddedilen kayıt da silinmez, gerekçesiyle kalır."

### 6. Kural sürümleri (1,5 dk)
**Kurallar** menüsüne gir.
> "Eşikler kodun içinde değil. Yönerge değişirse koordinatör yeni bir sürüm girer; eski sürüm ve eski değerlendirmeler olduğu gibi kalır."
*(İstersen canlı göster)* ÇAP için **+ Yeni sürüm** düğmesine bas:

1. "Program not ortalaması alt sınırı" alanına **2,00** yaz.
2. Sürüm adı ve dayanak yaz, bugünün tarihini seç ve kaydet.
3. Ana sayfaya dön: Kerem için "program not ortalaması" KRİTİK uyarısı kendiliğinden oluşur.

### 7. Kurul kararı işleme (1,5 dk)
**221101106 Ayşe Yandal** öğrencisinin **Durum ve uyarılar** sekmesine gir. "Sertifika koşulları sağlanıyor" bilgisi görünür.
1. **+ Kurul kararı işle** düğmesine bas.
2. Türü **Yan dal sertifikası** seç. Kurul: Fakülte Yönetim Kurulu, tarih 02.10.2026, sayı 2026/41-7.
3. Dayanak belge olarak yüklü karar yazısını seç, gerekçeyi yaz ve kaydet.

Programın durumu **"Sertifika aldı"** olur; açık uyarılar "karara bağlandı" diye kapanır.

> "Dayanak belge olmadan karar işlenemiyor. Bu kontrol hem ekranda hem serviste var."

### 8. Geçmiş verilerin aktarımı (1 dk)
**Ana sayfa → Veri aktarımı.** Geçmişte üç uygulanmış aktarım görünür; Mert ve Selin bunlarla geldi.
1. Türü **Ders ve not geçmişi** seç ve `docs\ornek_dosyalar\demo\notlar_hatali_demo.csv` dosyasını yükle.
2. Önizlemede 1 satır sorunsuz, 5 satır hatalı görünür ve her hatanın nedeni yazar: ders katalogda yok, "Kış" diye dönem yok, öğrenci yok, gelecek dönem, geçersiz harf notu. "Uygula" düğmesi çıkmaz.
> "Önizlemede veritabanına hiçbir şey yazılmıyor. Aktarım ya tamamen yapılıyor ya hiç yapılmıyor. Sütun adları esnek olduğu için ileride OBİS'ten alınacak dosyalara da hazır."
3. **Vazgeç** düğmesine bas.

### 9. Güvenlik ve işlem kaydı (1 dk)
- Herhangi bir öğrenci kartında sağdaki **İşlem geçmişi**: kim, ne zaman, ne yaptı. Bu kayıtlar veritabanı seviyesinde değiştirilemez ve silinemez.
- Söylenecekler:
  - Otomatik test sayısı (provada not aldığın sayı).
  - 24 güvenlik testi: erişim kontrolü, IDOR, XSS, SQL enjeksiyonu, CSRF, güvenlik başlıkları.
  - OWASP ZAP ile kendi test ortamımızda tarama yapıldı; bulgular düzeltildi.
- İstersen bölüm başkanı (`baskan`) olarak giriş yapıp her şeyi görebildiğini ama hiçbir şeyi değiştiremediğini göster.

### 10. Kapanış (30 sn)
> "Sonraki adımlar: OBİS entegrasyonu (veri kaynağı alanı ve aktarım altyapısı hazır), HTTPS ile sunucuya kurulum ve kullanıcı geri bildirimleri."

---

## 3. Olası sorular

**Neden Django?** Kimlik doğrulama, CSRF koruması, ORM (SQL enjeksiyonuna karşı parametreli sorgu) ve şablonlarda otomatik kaçış hazır geliyor. Python ile hızlı geliştiriliyor ve test altyapısı güçlü.

**Veritabanı?** Geliştirmede SQLite kullanılıyor; tek bir ortam değişkeniyle PostgreSQL'e geçiliyor. İşlem kaydı tabloları iki veritabanında da tetikleyicilerle (trigger) korunuyor.

**Bir kaydı yanlışlıkla silerseniz ne olur?** Sistemde silme yok. Kayıtlar "iptal" ya da "reddedildi" durumuna geçer, gerekçe zorunlu ve her değişiklik eski ve yeni değeriyle işlem kaydına yazılır.

**Yönerge değişirse kodu mu değiştireceksiniz?** Hayır. Koordinatör "Kurallar" ekranından yeni sürüm girer. Eski değerlendirmeler, kullandıkları sürümle birlikte saklanır.

**Öğrenci yanlış not girerse?** Koordinatör onaylamadan not hesaba girmez. Onaydan sonra fark edilirse koordinatör gerekçe yazarak düzeltir; eski değer kayıtta kalır.

**Kural motoru nasıl çalışıyor?** Onay, iptal, düzeltme, ana dal bilgisi ya da karar gibi bir olay olduğunda sadece onaylı verilerle yeniden hesaplanıyor. Sonuç, o anki girdi verisi ve kullanılan kural sürümüyle birlikte donmuş olarak saklanıyor.

**Neden sistem kendisi kayıt silmiyor?** Yönergeye göre bu karar kurulun yetkisinde. Sistem şartın oluştuğunu bildiriyor; koordinatör kurul kararını, karar yazısını dayanak göstererek işliyor.

**Güvenliği nasıl test ettiniz?** Otomatik testler (rol matrisi, IDOR, XSS, SQL enjeksiyonu, CSRF, başlıklar) ve OWASP ZAP taraması yapıldı. Sızma testleri yalnızca kendi uygulamamızda ve kendi test ortamımızda yapıldı.

**Dosya yükleme güvenli mi?** Uzantı ile birlikte dosyanın gerçek içeriği de kontrol ediliyor. JavaScript içeren PDF'ler reddediliyor. Dosyalar web'den doğrudan erişilemeyen bir klasörde rastgele adla saklanıyor ve sadece yetkili kişi indirebiliyor.

**Gerçek veri var mı?** Hayır. Hocamızın şartı gereği tüm veriler sentetik.

---

## 4. Bir şey ters giderse

| Sorun | Çözüm |
|---|---|
| Site açılmıyor | `demo_baslat.bat` penceresi açık mı? Kapandıysa yeniden çalıştır. |
| "Erişim engellendi" çıktı | Yanlış kullanıcıyla giriş yapılmış olabilir. Sağ üstten çıkış yap, doğru hesapla gir. |
| Demo verisi karıştı | Pencerede Ctrl+C'ye bas ve `demo_baslat.bat` dosyasını yeniden çalıştır. 20 saniyede sıfırlanır. |
| Şifre kabul edilmiyor | 5 hatalı denemede hesap 15 dakika kilitlenir (bu bir güvenlik özelliği). `demo_baslat.bat` ile sıfırla. |
