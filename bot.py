import os
import logging
import subprocess
import shutil
from uuid import uuid4
import time # Cookie timestamp için

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ORTAM DEĞİŞKENLERİ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SESSION_ID = os.getenv("INSTAGRAM_SESSIONID")

if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN ortam değişkeni eksik. Uygulama başlatılamıyor.")
    exit()

# --- YARDIMCI FONKSİYONLAR ---
def create_cookie_file(session_id_value: str, user_id: str) -> str:
    """Geçici bir cookie dosyası oluşturur."""
    if not session_id_value:
        return None

    cookie_file_path = f"temp_cookie_{user_id}_{uuid4()}.txt"

    # Netscape HTTP Cookie File format
    # http://www.netscape.com/newsref/std/cookie_spec.html
    # Domain<TAB>all_domains_flag<TAB>Path<TAB>secure_flag<TAB>expires_timestamp<TAB>name<TAB>value

    # Standart başlıklar
    header = (
        "# Netscape HTTP Cookie File\n"
        "# http://www.netscape.com/newsref/std/cookie_spec.html\n"
        "# This is a generated file!  Do not edit.\n\n"
    )

    # Expiration timestamp (örn: 10 yıl sonrası)
    expiration_timestamp = int(time.time()) + (10 * 365 * 24 * 60 * 60)

    # Cookie satırı (TAB karakterleri ile ayrılmış)
    # .instagram.com    TRUE    /    TRUE    <timestamp>    sessionid    <value>
    cookie_line = (
        f".instagram.com\tTRUE\t/\tTRUE\t{expiration_timestamp}\tsessionid\t{session_id_value}\n"
    )
    # Belki i.instagram.com için de eklemek gerekebilir, bazı araçlar bunu da kontrol eder.
    # cookie_line += (
    #     f".i.instagram.com\tTRUE\t/\tTRUE\t{expiration_timestamp}\tsessionid\t{session_id_value}\n"
    # )

    try:
        with open(cookie_file_path, 'w', encoding='utf-8') as f:
            f.write(header)
            f.write(cookie_line)
        logger.info(f"Cookie dosyası oluşturuldu: {cookie_file_path}")
        return cookie_file_path
    except Exception as e:
        logger.error(f"Cookie dosyası oluşturulurken hata: {e}")
        return None

def cleanup_files(*paths):
    """Verilen yollardaki dosya ve klasörleri temizler."""
    for path in paths:
        if not path: # None ise atla
            continue
        try:
            if os.path.isfile(path):
                os.remove(path)
                logger.info(f"Dosya silindi: {path}")
            elif os.path.isdir(path):
                shutil.rmtree(path)
                logger.info(f"Klasör silindi: {path}")
        except Exception as e:
            logger.error(f"{path} silinirken hata: {e}")

# --- TELEGRAM HANDLER'LARI ---
def start_command(update: Update, context: CallbackContext):
    user_name = update.effective_user.first_name
    update.message.reply_html(
        f"Merhaba {user_name}! 👋\n"
        "Bana bir Instagram Reel veya video linki gönder, senin için indirmeye çalışacağım.\n\n"
        "Bu bot `yt-dlp` kullanmaktadır. İndirme sorunları yaşarsanız, "
        "`INSTAGRAM_SESSIONID` ortam değişkeninin doğru ayarlandığından emin olun. "
        "Detaylar için README dosyasına bakabilirsiniz."
    )

