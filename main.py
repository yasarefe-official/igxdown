import os
import re
import aiohttp
import random
import json
from contextlib import asynccontextmanager
from urllib.parse import urlparse, parse_qs

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")  # Opsiyonel RapidAPI anahtarı

# --- ÇALIŞAN API'LER LİSTESİ (2025 Güncel) ---
DOWNLOADER_APIS = [
    {
        "name": "InstagramAPI_Direct",
        "url": "https://www.instagram.com/api/v1/media/{}/info/",
        "method": "GET",
        "headers": {
            'User-Agent': 'Instagram 219.0.0.12.117 Android',
            'Accept': '*/*',
        },
        "type": "direct"
    },
    {
        "name": "RapidAPI_InstagramDownloader",
        "url": "https://instagram-api-media-downloader.p.rapidapi.com/media-info",
        "method": "GET",
        "headers": {
            'X-RapidAPI-Host': 'instagram-api-media-downloader.p.rapidapi.com',
            'X-RapidAPI-Key': RAPIDAPI_KEY
        },
        "type": "rapidapi",
        "enabled": bool(RAPIDAPI_KEY)
    },
    {
        "name": "SaveInsta_Alternative",
        "url": "https://api.saveinsta.app/",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        },
        "type": "alternative"
    },
    {
        "name": "InstagramDP_API",
        "url": "https://instagram-dp1.p.rapidapi.com/getdata",
        "method": "GET",
        "headers": {
            'X-RapidAPI-Host': 'instagram-dp1.p.rapidapi.com',
            'X-RapidAPI-Key': RAPIDAPI_KEY
        },
        "type": "rapidapi",
        "enabled": bool(RAPIDAPI_KEY)
    }
]

# --- Bot ve FastAPI Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

def extract_instagram_id(url: str):
    """Instagram URL'sinden post ID'sini çıkarır"""
    patterns = [
        r'/p/([A-Za-z0-9_-]+)/',
        r'/reel/([A-Za-z0-9_-]+)/',
        r'/tv/([A-Za-z0-9_-]+)/',
        r'instagram.com/([^/]+/)?p/([A-Za-z0-9_-]+)',
        r'instagram.com/([^/]+/)?reel/([A-Za-z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(-1)  # Son grubu döndür
    
    return None

def shortcode_to_media_id(shortcode: str):
    """Instagram shortcode'unu media ID'ye çevirir"""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0
    
    for char in shortcode:
        media_id = media_id * 64 + alphabet.index(char)
    
    return str(media_id)

async def get_video_from_rapidapi(api_config: dict, url: str):
    """RapidAPI servislerinden video indirme"""
    if not api_config.get("enabled", True):
        return None
        
    timeout_config = aiohttp.ClientTimeout(total=15)
    
    try:
        params = {"url": url}
        
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.get(
                api_config['url'],
                params=params,
                headers=api_config['headers']
            ) as response:
                
                if response.status == 200:
                    data = await response.json()
                    
                    # Farklı RapidAPI yanıt formatlarını kontrol et
                    video_url = None
                    if isinstance(data, dict):
                        video_url = (data.get('video_url') or 
                                   data.get('download_url') or 
                                   data.get('media_url') or
                                   data.get('url'))
                        
                        # Nested data kontrolü
                        if not video_url and 'data' in data:
                            video_url = data['data'].get('video_url')
                    
                    return video_url
                    
    except Exception as e:
        print(f"RapidAPI error for {api_config['name']}: {e}")
        
    return None

async def get_video_from_alternative(api_config: dict, url: str):
    """Alternatif API'lerden video indirme"""
    timeout_config = aiohttp.ClientTimeout(total=20)
    
    try:
        payload = {"url": url}
        
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.post(
                api_config['url'],
                json=payload,
                headers=api_config['headers']
            ) as response:
                
                if response.status == 200:
                    try:
                        data = await response.json()
                        
                        # Çeşitli yanıt formatlarını kontrol et
                        if isinstance(data, dict):
                            video_url = (data.get('video') or 
                                       data.get('download_url') or 
                                       data.get('media_url'))
                            
                            if video_url:
                                return video_url
                                
                    except:
                        # JSON değilse HTML olabilir
                        html = await response.text()
                        video_match = re.search(r'href="(https?://[^"]*\.mp4[^"]*)"', html)
                        if video_match:
                            return video_match.group(1).replace("&amp;", "&")
                            
    except Exception as e:
        print(f"Alternative API error for {api_config['name']}: {e}")
        
    return None

async def get_video_link(url: str):
    """Ana video indirme fonksiyonu"""
    
    # Instagram ID'sini çıkar
    instagram_id = extract_instagram_id(url)
    if not instagram_id:
        return None, "Invalid Instagram URL format."
    
    print(f"Extracted Instagram ID: {instagram_id}")
    
    # API'leri karıştır ve dene
    available_apis = [api for api in DOWNLOADER_APIS if api.get('enabled', True)]
    random.shuffle(available_apis)
    
    for api in available_apis:
        try:
            print(f"Trying API: {api['name']}...")
            
            video_url = None
            
            if api['type'] == 'rapidapi':
                video_url = await get_video_from_rapidapi(api, url)
            elif api['type'] == 'alternative':
                video_url = await get_video_from_alternative(api, url)
            elif api['type'] == 'direct':
                # Instagram direct API denemesi
                media_id = shortcode_to_media_id(instagram_id)
                direct_url = api['url'].format(media_id)
                
                timeout_config = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout_config) as session:
                    async with session.get(direct_url, headers=api['headers']) as response:
                        if response.status == 200:
                            data = await response.json()
                            if 'items' in data and data['items']:
                                item = data['items'][0]
                                if 'video_versions' in item:
                                    video_url = item['video_versions'][0]['url']
            
            if video_url and await is_valid_video_url(video_url):
                print(f"Success with {api['name']}!")
                return video_url, None
                
        except Exception as e:
            print(f"API '{api['name']}' failed: {str(e)[:100]}...")
            continue
    
    return None, "Unable to download video. The post might be private, deleted, or the services are temporarily unavailable."

