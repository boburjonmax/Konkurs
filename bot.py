import logging
import random
import string
import io
import sqlite3
import csv
import os
from PIL import Image, ImageDraw, ImageFont
from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    KeyboardButton, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
from telegram.error import BadRequest

# --- SOZLAMALAR ---
TOKEN = "7695068578:AAGHYw38i6e8vPKv9YiQ4RvpAjrjOhVS4zs"
CHANNEL_1 = "@tsuebookclub"
CHANNEL_2 = "@MantiqLab"
CHANNEL_3 = "@Edu_Corner"
ADMIN_USER = "@okgoo"
BOT_USERNAME = "bookclub_konkurs_bot"
PHOTO_URL = "https://ibb.co/k2Hhm9P3"
ADMIN_ID = 1814162588

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MA'LUMOTLAR BAZASI (SQLite) ---
if os.path.exists('/app/data'):
    DB_PATH = '/app/data/konkurs.db'
    os.makedirs('/app/data', exist_ok=True)
else:
    DB_PATH = 'konkurs.db'
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT,
    referrer_id INTEGER,
    verified BOOLEAN DEFAULT 0,
    state TEXT
)
''')
conn.commit()

# --- DB YORDAMCHI FUNKSIYALAR ---

def db_get_user(user_id):
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone()

def db_add_user(user_id, referrer_id=None):
    try:
        cursor.execute('INSERT OR IGNORE INTO users (user_id, referrer_id, state) VALUES (?, ?, ?)', 
                       (user_id, referrer_id, 'check_sub'))
        conn.commit()
    except Exception as e:
        logger.error(f"DB Error add_user: {e}")

def db_update_state(user_id, state):
    cursor.execute('UPDATE users SET state = ? WHERE user_id = ?', (state, user_id))
    conn.commit()

def db_update_name(user_id, name):
    cursor.execute('UPDATE users SET name = ? WHERE user_id = ?', (name, user_id))
    conn.commit()

def db_update_phone(user_id, phone):
    cursor.execute('UPDATE users SET phone = ? WHERE user_id = ?', (phone, user_id))
    conn.commit()

def db_set_verified(user_id):
    cursor.execute('UPDATE users SET verified = 1, state = "registered" WHERE user_id = ?', (user_id,))
    conn.commit()

def db_get_top_users(limit=15):
    cursor.execute('''
        SELECT referrer_id, COUNT(*) as count 
        FROM users 
        WHERE verified = 1 
        AND referrer_id IS NOT NULL 
        AND referrer_id != ? 
        GROUP BY referrer_id 
        ORDER BY count DESC 
        LIMIT ?
    ''', (ADMIN_ID, limit))
    return cursor.fetchall()

def db_get_name(user_id):
    cursor.execute('SELECT name FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    return res[0] if res else "Noma'lum"

# --- CSV DAN DATABASE TIKLASH FUNKSIYASI (pandas siz) ---

def recover_database_from_csv(csv_file_path='users_list.csv'):
    """CSV fayldan SQLite database'ni to'liq tiklash (pandas siz)"""
    logger.info(f"📂 CSV fayldan database tiklash boshlandi: {csv_file_path}")
    
    if not os.path.exists(csv_file_path):
        logger.error(f"❌ CSV fayl topilmadi: {csv_file_path}")
        return False
    
    try:
        # Oldingi ma'lumotlarni tozalash
        cursor.execute('DELETE FROM users')
        
        # CSV faylni o'qish
        imported_count = 0
        error_count = 0
        
        with open(csv_file_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    # User ID ni olish
                    user_id = 0
                    if 'ID' in row:
                        user_id = int(row['ID'])
                    elif 'user_id' in row:
                        user_id = int(row['user_id'])
                    
                    if user_id == 0:
                        continue
                    
                    # Ism va telefon
                    name = row.get('Ism', row.get('name', '')).strip()
                    phone = row.get('Telefon', row.get('phone', '')).strip()
                    
                    # Verified field
                    verified_str = row.get('Tasdiqlangan', row.get('verified', '0'))
                    if isinstance(verified_str, str):
                        verified_str = verified_str.lower().strip()
                        verified = 1 if verified_str in ['true', '1', 'yes', 'ha', '✅', '✓'] else 0
                    else:
                        verified = int(verified_str) if verified_str else 0
                    
                    # Referrer field
                    referrer_str = row.get('Kim chaqirgan', row.get('referrer_id', ''))
                    referrer_id = None
                    
                    if referrer_str and str(referrer_str).strip() not in ['', 'None', '0', 'nan', 'NaN']:
                        try:
                            # Raqamli bo'lsa
                            if str(referrer_str).replace('.', '').isdigit():
                                referrer_id = int(float(referrer_str))
                            else:
                                referrer_id = None
                        except:
                            referrer_id = None
                    
                    # State aniqlash
                    state = 'registered' if verified else 'check_sub'
                    
                    # Database'ga qo'shish
                    cursor.execute('''
                        INSERT OR REPLACE INTO users 
                        (user_id, name, phone, referrer_id, verified, state)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (user_id, name, phone, referrer_id, verified, state))
                    
                    imported_count += 1
                    
                    if imported_count % 500 == 0:
                        logger.info(f"📊 {imported_count} ta foydalanuvchi import qilindi...")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Xato qatorda: {e}")
                    continue
        
        # Commit qilish
        conn.commit()
        
        # Statistikani olish
        cursor.execute('SELECT COUNT(*) FROM users')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM users WHERE verified=1')
        verified_count = cursor.fetchone()[0]
        
        logger.info(f"✅ IMPORT TUGADI!")
        logger.info(f"📊 Natijalar:")
        logger.info(f"   - Jami import qilingan: {imported_count}")
        logger.info(f"   - Xatolar soni: {error_count}")
        logger.info(f"   - Database'dagi jami: {total}")
        logger.info(f"   - Tasdiqlanganlar: {verified_count}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Tiklashda xatolik: {e}")
        return False
