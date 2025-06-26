import os
import re
import asyncio
import tempfile
import json
import random
from contextlib import asynccontextmanager
import aiohttp
import time
from urllib.parse import urlparse

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

# Rate limiting
last_request_time = 0
REQUEST_DELAY = 2  # saniye

# Cobalt.tools API endpoints
COBALT_INSTANCES = [
    "https://api.cobalt.tools",
    "https://co.wuk.sh",
    "https://cobalt-api.kwiateusz.co.uk"
]

def get_random_cobalt_instance():
    """Rastgele cobalt instance seç"""
    return random.choice(COBALT_INSTANCES)

async def normalize_instagram_url(url):
    """Instagram URL'ini normalize et"""
    try:
        patterns = [
            r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?\?.*',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                post_id = match.group(1)
                if '/reel/' in url or '/tv/' in url:
                    return f"https://www.instagram.com/reel/{post_id}/"
                else:
                    return f"https://www.instagram.com/p/{post_id}/"
        
        return None
    except Exception as e:
        print(f"URL normalize error: {e}")
        return None

async def download_with_cobalt(url):
    """Cobalt.tools API ile video indir"""
    try:
        # Normalized URL
        normalized_url = await normalize_instagram_url(url)
        if not normalized_url:
            return None, "Invalid URL format"
        
        print(f"Using Cobalt to download: {normalized_url}")
        
        # Cobalt API request
        for attempt in range(3):  # 3 instance dene
            try:
                cobalt_instance = get_random_cobalt_instance()
                print(f"Trying Cobalt instance: {cobalt_instance}")
                
                # API request payload
                payload = {
                    "url": normalized_url,
                    "vCodec": "h264",
                    "vQuality": "720",
                    "aFormat": "mp3",
                    "filenamePattern": "basic",
                    "isNoTTWatermark": False,
                    "isTTFullAudio": False,
                    "isAudioOnly": False,
                    "isAudioMuted": False,
                    "dubLang": False,
                    "disableMetadata": False
                }
                
                headers = {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
                
                timeout = aiohttp.ClientTimeout(total=60)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    # API'ye request gönder
                    async with session.post(
                        f"{cobalt_instance}/api/json",
                        json=payload,
                        headers=headers
                    ) as response:
                        
                        if response.status == 200:
                            data = await response.json()
                            print(f"Cobalt response: {data}")
                            
                            if data.get("status") == "success":
                                download_url = data.get("url")
                                if download_url:
                                    return download_url, None
                            elif data.get("status") == "error":
                                error_msg = data.get("text", "Unknown error")
                                print(f"Cobalt error: {error_msg}")
                                if "rate limit" in error_msg.lower():
                                    await asyncio.sleep(2)
                                    continue
                                return None, error_msg
                        else:
                            print(f"Cobalt HTTP {response.status}: {await response.text()}")
                            
            except asyncio.TimeoutError:
                print(f"Cobalt instance timeout: {cobalt_instance}")
                continue
            except Exception as e:
                print(f"Cobalt instance error: {e}")
                continue
        
        return None, "All Cobalt instances failed"
        
    except Exception as e:
        print(f"Cobalt download error: {e}")
        return None, str(e)

async def download_video_from_url(video_url, output_path):
    """Video URL'den dosyayı indir"""
    try:
        print(f"Downloading video from: {video_url[:100]}...")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'video',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site'
        }
        
        timeout = aiohttp.ClientTimeout(total=120)
        
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(video_url) as response:
                if response.status == 200:
                    total_size = 0
                    chunk_size = 16384  # 16KB chunks
                    
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            total_size += len(chunk)
                            
                            # Telegram dosya boyutu limiti (50MB)
                            if total_size > 50 * 1024 * 1024:
                                return False, "File too large (>50MB)"
                    
                    print(f"Downloaded {total_size / (1024*1024):.2f} MB")
                    return True, None
                else:
                    return False, f"HTTP {response.status} error"
                    
    except asyncio.TimeoutError:
        return False, "Download timeout"
    except Exception as e:
        return False, f"Download error: {str(e)}"

async def download_instagram_video_cobalt(url):
    """Cobalt.tools kullanarak Instagram video indir"""
    temp_path = None
    try:
        # Geçici dosya oluştur
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Cobalt ile video URL'ini al
        video_url, error = await download_with_cobalt(url)
        
        if error:
            return None, error
        
        if not video_url:
            return None, "Could not get video URL from Cobalt"
        
        # Video dosyasını indir
        success, download_error = await download_video_from_url(video_url, temp_path)
        
        if success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:
            return temp_path, None
        else:
            # Geçici dosyayı temizle
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return None, download_error or "Download failed"
        
    except Exception as e:
        # Geçici dosyayı temizle
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
        return None, f"Error: {str(e)}"

# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Instagram Video İndirici Bot v3.0\n\n"
        "⚡ Cobalt.tools API ile güçlendirildi!\n\n"
        "📱 Desteklenen formatlar:\n"
        "• instagram.com/reel/...\n"
        "• instagram.com/p/...\n"
        "• instagram.com/tv/...\n\n"
        "✨ Özellikler:\n"
        "🔥 Yüksek başarı oranı\n"
        "🛡️ Anti-ban koruması\n"
        "⚡ Hızlı indirme\n"
        "📺 HD kalite desteği\n\n"
        "💡 Bir Instagram linki gönderin ve indirmeye başlayalım!"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Yardım Menüsü\n\n"
        "🔧 Komutlar:\n"
        "/start - Botu başlat\n"
        "/help - Bu yardım menüsü\n"
        "/status - Bot durumu\n\n"
        "📱 Kullanım:\n"
        "1. Instagram video/reel linkini kopyalayın\n"
        "2. Bota gönderin\n"
        "3. Video indirilip size gönderilir!\n\n"
        "⚠️ Notlar:\n"
        "• Özel hesap videoları indirilemez\n"
        "• Maksimum dosya boyutu: 50MB\n"
        "• Rate limit: 2 saniye bekleme\n\n"
        "🆘 Sorun mu yaşıyorsunuz?\n"
        "Bot yeniden başlatılıyor olabilir. Birkaç saniye bekleyin."
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot durumunu göster"""
    try:
        # Test Cobalt instance
        test_url = "https://www.instagram.com/reel/test/"
        cobalt_instance = get_random_cobalt_instance()
        
        start_time = time.time()
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{cobalt_instance}/api/serverInfo") as response:
                if response.status == 200:
                    cobalt_status = "🟢 Online"
                    response_time = int((time.time() - start_time) * 1000)
                else:
                    cobalt_status = "🟡 Yavaş"
                    response_time = int((time.time() - start_time) * 1000)
        
        status_text = (
            f"📊 Bot Durumu\n\n"
            f"🤖 Bot: 🟢 Aktif\n"
            f"⚡ Cobalt API: {cobalt_status}\n"
            f"⏱️ Yanıt süresi: {response_time}ms\n"
            f"🔄 Son istek: {time.time() - last_request_time:.1f}s önce\n"
            f"🛡️ Rate limit: {REQUEST_DELAY}s\n"
            f"📍 Aktif instance: {len(COBALT_INSTANCES)} adet\n\n"
            f"✅ Sistem çalışıyor!"
        )
        
        await update.message.reply_text(status_text)
        
    except Exception as e:
        await update.message.reply_text(
            f"📊 Bot Durumu\n\n"
            f"🤖 Bot: 🟢 Aktif\n"
            f"⚡ Cobalt API: 🔴 Test edilemiyor\n"
            f"❌ Hata: {str(e)[:100]}\n\n"
            f"💡 Yine de deneyin, çalışıyor olabilir!"
        )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_request_time
    
    txt = update.message.text.strip()
    
    # Instagram URL kontrolü
    normalized_url = await normalize_instagram_url(txt)
    
    if not normalized_url:
        await update.message.reply_text(
            "❌ Geçerli bir Instagram URL'si göndermelisiniz!\n\n"
            "✅ Örnek formatlar:\n"
            "• https://www.instagram.com/reel/ABC123/\n"
            "• https://www.instagram.com/p/ABC123/\n"
            "• https://instagram.com/reel/ABC123/\n\n"
            "💡 Linki kopyala-yapıştır yapın!"
        )
        return

    # Rate limiting
    current_time = time.time()
    if current_time - last_request_time < REQUEST_DELAY:
        sleep_time = REQUEST_DELAY - (current_time - last_request_time)
        await update.message.reply_text(
            f"⏰ Çok hızlı! {sleep_time:.1f} saniye bekleyin."
        )
        return
    
    last_request_time = time.time()
    
    # Progress mesajı
    progress_msg = await update.message.reply_text(
        "🔄 Video indiriliyor...\n"
        "⚡ Cobalt.tools API kullanılıyor\n"
        "⏱️ Bu 15-30 saniye sürebilir"
    )
    
    try:
        # Cobalt ile video indir
        await progress_msg.edit_text("🔍 Video kaynağı bulunuyor...")
        
        video_path, error = await download_instagram_video_cobalt(normalized_url)
        
        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path)
            
            # Dosya boyutu kontrolleri
            if file_size > 50 * 1024 * 1024:  # 50MB
                await progress_msg.edit_text(
                    "❌ Video çok büyük! (>50MB)\n"
                    "Telegram dosya boyutu limiti aşıldı."
                )
                os.unlink(video_path)
                return
            
            if file_size < 1000:  # 1KB'den küçük
                await progress_msg.edit_text(
                    "❌ Video dosyası çok küçük!\n"
                    "Dosya bozuk olabilir."
                )
                os.unlink(video_path)
                return
            
            await progress_msg.edit_text("📤 Video gönderiliyor...")
            
            # Caption oluştur
            size_mb = file_size / (1024 * 1024)
            caption = (
                f"📱 Instagram Video İndirildi ✅\n"
                f"⚡ Cobalt.tools ile indirildi\n"
                f"📊 Boyut: {size_mb:.1f} MB\n"
                f"🔗 Kaynak: Instagram\n\n"
                f"🤖 @{context.bot.username} tarafından indirildi"
            )
            
            # Video gönder
            try:
                with open(video_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=video_file,
                        supports_streaming=True,
                        caption=caption,
                        read_timeout=180,
                        write_timeout=180,
                        connect_timeout=60
                    )
                
                await progress_msg.delete()
                
            except Exception as send_error:
                print(f"Send error: {send_error}")
                await progress_msg.edit_text(
                    "❌ Video gönderilirken hata oluştu!\n"
                    "Dosya çok büyük olabilir."
                )
            
            # Geçici dosyayı sil
            try:
                os.unlink(video_path)
            except:
                pass
            
        else:
            # Hata mesajını kullanıcı dostu hale getir
            user_error = "Bilinmeyen hata"
            if error:
                if "rate limit" in error.lower():
                    user_error = "Rate limit aşıldı. Birkaç dakika bekleyin."
                elif "not available" in error.lower():
                    user_error = "Video mevcut değil veya özel hesap."
                elif "invalid" in error.lower():
                    user_error = "Geçersiz URL formatı."
                elif "timeout" in error.lower():
                    user_error = "Bağlantı zaman aşımı."
                else:
                    user_error = error[:100]
            
            await progress_msg.edit_text(
                f"❌ Video indirilemedi! 😔\n\n"
                f"🔍 Hata: {user_error}\n\n"
                f"💡 Çözüm önerileri:\n"
                f"• Linki tekrar kontrol edin 📋\n"
                f"• 2-3 dakika bekleyip tekrar deneyin ⏰\n"
                f"• Video özel hesapta olmadığından emin olun 🔒\n"
                f"• /status ile bot durumunu kontrol edin 📊\n\n"
                f"🆘 Sorun devam ederse /help yazın"
            )
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error in handle_msg: {error_msg}")
        await progress_msg.edit_text(
            f"❌ Beklenmeyen hata oluştu!\n\n"
            f"🔧 Hata: {error_msg[:100]}...\n\n"
            f"💡 Bu geçici bir sorun olabilir.\n"
            f"Birkaç dakika bekleyip tekrar deneyin.\n\n"
            f"🆘 /status ile bot durumunu kontrol edin"
        )

# Handlers kayıt
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(CommandHandler("help", help_cmd))
bot_app.add_handler(CommandHandler("status", status_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot_app.initialize()
    
    # Cobalt instances test
    print("🧪 Testing Cobalt instances...")
    working_instances = []
    
    for instance in COBALT_INSTANCES:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{instance}/api/serverInfo") as response:
                    if response.status == 200:
                        working_instances.append(instance)
                        print(f"✅ {instance} - Working")
                    else:
                        print(f"⚠️ {instance} - Status {response.status}")
        except Exception as e:
            print(f"❌ {instance} - Error: {e}")
    
    if working_instances:
        print(f"🚀 {len(working_instances)}/{len(COBALT_INSTANCES)} Cobalt instances are working")
    else:
        print("⚠️ No Cobalt instances are responding (will still try during runtime)")
    
    # Webhook ayarla
    if WEBHOOK_URL:
        clean_url = WEBHOOK_URL.rstrip('/')
        webhook_url = f"{clean_url}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook set to: {webhook_url}")
    else:
        print("⚠️ WEBHOOK_URL not set")
    
    await bot_app.start()
    print("🚀 Instagram Video Downloader Bot v3.0 (Cobalt-powered) started!")
    
    yield
    
    # Shutdown
    await bot_app.stop()
    await bot_app.shutdown()
    print("🛑 Bot stopped")

# FastAPI app
app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    return {
        "status": "ok", 
        "message": "Instagram Video Downloader Bot v3.0 (Cobalt-powered)",
        "features": [
            "Cobalt.tools API integration",
            "High success rate",
            "Multiple instance support",
            "Rate limiting",
            "HD quality support"
        ],
        "cobalt_instances": len(COBALT_INSTANCES)
    }

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
    """Webhook bilgilerini al"""
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

@app.get("/test-cobalt")
async def test_cobalt():
    """Cobalt instances test endpoint"""
    results = []
    
    for instance in COBALT_INSTANCES:
        try:
            start_time = time.time()
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{instance}/api/serverInfo") as response:
                    response_time = int((time.time() - start_time) * 1000)
                    
                    if response.status == 200:
                        data = await response.json()
                        results.append({
                            "instance": instance,
                            "status": "working",
                            "response_time_ms": response_time,
                            "data": data
                        })
                    else:
                        results.append({
                            "instance": instance,
                            "status": f"error_{response.status}",
                            "response_time_ms": response_time
                        })
        except Exception as e:
            results.append({
                "instance": instance,
                "status": "failed",
                "error": str(e)
            })
    
    return {"cobalt_test_results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
