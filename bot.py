import os
import logging
import subprocess
import shutil
from uuid import uuid4
import time
import json
import glob
import threading

from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, CallbackContext,
    ConversationHandler, CallbackQueryHandler
)

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ORTAM DEĞİŞKENLERİ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SESSION_ID = os.getenv("INSTAGRAM_SESSIONID")

# --- FLASK UYGULAMASI ---
app = Flask(__name__)

# --- BOT AYARLARI ---
if not TELEGRAM_TOKEN:
    logger.critical("TELEGRAM_TOKEN ortam değişkeni bulunamadı. Bot başlatılamıyor.")
    updater = None
    dispatcher = None
else:
    updater = Updater(TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher

@app.route('/')
def index():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

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

# --- YARDIMCI FONKSİYONLAR ---
def create_cookie_file(session_id_value: str, user_id: str) -> str:
    if not session_id_value: 
        return None
    cookie_file_path = f"temp_cookie_{user_id}_{uuid4()}.txt"
    header = "# Netscape HTTP Cookie File\n# http://www.netscape.com/newsref/std/cookie_spec.html\n# This is a generated file!  Do not edit.\n\n"
    expiration_timestamp = int(time.time()) + (10 * 365 * 24 * 60 * 60)
    cookie_line = f".instagram.com\tTRUE\t/\tTRUE\t{expiration_timestamp}\tsessionid\t{session_id_value}\n"
    try:
        with open(cookie_file_path, 'w', encoding='utf-8') as f: 
            f.write(header + cookie_line)
        return cookie_file_path
    except Exception as e:
        logger.error(f"Cookie dosyası oluşturulurken hata: {e}")
        return None

def cleanup_files(*paths):
    for path in paths:
        if not path: 
            continue
        try:
            if os.path.isfile(path): 
                os.remove(path)
            elif os.path.isdir(path): 
                shutil.rmtree(path)
        except Exception as e:
            logger.error(f"{path} silinirken hata: {e}")

# --- TELEGRAM HANDLER'LARI ---
def start(update: Update, context: CallbackContext) -> int:
    keyboard = [
        [InlineKeyboardButton("Türkçe 🇹🇷", callback_data='tr')], 
        [InlineKeyboardButton("English 🇬🇧", callback_data='en')]
    ]
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
    video_url = update.message.text

    if "instagram.com/" not in video_url:
        update.message.reply_text(get_translation(user_lang, "invalid_link"))
        return

    # Progress mesajını gönder
    progress_msg = context.bot.send_message(
        chat_id=user_id, 
        text=get_translation(user_lang, "request_received")
    )

    cookie_file = create_cookie_file(SESSION_ID, user_id) if SESSION_ID else None
    download_dir = f"temp_dl_{user_id}_{uuid4()}"
    os.makedirs(download_dir, exist_ok=True)

    yt_dlp_command = [
        'yt-dlp', 
        '--no-warnings', 
        '--force-overwrites', 
        '--no-playlist',
        '--socket-timeout', '60',
        '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '-o', os.path.join(download_dir, '%(id)s.%(ext)s'),
        '--max-filesize', '100M'  # Maksimum dosya boyutu sınırı
    ]
    
    if cookie_file:
        yt_dlp_command.extend(['--cookies', cookie_file])
    
    yt_dlp_command.append(video_url)

    try:
        # yt-dlp'yi çalıştır
        process = subprocess.run(
            yt_dlp_command, 
            capture_output=True, 
            text=True, 
            check=False, 
            timeout=300
        )
        
        # Progress mesajını sil
        try:
            progress_msg.delete()
        except:
            pass

        if process.returncode != 0:
            error_msg = process.stderr or process.stdout
            logger.error(f"yt-dlp hatası: {error_msg}")
            raise Exception(f"yt-dlp returned error code {process.returncode}")

        # İndirilen dosyaları kontrol et
        downloaded_files = [
            os.path.join(download_dir, f) 
            for f in os.listdir(download_dir) 
            if f.endswith(('.mp4', '.mkv', '.webm'))
        ]
        
        if downloaded_files:
            video_path = downloaded_files[0]
            
            # Dosya boyutunu kontrol et (50MB sınırı)
            if os.path.getsize(video_path) > 50 * 1024 * 1024:
                update.message.reply_text(get_translation(user_lang, "error_file_too_large"))
                return
            
            # Videoyu gönder
            with open(video_path, 'rb') as video_file:
                context.bot.send_video(
                    chat_id=user_id, 
                    video=video_file, 
                    caption=get_translation(user_lang, "download_success_caption"),
                    timeout=180
                )
        else:
            logger.warning("Video dosyası bulunamadı - muhtemelen resim gönderisi")
            update.message.reply_text(get_translation(user_lang, "error_unsupported_url"))

    except subprocess.TimeoutExpired:
        try:
            progress_msg.delete()
        except:
            pass
        update.message.reply_text(get_translation(user_lang, "error_timeout"))
        
    except Exception as e:
        try:
            progress_msg.delete()
        except:
            pass
        
        error_text = str(e).lower()
        logger.error(f"İndirme hatası: {e}")
        
        if "login required" in error_text or "private" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_private_video"))
        elif "unsupported url" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_unsupported_url"))
        elif "403" in error_text or "forbidden" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_forbidden"))
        elif "file too large" in error_text:
            update.message.reply_text(get_translation(user_lang, "error_file_too_large"))
        else:
            update.message.reply_text(get_translation(user_lang, "error_yt_dlp"))
    
    finally:
        cleanup_files(cookie_file, download_dir)

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)
    if update and update.effective_message:
        user_lang = get_user_language(update)
        update.effective_message.reply_text(get_translation(user_lang, "error_generic"))

