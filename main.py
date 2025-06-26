import os
import re
import asyncio
import subprocess
import tempfile
import json
import random
from contextlib import asynccontextmanager
import aiohttp
import time
from urllib.parse import urlparse, parse_qs

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

# User agent rotasyonu
USER_AGENTS = [
    'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.210 Mobile Safari/537.36',
    'Instagram 239.0.0.10.109 Android (29/10; 420dpi; 1080x2340; samsung; SM-G973F; beyond1; exynos9820; tr_TR; 369149742)',
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

async def normalize_instagram_url(url):
    """Instagram URL'ini normalize et"""
    try:
        # Farklı Instagram URL formatları
        patterns = [
            r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)',
            r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)/?\?.*',
            r'(?:https?://)?(?:www\.)?instagram\.com/tv/([A-Za-z0-9_-]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                post_id = match.group(1)
                # Reel olup olmadığını kontrol et
                if '/reel/' in url or '/tv/' in url:
                    return f"https://www.instagram.com/reel/{post_id}/"
                else:
                    return f"https://www.instagram.com/p/{post_id}/"
        
        return None
    except Exception as e:
        print(f"URL normalize error: {e}")
        return None

async def get_instagram_video_url_advanced(post_url):
    """Gelişmiş Instagram video URL alma"""
    try:
        # Çoklu konfigürasyon stratejisi
        configs = [
            # Config 1: Temel mobil
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-url',
                    '--format', 'best[height<=720][ext=mp4]/best[ext=mp4]/best',
                    '--user-agent', get_random_user_agent(),
                    '--extractor-retries', '3',
                    '--fragment-retries', '3',
                    '--socket-timeout', '30',
                    post_url
                ]
            },
            # Config 2: Instagram-specific
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-url',
                    '--format', 'best',
                    '--user-agent', 'Instagram 239.0.0.10.109 Android',
                    '--add-header', 'Accept-Language:en-US,en;q=0.9',
                    '--add-header', 'Accept-Encoding:gzip, deflate, br',
                    '--extractor-retries', '5',
                    '--sleep-interval', '1',
                    '--max-sleep-interval', '3',
                    post_url
                ]
            },
            # Config 3: Proxy benzeri
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-url',
                    '--format', 'worst[ext=mp4]/worst',  # Daha küçük boyut
                    '--user-agent', get_random_user_agent(),
                    '--ignore-errors',
                    '--no-check-certificate',
                    post_url
                ]
            },
            # Config 4: Alternatif format
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--get-urls',
                    '--user-agent', get_random_user_agent(),
                    '--cookies-from-browser', 'chrome',  # Eğer Chrome cookie'si varsa
                    post_url
                ]
            }
        ]
        
        for i, config in enumerate(configs):
            try:
                print(f"Trying config {i+1}...")
                
                # Timeout ile process oluştur
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *config['cmd'],
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    ),
                    timeout=30
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=45
                )
                
                if process.returncode == 0:
                    output = stdout.decode().strip()
                    print(f"Config {i+1} output: {output[:100]}...")
                    
                    # Birden fazla URL varsa ilkini al
                    urls = [line.strip() for line in output.split('\n') if line.strip().startswith('http')]
                    if urls:
                        video_url = urls[0]
                        print(f"Found video URL: {video_url[:100]}...")
                        return video_url
                else:
                    error_msg = stderr.decode()
                    print(f"Config {i+1} failed: {error_msg[:200]}...")
                    
            except asyncio.TimeoutError:
                print(f"Config {i+1} timeout")
                continue
            except Exception as e:
                print(f"Config {i+1} error: {e}")
                continue
        
        return None
        
    except Exception as e:
        print(f"Get URL error: {e}")
        return None