def link_handler(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id) # Dosya adlarında kullanmak için str
    video_url = update.message.text

    if "instagram.com/" not in video_url:
        update.message.reply_text("Lütfen geçerli bir Instagram video/reel linki gönderin.")
        return

    context.bot.send_message(chat_id=user_id, text="Video talebin alındı, indirme işlemi başlatılıyor... ⏳")

    cookie_file = None
    if SESSION_ID:
        cookie_file = create_cookie_file(SESSION_ID, user_id)
    else:
        logger.info("INSTAGRAM_SESSIONID ayarlanmamış. Anonim indirme denenecek.")

    # İndirme için geçici bir klasör
    download_dir = f"temp_dl_{user_id}_{uuid4()}"
    os.makedirs(download_dir, exist_ok=True)

    # yt-dlp komutu
    # -S "height:1080" gibi kalite ayarları eklenebilir.
    # --force-overwrites: Varolan dosyaların üzerine yazar (genellikle temp klasörde gereksiz)
    # --no-playlist: Eğer link bir playlist'e aitse sadece videoyu indirir
    # --socket-timeout: Bağlantı zaman aşımı
    # --retries: Deneme sayısı
    yt_dlp_command = [
        'yt-dlp',
        '--no-warnings', # Uyarıları gizle (stdout'u temiz tutmak için)
        '--force-overwrites',
        '--no-playlist',
        '--socket-timeout', '30', # 30 saniye
        # '--retries', '3', # Deneme sayısı (isteğe bağlı)
        '-o', os.path.join(download_dir, '%(id)s.%(ext)s'), # Çıktı şablonu
        # Video formatı:
        # 1. En iyi mp4 video + en iyi m4a sesi birleştir.
        # 2. Olmazsa, en iyi mp4 (sesli veya sessiz) al.
        # 3. Olmazsa, en iyi video (herhangi bir format) + en iyi sesi (herhangi bir format) birleştir.
        # 4. Olmazsa, en iyi (sesli veya sessiz, herhangi bir format) al.
        '-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b',
    ]

    if cookie_file:
        yt_dlp_command.extend(['--cookies', cookie_file])

    yt_dlp_command.append(video_url)

    video_path = None
    try:
        logger.info(f"yt-dlp komutu çalıştırılıyor: {' '.join(yt_dlp_command)}")
        # capture_output=True ile stdout ve stderr yakalanır
        # text=True ile çıktılar string olarak gelir
        # timeout: subprocess'in toplam çalışma süresi (çok uzun videolar için artırılabilir)
        process = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=False, timeout=300) # 5 dakika timeout

        if process.returncode == 0:
            logger.info("yt-dlp başarıyla tamamlandı.")
            logger.debug(f"yt-dlp stdout:\n{process.stdout}")

            # İndirilen dosyayı bul (genellikle klasörde tek bir video olur)
            downloaded_files = os.listdir(download_dir)
            if downloaded_files:
                # Genellikle mp4 ararız, ancak başka formatlar da olabilir
                for f_name in downloaded_files:
                    if f_name.endswith(('.mp4', '.mkv', '.webm')): # Olası video uzantıları
                        video_path = os.path.join(download_dir, f_name)
                        break
                if not video_path and downloaded_files: # Eğer video uzantılı bulunamazsa ilk dosyayı al (riskli)
                     video_path = os.path.join(download_dir, downloaded_files[0])

                if video_path:
                    logger.info(f"Video bulundu: {video_path}")
                    with open(video_path, 'rb') as video_file:
                        context.bot.send_video(chat_id=user_id, video=video_file, caption="İşte videon! ✅ (yt-dlp ile indirildi)", timeout=120)
                    update.message.reply_text("Video başarıyla gönderildi!")
                else:
                    update.message.reply_text("Video indirildi ancak sunucuda bulunamadı veya formatı tanınmadı.")
                    logger.error(f"İndirilen video dosyası bulunamadı. Klasör içeriği: {downloaded_files}")
            else:
                update.message.reply_text("Video indirilemedi (yt-dlp klasörü boş).")
                logger.error("yt-dlp bir video indirmedi, klasör boş.")
                if process.stderr:
                    logger.error(f"yt-dlp stderr (boş klasör):\n{process.stderr}")
        else:
            error_message = f"Video indirilemedi (yt-dlp hata kodu: {process.returncode})."
            logger.error(error_message)
            logger.error(f"yt-dlp stdout:\n{process.stdout}")
            logger.error(f"yt-dlp stderr:\n{process.stderr}")

            # Kullanıcıya daha anlamlı bir hata mesajı göstermeye çalışalım
            if "Login required" in process.stderr or "login" in process.stderr.lower():
                update.message.reply_text("Bu videoyu indirmek için Instagram girişi gerekiyor. Lütfen `INSTAGRAM_SESSIONID`'nin doğru ayarlandığından emin olun.")
            elif "Unsupported URL" in process.stderr:
                update.message.reply_text("Bu link desteklenmiyor veya geçersiz.")
            elif "Private video" in process.stderr:
                 update.message.reply_text("Bu video özel. İndirmek için geçerli bir `INSTAGRAM_SESSIONID` gereklidir.")
            elif "403" in process.stderr or "Forbidden" in process.stderr:
                 update.message.reply_text("Instagram erişimi engelledi (403 Forbidden). `INSTAGRAM_SESSIONID`'nizi kontrol edin veya daha sonra tekrar deneyin.")
            else:
                update.message.reply_text(error_message + " Detaylar loglandı.")

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp zaman aşımına uğradı.")
        update.message.reply_text("Video indirme işlemi çok uzun sürdüğü için zaman aşımına uğradı.")
    except Exception as e:
        logger.error(f"Genel indirme hatası (yt-dlp): {e}", exc_info=True)
        update.message.reply_text(f"Video indirilirken beklenmedik bir hata oluştu: {type(e).__name__}")
    finally:
        cleanup_files(cookie_file, download_dir) # video_path'i silmeye gerek yok çünkü download_dir siliniyor

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        # Kullanıcıya çok fazla teknik detay vermeden genel bir hata mesajı
        update.effective_message.reply_text("İşlem sırasında bir sorun oluştu. Lütfen tekrar deneyin veya daha sonra gelin.")

# --- ANA UYGULAMA FONKSİYONU ---
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command))
    # Regex'i biraz daha genel tutabiliriz, /tv/, /stories/ gibi linkleri de yakalaması için
    # Ancak şimdilik /p/ ve /reel/ yeterli.
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("Bot başlatıldı ve polling modunda çalışıyor (yt-dlp kullanılıyor).")
    updater.idle()
    logger.info("Bot polling sonlandırıldı, uygulama kapatılıyor.")

if __name__ == '__main__':
    main()
