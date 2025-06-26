import os
import re
import instaloader
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Env'den al ngl
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # Webhook URL'ini env'den al

# Instagram login bilgileri (isteğe bağlı)
INSTAGRAM_USERNAME = os.environ.get("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.environ.get("INSTAGRAM_PASSWORD", "")

# Instaloader config - User-Agent ve rate limiting ayarları
L = instaloader.Instaloader(
    save_metadata=False,
    download_videos=False,
    download_video_thumbnails=False,
    compress_json=False,
    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    request_timeout=60,
)

# Instagram'a login (isteğe bağlı)
async def setup_instagram_session():
    if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
        try:
            L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
            print("Instagram'a başarıyla giriş yapıldı")
        except Exception as e:
            print(f"Instagram login hatası: {e}")
            print("Anonim modda devam ediliyor...")

# Rate limiting için son istek zamanı
last_request_time = 0
REQUEST_DELAY = 3  # saniye

# Telegram bot application
bot_app = ApplicationBuilder().token(TOKEN).build()

# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at ts, beni test et 🔥")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_request_time
    
    txt = update.message.text.strip()
    m = re.search(r"/reel/([^/?]+)", txt)
    if not m:
        await update.message.reply_text("Geçerli reel URL'si at ts 🙏")
        return

    sc = m.group(1)
    await update.message.reply_text("Link çekiliyor… crash out etme 😂")

    try:
        # Rate limiting - istekler arası bekle
        import time
        current_time = time.time()
        if current_time - last_request_time < REQUEST_DELAY:
            sleep_time = REQUEST_DELAY - (current_time - last_request_time)
            await asyncio.sleep(sleep_time)
        
        last_request_time = time.time()
        
        # Instagram session ayarları
        L.context.log("Fetching post data...")
        
        # Retry mekanizması
        max_retries = 3
        for attempt in range(max_retries):
            try:
                post = instaloader.Post.from_shortcode(L.context, sc)
                
                if post.is_video:
                    video_url = post.video_url
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_url,
                        supports_streaming=True,
                        caption=f"📱 İndirilen reel\n👤 @{post.owner_username}"
                    )
                else:
                    # Video değilse fotoğraf gönder
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=post.url,
                        caption=f"📷 İndirilen post\n👤 @{post.owner_username}"
                    )
                break
                    
            except instaloader.exceptions.ConnectionException as e:
                if "401" in str(e) or "Please wait" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # 10, 20, 30 saniye bekle
                        await update.message.reply_text(f"Instagram rate limit! {wait_time} saniye bekleniyor... 🕐")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        await update.message.reply_text("Instagram geçici olarak erişimi kısıtladı. Lütfen daha sonra tekrar deneyin 😔")
                        return
                else:
                    raise e
                    
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Please wait" in error_msg:
            await update.message.reply_text("Instagram rate limit! Biraz bekleyip tekrar deneyin 🕐")
        elif "404" in error_msg:
            await update.message.reply_text("Post bulunamadı! Link doğru mu? 🤔")
        else:
            await update.message.reply_text(f"Bir hata oluştu: {error_msg} 💔")

# Kayıt et
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot_app.initialize()
    
    # Instagram session setup
    await setup_instagram_session()
    
    # Webhook modunda çalıştır
    if WEBHOOK_URL:
        # URL'in sonunda slash varsa kaldır
        clean_url = WEBHOOK_URL.rstrip('/')
        webhook_url = f"{clean_url}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        print(f"Webhook set to: {webhook_url}")
    else:
        print("WEBHOOK_URL not set, webhook not configured")
    
    await bot_app.start()
    
    yield
    
    # Shutdown
    await bot_app.stop()
    await bot_app.shutdown()

# FastAPI app
app = FastAPI(lifespan=lifespan)

@app.get("/set-webhook")
async def set_webhook_manually():
    """Webhook'u manuel olarak ayarla"""
    try:
        if WEBHOOK_URL:
            clean_url = WEBHOOK_URL.rstrip('/')
            webhook_url = f"{clean_url}/webhook"
            await bot_app.bot.set_webhook(url=webhook_url)
            return {"status": "success", "webhook_url": webhook_url}
        else:
            return {"status": "error", "message": "WEBHOOK_URL not set"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/webhook-info")
async def get_webhook_info():
    """Mevcut webhook bilgilerini al"""
    try:
        webhook_info = await bot_app.bot.get_webhook_info()
        return {
            "url": webhook_info.url,
            "pending_update_count": webhook_info.pending_update_count,
            "last_error_date": webhook_info.last_error_date,
            "last_error_message": webhook_info.last_error_message
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/webhook")
async def webhook(request: Request):
    """Telegram webhook endpoint"""
    try:
        # JSON verisini al
        json_data = await request.json()
        print(f"Received webhook data: {json_data}")
        
        # Update objesini oluştur
        update = Update.de_json(json_data, bot_app.bot)
        
        if update:
            # Update'i işle
            await bot_app.process_update(update)
            print("Update processed successfully")
        else:
            print("Invalid update received")
            
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