async def download_video_with_session(video_url, output_path):
    """Gelişmiş video indirme"""
    try:
        # Session konfigürasyonu
        timeout = aiohttp.ClientTimeout(total=120, connect=30)
        headers = {
            'User-Agent': get_random_user_agent(),
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9,tr;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'video',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
        }
        
        connector = aiohttp.TCPConnector(
            limit=10,
            limit_per_host=5,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
        async with aiohttp.ClientSession(
            timeout=timeout, 
            headers=headers, 
            connector=connector
        ) as session:
            
            # Önce HEAD request ile boyutu kontrol et
            try:
                async with session.head(video_url) as head_response:
                    if head_response.status == 200:
                        content_length = head_response.headers.get('Content-Length')
                        if content_length:
                            size_mb = int(content_length) / (1024 * 1024)
                            print(f"Video size: {size_mb:.2f} MB")
                            if size_mb > 45:  # Telegram limiti
                                print("Video too large for Telegram")
                                return False
            except:
                pass  # HEAD request başarısız olursa devam et
            
            # Asıl indirme
            async with session.get(video_url) as response:
                if response.status == 200:
                    total_size = 0
                    with open(output_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(16384):  # 16KB chunks
                            f.write(chunk)
                            total_size += len(chunk)
                            
                            # Boyut kontrolü
                            if total_size > 50 * 1024 * 1024:  # 50MB
                                print("File too large, stopping download")
                                return False
                    
                    print(f"Downloaded {total_size / (1024*1024):.2f} MB")
                    return total_size > 0
                else:
                    print(f"HTTP {response.status}: {response.reason}")
                    return False
                    
    except asyncio.TimeoutError:
        print("Download timeout")
        return False
    except Exception as e:
        print(f"Download error: {e}")
        return False

async def download_instagram_video_improved(url):
    """Gelişmiş Instagram video indirme"""
    temp_path = None
    try:
        # URL'yi normalize et
        normalized_url = await normalize_instagram_url(url)
        if not normalized_url:
            print("Could not normalize URL")
            return None
        
        print(f"Normalized URL: {normalized_url}")
        
        # Geçici dosya oluştur
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # Strateji 1: Video URL'ini al ve doğrudan indir
        print("Strategy 1: Get video URL and download directly")
        video_url = await get_instagram_video_url_advanced(normalized_url)
        
        if video_url:
            print("Downloading video directly...")
            success = await download_video_with_session(video_url, temp_path)
            
            if success and os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:  # En az 1KB
                print(f"Success! File size: {os.path.getsize(temp_path)} bytes")
                return temp_path
        
        # Strateji 2: yt-dlp ile doğrudan indirme (farklı konfigürasyonlar)
        print("Strategy 2: Direct yt-dlp download")
        
        download_configs = [
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--format', 'best[height<=480][ext=mp4]/worst[ext=mp4]/best',
                    '--output', temp_path,
                    '--user-agent', get_random_user_agent(),
                    '--extractor-retries', '3',
                    '--fragment-retries', '3',
                    '--ignore-errors',
                    '--no-check-certificate',
                    normalized_url
                ]
            },
            {
                'cmd': [
                    'yt-dlp',
                    '--no-playlist',
                    '--format', 'worst',  # En küçük boyut
                    '--output', temp_path,
                    '--user-agent', 'Instagram 239.0.0.10.109 Android',
                    '--sleep-interval', '2',
                    '--max-sleep-interval', '5',
                    normalized_url
                ]
            }
        ]
        
        for i, config in enumerate(download_configs):
            try:
                print(f"Trying download config {i+1}...")
                
                process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *config['cmd'],
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    ),
                    timeout=30
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=90
                )
                
                if process.returncode == 0 and os.path.exists(temp_path) and os.path.getsize(temp_path) > 1000:
                    print(f"Download config {i+1} successful!")
                    return temp_path
                else:
                    error_msg = stderr.decode()
                    print(f"Download config {i+1} failed: {error_msg[:200]}...")
                    
            except asyncio.TimeoutError:
                print(f"Download config {i+1} timeout")
                continue
            except Exception as e:
                print(f"Download config {i+1} error: {e}")
                continue
        
        # Eğer hiç bir yöntem işe yaramazsa
        print("All strategies failed")
        return None
        
    except Exception as e:
        print(f"Download error: {e}")
        return None
    finally:
        # Başarısız olan geçici dosyayı temizle
        if temp_path and os.path.exists(temp_path) and os.path.getsize(temp_path) <= 1000:
            try:
                os.unlink(temp_path)
            except:
                pass

async def get_video_info_safe(url):
    """Güvenli video bilgisi alma"""
    try:
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-playlist',
            '--ignore-errors',
            '--user-agent', get_random_user_agent(),
            '--socket-timeout', '20',
            url
        ]
        
        process = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            ),
            timeout=25
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=30
        )
        
        if process.returncode == 0:
            info = json.loads(stdout.decode())
            return {
                'title': info.get('title', 'Instagram Video')[:100],  # Başlığı sınırla
                'uploader': info.get('uploader', 'Unknown')[:50],
                'duration': info.get('duration', 0),
                'view_count': info.get('view_count', 0)
            }
        return None
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
        print(f"Info error: {e}")
        return None