# Database ga yangi table qo'shing
cursor.execute('''
CREATE TABLE IF NOT EXISTS bot_messages (
    message_id INTEGER,
    chat_id INTEGER,
    user_id INTEGER,
    message_type TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (message_id, chat_id)
)
''')
conn.commit()

# Xabar yuborganida saqlash funksiyasi
async def save_bot_message(chat_id, message_id, user_id, message_type="text"):
    """Bot yuborgan xabarni saqlash"""
    try:
        cursor.execute('''
            INSERT INTO bot_messages (message_id, chat_id, user_id, message_type)
            VALUES (?, ?, ?, ?)
        ''', (message_id, chat_id, user_id, message_type))
        conn.commit()
    except Exception as e:
        logger.error(f"Xabarni saqlashda xato: {e}")

# Xabarlarni o'chirishda bu ID lardan foydalaning
# --- YORDAMCHI FUNKSIYALAR ---

def get_prizes_list():
    return [
        "5 kitob + Bunker + Surprise",
        "5 kitob + Mafia",
        "3 kitob + Bloknot + Uno",
        "3 kitob + Yangi yil surprise + bookmark",
        "3 kitob + Uno + bookmark",
        "3 kitob + bookmark",
        "2 kitob + 1 kg banan + bookmark",
        "2 kitob + bookmark",
        "2 kitob + bookmark",
        "2 kitob + bookmark",
        "60 000 so'm",
        "40 000 so'm",
        "1 kitob",
        "30 000 so'm",
        "20 000 so'm"
    ]

def generate_captcha_image():
    width, height = 280, 100
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    try:
        font = ImageFont.truetype("arial.ttf", 45)
    except:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(image)

    chars = string.ascii_uppercase + string.digits
    safe_chars = chars.replace('O', '').replace('0', '')
    text = ''.join(random.choice(safe_chars) for _ in range(5))

    for i, char in enumerate(text):
        x = 30 + i * 45 + random.randint(-5, 5)
        y = 25 + random.randint(-10, 10)
        draw.text((x, y), char, fill=(0, 0, 0), font=font)

    for _ in range(12):
        draw.line(((random.randint(0, width), random.randint(0, height)), 
                   (random.randint(0, width), random.randint(0, height))), 
                  fill=(120, 120, 120), width=2)
    
    bio = io.BytesIO()
    image.save(bio, 'PNG')
    bio.seek(0)
    bio.name = 'captcha.png'
    return bio, text

async def check_channels(user_id, context):
    channels = [CHANNEL_1, CHANNEL_2, CHANNEL_3]
    for channel in channels:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ['left', 'kicked']:
                return False
        except BadRequest:
            logger.error(f"Bot {channel} kanalida admin emas!")
            return False
        except Exception as e:
            logger.error(f"Kanal xato: {e}")
            return False
    return True

# ---------------------------------------------------------
#                 ADMIN BUYRUQLARI
# ---------------------------------------------------------

def is_admin(user):
    if user.username and f"@{user.username}" == ADMIN_USER:
        return True
    if user.id == ADMIN_ID:
        return True
    return False

# 1. /stat
async def admin_stat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE verified=1')
    verified = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(DISTINCT referrer_id) FROM users WHERE referrer_id IS NOT NULL')
    referrers = cursor.fetchone()[0]
    
    msg = (f"📊 **Bot Statistikasi:**\n\n"
           f"👥 Jami foydalanuvchilar: {total}\n"
           f"✅ Tasdiqlanganlar: {verified}\n"
           f"👤 Taklif qiluvchilar: {referrers}")
    await update.message.reply_text(msg, parse_mode='Markdown')

# 2. /xabar
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("❌ Xabar yo'q.\nMasalan: `/xabar Salom`", parse_mode='Markdown')
        return
    
    await update.message.reply_text("⏳ Xabar yuborish boshlandi...")
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    sent, blocked = 0, 0
    
    for row in users:
        try:
            await context.bot.send_message(chat_id=row[0], text=msg)
            sent += 1
        except Exception as e:
            logger.error(f"Xabar yuborishda xato user {row[0]}: {e}")
            blocked += 1
    
    await update.message.reply_text(f"✅ Tugadi.\n✅ Yuborildi: {sent}\n❌ Blok: {blocked}")

