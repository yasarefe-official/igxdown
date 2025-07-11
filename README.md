# Instagram Video İndirme Telegram Botu (Koyeb + GitHub Actions)

Bu proje, Telegram üzerinden gönderilen Instagram video linklerini işleyerek, video indirme görevini GitHub Actions'a yaptıran ve sonucu kullanıcıya gönderen bir mimari sunar. Ana Telegram bot mantığı Koyeb üzerinde sürekli çalışırken, ağır yük olan video indirme ve işleme GitHub Actions üzerinde isteğe bağlı olarak gerçekleştirilir.

**Bot Linki:** [IGXDOWN Bot](https://t.me/igxdown_bot) (Bu link, sizin deploy ettiğiniz botun linki olmalıdır)

## Mimarinin Özellikleri

-   **İstek Üzerine Çalışan Video İşleme:** GitHub Actions sadece bir indirme talebi geldiğinde tetiklenir, kaynakları verimli kullanır.
-   **Sürekli Aktif Bot Arayüzü:** Koyeb üzerinde çalışan ana bot, kullanıcılardan her zaman istek alabilir.
-   **Ölçeklenebilir İndirme:** Yoğun indirme işlemleri GitHub'ın altyapısında gerçekleşir.
-   **`yt-dlp` ve `ffmpeg` Kullanımı:** Videolar `yt-dlp` ile indirilir, video/ses birleştirme için `ffmpeg` kullanılır (GitHub Actions'ta otomatik kurulur).
-   **Opsiyonel `INSTAGRAM_SESSIONID`:** Gelişmiş durumlar veya özel videolar için GitHub Actions secret'ı olarak `INSTAGRAM_SESSIONID` tanımlanabilir.

## Nasıl Çalışır?

1.  **Kullanıcı Etkileşimi (Telegram):** Kullanıcı, Telegram botuna bir Instagram video linki gönderir.
2.  **Ana Bot (Koyeb):**
    *   Koyeb üzerinde sürekli çalışan Python tabanlı Telegram botu (`bot.py`) bu isteği alır.
    *   Kullanıcıya isteğin alındığına dair bir mesaj gönderir.
    *   GitHub API'sine bir `workflow_dispatch` isteği göndererek `.github/workflows/main.yml` adlı GitHub Actions workflow'unu tetikler. Bu istek, indirilecek Instagram URL'sini ve kullanıcının Telegram Chat ID'sini `inputs` olarak Actions'a iletir.
3.  **Video İşleme (GitHub Actions):**
    *   GitHub Actions workflow'u tetiklenir.
    *   Gerekli bağımlılıkları (`yt-dlp`, `ffmpeg` vb.) kurar.
    *   Eğer `INSTAGRAM_SESSIONID` (Actions secret olarak tanımlıysa) varsa, bunu kullanarak bir cookie dosyası oluşturur.
    *   `yt-dlp` aracılığıyla verilen Instagram URL'sinden videoyu indirir.
    *   İndirilen videoyu, `BOT_TOKEN_FOR_ACTIONS` (Koyeb'deki botunuzun Telegram token'ını içeren bir Actions secret'ı) kullanarak ve `inputs` ile gelen `chat_id`'ye doğrudan Telegram üzerinden gönderir.
    *   İşlem bittikten sonra tüm geçici dosyaları siler.
4.  **Sonuç (Telegram):** Kullanıcı, videoyu doğrudan Telegram üzerinden alır.

## Kurulum ve Kullanım (Bu Depoyu Forklayarak Kendi Botunuzu Oluşturmak İçin)

Bu mimariyi kendi hesabınızda kurmak için aşağıdaki adımları izleyin:

### 1. GitHub Tarafı Ayarları

1.  **Bu Depoyu Forklayın:** Bu GitHub deposunu kendi hesabınıza forklayın.
2.  **GitHub Personal Access Token (PAT) Oluşturun:**
    *   GitHub hesabınızda "Settings" > "Developer settings" > "Personal access tokens" > "Tokens (classic)" bölümüne gidin.
    *   "Generate new token" (veya "Generate new token (classic)") seçin.
    *   Token'a bir isim verin (örn: `KOYEB_ACTIONS_TRIGGER`).
    *   "Expiration" (Sona Erme Tarihi) seçin (örneğin, "No expiration" veya belirli bir süre).
    *   **`workflow`** scope'unu işaretleyin. Bu, token'ın Actions workflow'larını tetiklemesine izin verecektir.
    *   "Generate token" butonuna tıklayın ve oluşturulan token'ı **hemen kopyalayın**. Bu token bir daha gösterilmeyecektir.
3.  **GitHub Actions Secret'larını Ayarlayın:**
    *   Forkladığınız deponun GitHub sayfasına gidin.
    *   `Settings` > `Secrets and variables` > `Actions` sekmesine tıklayın.
    *   `New repository secret` butonuna tıklayarak aşağıdaki secret'ları ekleyin:
        *   **`BOT_TOKEN_FOR_ACTIONS`**: Değer olarak, Koyeb'de çalışacak olan Telegram botunuzun BotFather'dan aldığınız **API token**'ını yapıştırın. Bu, Actions'ın videoyu Telegram'a gönderebilmesi için gereklidir.
        *   **`INSTAGRAM_SESSIONID`** (Opsiyonel): Eğer özel videoları indirmek veya bazı erişim sorunlarını aşmak istiyorsanız, buraya kendi Instagram `sessionid`'nizi ekleyebilirsiniz. (Nasıl alınacağı aşağıda "Geliştiriciler İçin Notlar" bölümünde açıklanmıştır).

### 2. Telegram Bot Token'ı Alma (Eğer Yoksa)

1.  Telegram'da [BotFather](https://t.me/BotFather) ile konuşun.
2.  Yeni bir bot oluşturmak için `/newbot` komutunu kullanın ve talimatları izleyin.
3.  BotFather'ın size vereceği **API token**'ını kopyalayın. Bu token hem Koyeb'de hem de yukarıdaki `BOT_TOKEN_FOR_ACTIONS` secret'ında kullanılacak.

### 3. Koyeb Tarafı Ayarları

1.  **Koyeb Hesabı Oluşturun/Giriş Yapın:** [Koyeb](https://www.koyeb.com/) adresine gidin.
2.  **Yeni Bir Servis (App) Oluşturun:**
    *   Deployment metodu olarak "GitHub" seçin.
    *   Forkladığınız GitHub deposunu ve `main` dalını seçin.
    *   **Build & Run Komutları:**
        *   Koyeb, `requirements.txt` dosyasını otomatik olarak algılayıp bağımlılıkları yükleyecektir.
        *   Çalıştırma komutu (Run command) olarak `python bot.py` girin.
    *   **Ortam Değişkenleri (Environment Variables):**
        *   `TELEGRAM_TOKEN`: BotFather'dan aldığınız API token.
        *   `GITHUB_PAT`: GitHub'dan oluşturduğunuz Personal Access Token.
        *   `GITHUB_OWNER`: GitHub kullanıcı adınız veya organizasyon adınız (forkladığınız deponun sahibi).
        *   `GITHUB_REPO`: Forkladığınız deponun adı.
        *   `GITHUB_WORKFLOW_ID`: Genellikle `.github/workflows/` altındaki YAML dosyasının adı (örn: `main.yml`).
    *   Bölge (Region) seçin ve servisi deploy edin.
3.  **Servisin Çalıştığından Emin Olun:** Koyeb loglarını kontrol ederek botunuzun başarıyla başladığını ve Telegram'dan mesajları dinlediğini doğrulayın.

Artık Telegram botunuz Koyeb üzerinde çalışacak, gelen linkleri GitHub Actions'a ileterek video indirme işlemlerini orada yaptıracak ve sonuç kullanıcıya Actions tarafından gönderilecektir.

## Geliştiriciler İçin Notlar / İleri Düzey Kullanım

### `INSTAGRAM_SESSIONID` Kullanımı (Opsiyonel - Actions Secret'ı Olarak)

Bu mimaride, `INSTAGRAM_SESSIONID` doğrudan Koyeb'deki bota değil, **GitHub Actions Secret**'larına eklenir. GitHub Actions workflow'u, bu secret tanımlıysa `yt-dlp` için bir cookie dosyası oluşturur.

Kullanım senaryoları:
-   Özel (Private) Hesaplardan Video İndirme.
-   Giriş Gerektiren Videolar.
-   Rate Limiting / Engelleme Sorunlarını Aşma.

**`INSTAGRAM_SESSIONID` Nasıl Alınır?**
(Bu adımlar bir önceki README versiyonundaki gibidir)
1.  Tarayıcınızda Instagram.com'a gidin ve hesabınıza giriş yapın.
2.  Geliştirici araçlarını açın.
3.  `Application` (Chrome/Edge) veya `Storage` (Firefox) sekmesinden `Cookies` > `https://www.instagram.com` yolunu izleyin.
4.  `sessionid` adlı çerezi bulun ve değerini kopyalayın.
5.  Bu değeri, forklanmış deponuzdaki GitHub Actions Secrets ayarlarına `INSTAGRAM_SESSIONID` adıyla ekleyin.

## Dosya Yapısı

-   `bot.py`: Koyeb üzerinde çalışacak ana Telegram bot uygulaması (GitHub Actions tetikleyicisi).
-   `requirements.txt`: Koyeb'deki bot için gerekli Python kütüphaneleri.
-   `.github/workflows/main.yml`: GitHub Actions üzerinde video indirme ve gönderme iş akışını tanımlar.
-   `README.md`: Bu dosya.

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen bir issue açın veya pull request gönderin.

## Lisans

Bu proje MIT Lisansı ile lisanslanmıştır.
