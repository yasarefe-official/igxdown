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

# Env'den al
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# Telegram bot application
bot_app = ApplicationBuilder().token(TOKEN).build()

# Rate limiting için son istek zamanı
last_request_time = 0
REQUEST_DELAY = 3  # saniye

async def download_instagram_video(url):
    """yt-dlp kullanarak Instagram video indirme"""
    try:
        # Geçici dosya oluştur
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # yt-dlp komutu - cookies kullanmadan
        cmd = [
            'yt-dlp',
            '--no-playlist',
            '--format', 'best[ext=mp4]/mp4/best',
            '--output', temp_path,
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            '--extractor-retries', '3',
            '--fragment-retries', '3',
            '--socket-timeout', '30',
            url
        ]
        
        # Komut çalıştır
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            return temp_path
        else:
            print(f"yt-dlp error: {stderr.decode()}")
            # Dosya varsa sil
            if os.path.exists(temp_path):
                os.unlink(temp_path)
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
            '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
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
    await update.message.reply_text(
        "🔥 Instagram Video İndirici Bot\n\n"
        "📱 Bir Instagram reel/post linkini gönderin, size videoyu indireyim!\n\n"
        "✨ Desteklenen formatlar:\n"
        "• instagram.com/reel/...\n"
        "• instagram.com/p/...\n\n"
        "⚡ Hızlı ve güvenilir!"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_request_time
    
    txt = update.message.text.strip()
    
    # Instagram URL pattern'ları
    instagram_patterns = [
        r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)',
        r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?\?.*',
    ]
    
    found_url = None
    for pattern in instagram_patterns:
        match = re.search(pattern, txt)
        if match:
            # URL'yi normalize et
            post_id = match.group(1)
            if '/reel/' in txt:
                found_url = f"https://www.instagram.com/reel/{post_id}/"
            else:
                found_url = f"https://www.instagram.com/p/{post_id}/"
            break
    
    if not found_url:
        await update.message.reply_text(
            "❌ Geçerli bir Instagram reel/post URL'si göndermelisiniz!\n\n"
            "Örnek:\n"
            "• https://www.instagram.com/reel/ABC123/\n"
            "• https://www.instagram.com/p/ABC123/"
        )
        return

    # Rate limiting
    import time
    current_time = time.time()
    if current_time - last_request_time < REQUEST_DELAY:
        sleep_time = REQUEST_DELAY - (current_time - last_request_time)
        await asyncio.sleep(sleep_time)
    
    last_request_time = time.time()
    
    progress_msg = await update.message.reply_text("⏳ Video indiriliyor... Lütfen bekleyin...")
    
    try:
        # Video bilgilerini al
        info = await get_video_info(found_url)
        
        # Video indir
        video_path = await download_instagram_video(found_url)
        
        if video_path and os.path.exists(video_path):
            # Video boyutunu kontrol et (Telegram limiti ~50MB)
            file_size = os.path.getsize(video_path)
            if file_size > 50 * 1024 * 1024:  # 50MB
                await progress_msg.edit_text("❌ Video çok büyük! (>50MB)")
                os.unlink(video_path)
                return
            
            if file_size == 0:
                await progress_msg.edit_text("❌ Video dosyası boş!")
                os.unlink(video_path)
                return
            
            await progress_msg.edit_text("📤 Video gönderiliyor...")
            
            # Caption oluştur
            caption = "📱 Instagram Video İndirildi"
            if info:
                title = info['title'][:50] + "..." if len(info['title']) > 50 else info['title']
                caption = f"📱 {title}\n👤 {info['uploader']}"
            
            # Video gönder
            try:
                with open(video_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file,
                        supports_streaming=True,
                        caption=caption,
                        read_timeout=60,
                        write_timeout=60
                    )
                
                await progress_msg.delete()
                
            except Exception as send_error:
                print(f"Send error: {send_error}")
                await progress_msg.edit_text("❌ Video gönderilirken hata oluştu!")
            
            # Geçici dosyayı sil
            try:
                os.unlink(video_path)
            except:
                pass
            
        else:
            await progress_msg.edit_text(
                "❌ Video indirilemedi!\n\n"
                "Olası nedenler:\n"
                "• Video özel hesapta olabilir\n"
                "• Link geçersiz olabilir\n"
                "• Instagram erişimi engellenmiş olabilir\n"
                "• Video artık mevcut olmayabilir"
            )
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error in handle_msg: {error_msg}")
        await progress_msg.edit_text(f"❌ Hata oluştu: {error_msg[:100]}")

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
        stdout, _ = await process.communicate()
        print(f"yt-dlp version: {stdout.decode().strip()}")
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
    return {"status": "ok", "message": "Instagram Video Downloader Bot is running"}

@app.post("/webhook")
async def webhook(request: Request):
    """Telegram webhook endpoint"""
    try:
        json_data = await request.json()
        
        update = Update.de_json(json_data, bot_app.bot)
        
        if update:
            await bot_app.process_update(update)
        
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