# 3. /export
async def admin_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    await update.message.reply_text("📂 Fayl tayyorlanmoqda...")
    cursor.execute('SELECT user_id, name, phone, verified, referrer_id FROM users')
    data = cursor.fetchall()
    
    file = io.StringIO()
    writer = csv.writer(file)
    writer.writerow(['ID', 'Ism', 'Telefon', 'Tasdiqlangan', 'Kim chaqirgan'])
    writer.writerows(data)
    file.seek(0)
    
    bio = io.BytesIO(file.getvalue().encode('utf-8'))
    bio.name = 'users_list.csv'
    await update.message.reply_document(document=bio, caption="📁 Barcha foydalanuvchilar")

# 4. /info
async def admin_check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    if not context.args:
        await update.message.reply_text("ID kiritilmadi.\nMasalan: `/info 123456789`", parse_mode='Markdown')
        return
    
    try:
        tid = int(context.args[0])
    except:
        await update.message.reply_text("❌ Noto'g'ri ID format")
        return
    
    u = db_get_user(tid)
    if not u:
        await update.message.reply_text("❌ Foydalanuvchi topilmadi")
        return
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE referrer_id = ? AND verified=1', (tid,))
    score = cursor.fetchone()[0]
    
    ref_by = "O'zi kirgan"
    if u[3]:
        r_user = db_get_user(u[3])
        if r_user: 
            ref_by = f"{r_user[1]} (ID: {u[3]})"
    
    msg = (f"👤 **Foydalanuvchi ma'lumotlari:**\n\n"
           f"🆔 ID: `{u[0]}`\n"
           f"📝 Ism: {u[1]}\n"
           f"📞 Telefon: {u[2]}\n"
           f"✅ Tasdiqlangan: {'Ha' if u[4] else 'Yoʻq'}\n"
           f"🏆 Ball: {score}\n"
           f"🔗 Kim chaqirgan: {ref_by}")
    
    await update.message.reply_text(msg, parse_mode='Markdown')

# 5. /delete
async def admin_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    if not context.args:
        await update.message.reply_text("ID kiritilmadi.\nMasalan: `/delete 123456789`", parse_mode='Markdown')
        return
    
    tid = context.args[0]
    cursor.execute('DELETE FROM users WHERE user_id = ?', (tid,))
    conn.commit()
    
    await update.message.reply_text(f"✅ ID {tid} bazadan o'chirildi.")

# 6. /top_file
async def admin_top_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    top = db_get_top_users(100)
    txt = "🏆 TOP 100 REYTING:\n\n"
    
    for i, (uid, cnt) in enumerate(top, 1):
        name = db_get_name(uid)
        txt += f"{i}. {name} (ID: {uid}) - {cnt} ball\n"
    
    bio = io.BytesIO(txt.encode('utf-8'))
    bio.name = 'top_reyting.txt'
    await update.message.reply_document(document=bio, caption="📈 To'liq reyting")

