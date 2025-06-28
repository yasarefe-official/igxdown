import os
import logging
from threading import Thread
from io import BytesIO
from uuid import uuid4

# --- Web Framework ve Sunucu ---
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# --- Telegram Bot Kütüphanesi ---
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext

# --- Veritabanı (SQLAlchemy) ---
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base

# --- Instagram İndirici ---
import instaloader

# --- TEMEL AYARLAR ---
# Logging ayarlarını en başa alarak her şeyi görebilmemizi sağlıyoruz.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ORTAM DEĞİŞKENLERİNİ OKUMA ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
KOYEB_PUBLIC_URL = os.getenv("KOYEB_PUBLIC_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "bir-varsayilan-gizli-anahtar-ekleyin")

# --- ORTAM DEĞİŞKENLERİ TEŞHİSİ ---
# Uygulama başlamadan önce kritik değişkenlerin durumunu kontrol edelim.
logger.info("--- ORTAM DEĞİŞKENLERİ KONTROL EDİLİYOR ---")
logger.info(f"TELEGRAM_TOKEN ayarlı mı? -> {bool(TELEGRAM_TOKEN)}")
logger.info(f"KOYEB_PUBLIC_URL ayarlı mı? -> {bool(KOYEB_PUBLIC_URL)}")
if DATABASE_URL:
    logger.info("DATABASE_URL ayarlı. Başlangıcı: %s...", DATABASE_URL[:30])
else:
    # Eğer bu logu görüyorsanız, Koyeb'de DATABASE_URL değişkeni ya yok ya da boş.
    logger.error("!!! KRİTİK HATA: DATABASE_URL ORTAM DEĞİŞKENİ BULUNAMADI !!!")
logger.info("--- KONTROL TAMAMLANDI ---")

if not all([TELEGRAM_TOKEN, DATABASE_URL, KOYEB_PUBLIC_URL]):
    logger.critical("Gerekli ortam değişkenleri eksik. Uygulama başlatılamıyor.")
    exit()

# --- VERİTABANI KURULUMU (SQLAlchemy) ---
Base = declarative_base()

class UserSession(Base):
    __tablename__ = 'user_sessions'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False) # String olarak saklamak daha güvenli
    insta_username = Column(String(100), nullable=False)
    session_data = Column(Text, nullable=False)

try:
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Veritabanı bağlantısı ve tablo kontrolü başarılı.")
except Exception as e:
    logger.critical(f"Veritabanı bağlantısı kurulamadı: {e}", exc_info=True)
    exit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FastAPI UYGULAMASI VE TEMPLATE KURULUMU ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- TELEGRAM BOTU KURULUMU ---