# Handlers
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 Instagram Video İndirici Bot v2.0\n\n"
        "📱 Bir Instagram reel/post linkini gönderin, size videoyu indireyim!\n\n"
        "✨ Desteklenen formatlar:\n"
        "• instagram.com/reel/...\n"
        "• instagram.com/p/...\n"
        "• instagram.com/tv/...\n\n"
        "⚡ Gelişmiş multi-strateji indirme teknolojisi!\n"
        "🛡️ Anti-ban koruması aktif\n\n"
        "💡 İpucu: Özel hesap videoları indirilemez!"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global last_request_time
    
    txt = update.message.text.strip()
    
    # Instagram URL kontrolü
    normalized_url = await normalize_instagram_url(txt)
    
    if not normalized_url:
        await update.message.reply_text(
            "❌ Geçerli bir Instagram URL'si göndermelisiniz!\n\n"
            "✅ Desteklenen formatlar:\n"
            "• https://www.instagram.com/reel/ABC123/\n"
            "• https://www.instagram.com/p/ABC123/\n"
            "• https://www.instagram.com/tv/ABC123/\n\n"
            "💡 URL'yi kopyala-yapıştır yapın!"
        )
        return

    # Rate limiting
    current_time = time.time()
    if current_time - last_request_time < REQUEST_DELAY:
        sleep_time = REQUEST_DELAY - (current_time - last_request_time)
        await asyncio.sleep(sleep_time)
    
    last_request_time = time.time()
    
    # Progress mesajı
    progress_msg = await update.message.reply_text(
        "🔄 Video indiriliyor...\n"
        "⏱️ Bu işlem 30-60 saniye sürebilir\n"
        "🛡️ Anti-ban koruması aktif"
    )
    
    try:
        # Video indirme
        await asyncio.sleep(1)  # Kısa bekleme
        await progress_msg.edit_text("🔍 Video kaynağı bulunuyor...")
        
        video_path = await download_instagram_video_improved(normalized_url)
        
        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path)
            
            # Dosya boyutu kontrolleri
            if file_size > 50 * 1024 * 1024:  # 50MB
                await progress_msg.edit_text(
                    "❌ Video çok büyük! (>50MB)\n"
                    "Telegram limiti aşıldı."
                )
                os.unlink(video_path)
                return
            
            if file_size < 1000:  # 1KB'den küçük
                await progress_msg.edit_text(
                    "❌ Video dosyası çok küçük veya bozuk!\n"
                    "Lütfen farklı bir video deneyin."
                )
                os.unlink(video_path)
                return
            
            await progress_msg.edit_text("📤 Video gönderiliyor...")
            
            # Video bilgilerini al (opsiyonel)
            info = await get_video_info_safe(normalized_url)
            
            # Caption oluştur
            size_mb = file_size / (1024 * 1024)
            caption = f"📱 Instagram Video İndirildi ✅\n📊 Boyut: {size_mb:.1f} MB"
            
            if info:
                caption = (
                    f"📱 {info['title']}\n"
                    f"👤 {info['uploader']}\n"
                    f"📊 Boyut: {size_mb:.1f} MB\n"
                    f"⏱️ Süre: {info['duration']}s\n\n"
                    f"✅ Bot tarafından indirildi"
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
                    "Video çok büyük olabilir veya ağ problemi yaşanıyor."
                )
            
            # Geçici dosyayı sil
            try:
                os.unlink(video_path)
            except:
                pass
            
        else:
            await progress_msg.edit_text(
                "❌ Video indirilemedi! 😔\n\n"
                "🔍 Olası nedenler:\n"
                "• Video özel hesapta 🔒\n"
                "• Instagram anti-bot koruması 🛡️\n"
                "• Video silinmiş veya mevcut değil 🗑️\n"
                "• Geçici ağ problemi 🌐\n\n"
                "💡 Çözüm önerileri:\n"
                "• 2-3 dakika bekleyip tekrar deneyin ⏰\n"
                "• Farklı bir video deneyin 🔄\n"
                "• URL'yi tekrar kopyalayın 📋\n\n"
                "🆘 Sorun devam ederse /start ile yeniden başlatın"
            )
            
    except Exception as e:
        error_msg = str(e)
        print(f"Error in handle_msg: {error_msg}")
        await progress_msg.edit_text(
            f"❌ Beklenmeyen hata oluştu!\n\n"
            f"🔧 Hata: {error_msg[:100]}...\n\n"
            f"💡 /start ile yeniden başlatmayı deneyin"
        )

# Debug komutu
async def debug_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Debug bilgilerini göster"""
    try:
        # yt-dlp version
        process = await asyncio.create_subprocess_exec(
            'yt-dlp', '--version',
            stdout=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        yt_dlp_version = stdout.decode().strip()
        
        debug_info = (
            f"🔧 Debug Bilgileri:\n\n"
            f"📦 yt-dlp: {yt_dlp_version}\n"
            f"🐍 Python: {os.sys.version.split()[0]}\n"
            f"⏰ Son istek: {time.time() - last_request_time:.1f}s önce\n"
            f"🔄 Rate limit: {REQUEST_DELAY}s\n"
            f"🎯 User agents: {len(USER_AGENTS)} adet"
        )
        
        await update.message.reply_text(debug_info)
        
    except Exception as e:
        await update.message.reply_text(f"Debug hatası: {e}")

# Handlers kayıt
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(CommandHandler("debug", debug_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

# Lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot_app.initialize()
    
    # yt-dlp kontrolü
    try:
        process = await asyncio.create_subprocess_exec('yt-dlp', '--version', stdout=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        print(f"✅ yt-dlp version: {stdout.decode().strip()}")
    except FileNotFoundError:
        print("❌ WARNING: yt-dlp not found! Install with: pip install yt-dlp")
    
    # Webhook ayarla
    if WEBHOOK_URL:
        clean_url = WEBHOOK_URL.rstrip('/')
        webhook_url = f"{clean_url}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook set to: {webhook_url}")
    else:
        print("⚠️ WEBHOOK_URL not set, webhook not configured")
    
    await bot_app.start()
    print("🚀 Instagram Video Downloader Bot started!")
    
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
        "message": "Instagram Video Downloader Bot v2.0 is running",
        "features": ["Multi-strategy download", "Anti-ban protection", "Rate limiting"]
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
