# Instagram Video İndirme Telegram Botu (GitHub Actions ile)

Bu proje, Telegram üzerinden gönderilen Instagram video linklerini indirip kullanıcıya gönderen bir Python botudur. Bot, GitHub Actions kullanılarak zamanlanmış görevlerle çalışır ve belirli saatlerde aktif olur.

**Bot Linki:** [IGXDOWN Bot](https://t.me/igxdown_bot)

## Özellikler

-   Instagram Reel ve video gönderilerini `yt-dlp` kullanarak indirir.
-   Kullanımı kolay Telegram bot arayüzü.
-   GitHub Actions ile sunucusuz (serverless) çalışma.
-   Belirlenmiş zaman aralıklarında (örneğin her gün 6 saat) otomatik çalışma.
-   `ffmpeg` kullanarak video ve ses akışlarını birleştirme (sesli indirme için).
-   Opsiyonel `INSTAGRAM_SESSIONID` kullanımı (geliştiriciler veya özel durumlar için).

## Nasıl Çalışır?

Bu bot, `python-telegram-bot` kütüphanesi ile Telegram API'sine bağlanır. Instagram içeriklerini indirmek için ise popüler ve güçlü bir komut satırı aracı olan `yt-dlp` kullanılır. `yt-dlp`, `bot.py` scripti içerisinden `subprocess` modülü aracılığıyla çalıştırılır.

Eğer indirilen video ve ses ayrı akışlar halindeyse, `yt-dlp` bu akışları birleştirmek için `ffmpeg` aracını kullanır. Bu nedenle, `ffmpeg` de GitHub Actions iş akışında otomatik olarak kurulmaktadır.

### Zamanlama ve Çalışma Prensibi

Bot, GitHub Actions üzerinde bir cron job ile **her gün Türkiye saati ile 12:00'de (UTC 09:00)** otomatik olarak çalışmaya başlar ve yaklaşık **6 saat boyunca (Türkiye saati ile 18:00'e kadar, UTC 15:00)** aktif kalır. Bu süre sonunda GitHub Actions iş akışı otomatik olarak sonlanır.