# 7. /backup
async def admin_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    await update.message.reply_text("📦 Baza fayli yuklanmoqda...")
    try:
        with open(DB_PATH, 'rb') as f:
            await update.message.reply_document(
                document=f, 
                filename=f"konkurs_backup.db", 
                caption="💾 Database backup"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")

# 8. /search
async def admin_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    if not context.args:
        await update.message.reply_text("Qidiruv so'zini yozing.\nMasalan: `/search Ali`", parse_mode='Markdown')
        return
    
    keyword = context.args[0]
    cursor.execute("SELECT user_id, name, phone FROM users WHERE name LIKE ? OR phone LIKE ?", 
                   (f'%{keyword}%', f'%{keyword}%'))
    results = cursor.fetchall()
    
    if not results:
        await update.message.reply_text("❌ Hech kim topilmadi.")
        return
    
    msg = "🔍 **Qidiruv natijalari:**\n\n"
    for row in results:
        msg += f"👤 {row[1]} (Tel: {row[2]}) → ID: `{row[0]}`\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

# 9. /post
async def admin_post_to_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("❌ Xabar matni yo'q.\nNamuna: `/post Diqqat! Yangilik!`", parse_mode='Markdown')
        return
    
    await update.message.reply_text("⏳ Kanallarga joylash boshlandi...")
    
    target_channels = [CHANNEL_1, CHANNEL_2, CHANNEL_3]
    sent_count = 0
    error_count = 0
    error_details = ""
    
    for channel in target_channels:
        try:
            await context.bot.send_message(chat_id=channel, text=msg)
            sent_count += 1
        except Exception as e:
            error_count += 1
            error_details += f"\n{channel}: {e}"
    
    report = f"✅ **Natija:**\n\n📢 Yuborildi: {sent_count} ta kanalga\n❌ Xatolik: {error_count} ta"
    if error_details:
        report += f"\n\nXatoliklar:{error_details}"
    
    await update.message.reply_text(report)

# 10. /recover - CSV dan database tiklash
async def admin_recover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    await update.message.reply_text("🔄 Database tiklash boshlandi...")
    
    # Faylni tekshirish
    csv_path = 'users_list.csv'
    if not os.path.exists(csv_path):
        await update.message.reply_text("❌ CSV fayl topilmadi. users_list.csv faylini yuklang.")
        return
    
    # Tiklash jarayoni
    success = recover_database_from_csv(csv_path)
    
    if success:
        await update.message.reply_text("✅ Database muvaffaqiyatli tiklandi!")
    else:
        await update.message.reply_text("❌ Database tiklashda xatolik!")

# 11. /stats_detailed - Batafsil statistika
async def admin_stats_detailed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    # Simple daily stats (without pandas)
    cursor.execute('''
        SELECT COUNT(*) as today_count
        FROM users 
        WHERE verified = 1 
        AND user_id > ?
    ''', (int((time.time() - 86400) * 1000000),))
    
    today_count = cursor.fetchone()[0]
    
    msg = "📊 **Batafsil statistika:**\n\n"
    msg += f"📅 Bugungi ro'yxatdan o'tishlar: {today_count}\n"
    
    # Eng faol referrerlar
    msg += "\n🏆 **TOP 10 Referrerlar:**\n"
    top_referrers = db_get_top_users(10)
    
    for i, (uid, cnt) in enumerate(top_referrers, 1):
        name = db_get_name(uid)
        msg += f"{i}. {name} - {cnt} ball\n"
    
    await update.message.reply_text(msg)

# 12. /send - Bitta userga shaxsiy xabar yuborish
async def admin_send_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    # Format: /send USER_ID Xabar matni
    # Masalan: /send 123456789 Salom, qalaysiz?
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format noto'g'ri.\n"
            "Namuna: `/send 123456789 Salom, bu shaxsiy xabar`",
            parse_mode='Markdown'
        )
        return
    
    try:
        target_id = int(context.args[0])
        message_text = " ".join(context.args[1:])
        
        await update.message.reply_text(f"⏳ Xabar yuborilmoqda user {target_id} ga...")
        
        # Xabar yuborish
        await context.bot.send_message(chat_id=target_id, text=message_text)
        
        # Foydalanuvchi nomini olish
        target_user = db_get_user(target_id)
        target_name = target_user[1] if target_user else "Noma'lum"
        
        await update.message.reply_text(
            f"✅ Xabar muvaffaqiyatli yuborildi!\n"
            f"👤 Kimga: {target_name} (ID: {target_id})\n"
            f"📝 Xabar: {message_text[:50]}..."
        )
        
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID format. ID raqam bo'lishi kerak.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")

# 13. /send_all - Hammaga, lekin progress bilan
async def admin_send_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text(
            "❌ Xabar matni yo'q.\n"
            "Namuna: `/send_all Yangi konkurs haqida!`",
            parse_mode='Markdown'
        )
        return
    
    await update.message.reply_text("⏳ Barchaga xabar yuborish boshlandi...")
    
    cursor.execute('SELECT user_id FROM users WHERE verified = 1')
    users = cursor.fetchall()
    total = len(users)
    
    if total == 0:
        await update.message.reply_text("❌ Hech qanday tasdiqlangan foydalanuvchi yo'q")
        return
    
    sent = 0
    blocked = 0
    errors = []
    
    # Progress xabari
    progress_msg = await update.message.reply_text(f"📤 Progress: 0/{total} (0%)")
    
    import asyncio
    import time
    
    start_time = time.time()
    
    for i, row in enumerate(users):
        user_id = row[0]
        
        try:
            await context.bot.send_message(chat_id=user_id, text=msg)
            sent += 1
            
            # Har 50 ta xabardan keyin progress yangilash
            if i % 50 == 0 or i == total - 1:
                percentage = (i + 1) / total * 100
                elapsed = time.time() - start_time
                eta = (elapsed / (i + 1)) * (total - i - 1) if i > 0 else 0
                
                try:
                    await progress_msg.edit_text(
                        f"📤 Progress: {i+1}/{total} ({percentage:.1f}%)\n"
                        f"✅ Yuborildi: {sent}\n"
                        f"❌ Blok: {blocked}\n"
                        f"⏱️ Qolgan vaqt: {eta/60:.1f} min"
                    )
                except:
                    pass
            
            # Har 30 ta xabardan keyin 1 soniya pauza (Telegram limiti uchun)
            if i % 30 == 0 and i > 0:
                await asyncio.sleep(1)
                
        except Exception as e:
            blocked += 1
            errors.append(f"User {user_id}: {str(e)[:50]}")
    
    # Yakuniy hisobot
    elapsed_time = time.time() - start_time
    
    report = (f"✅ **Xabar yuborish tugadi!**\n\n"
              f"📊 **Natijalar:**\n"
              f"👥 Jami: {total} ta\n"
              f"✅ Yuborildi: {sent} ta\n"
              f"❌ Blok: {blocked} ta\n"
              f"⏱️ Vaqt: {elapsed_time/60:.1f} minut\n"
              f"📈 Muvaffaqiyat: {sent/total*100:.1f}%")
    
    if errors:
        report += f"\n\n❌ **Xatolar ({min(5, len(errors))} ta):**\n" + "\n".join(errors[:5])
    
    await update.message.reply_text(report, parse_mode='Markdown')

