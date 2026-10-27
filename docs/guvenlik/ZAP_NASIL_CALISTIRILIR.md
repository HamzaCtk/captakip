# OWASP ZAP taramasını tekrarlamak

> Tarama **yalnızca kendi bilgisayarınızda çalışan bu uygulamaya** (http://127.0.0.1:8000) yapılır.
> Başka hiçbir siteye (üniversite sistemleri dahil) tarama yapmayın.

1. Java 17+ ve OWASP ZAP 2.16'yı kurun (https://www.zaproxy.org/download/).
2. `demo_baslat.bat` ile demoyu başlatın. Tarama demo verisini değiştirir; asıl veritabanınıza dokunmaz.
3. **Anonim tarama:** proje klasöründe şu komutu çalıştırın (ZAP'ın kurulu olduğu yolu yazın):
   ```
   "C:\Program Files\ZAP\Zed Attack Proxy\zap.bat" -cmd -autorun docs\guvenlik\zap_plan_anonim.yaml
   ```
4. **Koordinatör oturumuyla aktif tarama:**
   1. Tarayıcıda `koordinator` olarak giriş yapın.
   2. Geliştirici araçları (F12) → Application → Cookies bölümünden `csrftoken` ve `sessionid` değerlerini kopyalayın.
   3. `zap_plan_koordinator.yaml` içindeki `BURAYA` yerlerine yapıştırın ve aynı komutla çalıştırın.
   4. Aktif tarama 25–30 dakika sürer.
5. Raporlar `zap_anonim.html` / `zap_koordinator.html` olarak oluşur. Bu klasördeki HTML dosyaları 16.10.2026 taramasının sonuçlarıdır.

Not: Oturum çerezleri gizli bilgidir; plan dosyasını çerezlerle birlikte paylaşmayın.
