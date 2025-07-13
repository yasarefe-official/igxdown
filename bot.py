import os
import logging
import subprocess
import shutil
from uuid import uuid4
import time
import json
import glob
from math import ceil
import threading # Arka planda botu çalıştırmak için

from flask import Flask # Web server için
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    ConversationHandler, CallbackQueryHandler
)

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FLASK UYGULAMASI ---
# Render'ın "Port scan timeout" hatasını çözmek için.
app = Flask(__name__)

@app.route('/')
def index():
    """Render'ın sağlık kontrolleri için basit bir endpoint."""
    return "Bot is running!", 200

# --- ÇOKLU DİL DESTEĞİ ---
TRANSLATIONS = {}
USER_LANGS = {}
SELECTING_LANGUAGE = 0

def load_translations():
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
    user_id = update.effective_user.id
    auto_lang_code = (update.effective_user.language_code or 'en').split('-')[0]
    return USER_LANGS.get(user_id, auto_lang_code)

def get_translation(lang_code, key, **kwargs):
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
    # Flask context'i dışında olduğumuz için exit() güvenli
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
def start(update: Update, context: CallbackContext) -> int:
    keyboard = [[InlineKeyboardButton("Türkçe 🇹🇷", callback_data='tr')], [InlineKeyboardButton("English 🇬🇧", callback_data='en')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(get_translation('en', 'welcome_prompt'), reply_markup=reply_markup)
    return SELECTING_LANGUAGE

def language_button(update: Update, context: CallbackContext) -> int:
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
    yt_dlp_command = ['yt-dlp', '--no-warnings', '--force-overwrites', '--no-playlist', '--socket-timeout', '60', '--ignore-no-formats-error', '-o', os.path.join(download_dir, '%(id)s_%(n)s.%(ext)s')]
    if cookie_file: yt_dlp_command.extend(['--cookies', cookie_file])
    yt_dlp_command.append(post_url)
    try:
        process = subprocess.run(yt_dlp_command, capture_output=True, text=True, check=False, timeout=300)
        downloaded_files = sorted([os.path.join(download_dir, f) for f in os.listdir(download_dir) if f.endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mkv', '.webm'))])
        message_to_edit.delete()
        if downloaded_files:
            media_groups = [downloaded_files[i:i + 10] for i in range(0, len(downloaded_files), 10)]
            for i, group in enumerate(media_groups):
                media_to_send = []
                # Dosyaları açıp hemen kapatmak için bir liste
                open_files = []
                for file_path in group:
                    media_file = open(file_path, 'rb')
                    open_files.append(media_file)
                    if file_path.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        media_to_send.append(InputMediaPhoto(media=media_file))
                    elif file_path.endswith(('.mp4', '.mkv', '.webm')):
                        media_to_send.append(InputMediaVideo(media=media_file))
                if media_to_send:
                    if i == 0:
                        media_to_send[0].caption = get_translation(user_lang, "download_success_caption")
                    context.bot.send_media_group(chat_id=user_id, media=media_to_send, timeout=180)
                # Dosyaları kapattığımızdan emin olalım
                for f in open_files:
                    f.close()
        elif process.returncode != 0:
            raise Exception(f"yt-dlp returned error code {process.returncode} and no files were downloaded. stderr: {process.stderr}")
        else:
            logger.warning("yt-dlp ran successfully but downloaded no files.")
            update.message.reply_text(get_translation(user_lang, "error_yt_dlp"))
    except Exception as e:
        if 'message_to_edit' in locals() and message_to_edit:
            try: message_to_edit.delete()
            except: pass
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
def run_telegram_bot():
    """Telegram botunu başlatan ve çalıştıran fonksiyon."""
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN ortam değişkeni bulunamadı. Bot thread'i başlatılamıyor.")
        return

    load_translations()
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={SELECTING_LANGUAGE: [CallbackQueryHandler(language_button)]},
        fallbacks=[CommandHandler('start', start)],
    )
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command & Filters.regex(r'https?://www\.instagram\.com/(p|reel|tv|stories)/\S+'), link_handler))
    dispatcher.add_error_handler(error_handler)
    updater.start_polling()
    logger.info("Telegram botu arka planda polling modunda başlatıldı.")
    updater.idle()

# --- UYGULAMAYI BAŞLATMA ---
# Gunicorn bu dosyayı import ettiğinde, aşağıdaki kodlar çalışacak ve
# bot thread'i otomatik olarak başlayacaktır.
bot_thread = threading.Thread(target=run_telegram_bot)
bot_thread.daemon = True
bot_thread.start()

# Lokal testler için, bu dosyayı doğrudan çalıştırdığınızda
# Flask'ın kendi geliştirme sunucusunu kullanabilirsiniz.
if __name__ == '__main__':
    # Render, PORT ortam değişkenini otomatik olarak sağlar.
    port = int(os.environ.get('PORT', 8080))
    # debug=False üretim için daha güvenlidir.
    app.run(host='0.0.0.0', port=port, debug=False)
