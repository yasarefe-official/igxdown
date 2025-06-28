import os
import re
import aiohttp
import random
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- Ortam Değişkenleri ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# --- GÜNCELLENMİŞ VE ÇALIŞAN API'LER LİSTESİ ---
DOWNLOADER_APIS = [
    {
        "name": "InstaDownloader",
        "url": "https://instadownloader.co/ajax.php",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        "payload_key": "url"
    },
    {
        "name": "SnapSave",
        "url": "https://snapsave.app/action.php?lang=en",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        "payload_key": "url"
    },
    {
        "name": "SaveInsta",
        "url": "https://saveinsta.app/core/ajax.php",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        "payload_key": "url"
    },
    {
        "name": "IGDownloader",
        "url": "https://igdownloader.app/api/ajaxSearch",
        "method": "POST",
        "headers": {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        },
        "payload_key": "q"
    }
]

# --- Bot ve FastAPI Kurulumu ---
bot_app = ApplicationBuilder().token(TOKEN).build()
app = FastAPI()

def extract_video_from_html(html_content: str):
    """HTML içerikten video URL'sini çıkarır"""
    patterns = [
        r'href="(https?://[^"]*\.mp4[^"]*)"',
        r'"(https?://[^"]*\.mp4[^"]*)"',
        r'src="(https?://[^"]*\.mp4[^"]*)"',
        r'data-src="(https?://[^"]*\.mp4[^"]*)"',
        r'(https?://[^\s<>"\']*\.mp4[^\s<>"\']*)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        if matches:
            # En uzun URL'yi seç (genellikle daha kaliteli)
            return max(matches, key=len).replace("&amp;", "&")
    
    return None

async def get_video_link(url: str):
    """Farklı API'leri deneyerek video indirme linki bulmaya çalışır"""
    timeout_config = aiohttp.ClientTimeout(total=30)
    
    # API listesini karıştır
    random.shuffle(DOWNLOADER_APIS)

    for api in DOWNLOADER_APIS:
        try:
            print(f"Trying API: {api['name']}...")
            
            # Payload hazırla
            payload = {api['payload_key']: url}
            
            async with aiohttp.ClientSession(timeout=timeout_config) as session:
                async with session.post(
                    api['url'], 
                    data=payload, 
                    headers=api['headers']
                ) as response:
                    
                    if response.status != 200:
                        print(f"API '{api['name']}' returned status {response.status}")
                        continue

                    # Yanıtı al
                    try:
                        # JSON yanıt dene
                        data = await response.json()
                        
                        # JSON içinde HTML var mı kontrol et
                        if isinstance(data, dict):
                            for key in ['data', 'html', 'result', 'content']:
                                if key in data and isinstance(data[key], str):
                                    video_url = extract_video_from_html(data[key])
                                    if video_url:
                                        print(f"Success with {api['name']} (JSON-HTML)!")
                                        return video_url, None
                    except:
                        # JSON değilse HTML olarak işle
                        html_content = await response.text()
                        video_url = extract_video_from_html(html_content)
                        if video_url:
                            print(f"Success with {api['name']} (HTML)!")
                            return video_url, None
            
        except Exception as e:
            print(f"API '{api['name']}' failed: {str(e)[:100]}...")
            continue

    return None, "All download services are currently unavailable. Please try again later."

async def is_valid_video_url(url: str):
    """Video URL'sinin geçerli olup olmadığını kontrol eder"""
    try:
        timeout_config = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout_config) as session:
            async with session.head(url) as response:
                content_type = response.headers.get('content-type', '').lower()
                return response.status == 200 and ('video' in content_type or 'mp4' in content_type)
    except:
        return False

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎥 Instagram Video Downloader Bot\n\n"
        "Send me an Instagram post or reel link and I'll download the video for you!\n\n"
        "Example: https://www.instagram.com/p/xxxxx/"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Instagram URL kontrolü
    if not any(domain in url.lower() for domain in ['instagram.com', 'instagr.am']):
        await update.message.reply_text(
            "❌ Please provide a valid Instagram link.\n\n"
            "Example: https://www.instagram.com/p/xxxxx/"
        )
        return

    progress_msg = await update.message.reply_text("🔄 Processing your request...")
    
    try:
        video_url, error = await get_video_link(url)

        if error:
            await progress_msg.edit_text(f"❌ Failed to download.\n\nReason: {error}")
            return

        # Video URL'sinin geçerliliğini kontrol et
        await progress_msg.edit_text("🔄 Validating video link...")
        
        if not await is_valid_video_url(video_url):
            await progress_msg.edit_text("❌ The video link appears to be invalid or expired. Please try again.")
            return

        await progress_msg.edit_text("📤 Sending video...")

        # Video gönder
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=video_url,
            caption="✅ Video downloaded successfully!",
            supports_streaming=True,
            read_timeout=120, 
            connect_timeout=60,
            write_timeout=120
        )
        
        await progress_msg.delete()
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error in handle_msg: {error_msg}")
        
        if "file is too big" in error_msg.lower():
            await progress_msg.edit_text("❌ The video file is too large for Telegram. Please try a shorter video.")
        elif "timeout" in error_msg.lower():
            await progress_msg.edit_text("❌ Request timed out. The video might be too large or the server is busy.")
        else:
            await progress_msg.edit_text("❌ An error occurred while processing your request. Please try again later.")

# --- Uygulama Yaşam Döngüsü ve Webhook ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook"
    await bot_app.bot.set_webhook(url=webhook_url)
    await bot_app.start()
    print(f"🚀 Instagram Downloader Bot started! Webhook: {webhook_url}")
    yield
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

# Handler'ları ekle
bot_app.add_handler(CommandHandler("start", start_cmd))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))

@app.post("/webhook")
async def webhook(request: Request):
    try:
        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error"}

@app.get("/")
async def root():
    return {"message": "Instagram Downloader Bot is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
