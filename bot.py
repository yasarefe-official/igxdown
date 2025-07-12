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
# Bu artık bir Actions secret'ı olacak, botun çalıştığı ortamda değil.
# Ancak kodun içinde referans olarak kalabilir, çünkü Actions'ta bu değişken olacak.
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

    header = (
        "# Netscape HTTP Cookie File\n"
        "# http://www.netscape.com/newsref/std/cookie_spec.html\n"
        "# This is a generated file!  Do not edit.\n\n"
    )
    expiration_timestamp = int(time.time()) + (10 * 365 * 24 * 60 * 60)
    cookie_line = (
        f".instagram.com\tTRUE\t/\tTRUE\t{expiration_timestamp}\tsessionid\t{session_id_value}\n"
    )

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
        if not path:
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
        f"Merhaba {user_name}! 👋\n\n"
        "Instagram'dan video veya Reel indirmek için bana linkini göndermen yeterli.\n"
        "Örneğin: <code>https://www.instagram.com/p/Cxyz123.../</code>\n\n"
        "Bot sadece günün belirli saatlerinde (örneğin, 12:00-24:00 TRT) aktiftir."
    )

def link_handler(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
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

    download_dir = f"temp_dl_{user_id}_{uuid4()}"
    os.makedirs(download_dir, exist_ok=True)

    yt_dlp_command = [
        'yt-dlp', '--no-warnings', '--force-overwrites', '--no-playlist',
        '--socket-timeout', '30',
        '-o', os.path.join(download_dir, '%(id)s.%(ext)s'),
        '-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b',
    ]

    if cookie_file:
        yt_dlp_command.extend(['--cookies', cookie_file])

    yt_dlp_command.append(video_url)

    video_path = None
    try:
        logger.info(f"yt-dlp komutu çalıştırılıyor: {' '.join(yt_dlp_command)}")
        process = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=False, timeout=300)

        if process.returncode == 0:
            logger.info("yt-dlp başarıyla tamamlandı.")
            downloaded_files = os.listdir(download_dir)
            if downloaded_files:
                for f_name in downloaded_files:
                    if f_name.endswith(('.mp4', '.mkv', '.webm')):
                        video_path = os.path.join(download_dir, f_name)
                        break
                if not video_path:
                    video_path = os.path.join(download_dir, downloaded_files[0])

                if video_path:
                    logger.info(f"Video bulundu: {video_path}")
                    with open(video_path, 'rb') as video_file:
                        context.bot.send_video(chat_id=user_id, video=video_file, caption="İşte videon! ✅", timeout=120)
                    update.message.reply_text("Video başarıyla gönderildi!")
                else:
                    update.message.reply_text("Video indirildi ancak sunucuda bulunamadı veya formatı tanınmadı.")
            else:
                update.message.reply_text("Video indirilemedi (yt-dlp klasörü boş).")
                logger.error(f"yt-dlp bir video indirmedi. stderr:\n{process.stderr}")
        else:
            logger.error(f"yt-dlp hata kodu: {process.returncode}. stderr:\n{process.stderr}")
            if "Login required" in process.stderr or "login" in process.stderr.lower() or "Private video" in process.stderr:
                update.message.reply_text("Bu video indirilemedi. Video gizli olabilir veya özel erişim gerektiriyor olabilir.")
            elif "Unsupported URL" in process.stderr:
                update.message.reply_text("Gönderdiğiniz link desteklenmiyor veya geçersiz görünüyor.")
            elif "403" in process.stderr or "Forbidden" in process.stderr:
                 update.message.reply_text("Instagram'a erişimde bir sorun oluştu (Erişim Engellendi). Lütfen daha sonra tekrar deneyin.")
            else:
                update.message.reply_text("Video indirilirken bir sorunla karşılaşıldı. Lütfen linki kontrol edin veya daha sonra tekrar deneyin.")

    except subprocess.TimeoutExpired:
        logger.error("yt-dlp zaman aşımına uğradı.")
        update.message.reply_text("Video indirme işlemi çok uzun sürdüğü için zaman aşımına uğradı.")
    except Exception as e:
        logger.error(f"Genel indirme hatası (yt-dlp): {e}", exc_info=True)
        update.message.reply_text(f"Video indirilirken beklenmedik bir hata oluştu: {type(e).__name__}")
    finally:
        cleanup_files(cookie_file, download_dir)

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        update.effective_message.reply_text("İşlem sırasında beklenmedik bir sorun oluştu.")

# --- ANA UYGULAMA FONKSİYONU ---
def main():
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("Bot başlatıldı ve GitHub Actions üzerinde çalışıyor.")
    updater.idle()
    logger.info("Bot polling sonlandırıldı, uygulama kapatılıyor.")

if __name__ == '__main__':
    main()
