import os
import logging
from uuid import uuid4
from urllib.parse import quote_plus

# --- Web Framework ve Sunucu ---
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# --- Telegram Bot Kütüphanesi ---
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --- Instagram İndirici ---
import instaloader
from instaloader.exceptions import LoginException # <-- Hata yakalamak için özel import

# --- TEMEL AYARLAR ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ORTAM DEĞİŞKENLERİ ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
KOYEB_PUBLIC_URL = os.getenv("KOYEB_PUBLIC_URL")

if not all([TELEGRAM_TOKEN, KOYEB_PUBLIC_URL]):
    logger.critical("Gerekli ortam değişkenleri (TELEGRAM_TOKEN, KOYEB_PUBLIC_URL) eksik. Uygulama başlatılamıyor.")
    exit()

# --- FastAPI ve Telegram Kurulumu ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")
bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# --- TELEGRAM HANDLER'LARI ---
def start_command(update: Update, context: CallbackContext):
    update.message.reply_html(
        "Merhaba! 👋\nBana bir Instagram Reel veya video linki gönder, sana onu indirmen için özel bir sayfa oluşturayım."
    )

def link_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    video_url = update.message.text
    
    if "instagram.com/" not in video_url:
        update.message.reply_text("Lütfen geçerli bir Instagram video linki gönderin.")
        return

    encoded_video_url = quote_plus(video_url)
    auth_page_url = f"{KOYEB_PUBLIC_URL.rstrip('/')}/auth?user_id={user_id}&video_url={encoded_video_url}"
    
    message = (
        "Harika! Bu videoyu indirmek için aşağıdaki linke tıklayıp Instagram bilgilerinizle giriş yapın:\n\n"
        f"<a href='{auth_page_url}'><b>BU LİNKE TIKLA VE GİRİŞ YAP</b></a>\n\n"
        "Giriş bilgileriniz sadece bu indirme için kullanılacak ve asla kaydedilmeyecektir."
    )
    update.message.reply_html(message, disable_web_page_preview=True)

def error_handler(update: Update, context: CallbackContext):
    logger.error(f"Update '{update}' caused error '{context.error}'", exc_info=context.error)

# --- FastAPI ROUTE'LARI ---
@app.post(f'/{TELEGRAM_TOKEN}')
async def process_telegram_update(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return {"status": "ok"}

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request, user_id: str, video_url: str):
    return templates.TemplateResponse("auth.html", {"request": request, "user_id": user_id, "video_url": video_url})

@app.post("/download")
async def handle_download(
    user_id: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    video_url: str = Form(...)
):
    bot.send_message(chat_id=user_id, text="Giriş yapılıyor ve video indiriliyor... Bu işlem biraz sürebilir. ⏳")
    
    L = instaloader.Instaloader(
        download_pictures=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False,
        save_metadata=False, compress_json=False
    )
    
    try:
        logger.info(f"{username} olarak Instagram'a giriş yapılıyor.")
        L.login(username, password)
        logger.info("Giriş başarılı.")

        shortcode = video_url.split("instagram.com/p/")[-1].split("instagram.com/reel/")[-1].split("/")[0]
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        target_dir = f"temp_{uuid4()}"
        L.download_post(post, target=target_dir)

        video_path = None
        for filename in os.listdir(target_dir):
            if filename.endswith('.mp4'):
                video_path = os.path.join(target_dir, filename)
                break
        
        if video_path:
            with open(video_path, 'rb') as video_file:
                bot.send_video(chat_id=user_id, video=video_file, caption="İşte videon! ✅")
            return HTMLResponse(content="<h1>Başarılı!</h1><p>Videonuz Telegram botuna gönderildi. Bu pencereyi kapatabilirsiniz.</p>")
        else:
            raise FileNotFoundError("İndirilen video dosyası sunucuda bulunamadı.")

    # !!!!! İŞTE SİHİR BURADA BAŞLIYOR !!!!!
    except LoginException as e:
        error_message = str(e)
        logger.warning(f"LoginException yakalandı: {error_message}")
        
        # Checkpoint hatasını özel olarak ele alıyoruz
        if "Checkpoint required" in error_message:
            try:
                # Hata metninden URL'i çekip çıkarıyoruz
                challenge_url = error_message.split("https://")[1].split(" - ")[0]
                challenge_url = "https://" + challenge_url
                
                # Kullanıcıya özel onay linkini gönderiyoruz
                bot.send_message(
                    chat_id=user_id,
                    text=(
                        "<b>❗️ ÖNEMLİ: GÜVENLİK ONAYI GEREKİYOR ❗️</b>\n\n"
                        "Instagram, bu giriş denemesini onaylamanızı istiyor. Lütfen aşağıdaki linke tıklayın, açılan sayfada 'Bu Bendim' seçeneğini işaretleyin ve ardından web sayfasındaki 'İndir' butonuna <b>tekrar basın.</b>\n\n"
                        f"<a href='{challenge_url}'><b>GÜVENLİK ONAYI İÇİN TIKLA</b></a>"
                    ),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return HTMLResponse(content="<h1>Onay Gerekli!</h1><p>Giriş yapabilmek için Telegram botuna gönderilen onay linkine tıklamanız gerekiyor. Onayı verdikten sonra bu sayfaya geri dönüp tekrar 'İndir' butonuna basın.</p>", status_code=403)
            except Exception as url_exc:
                logger.error(f"Checkpoint URL'i çıkarılamadı: {url_exc}")
        
        # Diğer tüm giriş hataları için genel bir mesaj
        bot.send_message(chat_id=user_id, text=f"Giriş işlemi başarısız oldu. 😞\n\n<b>Hata:</b> Bilgilerinizi kontrol edin.", parse_mode="HTML")
        return HTMLResponse(content=f"<h1>Hata!</h1><p>Giriş başarısız oldu: Bilgilerinizi kontrol edin.</p>", status_code=401)
        
    except Exception as e:
        logger.error(f"Genel indirme hatası ({username}): {e}", exc_info=True)
        bot.send_message(chat_id=user_id, text=f"İndirme işlemi sırasında beklenmedik bir hata oluştu. 😞\n\n<b>Hata:</b> {type(e).__name__}", parse_mode="HTML")
        return HTMLResponse(content=f"<h1>Hata!</h1><p>İşlem başarısız oldu: {e}</p>", status_code=500)
    finally:
        if 'target_dir' in locals() and os.path.exists(target_dir):
            for f in os.listdir(target_dir):
                os.remove(os.path.join(target_dir, f))
            os.rmdir(target_dir)
            logger.info(f"Geçici klasör {target_dir} temizlendi.")

# --- UYGULAMA BAŞLANGIÇ NOKTASI ---
@app.on_event("startup")
def on_startup():
    webhook_url = f"{KOYEB_PUBLIC_URL.rstrip('/')}/{TELEGRAM_TOKEN}"
    bot.set_webhook(url=webhook_url)
    
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, link_handler))
    dispatcher.add_error_handler(error_handler)
    
    logger.info(f"Uygulama başlatıldı. Webhook ayarlandı: {webhook_url}")
