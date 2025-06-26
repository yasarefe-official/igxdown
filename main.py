import os
import re
import asyncio
import subprocess
import tempfile
import json
from contextlib import asynccontextmanager
import aiohttp
import time

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
REQUEST_DELAY = 5  # saniye

async def get_instagram_video_url(post_url):
    """Instagram video URL'ini al - alternatif yöntem"""
    try:
        # Farklı yt-dlp konfigürasyonları dene
        configs = [
            # Config 1: Basit
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-url',
                    '--format', 'best[ext=mp4]/best',
                    post_url
                ]
            },
            # Config 2: Farklı user agent
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-url',
                    '--format', 'best[ext=mp4]/best',
                    '--user-agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
                    post_url
                ]
            },
            # Config 3: Mobile user agent
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-url',
                    '--format', 'best',
                    '--user-agent', 'Instagram 219.0.0.12.117 Android',
                    post_url
                ]
            }
        ]
        
        for config in configs:
            try:
                process = await asyncio.create_subprocess_exec(
                    *config['cmd'],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    video_url = stdout.decode().strip()
                    if video_url and video_url.startswith('http'):
                        return video_url
                else:
                    print(f"Config failed: {stderr.decode()}")
                    
            except Exception as e:
                print(f"Config error: {e}")
                continue
        
        return None
        
    except Exception as e:
        print(f"Get URL error: {e}")
        return None

async def download_video_direct(video_url, output_path):
    """Videoyu doğrudan indir"""
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                    return True
                else:
                    print(f"HTTP {response.status} error")
                    return False
                    
    except Exception as e:
        print(f"Direct download error: {e}")
        return False

async def download_instagram_video(url):
    """Instagram video indirme - gelişmiş yöntem"""
    try:
        # Geçici dosya oluştur
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Önce video URL'ini al
        video_url = await get_instagram_video_url(url)
        
        if video_url:
            # Videoyu doğrudan indir
            success = await download_video_direct(video_url, temp_path)
            
            if success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path
        
        # Eğer yukarıdaki yöntem başarısız olursa, yt-dlp ile doğrudan indir
        print("Trying direct yt-dlp download...")
        
        cmd = [
            'yt-dlp',
            '--no-playlist',
            '--format', 'best[ext=mp4]/best',
            '--output', temp_path,
            '--user-agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
            '--extractor-retries', '5',
            '--fragment-retries', '5',
            '--ignore-errors',
            url
        ]
        
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
            '--ignore-errors',
            url
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
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
        "⚡ Gelişmiş indirme teknolojisi ile hızlı ve güvenilir!"
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
    current_time = time.time()
    if current_time - last_request_time < REQUEST_DELAY:
        sleep_time = REQUEST_DELAY - (current_time - last_request_time)
        await asyncio.sleep(sleep_time)
    
    last_request_time = time.time()
    
    progress_msg = await update.message.reply_text("⏳ Video indiriliyor... Bu biraz zaman alabilir...")
    
    try:
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
            
            # Video bilgilerini al
            info = await get_video_info(found_url)
            
            # Caption oluştur
            caption = "📱 Instagram Video İndirildi ✅"
            if info:
                title = info['title'][:50] + "..." if len(info['title']) > 50 else info['title']
                caption = f"📱 {title}\n👤 {info['uploader']}\n\n✅ Bot tarafından indirildi"
            
            # Video gönder
            try:
                with open(video_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file,
                        supports_streaming=True,
                        caption=caption,
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=60
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
                "• Instagram anti-bot koruması aktif\n"
                "• Video artık mevcut olmayabilir\n\n"
                "💡 Birkaç dakika sonra tekrar deneyin."
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
