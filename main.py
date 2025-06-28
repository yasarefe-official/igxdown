import os
import re
import aiohttp
import random
import json
import asyncio
from contextlib import asynccontextmanager
from urllib.parse import quote, unquote

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- ÜCRETSIZ VE SINIR­SIZ API'LER LİSTESİ ---
DOWNLOADER_APIS = [
    {
        "name": "FastDL",
        "url": "https://fastdl.app/c/",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://fastdl.app/en'
        },
        "enabled": True
    },
    {
        "name": "Snapins",
        "url": "https://snapins.ai/wp-json/aio-dl/video-data/",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://snapins.ai'
        },
        "enabled": True
    },
    {
        "name": "InDown",
        "url": "https://indown.io/action",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        },
        "enabled": True
    },
    {
        "name": "Inflact",
        "url": "https://inflact.com/save-instagram/",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'X-Requested-With': 'XMLHttpRequest'
        },
        "enabled": True
    },
    {
        "name": "SaveFrom_Net",
        "url": "https://worker.sf-tools.com/save-from-net",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        "enabled": True
    }
]

# --- Bot ve FastAPI Kurulumu ---
bot_app = None
app = FastAPI()

def extract_instagram_id(url: str):
    """Instagram URL'sinden post ID'sini çıkarır - düzeltilmiş regex"""
    patterns = [
        r'/p/([A-Za-z0-9_-]+)',
        r'/reel/([A-Za-z0-9_-]+)',
        r'/tv/([A-Za-z0-9_-]+)',
        r'instagram\.com/p/([A-Za-z0-9_-]+)',
        r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        r'instagram\.com/tv/([A-Za-z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def extract_video_urls_from_html(html_content: str):
    """HTML içerikten video URL'lerini çıkarır"""
    video_patterns = [
        r'"(https?://[^"]*\.mp4[^"]*)"',
        r"'(https?://[^']*\.mp4[^']*)'",
        r'href="(https?://[^"]*\.mp4[^"]*)"',
        r'src="(https?://[^"]*\.mp4[^"]*)"',
        r'data-src="(https?://[^"]*\.mp4[^"]*)"',
        r'url:"(https?://[^"]*\.mp4[^"]*)"',
        r'video_url["\']?\s*:\s*["\']([^"\']+)["\']',
        r'download["\']?\s*:\s*["\']([^"\']*\.mp4[^"\']*)["\']'
    ]
    
    found_urls = []
    
    for pattern in video_patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        for match in matches:
            clean_url = match.replace('\\/', '/').replace('&amp;', '&')
            if clean_url.startswith('http') and '.mp4' in clean_url:
                found_urls.append(clean_url)
    
    # En uzun URL'yi döndür (genellikle daha kaliteli)
    return max(found_urls, key=len) if found_urls else None

async def try_fastdl_api(url: str):
    """FastDL API'sini dener"""
    timeout_config = aiohttp.ClientTimeout(total=30)
    
    try:
        payload = {
            'url': url,
            'lang': 'en'
        }
        
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(
                DOWNLOADER_APIS[0]['url'],
                data=payload,
                headers=DOWNLOADER_APIS[0]['headers'],
                ssl=False  # SSL doğrulama sorunlarını önlemek için
            ) as response:
                
                if response.status == 200:
                    html_content = await response.text()
                    video_url = extract_video_urls_from_html(html_content)
                    if video_url:
                        return video_url
                        
    except Exception as e:
        print(f"FastDL API error: {e}")
        
    return None

async def try_snapins_api(url: str):
    """Snapins API'sini dener"""
    timeout_config = aiohttp.ClientTimeout(total=25)
    
    try:
        payload = {
            "url": url,
            "token": ""
        }
        
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(
                DOWNLOADER_APIS[1]['url'],
                json=payload,
                headers=DOWNLOADER_APIS[1]['headers'],
                ssl=False
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Snapins yanıt yapısını kontrol et
                    if isinstance(data, dict):
                        video_url = (data.get('url') or 
                                   data.get('video_url') or 
                                   data.get('download_url'))
                        
                        if video_url:
                            return video_url
                        
                        # Medya listesi kontrolü
                        if 'medias' in data and data['medias']:
                            for media in data['medias']:
                                if media.get('url') and '.mp4' in media.get('url', ''):
                                    return media['url']
                        
    except Exception as e:
        print(f"Snapins API error: {e}")
        
    return None

async def try_indown_api(url: str):
    """InDown API'sini dener"""
    timeout_config = aiohttp.ClientTimeout(total=25)
    
    try:
        payload = {
            'url': url,
            'submit': 'Download'
        }
        
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(
                DOWNLOADER_APIS[2]['url'],
                data=payload,
                headers=DOWNLOADER_APIS[2]['headers'],
                ssl=False
            ) as response:
                
                if response.status == 200:
                    html_content = await response.text()
                    video_url = extract_video_urls_from_html(html_content)
                    if video_url:
                        return video_url
                        
    except Exception as e:
        print(f"InDown API error: {e}")
        
    return None

async def try_savefrom_api(url: str):
    """SaveFrom API'sini dener"""
    timeout_config = aiohttp.ClientTimeout(total=25)
    
    try:
        payload = {
            "sf_url": url,
            "sf_submit": "",
            "new": 2
        }
        
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(
                DOWNLOADER_APIS[4]['url'],
                json=payload,
                headers=DOWNLOADER_APIS[4]['headers'],
                ssl=False
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list) and data:
                        for item in data:
                            if isinstance(item, dict) and item.get('url'):
                                url_candidate = item['url']
                                if '.mp4' in url_candidate:
                                    return url_candidate
                                    
    except Exception as e:
        print(f"SaveFrom API error: {e}")
        
    return None

async def get_video_link(url: str):
    """Ana video indirme fonksiyonu - tüm ücretsiz yöntemleri dener"""
    
    # Instagram ID'sini çıkar
    instagram_id = extract_instagram_id(url)
    if not instagram_id:
        return None, "Invalid Instagram URL format."
    
    print(f"Extracted Instagram ID: {instagram_id}")
    
    # API denemelerini tanımla
    api_attempts = [
        ("InDown", try_indown_api),
        ("SaveFrom", try_savefrom_api),
        ("FastDL", try_fastdl_api),
        ("Snapins", try_snapins_api)
    ]
    
    # API'leri rastgele sırada dene
    random.shuffle(api_attempts)
    
    for api_name, api_func in api_attempts:
        try:
            print(f"Trying {api_name} API...")
            video_url = await api_func(url)
            
            if video_url and await is_valid_video_url(video_url):
                print(f"Success with {api_name}!")
                return video_url, None
                
        except Exception as e:
            print(f"{api_name} API failed: {str(e)[:100]}...")
            continue
    
    return None, ("Unable to download video. This might happen if:\n"
                  "• The post is from a private account\n"
                  "• The post has been deleted\n"
                  "• The content is a Story (not supported)\n"
                  "• All services are temporarily busy")

async def is_valid_video_url(url: str):
    """Video URL'sinin geçerli olup olmadığını kontrol eder"""
    if not url or not url.startswith('http'):
        return False
        
    try:
        timeout_config = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.head(url, ssl=False) as response:
                content_type = response.headers.get('content-type', '').lower()
                content_length = int(response.headers.get('content-length', 0))
                
                return (response.status == 200 and 
                       ('video' in content_type or 'mp4' in content_type or content_length > 10000))
    except:
        # HEAD request başarısızsa GET ile küçük bir kısım indirmeyi dene
        try:
            timeout_config = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                headers = {'Range': 'bytes=0-1023'}  # İlk 1KB
                async with session.get(url, headers=headers, ssl=False) as response:
                    return response.status in [200, 206]  # 206 = Partial Content
        except:
            return False

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "🎥 <b>Instagram Video Downloader Bot</b>\n\n"
        "📱 Send me an Instagram post or reel link and I'll download the video for you!\n\n"
        "📋 <b>Supported formats:</b>\n"
        "• Posts: instagram.com/p/xxxxx/\n"
        "• Reels: instagram.com/reel/xxxxx/\n"
        "• IGTV: instagram.com/tv/xxxxx/\n\n"
        "⚡️ <b>Features:</b>\n"
        "• 100% Free & Unlimited\n"
        "• High quality downloads\n"
        "• No watermarks\n"
        "• Multiple backup systems\n"
        "• Fast processing\n\n"
        "🚀 Just paste your Instagram link below!"
    )
    
    await update.message.reply_text(message, parse_mode='HTML')

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Instagram URL kontrolü
    if not any(domain in url.lower() for domain in ['instagram.com', 'instagr.am']):
        await update.message.reply_text(
            "❌ <b>Invalid URL</b>\n\n"
            "Please provide a valid Instagram link.\n\n"
            "📋 <b>Examples:</b>\n"
            "• https://www.instagram.com/p/xxxxx/\n"
            "• https://www.instagram.com/reel/xxxxx/",
            parse_mode='HTML'
        )
        return

    progress_msg = await update.message.reply_text("🔄 Processing your request...")
    
    try:
        video_url, error = await get_video_link(url)

        if error:
            await progress_msg.edit_text(f"❌ <b>Download Failed</b>\n\n{error}", parse_mode='HTML')
            return

        await progress_msg.edit_text("✅ Video found! Sending...")

        # Video gönder
        try:
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=video_url,
                caption="✅ <b>Downloaded successfully!</b>\n\n💯 <i>Free & Unlimited!</i>",
                supports_streaming=True,
                parse_mode='HTML',
                read_timeout=300,  # 5 dakika
                connect_timeout=60,
                write_timeout=300,  # 5 dakika
                pool_timeout=60
            )
            
            await progress_msg.delete()
            
        except Exception as video_error:
            print(f"Video send error: {video_error}")
            # Video gönderilemezse, link olarak gönder
            await progress_msg.edit_text(
                f"📹 <b>Video Ready!</b>\n\n"
                f"<a href='{video_url}'>Click here to download</a>\n\n"
                f"💡 <i>If the video doesn't download automatically, "
                f"copy the link and paste it in your browser.</i>",
                parse_mode='HTML',
                disable_web_page_preview=False
            )
        
    except Exception as e:
        error_msg = str(e).lower()
        print(f"Error in handle_msg: {e}")
        
        if "file is too big" in error_msg:
            await progress_msg.edit_text(
                "❌ <b>File Too Large</b>\n\n"
                "The video file exceeds Telegram's 50MB limit.\n"
                "Please try a shorter video.",
                parse_mode='HTML'
            )
        elif "timeout" in error_msg:
            await progress_msg.edit_text(
                "⏱ <b>Request Timeout</b>\n\n"
                "The request took too long. Please try again.",
                parse_mode='HTML'
            )
        elif "bad request" in error_msg:
            await progress_msg.edit_text(
                "❌ <b>Invalid Video</b>\n\n"
                "The video link appears to be invalid or expired.",
                parse_mode='HTML'
            )
        else:
            await progress_msg.edit_text(
                "❌ <b>Processing Error</b>\n\n"
                "Please try again. If the problem persists:\n"
                "• Check if the account is private\n"
                "• Verify the post still exists\n"
                "• Make sure it's not a Story",
                parse_mode='HTML'
            )