# Webhook endpoint
@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    if not updater or not dispatcher:
        return 'Bot not initialized', 500
    
    try:
        update = Update.de_json(request.get_json(force=True), updater.bot)
        dispatcher.process_update(update)
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook hatası: {e}")
        return 'Error', 500

def setup_bot(is_webhook: bool):
    """Botun handler'larını ve webhook'unu kurar."""
    if not updater or not dispatcher:
        logger.error("Bot başlatılamadı - updater veya dispatcher eksik.")
        return

    # Çeviri dosyalarını yükle
    load_translations()

    # Handler'ları sadece bir kere ekle
    if not dispatcher.handlers:
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={SELECTING_LANGUAGE: [CallbackQueryHandler(language_button)]},
            fallbacks=[CommandHandler('start', start)],
        )
        dispatcher.add_handler(conv_handler)
        dispatcher.add_handler(
            MessageHandler(
                Filters.text & ~Filters.command &
                Filters.regex(r'https?://www\.instagram\.com/(p|reel|tv|stories)/\S+'),
                link_handler
            )
        )
        dispatcher.add_error_handler(error_handler)
        logger.info("Bot handler'ları eklendi.")

    if is_webhook:
        deploy_url = os.environ.get("RENDER_EXTERNAL_URL")
        if deploy_url:
            webhook_url = f"{deploy_url}/{TELEGRAM_TOKEN}"
            logger.info(f"Webhook {webhook_url} adresine ayarlanıyor...")
            try:
                # Mevcut webhook'u al ve karşılaştır
                current_webhook_info = updater.bot.get_webhook_info()
                if current_webhook_info.url != webhook_url:
                    updater.bot.delete_webhook()
                    time.sleep(0.5)
                    success = updater.bot.set_webhook(url=webhook_url)
                    if success:
                        logger.info("Webhook başarıyla ayarlandı.")
                    else:
                        logger.error("Webhook ayarlanamadı. set_webhook 'False' döndürdü.")
                else:
                    logger.info("Webhook zaten doğru şekilde ayarlanmış.")
            except Exception as e:
                logger.error(f"Webhook ayarlanırken kritik bir hata oluştu: {e}", exc_info=True)
        else:
            logger.warning("RENDER_EXTERNAL_URL ortam değişkeni bulunamadı. Webhook ayarlanamadı.")

# --- UYGULAMA BAŞLANGICI ---
# Bu kısım, dosya Gunicorn tarafından içe aktarıldığında veya doğrudan çalıştırıldığında çalışır.
if TELEGRAM_TOKEN and updater:
    # Gunicorn ile çalışıyorsak (yani __name__ != '__main__'), webhook modunda kur.
    # Aksi takdirde, yerel geliştirme için webhook'suz kur.
    setup_bot(is_webhook=(__name__ != '__main__'))

# --- YEREL GELİŞTİRME SUNUCUSU ---
# Bu blok sadece dosyayı doğrudan `python bot.py` komutuyla çalıştırdığınızda devreye girer.
if __name__ == '__main__':
    logger.info("Yerel geliştirme modu aktif. Polling başlatılıyor...")
    if updater:
        # Flask'ı bir thread'de çalıştırarak yerel testleri kolaylaştırabiliriz (isteğe bağlı)
        # Ama bu bot için öncelikli olan polling.
        updater.start_polling()
        logger.info("Bot polling ile çalışıyor. Çıkmak için CTRL+C.")
        updater.idle()
    else:
        logger.critical("TELEGRAM_TOKEN bulunamadı, bot başlatılamıyor.")
