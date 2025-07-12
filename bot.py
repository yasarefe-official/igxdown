import os
import logging
import subprocess
import shutil
from uuid import uuid4
import time
import json
import glob

from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ÇOKLU DİL DESTEĞİ ---
TRANSLATIONS = {}

def load_translations():
    """locales klasöründeki tüm .json dosyalarını yükler."""
    global TRANSLATIONS
    lang_files = glob.glob("locales/*.json")
    for file in lang_files:
        lang_code = os.path.basename(file).split('.')[0]
        try:
            with open(file, 'r', encoding='utf-8') as f:
                TRANSLATIONS[lang_code] = json.load(f)
            logger.info(f"{lang_code} dil dosyası başarıyla yüklendi.")
        except Exception as e:
            logger.error(f"{file} dil dosyası yüklenirken hata: {e}")

def get_translation(lang_code, key, **kwargs):
    """Belirtilen dildeki metni alır, bulamazsa varsayılan dile döner."""
    # Kullanıcının dil kodunun ilk iki harfini al (örn: 'en_US' -> 'en')
    base_lang_code = lang_code.split('-')[0] if lang_code else 'en'

    # Önce tam dil kodunu dene, sonra temel dil kodunu, sonra varsayılanı (en)
    lang_to_try = [lang_code, base_lang_code, 'en']

    message = "Translation key not found." # Varsayılan hata mesajı
    for lang in lang_to_try:
        if lang in TRANSLATIONS and key in TRANSLATIONS[lang]:
            message = TRANSLATIONS[lang][key]
            break

    return message.format(**kwargs)


# --- ORTAM DEĞİŞKENLERİ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SESSION_ID = os.getenv("INSTAGRAM_SESSIONID")

if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN ortam değişkeni eksik. Uygulama başlatılamıyor.")
    exit()

# --- YARDIMCI FONKSİYONLAR ---
def create_cookie_file(session_id_value: str, user_id: str) -> str:
    if not session_id_value: return None
    cookie_file_path = f"temp_cookie_{user_id}_{uuid4()}.txt"
    header = "# Netscape HTTP Cookie File\n# http://www.netscape.com/newsref/std/cookie_spec.html\n# This is a generated file!  Do not edit.\n\n"
    expiration_timestamp = int(time.time()) + (10 * 365 * 24 * 60 * 60)
    cookie_line = f".instagram.com\tTRUE\t/\tTRUE\t{expiration_timestamp}\tsessionid\t{session_id_value}\n"
    try:
        with open(cookie_file_path, 'w', encoding='utf-8') as f: f.write(header + cookie_line)
        logger.info(f"Cookie dosyası oluşturuldu: {cookie_file_path}")
        return cookie_file_path
    except Exception as e:
        logger.error(f"Cookie dosyası oluşturulurken hata: {e}")
        return None

def cleanup_files(*paths):
    for path in paths:
        if not path: continue
        try:
            if os.path.isfile(path): os.remove(path)
            elif os.path.isdir(path): shutil.rmtree(path)
        except Exception as e:
            logger.error(f"{path} silinirken hata: {e}")

# --- TELEGRAM HANDLER'LARI ---
def start_command(update: Update, context: CallbackContext):
    user_lang = update.effective_user.language_code
    user_name = update.effective_user.first_name
    welcome_message = get_translation(user_lang, "welcome", user_name=user_name)
    update.message.reply_html(welcome_message)

def link_handler(update: Update, context: CallbackContext):
    user_lang = update.effective_user.language_code
    user_id = str(update.effective_user.id)
    video_url = update.message.text

    if "instagram.com/" not in video_url:
        update.message.reply_text(get_translation(user_lang, "invalid_link"))
        return

    context.bot.send_message(chat_id=user_id, text=get_translation(user_lang, "request_received"))

    cookie_file = create_cookie_file(SESSION_ID, user_id) if SESSION_ID else None
    download_dir = f"temp_dl_{user_id}_{uuid4()}"
    os.makedirs(download_dir, exist_ok=True)

    yt_dlp_command = ['yt-dlp', '--no-warnings', '--force-overwrites', '--no-playlist', '--socket-timeout', '30', '-o', os.path.join(download_dir, '%(id)s.%(ext)s'), '-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b']
    if cookie_file: yt_dlp_command.extend(['--cookies', cookie_file])
    yt_dlp_command.append(video_url)

    video_path = None
    try:
        process = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=False, timeout=300)
        if process.returncode == 0:
            downloaded_files = os.listdir(download_dir)
            if downloaded_files:
                for f_name in downloaded_files:
                    if f_name.endswith(('.mp4', '.mkv', '.webm')):
                        video_path = os.path.join(download_dir, f_name)
                        break
                if not video_path: video_path = os.path.join(download_dir, downloaded_files[0])

                if video_path:
                    with open(video_path, 'rb') as video_file:
                        context.bot.send_video(chat_id=user_id, video=video_file, caption=get_translation(user_lang, "download_success_caption"), timeout=120)
                else:
                    update.message.reply_text("Video indirildi ancak sunucuda bulunamadı veya formatı tanınmadı.")
            else:
                update.message.reply_text(get_translation(user_lang, "error_yt_dlp"))
                logger.error(f"yt-dlp bir video indirmedi. stderr:\n{process.stderr}")
        else:
            logger.error(f"yt-dlp hata kodu: {process.returncode}. stderr:\n{process.stderr}")
            if "Login required" in process.stderr or "login" in process.stderr.lower() or "Private video" in process.stderr:
                update.message.reply_text(get_translation(user_lang, "error_private_video"))
            elif "Unsupported URL" in process.stderr:
                update.message.reply_text(get_translation(user_lang, "error_unsupported_url"))
            elif "403" in process.stderr or "Forbidden" in process.stderr:
                 update.message.reply_text(get_translation(user_lang, "error_forbidden"))
            else:
                update.message.reply_text(get_translation(user_lang, "error_yt_dlp"))
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp zaman aşımına uğradı.")
        update.message.reply_text(get_translation(user_lang, "error_timeout"))
    except Exception as e:
        logger.error(f"Genel indirme hatası (yt-dlp): {e}", exc_info=True)
        update.message.reply_text(get_translation(user_lang, "error_generic"))
    finally:
        cleanup_files(cookie_file, download_dir)

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        user_lang = update.effective_user.language_code
        update.effective_message.reply_text(get_translation(user_lang, "error_generic"))

# --- ANA UYGULAMA FONKSİYONU ---
def main():
    # Bot başladığında dil dosyalarını yükle
    load_translations()

    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("Bot başlatıldı ve Render üzerinde çalışıyor (çoklu dil destekli).")
    updater.idle()
    logger.info("Bot polling sonlandırıldı, uygulama kapatılıyor.")

if __name__ == '__main__':
    main()