# 14. /send_group - Guruhga xabar yuborish (bir necha ID ga)
async def admin_send_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    # Format: /send_group ID1 ID2 ID3 Xabar matni
    # Masalan: /send_group 123 456 789 Test xabar
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Format noto'g'ri.\n"
            "Namuna: `/send_group 123 456 789 Salom, guruh!`",
            parse_mode='Markdown'
        )
        return
    
    # ID larni ajratish
    ids = []
    message_parts = []
    
    for arg in context.args:
        if arg.isdigit():
            ids.append(int(arg))
        else:
            # Birinchi non-digit qismdan keyin hammasi xabar
            message_start = context.args.index(arg)
            message_parts = context.args[message_start:]
            break
    
    if not ids or not message_parts:
        await update.message.reply_text("❌ ID lar yoki xabar yo'q")
        return
    
    message_text = " ".join(message_parts)
    
    await update.message.reply_text(f"⏳ {len(ids)} ta userga xabar yuborilmoqda...")
    
    sent = 0
    failed = 0
    results = []
    
    for user_id in ids:
        try:
            # Foydalanuvchi borligini tekshirish
            user = db_get_user(user_id)
            if not user:
                results.append(f"❌ {user_id}: Bazada yo'q")
                failed += 1
                continue
            
            await context.bot.send_message(chat_id=user_id, text=message_text)
            results.append(f"✅ {user_id}: {user[1]}")
            sent += 1
            
        except Exception as e:
            results.append(f"❌ {user_id}: {str(e)[:30]}")
            failed += 1
    
    # Natijalarni chiqarish
    report = (f"📊 **Guruh xabari natijalari:**\n\n"
              f"✅ Yuborildi: {sent} ta\n"
              f"❌ Xatolik: {failed} ta\n\n"
              f"**Batafsil:**\n")
    
    for result in results[:20]:  # Faqat 20 tasini ko'rsatish
        report += result + "\n"
    
    if len(results) > 20:
        report += f"\n... va yana {len(results)-20} ta"
    
    await update.message.reply_text(report)

# 15. /active - Faqat aktiv (oxirgi 7 kun) foydalanuvchilarga
async def admin_send_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("❌ Xabar yo'q. `/active Xabar matni`", parse_mode='Markdown')
        return
    
    # Oxirgi 7 kun ichida ro'yxatdan o'tganlar (qiyinchilik uchun oddiy versiya)
    # Agar sizda registration_date ustuni bo'lsa, uni qo'shing
    cursor.execute('''
        SELECT user_id FROM users 
        WHERE verified = 1 
        ORDER BY user_id DESC 
        LIMIT 500  # Oxirgi 500 tasi
    ''')
    
    users = cursor.fetchall()
    
    if not users:
        await update.message.reply_text("❌ Faol foydalanuvchilar topilmadi")
        return
    
    await update.message.reply_text(f"⏳ {len(users)} ta faol userga xabar yuborilmoqda...")
    
    sent = 0
    blocked = 0
    
    for i, row in enumerate(users):
        try:
            await context.bot.send_message(chat_id=row[0], text=msg)
            sent += 1
            
            # Progress
            if i % 100 == 0:
                await update.message.reply_text(f"📤 {i+1}/{len(users)} yuborildi...")
                
        except:
            blocked += 1
    
    await update.message.reply_text(
        f"✅ Faol foydalanuvchilarga xabar yuborish tugadi!\n"
        f"✅ Yuborildi: {sent}\n"
        f"❌ Blok: {blocked}"
    )

# 16. /delete_last - Botning oxirgi xabarlarini o'chirish
async def admin_delete_last_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botning oxirgi yuborgan xabarlarini o'chirish"""
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    try:
        # Nechta xabarni o'chirish kerakligini aniqlash
        count = 1  # default: 1 ta xabar
        if context.args:
            try:
                count = int(context.args[0])
                if count < 1:
                    count = 1
                if count > 50:  # Limit qo'yish
                    count = 50
            except ValueError:
                await update.message.reply_text("❌ Noto'g'ri son format. Masalan: `/delete_last 5`", parse_mode='Markdown')
                return
        
        await update.message.reply_text(f"⏳ Botning oxirgi {count} ta xabarini o'chirish...")
        
        # Context ni tekshirish va xabarlarni o'chirish
        deleted_count = 0
        
        # G'ayritabiiy faollikni aniqlash
        user_id = update.effective_user.id
        user = db_get_user(user_id)
        
        # Agar user ro'yxatdan o'tgan va tasdiqlangan bo'lsa
        if user and user[4]:  # verified=1
            # Bot yuborgan oxirgi xabarlarni o'chirish
            try:
                # Context orqali oxirgi xabarlarni olish va o'chirish
                chat_id = update.effective_chat.id
                
                # Oxirgi count ta xabarni o'chirish
                for i in range(count):
                    try:
                        # Bu faqat bot yuborgan xabarlar uchun ishlaydi
                        # Siz botning ID sini olishingiz kerak
                        bot_info = await context.bot.get_me()
                        bot_id = bot_info.id
                        
                        # Oxirgi xabarlarni olish (oddiy implementatsiya)
                        # Yaxshiroq versiya uchun oxirgi xabarlarni saqlash kerak
                        await context.bot.delete_message(
                            chat_id=chat_id,
                            message_id=update.message.message_id - i - 1
                        )
                        deleted_count += 1
                        
                    except Exception as e:
                        logger.error(f"Xabarni o'chirishda xato: {e}")
                        break
                
                await update.message.reply_text(f"✅ {deleted_count} ta xabar o'chirildi")
                
                # Log yozish
                logger.warning(f"Admin {update.effective_user.id} botning {deleted_count} ta xabarini o'chirdi")
                
            except Exception as e:
                logger.error(f"Xabarlarni o'chirishda xato: {e}")
                await update.message.reply_text(f"❌ Xatolik: {str(e)[:100]}")
        else:
            await update.message.reply_text("❌ Siz admin emassiz yoki tasdiqlanmagansiz")
            
    except Exception as e:
        logger.error(f"Admin delete_last da xato: {e}")
        await update.message.reply_text("❌ Xatolik yuz berdi")

