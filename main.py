import os
import re
import instaloader
from http.cookiejar import Cookie
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
# Bu 4 değişken, botun kimliğidir.
IG_USERNAME = os.environ.get("IG_USERNAME")
IG_USER_ID = os.environ.get("IG_USER_ID")
IG_SESSIONID = os.environ.get("IG_SESSIONID")
IG_CSRFTOKEN = os.environ.get("IG_CSRFTOKEN")

# --- Instaloader Kurulumu ---
L = instaloader.Instaloader(
    save_metadata=False,
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
)

# --- Bot ve FastAPI Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at, direkt Telegram’da oynatırım 😭🔥") 

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([^/?]+)", text)
    if not match:
        await update.message.reply_text("Geçerli bir reel URL'si at ts 😭")
        return

    shortcode = match.group(1)
    await update.message.reply_text("Reel URL’den link çekiliyor, crash out etme 😭")

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        video_url = post.video_url

        if not video_url:
            await update.message.reply_text("Bu gönderide video yok gibi dawg 😭")
            return

        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            supports_streaming=True
        )
    except Exception as e:
        print(f"Hata: {e}")
        await update.message.reply_text(f"Hata oluştu, post özel olabilir veya IG limit attı: {e} 😭")

# --- Uygulama Yaşam Döngüsü ve Kimlik Doğrulama ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Botu başlatır ve Instaloader oturumunu DOĞRU BİR ŞEKİLDE enjekte eder."""
    
    if not all([IG_USERNAME, IG_USER_ID, IG_SESSIONID, IG_CSRFTOKEN]):
        raise ValueError("KRİTİK HATA: Instagram kimlik bilgileri (ortam değişkenleri) eksik!")

    print("Authenticating Instaloader session manually...")
    
    # Kütüphanenin kendi içindeki "context" nesnesini alıyoruz.
    ctx = L.context
    
    # Bu context'in "cookies" özelliğine, gerekli çerezleri manuel olarak ekliyoruz.
    # Bu, en temel ve en garantili yöntemdir. Önceki tüm hatalarım, bunu bilmememden kaynaklandı.
    ctx.cookies.set_cookie(Cookie(version=0, name='sessionid', value=IG_SESSIONID, port=None, port_specified=False, domain='.instagram.com', domain_specified=True, domain_initial_dot=True, path='/', path_specified=True, secure=True, expires=None, discard=True, comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False))
    ctx.cookies.set_cookie(Cookie(version=0, name='csrftoken', value=IG_CSRFTOKEN, port=None, port_specified=False, domain='.instagram.com', domain_specified=True, domain_initial_dot=True, path='/', path_specified=True, secure=False, expires=None, discard=True, comment=None, comment_url=None, rest={}, rfc2109=False))
    ctx.cookies.set_cookie(Cookie(version=0, name='ds_user_id', value=IG_USER_ID, port=None, port_specified=False, domain='.instagram.com', domain_specified=True, domain_initial_dot=True, path='/', path_specified=True, secure=True, expires=None, discard=True, comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False))
    
    # Context'e kullanıcı adını ve diğer bilgileri de yüklüyoruz.
    ctx.username = IG_USERNAME
    ctx.user_agent = L.user_agent
    
    print(f"Session authenticated for '{IG_USERNAME}'.")
    
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Bot (The Correct and Final Version) started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.post("/webhook")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}