async def is_valid_video_url(url: str):
    """Video URL'sinin geçerli olup olmadığını kontrol eder"""
    try:
        timeout_config = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.head(url) as response:
                content_type = response.headers.get('content-type', '').lower()
                content_length = int(response.headers.get('content-length', 0))
                
                return (response.status == 200 and 
                       ('video' in content_type or 'mp4' in content_type) and
                       content_length > 1000)  # En az 1KB olmalı
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
        "• High quality downloads\n"
        "• No watermarks\n"
        "• Fast processing\n"
        "• Multiple backup APIs\n\n"
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
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            caption="✅ <b>Downloaded successfully!</b>\n\n💡 <i>Share this bot with your friends!</i>",
            supports_streaming=True,
            parse_mode='HTML',
            read_timeout=180, 
            connect_timeout=60,
            write_timeout=180
        )
        
        await progress_msg.delete()
        
    except Exception as e:
        error_msg = str(e).lower()
        print(f"Error in handle_msg: {e}")
        
        if "file is too big" in error_msg:
            await progress_msg.edit_text(
                "❌ <b>File Too Large</b>\n\n"
                "The video file exceeds Telegram's size limit (50MB).\n"
                "Please try a shorter video.",
                parse_mode='HTML'
            )
        elif "timeout" in error_msg:
            await progress_msg.edit_text(
                "⏱ <b>Request Timeout</b>\n\n"
                "The request took too long. This might happen with very large videos.\n"
                "Please try again with a shorter video.",
                parse_mode='HTML'
            )
        elif "bad request" in error_msg:
            await progress_msg.edit_text(
                "❌ <b>Invalid Video</b>\n\n"
                "The video link appears to be invalid or the post might be private.",
                parse_mode='HTML'
            )
        else:
            await progress_msg.edit_text(
                "❌ <b>Processing Error</b>\n\n"
                "An unexpected error occurred. Please try again later.\n\n"
                "If the problem persists, the post might be:\n"
                "• Private account\n"
                "• Deleted post\n"
                "• Story (not supported)",
                parse_mode='HTML'
            )

# --- Uygulama Yaşam Döngüsü ve Webhook ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    
    api_status = "✅ RapidAPI Enabled" if RAPIDAPI_KEY else "⚠️ RapidAPI Disabled (add RAPIDAPI_KEY)"
    print(f"🚀 Instagram Downloader Bot started!")
    print(f"📡 Webhook: {webhook_url}")
    print(f"🔑 API Status: {api_status}")
    
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

# Handler'ları ekle
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(CommandHandler("help", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@app.post("/webhook")
async def webhook(request: Request):
    try:
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
        "status": "active",
        "rapidapi_enabled": bool(RAPIDAPI_KEY),
        "available_apis": len([api for api in DOWNLOADER_APIS if api.get('enabled', True)])
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": "2025-06-28"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