# 17. /block_spam - Spam yuborgan userni bloklash
async def admin_block_spam_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Spam yuborgan userni bloklash va xabarlarini o'chirish"""
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ ID kiritilmadi.\n"
            "Masalan: `/block_spam 123456789`\n"
            "Yoki: `/block_spam 123456789 10` (10 ta xabarini o'chirish)",
            parse_mode='Markdown'
        )
        return
    
    try:
        spam_user_id = int(context.args[0])
        delete_count = int(context.args[1]) if len(context.args) > 1 else 20
        
        if delete_count > 100:
            delete_count = 100
        
        await update.message.reply_text(
            f"⚠️ User {spam_user_id} ni bloklash va {delete_count} ta xabarini o'chirish..."
        )
        
        # 1. Avval xabarlarni o'chirish
        deleted_messages = 0
        
        # Bu yerda bot yuborgan xabarlar ID larini saqlash kerak
        # Lekin oddiy versiyada:
        try:
            # User bazadan o'chirish
            cursor.execute('DELETE FROM users WHERE user_id = ?', (spam_user_id,))
            conn.commit()
            
            # Log yozish
            logger.warning(f"Admin {update.effective_user.id} user {spam_user_id} ni blokladi va o'chirdi")
            
            await update.message.reply_text(
                f"✅ User {spam_user_id} bloklandi va bazadan o'chirildi\n"
                f"⚠️ Xabarlarni o'chirish uchun kanal admini bo'lishingiz kerak"
            )
            
        except Exception as e:
            logger.error(f"Bloklashda xato: {e}")
            await update.message.reply_text(f"❌ Xatolik: {str(e)[:100]}")
            
    except ValueError:
        await update.message.reply_text("❌ Noto'g'ri ID format")


