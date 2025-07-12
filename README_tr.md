[Read in English](README.md)

---

# Instagram Video İndirme Telegram Botu (Render + Docker)

Bu proje, Telegram üzerinden gönderilen Instagram video linklerini indirip kullanıcıya gönderen bir Python botudur. Bot, tüm işlevselliğiyle birlikte [Render](https://render.com/) üzerinde `Dockerfile` kullanılarak barındırılmak üzere tasarlanmıştır.

**Bot Linki:** [IGXDOWN Bot](https://t.me/igxdown_bot) (Bu link, sizin deploy ettiğiniz botun linki olmalıdır)

## Özellikler

-   Instagram Reel ve video gönderilerini `yt-dlp` kullanarak indirir.
-   Kullanımı kolay Telegram bot arayüzü.
-   Render üzerinde `Dockerfile` ile kolay ve güvenilir dağıtım (deployment).
-   `ffmpeg` desteği sayesinde sesli video indirme.
-   Opsiyonel `INSTAGRAM_SESSIONID` kullanımı.

## Nasıl Çalışır?

Bu bot, `python-telegram-bot` kütüphanesi ile Telegram API'sine bağlanır. Video indirme ve Telegram'a gönderme işlemleri `bot.py` script'i tarafından yönetilir. Script, video indirmek için popüler ve güçlü bir komut satırı aracı olan `yt-dlp`'yi `subprocess` modülü aracılığıyla çalıştırır.

Video ve ses akışlarını birleştirmek için gerekli olan `ffmpeg` bağımlılığı, proje kök dizinindeki `Dockerfile` aracılığıyla otomatik olarak kurulur.

Bot, Render üzerinde bir "Worker Service" olarak sürekli çalışır ve Telegram'dan gelen mesajları dinler.

## Kurulum ve Kullanım (Bu Depoyu Forklayarak Kendi Botunuzu Oluşturmak İçin)

Bu botu kendi Telegram hesabınızla Render üzerinde çalıştırmak için aşağıdaki adımları izleyin:

### 1. Ön Hazırlık

1.  **Bu Depoyu Forklayın:** Bu GitHub deposunu kendi hesabınıza forklayın.
2.  **Telegram Bot Token'ı Alın:**
    *   Eğer bir botunuz yoksa, Telegram'da [BotFather](https://t.me/BotFather) ile konuşun.
    *   `/newbot` komutunu kullanarak yeni bir bot oluşturun ve talimatları izleyin.
    *   BotFather'ın size vereceği **API token**'ını kopyalayın. Bu token gizli tutulmalıdır.

### 2. Render'da Deploy Etme

1.  **Render Hesabı Oluşturun/Giriş Yapın:** [Render.com](https://render.com/) adresine gidin. GitHub hesabınızla giriş yapmanız, depolarınıza erişimi kolaylaştıracaktır.
2.  **Yeni Bir Servis Oluşturun:**
    *   Render kontrol panelinde **"New +" > "Worker Service"** seçeneğini seçin. Bot sürekli arka planda çalışacağı için bu en uygun servis türüdür.
3.  **Deponuzu Bağlayın:**
    *   GitHub hesabınızı Render'a bağlayın ve forkladığınız bu depoyu listeden seçip "Connect" butonuna tıklayın.
4.  **Servisi Yapılandırın:**
    *   **Name:** Servisinize bir isim verin (örn: `igxdown-bot`).
    *   **Region:** Size en yakın bir bölge seçin (örn: `Frankfurt`).
    *   **Branch:** `main` dalını seçin.
    *   **Runtime:** Render, deponuzdaki `Dockerfile`'ı otomatik olarak algılayacaktır. "Runtime" olarak **"Docker"** seçildiğinden emin olun. Bu durumda "Build Command" ve "Start Command" alanlarını doldurmanıza gerek kalmaz.
    *   **Instance Type:** Ücretsiz plan (`Free`) ile başlayabilirsiniz.
5.  **Ortam Değişkenlerini (Environment Variables) Ekleyin:**
    *   "Advanced" bölümüne gidin ve "Add Environment Variable" butonuna tıklayarak aşağıdaki değişkenleri ekleyin:
        *   **`TELEGRAM_TOKEN`**: Değer olarak BotFather'dan aldığınız API token'ını yapıştırın.
        *   **`INSTAGRAM_SESSIONID`** (Opsiyonel): Eğer özel videoları indirmek veya bazı erişim sorunlarını aşmak istiyorsanız, buraya kendi Instagram `sessionid`'nizi ekleyebilirsiniz.
6.  **Deploy Edin:**
    *   "Create Worker Service" butonuna tıklayın.
    *   Render, GitHub deponuzdaki kodu çekecek, `Dockerfile`'ı kullanarak bir imaj oluşturacak (bu adımda `ffmpeg` ve Python bağımlılıkları kurulacak) ve son olarak botunuzu başlatacaktır.
7.  **Logları Kontrol Edin:**
    *   Deploy işlemi bittikten sonra, Render kontrol panelindeki "Logs" sekmesinden botunuzun loglarını takip edebilirsiniz. "Bot başlatıldı..." gibi mesajları gördüğünüzde, botunuz başarıyla çalışıyor demektir.

## Geliştiriciler İçin Notlar

### `INSTAGRAM_SESSIONID` Kullanımı (Opsiyonel)

Bu bot, çoğu herkese açık videoyu `sessionid` olmadan da indirebilir. Ancak, aşağıdaki durumlarda Render'da `INSTAGRAM_SESSIONID` ortam değişkenini ayarlamak faydalı olabilir:
-   **Özel (Private) Hesaplardan Video İndirme.**
-   **Giriş Gerektiren Videolar.**
-   **Rate Limiting / Engelleme Sorunları:** Anonim isteklerin Instagram tarafından sık sık kısıtlandığı veya engellendiği durumlarda.

Bot, bu ortam değişkeni ayarlanmışsa, `yt-dlp`'ye bu bilgiyi bir cookie dosyası aracılığıyla otomatik olarak iletir.

**`INSTAGRAM_SESSIONID` Nasıl Alınır?**
1.  Tarayıcınızda Instagram.com'a gidin ve hesabınıza giriş yapın.
2.  Geliştirici araçlarını açın (genellikle F12).
3.  `Application` (Chrome/Edge) veya `Storage` (Firefox) sekmesinden `Cookies` > `https://www.instagram.com` yolunu izleyin.
4.  `sessionid` adlı çerezi bulun ve değerini kopyalayın.
5.  Bu değeri, Render'daki servisinizin ortam değişkenlerine `INSTAGRAM_SESSIONID` adıyla ekleyin.

## Dosya Yapısı

-   `bot.py`: Ana Telegram bot uygulamasının Python kodunu içerir.
-   `requirements.txt`: Gerekli Python kütüphanelerini listeler.
-   `Dockerfile`: Render'da uygulamanın çalışacağı ortamı (Python + ffmpeg) oluşturan talimatları içerir.
-   `README.md`: Bu dosya.

## Katkıda Bulunma

Katkılarınızı bekliyoruz! Lütfen bir issue açın veya pull request gönderin.

## Lisans

Bu proje MIT Lisansı ile lisanslanmıştır.