bot = Bot(token=TELEGRAM_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# --- INSTALOADER YARDIMCI FONKSİYONU ---
def get_instaloader_for_user(db_session: Session, telegram_id: str):
    user_record = db_session.query(UserSession).filter_by(telegram_id=str(telegram_id)).first()
    if not user_record:
        return None, None

    L = instaloader.Instaloader(
        download_pictures=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False,
        save_metadata=False, compress_json=False
    )
    
    try:
        session_file = BytesIO(user_record.session_data.encode('utf-8'))
        session_file.name = user_record.insta_username
        L.load_session_from_file(user_record.insta_username, session_file)
        logger.info(f"{user_record.insta_username} için oturum başarıyla yüklendi.")
        return L, user_record.insta_username
    except Exception as e:
        logger.error(f"Kullanıcı {telegram_id} için oturum yüklenemedi: {e}")
        return None, None

# --- TELEGRAM HANDLER'LARI ---
def start_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    auth_url = f"{KOYEB_PUBLIC_URL.rstrip('/')}/auth?user_id={user_id}"
    message = (
        "Merhaba! 👋\n"
        "Instagram videolarını indirebilmek için hesabını güvenli bir şekilde bağlaman gerekiyor.\n\n"
        f"Lütfen şu linke tıkla ve giriş yap: {auth_url}\n\n"
        "Not: Güvenliğiniz için bu botla kullanmak üzere yeni bir Instagram hesabı açmanızı öneririz."
    )
    update.message.reply_html(message)

def download_video_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    db = SessionLocal()
    L, username = get_instaloader_for_user(db, str(user_id))
    db.close()

    if not L:
        update.message.reply_text("Lütfen önce /start komutu ile hesabınızı bağlayın.")
        return

    url = update.message.text
    msg = update.message.reply_text("Video indiriliyor, lütfen bekleyin... ⏳")

    try:
        shortcode = url.split("/")[-2]
        post = instaloader.Post.from_shortcode(L.context, shortcode)

        # İndirme için geçici ve benzersiz bir klasör
        target_dir = f"temp_{uuid4()}"
        L.download_post(post, target=target_dir)

        video_path = None
        for filename in os.listdir(target_dir):
            if filename.endswith('.mp4'):
                video_path = os.path.join(target_dir, filename)
                break
        
        if video_path:
            with open(video_path, 'rb') as video_file:
                context.bot.send_video(chat_id=user_id, video=video_file, caption=f"İndiren: @{username}", supports_streaming=True)
            msg.edit_text("İşte videon! ✅")
        else:
            msg.edit_text("Bir hata oluştu, video dosyası bulunamadı. 😕")
            
    except Exception as e:
        logger.error(f"Video indirme hatası: {e}", exc_info=True)
        msg.edit_text(f"Üzgünüm, bir hata oluştu. Linkin doğru olduğundan emin misin?\nHata: {str(e)}")
    finally:
        # Temizlik
        if 'target_dir' in locals() and os.path.exists(target_dir):
            for f in os.listdir(target_dir):
                os.remove(os.path.join(target_dir, f))
            os.rmdir(target_dir)

# --- FastAPI ROUTE'LARI (WEB ARAYÜZÜ) ---
@app.post(f'/{TELEGRAM_TOKEN}')
async def process_telegram_update(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return {"status": "ok"}

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request, user_id: str):
    return templates.TemplateResponse("auth.html", {"request": request, "user_id": user_id})

@app.post("/login")
async def handle_login(
    user_id: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    L = instaloader.Instaloader()
    try:
        L.login(username, password)
        
        session_filename = f"{username}"
        L.save_session_to_file(session_filename)
        
        with open(session_filename, 'r') as f:
            session_content = f.read()
        os.remove(session_filename)

        user_record = db.query(UserSession).filter_by(telegram_id=str(user_id)).first()
        if user_record:
            user_record.insta_username = username
            user_record.session_data = session_content
        else:
            new_session = UserSession(telegram_id=str(user_id), insta_username=username, session_data=session_content)
            db.add(new_session)
        
        db.commit()

        bot.send_message(chat_id=user_id, text=f"✅ Harika! '{username}' adlı Instagram hesabın başarıyla bağlandı.")
        return HTMLResponse(content="<h1>Başarılı!</h1><p>Hesabınız bağlandı. Artık Telegram'a dönebilirsiniz.</p>", status_code=200)

    except Exception as e:
        logger.error(f"Instagram giriş hatası ({username}): {e}")
        error_message = "<h1>Giriş Başarısız!</h1><p>Kullanıcı adı veya şifre yanlış. Lütfen bilgileri kontrol edip tekrar deneyin.</p>"
        return HTMLResponse(content=error_message, status_code=401)


# --- UYGULAMA BAŞLANGIÇ NOKTASI ---
@app.on_event("startup")
async def on_startup():
    # Telegram webhook'unu ayarla
    webhook_url = f"{KOYEB_PUBLIC_URL.rstrip('/')}/{TELEGRAM_TOKEN}"
    current_webhook = await bot.get_webhook_info()
    if current_webhook.url != webhook_url:
        await bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook ayarlandı: {webhook_url}")
    else:
        logger.info("Webhook zaten doğru şekilde ayarlanmış.")

    # Telegram handler'larını dispatcher'a ekle
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, download_video_handler))
    logger.info("Telegram handler'ları eklendi.")
    logger.info("Uygulama başarıyla başlatıldı ve istekleri dinlemeye hazır.")