# 18. /security - Xavfsizlik sozlamalari
async def admin_security_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xavfsizlik sozlamalari"""
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("🛡️ Aktiv foydalanuvchilar", callback_data="security_active"),
            InlineKeyboardButton("🚫 Bloklanganlar", callback_data="security_blocked")
        ],
        [
            InlineKeyboardButton("📊 Oxirgi faollik", callback_data="security_activity"),
            InlineKeyboardButton("⚙️ Sozlamalar", callback_data="security_settings")
        ]
    ]
    
    await update.message.reply_text(
        "🛡️ **Xavfsizlik paneli:**\n\n"
        "1. Aktiv foydalanuvchilar ro'yxati\n"
        "2. Bloklangan userlar\n"
        "3. Oxirgi 1 soatdagi faollik\n"
        "4. Xavfsizlik sozlamalari",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )



# ---------------------------------------------------------
#                 ASOSIY BOT FUNKSIYALARI
# ---------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    args = context.args

    db_user = db_get_user(user_id)

    if not db_user:
        referrer_id = None
        if args and args[0].startswith('ref_'):
            try:
                ref_id = int(args[0].split('_')[1])
                if ref_id != user_id:
                    ref_user_exists = db_get_user(ref_id)
                    if ref_user_exists:
                        referrer_id = ref_id
            except:
                pass
        
        db_add_user(user_id, referrer_id)
        db_user = db_get_user(user_id)

    # Agar ro'yxatdan o'tgan bo'lsa
    if db_user and db_user[4]: 
        if await check_channels(user_id, context):
            await show_main_menu(update, context)
            return
    
    await send_subscription_message(update)

async def send_subscription_message(update):
    keyboard = [
        [InlineKeyboardButton("📢 BookClub", url=f"https://t.me/{CHANNEL_1.lstrip('@')}")],
        [InlineKeyboardButton("📢 MantiqLab", url=f"https://t.me/{CHANNEL_2.lstrip('@')}")],
        [InlineKeyboardButton("📢 Edu Corner", url=f"https://t.me/{CHANNEL_3.lstrip('@')}")],
        [InlineKeyboardButton("✅ A'zo bo'ldim", callback_data="check_subscription")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"👋 Salom {update.effective_user.first_name}!\n\n"
        "🎁 Konkurs aksiyasida qatnashing va ajoyib hadyalar yuting!\n\n"
        "Aksiyada ishtirok etish uchun quyidagi kanallarga obuna bo'ling:"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if await check_channels(user_id, context):
        db_user = db_get_user(user_id)
        if db_user and db_user[4]: 
            await query.delete_message()
            await query.message.reply_text("✅ Obuna qayta tasdiqlandi. Davom etishingiz mumkin.")
            await show_main_menu(update, context)
        else:
            db_update_state(user_id, 'awaiting_name')
            await query.delete_message()
            await query.message.reply_text("✅ Rahmat! A'zolik tasdiqlandi.\n\nIltimos, Ismingizni yozib yuboring:")
    else:
        await query.answer("❌ Hali to'liq obuna bo'lmadingiz. Iltimos, barcha kanallarga a'zo bo'ling!", show_alert=True)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    user_id = update.effective_user.id
    text = update.message.text
    db_user = db_get_user(user_id)
    
    if not db_user:
        await start(update, context)
        return

    user_state = db_user[5]
    is_verified = db_user[4]

    # 1. Ismni qabul qilish
    if user_state == 'awaiting_name':
        if len(text) < 2:
            await update.message.reply_text("❌ Ism juda qisqa. Iltimos, to'liq ismingizni yozing:")
            return
        
        db_update_name(user_id, text)
        db_update_state(user_id, 'awaiting_phone')
        
        btn = [[KeyboardButton("📞 Telefon raqamni ulashish", request_contact=True)]]
        kb = ReplyKeyboardMarkup(btn, resize_keyboard=True, one_time_keyboard=True)
        
        await update.message.reply_text(
            f"Rahmat {text}! 👍\n\nIltimos, telefon raqamingizni quyidagi tugma orqali ulashish:",
            reply_markup=kb
        )
        return

    # 2. Captcha
    if user_state == 'awaiting_captcha':
        correct_answer = context.user_data.get('captcha_answer')
        if text.upper() == correct_answer:
            await complete_registration(update, context)
        else:
            await update.message.reply_text("❌ Javob noto'g'ri. Iltimos, qayta urinib ko'ring:")
            await send_captcha(update, context)
        return

    # 3. Asosiy Menyu
    if is_verified:
        if not await check_channels(user_id, context):
            await update.message.reply_text("⚠️ Diqqat! Siz kanallardan chiqib ketgansiz.")
            await send_subscription_message(update)
            return

        if text == "💠 Do'stlarni taklif qilish":
            await send_invite_info(update, context)
        elif text == "🏆 Reyting":
            await send_rating(update, context)
        elif text == "ℹ️ Yordam":
            await send_help(update, context)
        else:
            await show_main_menu(update, context)

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = db_get_user(user_id)
    
    if db_user and db_user[5] == 'awaiting_phone':
        contact = update.message.contact

        # Birovning raqamini bloklash
        if contact.user_id and contact.user_id != user_id:
            await update.message.reply_text(
                "❌ Iltimos, faqat o'zingizning telefon raqamingizni yuboring!\n"
                "Pastdagi 📱 tugmani bosing."
            )
            return

        # Raqamni olish
        phone = contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone 

        # Faqat O'zbekiston raqamlari (+998)
        if not phone.startswith('+998'):
            await update.message.reply_text(
                "❌ Kechirasiz, konkursda faqat O'zbekiston (+998) raqamlari qatnashishi mumkin."
            )
            return

        # Bu raqam oldin ishlatilganmi?
        cursor.execute('SELECT user_id FROM users WHERE phone = ?', (phone,))
        existing_user = cursor.fetchone()

        if existing_user and existing_user[0] != user_id:
            await update.message.reply_text(
                "❌ Bu telefon raqam allaqachon ro'yxatdan o'tgan!"
            )
            return

        # Hammasi yaxshi
        db_update_phone(user_id, phone)
        db_update_state(user_id, 'awaiting_captcha')
        
        await update.message.reply_text("✅ Raqam qabul qilindi", reply_markup=ReplyKeyboardRemove())
        await send_captcha(update, context)

async def send_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    img_byte, text = generate_captcha_image()
    context.user_data['captcha_answer'] = text
    await update.message.reply_photo(
        photo=img_byte,
        caption="🤖 Bot emasligingizni tasdiqlash uchun rasmda ko'rgan matnni yuboring:"
    )

async def complete_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_user = update.effective_user
    
    # Bazada tasdiqlangan deb belgilash
    db_set_verified(user_id)
    
    # Taklif qilgan odamga xabar
    db_user = db_get_user(user_id)
    referrer_id = db_user[3]
    
    if referrer_id:
        invited_name = db_user[1]
        invited_username = f"@{current_user.username}" if current_user.username else ""
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"👏 Tabriklaymiz! {invited_name} {invited_username} do'stingizni taklif qildingiz!"
            )
        except Exception as e:
            logger.error(f"Referrerga xabar yuborishda xato: {e}")

    # Tabrik xabari
    await update.message.reply_text(
        "✅ Tabriklaymiz! Siz muvaffaqiyatli ro'yxatdan o'tdingiz!\n"
        "Quyida sizning maxsus havolangiz va yutuqlar ro'yxati 👇"
    )

    # Rasm va link chiqarish
    await send_invite_info(update, context)

    # Asosiy menyuni ko'rsatish
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        message_func = update.callback_query.message.reply_text
    else:
        message_func = update.message.reply_text

    keyboard = [
        [KeyboardButton("💠 Do'stlarni taklif qilish")],
        [KeyboardButton("🏆 Reyting"), KeyboardButton("ℹ️ Yordam")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await message_func("📱 Bosh Menu:", reply_markup=markup)

async def send_invite_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    msg_text = f"""#diqqat_konkurs

