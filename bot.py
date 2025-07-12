import os
import logging
import subprocess
import shutil
from uuid import uuid4
import time
import json
import glob
from math import ceil

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    ConversationHandler, CallbackQueryHandler
)

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ÇOKLU DİL DESTEĞİ ---
TRANSLATIONS = {}
# Kullanıcıların dil tercihlerini saklamak için bellek içi sözlük
# Not: Bot yeniden başladığında bu bilgiler kaybolur.
USER_LANGS = {}
# Konuşma durumları
SELECTING_LANGUAGE = 0

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

def get_user_language(update: Update) -> str:
    """Kullanıcının seçtiği dili alır, yoksa varsayılanı döner."""
    user_id = update.effective_user.id
    # Otomatik dil kodunu al, ama öncelik kullanıcının seçimi
    auto_lang_code = (update.effective_user.language_code or 'en').split('-')[0]
    return USER_LANGS.get(user_id, auto_lang_code)

def get_translation(lang_code, key, **kwargs):
    """Belirtilen dildeki metni alır, bulamazsa varsayılan dile döner."""
    base_lang_code = lang_code.split('-')[0]
    lang_to_try = [lang_code, base_lang_code, 'en']

    message = f"Translation key '{key}' not found."
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

# --- Dil Seçimi Conversation ---
def start(update: Update, context: CallbackContext) -> int:
    """/start komutu ile dil seçimi başlatır."""
    keyboard = [
        [InlineKeyboardButton("Türkçe 🇹🇷", callback_data='tr')],
        [InlineKeyboardButton("English 🇬🇧", callback_data='en')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(get_translation('en', 'welcome_prompt'), reply_markup=reply_markup)
    return SELECTING_LANGUAGE

def language_button(update: Update, context: CallbackContext) -> int:
    """Dil seçimi butonuna tıklandığında çalışır."""
    query = update.callback_query
    query.answer()
    lang_code = query.data
    user_id = query.from_user.id
    user_name = query.from_user.first_name

    USER_LANGS[user_id] = lang_code
    logger.info(f"Kullanıcı {user_id} dilini '{lang_code}' olarak ayarladı.")

    text = get_translation(lang_code, "language_selected", user_name=user_name)
    query.edit_message_text(text=text, parse_mode='HTML')
    return ConversationHandler.END

def link_handler(update: Update, context: CallbackContext):
    user_lang = get_user_language(update)
    user_id = str(update.effective_user.id)
    post_url = update.message.text

    if "instagram.com/" not in post_url:
        update.message.reply_text(get_translation(user_lang, "invalid_link"))
        return

    message_to_edit = context.bot.send_message(chat_id=user_id, text=get_translation(user_lang, "request_received"))

    cookie_file = create_cookie_file(SESSION_ID, user_id) if SESSION_ID else None
    download_dir = f"temp_dl_{user_id}_{uuid4()}"
    os.makedirs(download_dir, exist_ok=True)

    # -f (format) parametresini kaldırarak tüm medyaları indir
    yt_dlp_command = ['yt-dlp', '--no-warnings', '--force-overwrites', '--no-playlist', '--socket-timeout', '60', '-o', os.path.join(download_dir, '%(id)s_%(n)s.%(ext)s')]
    if cookie_file: yt_dlp_command.extend(['--cookies', cookie_file])
    yt_dlp_command.append(post_url)

    try:
        process = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=False, timeout=300)
        if process.returncode == 0:
            downloaded_files = sorted([os.path.join(download_dir, f) for f in os.listdir(download_dir)])
            if not downloaded_files:
                raise FileNotFoundError("yt-dlp klasörü boş.")

            # Medyaları 10'arlı gruplara ayır (Telegram limiti)
            media_groups = [downloaded_files[i:i + 10] for i in range(0, len(downloaded_files), 10)]

            # İlk mesajı sil veya düzenle
            message_to_edit.delete()

            for i, group in enumerate(media_groups):
                media_to_send = []
                for file_path in group:
                    if file_path.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        media_to_send.append(InputMediaPhoto(media=open(file_path, 'rb')))
                    elif file_path.endswith(('.mp4', '.mkv', '.webm')):
                        media_to_send.append(InputMediaVideo(media=open(file_path, 'rb')))

                if media_to_send:
                    # Sadece ilk gruba başlık ekle
                    if i == 0:
                        media_to_send[0].caption = get_translation(user_lang, "download_success_caption")

                    context.bot.send_media_group(chat_id=user_id, media=media_to_send, timeout=180)
        else:
            raise Exception(f"yt-dlp hata kodu: {process.returncode}. stderr: {process.stderr}")

    except Exception as e:
        message_to_edit.delete()
        error_text = str(e).lower()
        logger.error(f"İndirme hatası: {e}")
        if "login required" in error_text or "private" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_private_video"))
        elif "unsupported url" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_unsupported_url"))
        elif "403" in error_text or "forbidden" in error_text:
             update.message.reply_text(get_translation(user_lang, "error_forbidden"))
        elif "timed out" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_timeout"))
        else:
            update.message.reply_text(get_translation(user_lang, "error_yt_dlp"))
    finally:
        cleanup_files(cookie_file, download_dir)

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        user_lang = get_user_language(update)
        update.effective_message.reply_text(get_translation(user_lang, "error_generic"))

# --- ANA UYGULAMA FONKSİYONU ---
def main():
    load_translations()
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

    # Dil seçimi için ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECTING_LANGUAGE: [CallbackQueryHandler(language_button)],
        },
        fallbacks=[CommandHandler('start', start)],
    )

    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel|tv|stories)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    logger.info("Bot başlatıldı ve Render üzerinde çalışıyor (manuel dil seçimi + çoklu medya).")
    updater.idle()
    logger.info("Bot polling sonlandırıldı, uygulama kapatılıyor.")

if __name__ == '__main__':
    main()