# --- Uygulama Yaşam Döngüsü ve Webhook ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot_app
    
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
    
    bot_app = ApplicationBuilder().token(TOKEN).build()
    await bot_app.initialize()
    
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        print(f"📡 Webhook: {webhook_url}")
    else:
        print("⚠️ No WEBHOOK_URL provided, running in polling mode")
    
    await bot_app.start()
    
    print(f"🚀 Instagram Downloader Bot started!")
    print(f"💯 Status: FREE & UNLIMITED")
    print(f"🔧 Available APIs: {len(DOWNLOADER_APIS)}")
    
    yield
    
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

# Handler'ları ekle
def setup_handlers():
    if bot_app:
        bot_app.add_handler(CommandHandler("start", start_cmd))
        bot_app.add_handler(CommandHandler("help", start_cmd))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@app.post("/webhook")
async def webhook(request: Request):
    try:
        if not bot_app:
            return {"status": "error", "message": "Bot not initialized"}
            
        # İlk kez çağrılıyorsa handler'ları ekle
        if not bot_app.handlers:
            setup_handlers()
            
        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {
        "message": "Instagram Downloader Bot is running!",
        "status": "FREE & UNLIMITED",
        "available_apis": len(DOWNLOADER_APIS),
        "supported_formats": ["Posts", "Reels", "IGTV"]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": "2025-06-28"}

# Handler'ları başlangıçta ekle
setup_handlers()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