🚀 BookLabEduMen tomonidan tashkil etilgan super konkursda ishtirok eting va kitoblar, stol o'yinlar hamda pul mukofotlaridan birini qo'lga kiriting!

✅ G'oliblar 20.12.2025 21:00 da e'lon qilinadi.
Viktorinada ishtirok etish👇
{ref_link}"""

    # Linkni toza qilib yozish
    share_url = f"https://t.me/share/url?url={ref_link}"
    kb = [[InlineKeyboardButton("🔗 Linkni ulashish", url=share_url)]]
    
    try:
        await update.message.reply_photo(
            photo=PHOTO_URL,
            caption=msg_text,
            reply_markup=InlineKeyboardMarkup(kb)
        )
    except Exception as e:
        logger.error(f"Rasmda xato: {e}")
        await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(kb))

async def send_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_users = db_get_top_users(15)
    prizes = get_prizes_list()
    
    text = "🏆 **Reyting (TOP 15):**\n\n"

    if not top_users:
        text += "Hozircha natijalar yo'q."
    else:
        for idx, (uid, count) in enumerate(top_users, 1):
            name = db_get_name(uid)
            if len(name) > 20:
                name = name[:20] + "..."
            
            if idx <= len(prizes):
                prize = prizes[idx - 1]
                prize_text = f"🎁 ({prize})"
            else:
                prize_text = ""

            text += f"{idx}-o'rin: {name} — {count} ball {prize_text}\n"

    await update.message.reply_text(text)

async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🤖 **Bot haqida:**

📌 Bu bot orqali siz konkursda ishtirok etishingiz va do'stlaringizni taklif qilishingiz mumkin.

📌 Har bir taklif qilgan do'stingiz uchun sizga ball beriladi.

📌 Eng ko'p ball to'plagan 15 ta g'olib mukofotlarga ega bo'ladi.

📌 Admin bilan bog'lanish: @okgoo

📌 Yordam kerak bo'lsa, /start ni bosing."""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ---------------------------------------------------------
#                 MAIN FUNCTION
# ---------------------------------------------------------

import time  # Import qo'shing

def main():
    # Database tiklashni tekshirish
    csv_path = 'users_list.csv'
    if os.path.exists(csv_path):
        logger.info("📂 CSV fayl topildi, database tiklash...")
        success = recover_database_from_csv(csv_path)
        if success:
            logger.info("✅ Database muvaffaqiyatli tiklandi")
        else:
            logger.warning("❌ Database tiklashda muammo")
    
    # Botni ishga tushirish
    application = Application.builder().token(TOKEN).build()

    # Start handler
    application.add_handler(CommandHandler("start", start))
    
    # Admin handlers (TO'G'RI VERSIYA)
    admin_commands = [
        ("stat", admin_stat),
        ("xabar", admin_broadcast),
        ("export", admin_export),
        ("info", admin_check_user),
        ("delete", admin_delete_user),
        ("top_file", admin_top_file),
        ("backup", admin_backup),
        ("search", admin_search),
        ("post", admin_post_to_channels),
        ("recover", admin_recover),
        ("stats_detailed", admin_stats_detailed),
        
        # --- YANGI FUNKSIYALAR ---
        ("send", admin_send_message),           # /send
        ("send_all", admin_send_all),           # /send_all  
        ("send_group", admin_send_group),       # /send_group
        ("active", admin_send_active),          # /active
        # -------------------------
        
        ("admin", admin_stat)  # /admin ham /stat kabi ishlaydi
         # --- XAVFSIZLIK FUNKSIYALARI ---
        ("delete_last", admin_delete_last_messages),    # /delete_last [count]
        ("block_spam", admin_block_spam_user),          # /block_spam user_id [count]
        ("security", admin_security_settings),          # /security
        ("clean", admin_delete_last_messages),          # /clean - qisqa nom
    ]
    
    for cmd, func in admin_commands:
        application.add_handler(CommandHandler(cmd, func))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_subscription$"))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Error handler
    application.add_error_handler(lambda update, context: logger.error(f"Error: {context.error}"))
    
    # Ishga tushirish
    logger.info("🤖 Bot ishga tushdi...")
    application.run_polling()

if __name__ == "__main__":
    main()



