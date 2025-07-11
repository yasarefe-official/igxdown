# Instagram Video İndirme Telegram Botu (GitHub Actions ile)

Bu proje, Telegram üzerinden gönderilen Instagram video linklerini indirip kullanıcıya gönderen bir Python botudur. Bot, GitHub Actions kullanılarak zamanlanmış görevlerle çalışır ve belirli saatlerde aktif olur.

**Bot Linki:** [IGXDOWN Bot](https://t.me/igxdown_bot)

## Özellikler

-   Instagram Reel ve video gönderilerini indirir.
-   Kullanımı kolay Telegram bot arayüzü.
-   GitHub Actions ile sunucusuz (serverless) çalışma.
-   Belirli zaman aralıklarında otomatik aktif/pasif olma.
-   Herkese açık videolar için anonim indirme.
-   Özel veya giriş gerektiren videolar için opsiyonel `INSTAGRAM_SESSIONID` kullanımı.

## Nasıl Çalışır?

Bot, `python-telegram-bot` kütüphanesi kullanılarak oluşturulmuştur ve Instagram içeriklerini indirmek için `instaloader` kütüphanesini kullanır.

### Zamanlama ve Çalışma Prensibi

Bot, GitHub Actions üzerinde bir cron job ile her saat başı tetiklenir.
-   **Çift saatlerde** (UTC olarak 00:00, 02:00, 04:00, ..., 22:00): Bot başlatılır ve yaklaşık 55-58 dakika boyunca aktif kalır. Bu süre zarfında gönderilen Instagram linklerini işler.
-   **Tek saatlerde** (UTC olarak 01:00, 03:00, 05:00, ..., 23:00): Bot başlatılmaz veya başlatılsa bile aktif olmadığını belirterek hemen kapanır.

Bu zamanlama, botun GitHub Actions üzerindeki ücretsiz kullanım limitlerini aşmadan çalışmasını sağlar.

### Instagram İndirme Mantığı

1.  **Anonim İndirme:** Bot öncelikle videoyu Instagram'a giriş yapmadan (anonim olarak) indirmeye çalışır. Bu, çoğu herkese açık video için yeterlidir.
2.  **`INSTAGRAM_SESSIONID` ile İndirme (Opsiyonel):**
    Eğer bir video anonim olarak indirilemiyorsa (örneğin, özel bir hesaba aitse veya Instagram giriş gerektiriyorsa), bot kullanıcıya `INSTAGRAM_SESSIONID` kullanması gerektiğini belirtebilir. Bu `sessionid`, kullanıcının kendi Instagram oturumunu temsil eder ve botun bu oturum üzerinden işlem yapmasını sağlar. **Bu yöntem, kullanıcının şifresini paylaşmasından daha güvenlidir.**

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

### `INSTAGRAM_SESSIONID` Nasıl Alınır?

`sessionid`'nizi tarayıcınızın geliştirici araçlarını kullanarak bulabilirsiniz:

1.  Tarayıcınızda Instagram.com'a gidin ve hesabınıza giriş yapın.
2.  Geliştirici araçlarını açın (genellikle F12 tuşu veya sağ tıklayıp "İncele" seçeneği).
3.  `Application` (Chrome/Edge) veya `Storage` (Firefox) sekmesine gidin.
4.  Sol menüden `Cookies` > `https://www.instagram.com` seçeneğini bulun.
5.  Çerezler listesinde `sessionid` adlı çerezi bulun ve değerini kopyalayın. Bu değeri GitHub secret olarak `INSTAGRAM_SESSIONID` adıyla kaydedin.

**Not:** `sessionid`'niz zaman zaman geçersiz olabilir (örneğin, Instagram'dan çıkış yaptığınızda veya uzun bir süre sonra). Eğer bot video indiremezse, `sessionid`'nizi güncellemeyi deneyin.

## Dosya Yapısı

-   `bot.py`: Ana Telegram bot uygulamasının Python kodunu içerir.
-   `requirements.txt`: Gerekli Python kütüphanelerini listeler.
-   `.github/workflows/main.yml`: Botu zamanlayan ve çalıştıran GitHub Actions iş akışını tanımlar.
-   `README.md`: Bu dosya.

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen bir issue açın veya pull request gönderin.

## Lisans

Bu proje MIT Lisansı ile lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakınız (eğer varsa).
