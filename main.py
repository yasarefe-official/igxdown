# app.py
import os
import logging
from threading import Thread
from io import BytesIO

from flask import Flask, request, render_template, redirect, url_for
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters
import instaloader
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# --- Genel Ayarlar ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Ortam Değişkenleri ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL") # Koyeb'den aldığımız PostgreSQL URI'si
KOYEB_PUBLIC_URL = os.getenv("KOYEB_PUBLIC_URL")
SECRET_KEY = os.getenv("SECRET_KEY", "default-super-secret-key") # Flask için gizli anahtar

# --- Flask Uygulaması ---
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY

# --- Veritabanı Ayarları (SQLAlchemy) ---
Base = declarative_base()

class UserSession(Base):
    __tablename__ = 'user_sessions'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    insta_username = Column(String(100), nullable=False)
    session_data = Column(Text, nullable=False)

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine) # Tabloyu oluştur
Session = sessionmaker(bind=engine)
db_session = Session()

# --- Telegram Bot Ayarları ---
bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# --- Instaloader Fonksiyonları ---
def get_instaloader_for_user(telegram_id):
    user_record = db_session.query(UserSession).filter_by(telegram_id=telegram_id).first()
    if not user_record:
        return None, None

    L = instaloader.Instaloader(
        download_pictures=False, download_video_thumbnails=False,
        download_geotags=False, download_comments=False,
        save_metadata=False, compress_json=False
    )
    
    # Session verisini dosyaya yazmak yerine direkt olarak yükle
    try:
        session_file = BytesIO(user_record.session_data.encode('utf-8'))
        session_file.name = user_record.insta_username
        L.load_session_from_file(user_record.insta_username, session_file)
        logger.info(f"{user_record.insta_username} için oturum başarıyla yüklendi.")
        return L, user_record.insta_username
    except Exception as e:
        logger.error(f"Oturum yüklenemedi: {e}")
        return None, None

# --- Telegram Handler Fonksiyonları ---
def start(update: Update, context):
    user_id = update.effective_user.id
    user_record = db_session.query(UserSession).filter_by(telegram_id=user_id).first()

    if user_record:
        update.message.reply_text(f"Merhaba! Instagram hesabın ({user_record.insta_username}) zaten bağlı. Bana bir video linki gönderebilirsin.")
    else:
        auth_url = f"{KOYEB_PUBLIC_URL.rstrip('/')}{url_for('auth_page', user_id=user_id)}"
        update.message.reply_text(
            "Merhaba! Videoları indirebilmek için Instagram hesabını bağlaman gerekiyor.\n"
            f"Lütfen şu linke tıkla: {auth_url}"
        )

def download_video(update: Update, context):
    user_id = update.effective_user.id
    L, username = get_instaloader_for_user(user_id)

    if not L:
        update.message.reply_text("Lütfen önce /start komutu ile hesabınızı bağlayın.")
        return

    # ... (Buraya önceki kodumuzdaki video indirme mantığı gelecek) ...
    # ... `download_video` fonksiyonunun içeriğini buraya kopyalayın ...
    # ... Ve her yerde `L` nesnesini bu fonksiyondan gelen `L` ile kullanın ...
    update.message.reply_text("Video indirme özelliği şu an yapım aşamasında!")


# --- Flask Route'ları (Web Arayüzü) ---
@app.route('/auth', methods=['GET', 'POST'])
def auth_page():
    user_id = request.args.get('user_id')
    if not user_id:
        return "Geçersiz istek: kullanıcı ID'si bulunamadı.", 400

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        L = instaloader.Instaloader()
        try:
            L.login(username, password)
            
            # Oturumu bir dosyaya kaydet ve içeriğini oku
            session_filename = f"{username}"
            L.save_session_to_file(session_filename)
            
            with open(session_filename, 'r') as f:
                session_content = f.read()
            os.remove(session_filename) # Güvenlik için dosyayı sil
            
            # Veritabanına kaydet/güncelle
            user_record = db_session.query(UserSession).filter_by(telegram_id=user_id).first()
            if user_record:
                user_record.insta_username = username
                user_record.session_data = session_content
            else:
                new_session = UserSession(telegram_id=user_id, insta_username=username, session_data=session_content)
                db_session.add(new_session)
            
            db_session.commit()
            
            bot.send_message(chat_id=user_id, text=f"✅ Harika! '{username}' adlı Instagram hesabın başarıyla bağlandı.")
            return "Başarılı! Hesabınız bağlandı. Telegram'a dönebilirsiniz."

        except Exception as e:
            logger.error(f"Giriş hatası: {e}")
            return f"Giriş yapılamadı. Lütfen bilgileri kontrol edip tekrar deneyin. Hata: {e}", 401

    # `templates/auth.html` adında bir dosya oluşturmanız gerekecek.
    return render_template('auth.html', user_id=user_id)


@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'


# --- Ana Çalıştırma Bloğu ---
if __name__ == "__main__":
    # Bot ve webhook kurulumu
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, download_video))
    
    webhook_url = f"{KOYEB_PUBLIC_URL.rstrip('/')}/{TOKEN}"
    if bot.get_webhook_info().url != webhook_url:
        bot.set_webhook(url=webhook_url)

    logger.info("Bot ve Webhook ayarlandı.")
    
    # Flask uygulamasını production için Gunicorn'dan çalıştırın
    # Bu blok sadece lokal test için. Koyeb `gunicorn` kullanacak.
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
