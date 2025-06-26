import os
import re
import asyncio
import subprocess
import tempfile
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
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# Telegram bot application
bot_app = ApplicationBuilder().token(TOKEN).build()

# Rate limiting için son istek zamanı
last_request_time = 0
REQUEST_DELAY = 5  # saniye

async def download_instagram_video(url):
    """yt-dlp kullanarak Instagram video indirme"""
    try:
        # Geçici dosya oluştur
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # yt-dlp komutu
        cmd = [
            'yt-dlp',
            '--no-playlist',
            '--format', 'best[ext=mp4]',
            '--output', temp_path,
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            '--cookies-from-browser', 'chrome',  # Chrome cookies kullan
            url
        ]
        
        # Komut çalıştır
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return temp_path
        else:
            print(f"yt-dlp error: {stderr.decode()}")
            return None
            
    except Exception as e:
        print(f"Download error: {e}")
        return None

async def get_video_info(url):
    """Video bilgilerini al"""
    try:
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-playlist',
            url
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            import json
            info = json.loads(stdout.decode())
            return {
                'title': info.get('title', 'Instagram Video'),
                'uploader': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0)
            }
        return None
    except Exception as e:
        print(f"Info error: {e}")
        return None

# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Yo dawg, reel linkini at ts, beni test et 🔥\n\n✨ Artık daha güvenilir yöntem kullanıyorum!")

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_request_time
    
    txt = update.message.text.strip()
    
    # Instagram URL pattern'ları
    instagram_patterns = [
        r'instagram\.com/(?:p|reel)/([^/?]+)',
        r'instagram\.com/(?:p|reel)/([^/?]+)/?\?.*',
    ]
    
    found_url = None
    for pattern in instagram_patterns:
        if re.search(pattern, txt):
            found_url = txt
            break
    
    if not found_url:
        await update.message.reply_text("Geçerli Instagram reel/post URL'si at ts 🙏")
        return

    # Rate limiting
    import time
    current_time = time.time()
    if current_time - last_request_time < REQUEST_DELAY:
        sleep_time = REQUEST_DELAY - (current_time - last_request_time)
        await asyncio.sleep(sleep_time)
    
    last_request_time = time.time()
    
    progress_msg = await update.message.reply_text("Video indiriliyor... 📥")
    
    try:
        # Video bilgilerini al
        info = await get_video_info(found_url)
        
        # Video indir
        video_path = await download_instagram_video(found_url)
        
        if video_path and os.path.exists(video_path):
            # Video boyutunu kontrol et (Telegram limiti ~50MB)
            file_size = os.path.getsize(video_path)
            if file_size > 50 * 1024 * 1024:  # 50MB
                await progress_msg.edit_text("Video çok büyük! (>50MB) 😔")
                os.unlink(video_path)
                return
            
            await progress_msg.edit_text("Video gönderiliyor... 📤")
            
            # Caption oluştur
            caption = "📱 İndirilen reel/video"
            if info:
                caption = f"📱 {info['title'][:100]}\n👤 @{info['uploader']}"
            
            # Video gönder
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    supports_streaming=True,
                    caption=caption
                )
            
            # Geçici dosyayı sil
            os.unlink(video_path)
            await progress_msg.delete()
            
        else:
            await progress_msg.edit_text("Video indirilemedi 😔\n\nMümkün nedenler:\n• Video özel hesapta\n• Link geçersiz\n• Instagram rate limit")
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error in handle_msg: {error_msg}")
        await progress_msg.edit_text(f"Bir hata oluştu: {error_msg[:100]} 💔")

# Kayıt et
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot_app.initialize()
    
    # yt-dlp varlığını kontrol et
    try:
        process = await asyncio.create_subprocess_exec('yt-dlp', '--version', stdout=asyncio.subprocess.PIPE)
        await process.communicate()
        print("yt-dlp is available")
    except FileNotFoundError:
        print("WARNING: yt-dlp not found! Install with: pip install yt-dlp")
    
    # Webhook modunda çalıştır
    if WEBHOOK_URL:
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

@app.get("/")
async def health():
    return {"status": "ok", "message": "Bot is running with yt-dlp"}

@app.post("/webhook")
async def webhook(request: Request):
    """Telegram webhook endpoint"""
    try:
        json_data = await request.json()
        print(f"Received webhook data: {json_data}")
        
        update = Update.de_json(json_data, bot_app.bot)
        
        if update:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
