# ÇAP / YDP Öğrenci Takip Otomasyonu

Selçuk Üniversitesi Teknoloji Fakültesi Bilgisayar Mühendisliği Bölümü'nde Çift Ana Dal (ÇAP) ve Yan Dal (YDP) öğrencilerinin derslerini, notlarını, belgelerini ve yönerge şartlarını izleyen web uygulaması.

**Hazırlayan:** Hamza Çeliktürk (213301056) · **Ders:** Bilgisayar Mühendisliği Uygulamaları

> Sistemdeki bütün kişi, not ve belgeler **sentetik** (uydurma) test verisidir. Gerçek kişilere ait değildir.

## Özellikler

| Modül | Durum | Açıklama |
|---|---|---|
| Kimlik ve roller | ✅ | Koordinatör, öğrenci, bölüm başkanı (salt okunur). 5 hatalı denemede 15 dk kilit; ilk girişte zorunlu şifre değişimi. |
| Öğrenci ve program kaydı | ✅ | ÇAP/YDP kaydı, ders kataloğu, EEM → BM ÇAP protokolü (135 AKTS), öğrenci kartı |
| Onay mekanizması | ✅ | Öğrencinin girdiği ders, dönem kaydı ve not koordinatör onayına düşer. Onaylanan kayıt kilitlenir; red ve iptal gerekçeyle yapılır. |
| Belge yönetimi | ✅ | Güvenli dosya yükleme (içerik doğrulama, JavaScript içeren PDF reddi), sürümleme, belge isteği |
| Kural motoru ve uyarılar | ✅ | Yönerge şartları (GANO sınırı, iki dönem ders almama, azami süre, YDP asgari yük…) otomatik denetlenir. Sürümlü kural ayarları vardır. |
| Kurul kararları | ✅ | Dondurma, mezuniyet, sertifika, kayıt silme ve ayrılma kararları karar yazısı dayanak gösterilerek işlenir. |
| Mesajlaşma ve bildirim | ✅ | Öğrenci–koordinatör yazışması (ekli), sistem içi bildirimler |
| Geçmiş veri aktarımı | ✅ | CSV ile toplu aktarım: önce önizleme, sonra ya hep ya hiç uygulama. Sütun eşlemesi OBİS dökümlerine hazır. |
| İşlem kaydı | ✅ | Bütün işlemler değiştirilemez bir işlem kaydına yazılır (veritabanı tetikleyicileriyle korunur). |
| Güvenlik testleri | ✅ | 198 otomatik test (güvenlik paketi dahil), OWASP ZAP taraması: `docs/guvenlik/` |
| OBİS entegrasyonu | ⏳ | Veri kaynağı alanı ve aktarım altyapısı hazır; bağlantı sonraki aşamada. |

## Teknoloji

Python 3.13 · Django 5.2 · PostgreSQL (canlı, Neon) / SQLite (yerel) · Gunicorn + WhiteNoise · Render

## Yerelde çalıştırma (Windows)

Ayrıntılı kurulum için `KURULUM.md` dosyasına bakın. Kısaca:

```
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
demo_baslat.bat
```

`demo_baslat.bat` ayrı bir demo veritabanı kurar, 9 sentetik öğrenci yükler ve siteyi açar. Testler `testleri_calistir.bat` ile çalışır.

## Canlı ortam

Kurulum adımları `CANLIYA_ALMA.md` dosyasında. Canlı sitenin adresi ve test hesapları ders sorumlusuna e-postayla iletilmiştir. Canlı ortamın şifreleri bu depoda **yer almaz**.

## Belgeler

- `docs/guvenlik/Guvenlik_ve_Tasarim_Raporu.pdf`: güvenlik testleri, OWASP Top 10 eşlemesi, mimari
- `docs/Demo_Senaryosu.pdf`: sunum akışı
- `PROJE_DURUMU.md`: geliştirme adımları ve teknik ayrıntılar