Bu zamanlama, `.github/workflows/main.yml` dosyasındaki `schedule: - cron: '0 9 * * *'` (her gün UTC 09:00'da çalıştır) ve `run-bot` işindeki `timeout-minutes: 358` (yaklaşık 6 saatlik çalışma süresi) ayarları ile yönetilir.

### Instagram İndirme Mantığı

Bot, bir Instagram linki aldığında aşağıdaki adımları izler:
1.  Eğer `INSTAGRAM_SESSIONID` ortam değişkeni (GitHub Secrets aracılığıyla) ayarlanmışsa, bu `sessionid` kullanılarak geçici bir cookie dosyası oluşturulur ve `yt-dlp`'ye bu dosya `--cookies` parametresi ile verilir. Bu, özel veya giriş gerektiren bazı videoların indirilmesine yardımcı olabilir.
2.  `yt-dlp`, verilen URL'yi ve (varsa) cookie dosyasını kullanarak videoyu indirmeye çalışır. Mümkün olan en iyi kalitede MP4 video ve sesi birleştirmeye çalışır.
3.  İndirme işlemi başarılı olursa, video kullanıcıya Telegram üzerinden gönderilir.
4.  Tüm geçici dosyalar (cookie dosyası, indirilen video) işlem sonunda otomatik olarak silinir.

Genel kullanıcıların `INSTAGRAM_SESSIONID` ayarlamasına gerek yoktur; bot, ayarlanmamışsa anonim olarak indirme deneyecektir. Ancak, bazı videoların (örneğin özel hesaplara ait olanlar) sadece geçerli bir `sessionid` ile indirilebileceği unutulmamalıdır.

## Kurulum ve Kullanım

Bu botu kendi Telegram hesabınızla kullanmak için aşağıdaki adımları izleyin:

1.  **Bu Depoyu Forklayın:** Bu GitHub deposunu kendi hesabınıza forklayın.
2.  **Telegram Bot Token'ı Alın:**
    *   Telegram'da [BotFather](https://t.me/BotFather) ile konuşun.
    *   Yeni bir bot oluşturmak için `/newbot` komutunu kullanın.
    *   BotFather'ın size vereceği **API token**'ını kopyalayın. Bu token gizli tutulmalıdır.
3.  **GitHub Secrets Ayarları:**
    *   Forkladığınız deponun GitHub sayfasına gidin.
    *   `Settings` > `Secrets and variables` > `Actions` sekmesine tıklayın.
    *   `New repository secret` butonuna tıklayarak aşağıdaki secret'ları ekleyin:
        *   **`TELEGRAM_TOKEN`**: Değer olarak BotFather'dan aldığınız API token'ını yapıştırın.
        *   **`INSTAGRAM_SESSIONID`** (Opsiyonel): Eğer özel videoları indirmek veya giriş sorunlarını aşmak istiyorsanız, buraya kendi Instagram `sessionid`'nizi ekleyebilirsiniz.

4.  **GitHub Actions'ı Etkinleştirin:**
    *   Forkladığınız deponun `Actions` sekmesine gidin.
    *   Eğer bir uyarı görüyorsanız ("Workflows aren't running on this repository"), "I understand my workflows, go ahead and enable them" butonuna tıklayarak Actions'ı etkinleştirin.

Bot artık belirlediğiniz zamanlarda otomatik olarak çalışmaya başlayacaktır.

## Geliştiriciler İçin Notlar / İleri Düzey Kullanım

### `INSTAGRAM_SESSIONID` Kullanımı (Opsiyonel)

Bu bot, genel kullanıcılar için `INSTAGRAM_SESSIONID` ayarlanmasını **gerektirmez**. Çoğu herkese açık video, `sessionid` olmadan da indirilebilir.

Ancak, aşağıdaki durumlarda `INSTAGRAM_SESSIONID` kullanmak faydalı veya gerekli olabilir:
-   **Özel (Private) Hesaplardan Video İndirme:** Eğer takip ettiğiniz özel bir hesaptan video indirmek istiyorsanız.
-   **Giriş Gerektiren Videolar:** Instagram'ın bazı videolar için giriş yapılmasını zorunlu kıldığı durumlar.
-   **Rate Limiting / Engelleme Sorunları:** Anonim isteklerin Instagram tarafından sık sık kısıtlandığı veya engellendiği durumlarda, geçerli bir `sessionid` kullanmak bu sorunları aşmaya yardımcı olabilir.

Eğer bu depoyu forklayıp kendi botunuzu çalıştırıyorsanız ve yukarıdaki durumlar için `sessionid` kullanmak isterseniz, `INSTAGRAM_SESSIONID` adlı bir GitHub Secret oluşturarak kendi `sessionid` değerinizi buraya ekleyebilirsiniz. Bot, bu secret ayarlanmışsa otomatik olarak `yt-dlp`'ye cookie dosyası aracılığıyla iletecektir.

**`INSTAGRAM_SESSIONID` Nasıl Alınır?**

1.  Tarayıcınızda Instagram.com'a gidin ve hesabınıza giriş yapın.
2.  Geliştirici araçlarını açın (genellikle F12 tuşu veya sağ tıklayıp "İncele" seçeneği).
3.  `Application` (Chrome/Edge) veya `Storage` (Firefox) sekmesine gidin.
4.  Sol menüden `Cookies` > `https://www.instagram.com` seçeneğini bulun.
5.  Çerezler listesinde `sessionid` adlı çerezi bulun ve değerini kopyalayın.
6.  Bu değeri, forklanmış deponuzdaki GitHub Secrets ayarlarına `INSTAGRAM_SESSIONID` adıyla ekleyin.

**Not:** `sessionid`'niz zaman zaman geçersiz olabilir. Eğer `sessionid` kullanmanıza rağmen indirme sorunları devam ediyorsa, yeni bir `sessionid` alıp secret'ı güncellemeyi deneyin.

## Dosya Yapısı

-   `bot.py`: Ana Telegram bot uygulamasının Python kodunu içerir.
-   `requirements.txt`: Gerekli Python kütüphanelerini listeler.
-   `.github/workflows/main.yml`: Botu zamanlayan ve çalıştıran GitHub Actions iş akışını tanımlar.
-   `README.md`: Bu dosya.

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen bir issue açın veya pull request gönderin.

## Lisans

Bu proje MIT Lisansı ile lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakınız (eğer varsa).
