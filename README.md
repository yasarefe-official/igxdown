# IGXDOWN

Bu proje, Telegram üzerinden gönderilen Instagram video linklerini indirip kullanıcıya gönderen bir Python botudur. Bot, tamamen GitHub Actions üzerinde, günde iki ayrı zaman diliminde çalışacak şekilde tasarlanmıştır.

**Public Bot Linki:** [IGXDOWN Bot](https://t.me/igxdown_bot) (Bu link, herkesin kullanımı içindir)

## Özellikler

-   Instagram Reel ve video gönderilerini `yt-dlp` kullanarak indirir.
-   Kullanımı kolay Telegram bot arayüzü.
-   GitHub Actions ile sunucusuz (serverless) çalışma.
-   Günde iki ayrı 6 saatlik blok halinde (toplam 12 saat) otomatik çalışma.
-   `ffmpeg` kullanarak video ve ses akışlarını birleştirme (sesli indirme için).
-   Opsiyonel `INSTAGRAM_SESSIONID` kullanımı (geliştiriciler veya özel durumlar için).

## Nasıl Çalışır?

Bu bot, `python-telegram-bot` kütüphanesi ile Telegram API'sine bağlanır. Video indirme ve Telegram'a gönderme işlemleri `bot.py` script'i tarafından yönetilir. Script, video indirmek için popüler ve güçlü bir komut satırı aracı olan `yt-dlp`'yi kullanır.

### Zamanlama ve Çalışma Prensibi

Bot, tamamen GitHub Actions üzerinde çalışır ve iki ayrı workflow dosyası ile yönetilir:

1.  **Sabah Çalışması (`morning_run.yml`):**
    *   Her gün **UTC 09:00**'da (Türkiye saati ile 12:00) otomatik olarak çalışmaya başlar.
    *   Yaklaşık 6 saat sonra (UTC 15:00 civarı) otomatik olarak sonlanır.

2.  **Öğleden Sonra Çalışması (`afternoon_run.yml`):**
    *   Her gün **UTC 15:00**'de (Türkiye saati ile 18:00) otomatik olarak çalışmaya başlar.
    *   Yaklaşık 6 saat sonra (UTC 21:00 civarı) otomatik olarak sonlanır.

Bu yapı, botun günde toplam 12 saat boyunca aktif olmasını sağlar. Her workflow, `timeout-minutes: 358` (yaklaşık 6 saat) ayarı ile kendi çalışma süresini yönetir.

## Kurulum ve Kullanım (Bu Depoyu Forklayarak Kendi Botunuzu Oluşturmak İçin)

Bu botu kendi Telegram hesabınızla kullanmak için aşağıdaki adımları izleyin:

1.  **Bu Depoyu Forklayın:** Bu GitHub deposunu kendi hesabınıza forklayın.
2.  **Telegram Bot Token'ı Alın:**
    *   Telegram'da [BotFather](https://t.me/BotFather) ile konuşun.
    *   Yeni bir bot oluşturmak için `/newbot` komutunu kullanın ve talimatları izleyin.
    *   BotFather'ın size vereceği **API token**'ını kopyalayın. Bu token gizli tutulmalıdır.
3.  **GitHub Actions Secret'larını Ayarlayın:**
    *   Forkladığınız deponun GitHub sayfasına gidin.
    *   `Settings` > `Secrets and variables` > `Actions` sekmesine tıklayın.
    *   `New repository secret` butonuna tıklayarak aşağıdaki secret'ları ekleyin:
        *   **`TELEGRAM_TOKEN`**: Değer olarak BotFather'dan aldığınız API token'ını yapıştırın. Bu, botun Telegram'a bağlanması ve mesaj gönderip alması için gereklidir.
        *   **`INSTAGRAM_SESSIONID`** (Opsiyonel): Eğer özel videoları indirmek veya bazı erişim sorunlarını aşmak istiyorsanız, buraya kendi Instagram `sessionid`'nizi ekleyebilirsiniz.

4.  **GitHub Actions'ı Etkinleştirin:**
    *   Forkladığınız deponun `Actions` sekmesine gidin.
    *   Eğer bir uyarı görüyorsanız ("Workflows aren't running on this repository"), "I understand my workflows, go ahead and enable them" butonuna tıklayarak Actions'ı etkinleştirin.

Bot artık belirlediğiniz zamanlarda (UTC 09:00 ve 15:00) otomatik olarak çalışmaya başlayacaktır.

## Geliştiriciler İçin Notlar

### `INSTAGRAM_SESSIONID` Kullanımı (Opsiyonel)

Bu bot, çoğu herkese açık videoyu `sessionid` olmadan da indirebilir. Ancak, aşağıdaki durumlarda `INSTAGRAM_SESSIONID` secret'ını ayarlamak faydalı veya gerekli olabilir:
-   **Özel (Private) Hesaplardan Video İndirme.**
-   **Giriş Gerektiren Videolar.**
-   **Rate Limiting / Engelleme Sorunları:** Anonim isteklerin Instagram tarafından sık sık kısıtlandığı veya engellendiği durumlarda.

Bot, `INSTAGRAM_SESSIONID` secret'ı ayarlanmışsa, `yt-dlp`'ye bu bilgiyi bir cookie dosyası aracılığıyla otomatik olarak iletir.

**`INSTAGRAM_SESSIONID` Nasıl Alınır?**
1.  Tarayıcınızda Instagram.com'a gidin ve hesabınıza giriş yapın.
2.  Geliştirici araçlarını açın (genellikle F12).
3.  `Application` (Chrome/Edge) veya `Storage` (Firefox) sekmesinden `Cookies` > `https://www.instagram.com` yolunu izleyin.
4.  `sessionid` adlı çerezi bulun ve değerini kopyalayın.
5.  Bu değeri, forklanmış deponuzdaki GitHub Actions Secrets ayarlarına `INSTAGRAM_SESSIONID` adıyla ekleyin.

## Dosya Yapısı

-   `bot.py`: Ana Telegram bot uygulamasının Python kodunu içerir.
-   `requirements.txt`: Gerekli Python kütüphanelerini listeler.
-   `.github/workflows/morning_run.yml`: Botun sabah (09:00 UTC) çalışmasını yöneten iş akışı.
-   `.github/workflows/afternoon_run.yml`: Botun öğleden sonra (15:00 UTC) çalışmasını yöneten iş akışı.
-   `README.md`: Bu dosya.

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen bir issue açın veya pull request gönderin.

## Lisans

Bu proje MIT Lisansı ile lisanslanmıştır.
