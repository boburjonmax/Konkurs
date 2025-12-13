import logging
import random
import string
import io
import sqlite3
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
CHANNEL_3 = "@kinomen_2025"   # <-- Yangi kanal
CHANNEL_4 = "@Edu_Corner"  # <-- Yangi kanal

ADMIN_USER = "@okgoo"
BOT_USERNAME = "bookclub_konkurs_bot"

# Rasmning to'g'ridan-to'g'ri linki
PHOTO_URL = "https://ibb.co/k2Hhm9P3"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MA'LUMOTLAR BAZASI (SQLite) ---
conn = sqlite3.connect('konkurs.db', check_same_thread=False)
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
        WHERE verified = 1 AND referrer_id IS NOT NULL 
        GROUP BY referrer_id 
        ORDER BY count DESC 
        LIMIT ?
    ''', (limit,))
    return cursor.fetchall()

def db_get_name(user_id):
    cursor.execute('SELECT name FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    return res[0] if res else "Noma'lum"

# --- YORDAMCHI FUNKSIYALAR ---

def get_prizes_list():
    return [
        """BookLabEduMen tomonidan tashkil etilgan konkursda ishtirok eting va bir qancha mukofotlarni yutib oling!

Sovrinlar:

1. 5 kitob+Bunker+Surprise 
2. 5 kitob+Mafia
3. 3 kitob+Bloknot+Uno
4. 3 kitob+Yangi yil surprise+bookmark
5. 3 kitob+Uno+bookmark
6. 3 kitob+bookmark
"7. 2 kitob+1 kg banan+bookmark"
8-9-10. 2 kitob+bookmark
11. 60000 
12. 40000 so'm
13. 1 kitob
14. 30000 so'm
15. 20000 so'm

🔽Ishtirok etish uchun start bosing:

"Referal havola orqali do'stlaringizni taklif qiling va sovrinlarni qo'lga kiriting."
"""
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
    channels = [CHANNEL_1, CHANNEL_2, CHANNEL_3, CHANNEL_4]
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

# --- HANDLERS ---

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

    # Agar ro'yxatdan o'tgan bo'lsa (verified=1)
    if db_user[4]: 
        if await check_channels(user_id, context):
            await show_main_menu(update, context)
            return
    
    await send_subscription_message(update)

async def send_subscription_message(update):
    keyboard = [
        [InlineKeyboardButton("📢 Kanal 1", url=f"https://t.me/{CHANNEL_1.lstrip('@')}")],
        [InlineKeyboardButton("📢 Kanal 2", url=f"https://t.me/{CHANNEL_2.lstrip('@')}")],
        # Yangi qo'shilgan tugmalar:
        [InlineKeyboardButton("📢 Kanal 3", url=f"https://t.me/{CHANNEL_3.lstrip('@')}")],
        [InlineKeyboardButton("📢 Kanal 4", url=f"https://t.me/{CHANNEL_4.lstrip('@')}")],
        
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
    """
    TUZATILGAN QISM: 
    Foydalanuvchi "A'zo bo'ldim"ni bosganda, agar u oldin ro'yxatdan o'tgan bo'lsa,
    qaytadan ism so'ramasdan, to'g'ri menyuga o'tkazish.
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if await check_channels(user_id, context):
        # User ma'lumotlarini olish
        db_user = db_get_user(user_id)
        
        # Agar user allaqachon tasdiqlangan (verified=1) bo'lsa
        if db_user and db_user[4]: 
            await query.delete_message()
            await query.message.reply_text("✅ Obuna qayta tasdiqlandi. Davom etishingiz mumkin.")
            await show_main_menu(update, context) # <-- MUHIM: Menyuni chiqarish
        else:
            # Agar yangi user bo'lsa, ism so'rashga o'tish
            db_update_state(user_id, 'awaiting_name')
            await query.delete_message()
            await query.message.reply_text("✅ Rahmat! A'zolik tasdiqlandi.\n\nIltimos, Ismingizni yozib yuboring:")
    else:
        await query.answer("❌ Hali to'liq obuna bo'lmadingiz. Iltimos, ikkala kanalga ham a'zo bo'ling!", show_alert=True)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # --- YANGI QO'SHILGAN QISM ---
    # Agar user yoki xabar yo'q bo'lsa (masalan, kanal posti), funksiyani to'xtatamiz
    if not update.effective_user or not update.message:
        return
    # -----------------------------

    user_id = update.effective_user.id
    text = update.message.text
    
    db_user = db_get_user(user_id)
    
    # Agar user bazada bo'lmasa, /start bosishini so'raymiz
    if not db_user:
        await start(update, context)
        return

    user_state = db_user[5]
    is_verified = db_user[4]

    # ... kod davom etadi ...

    # 1. Ismni qabul qilish
    if user_state == 'awaiting_name':
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
        # A'zolikni qayta tekshirish
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
        db_update_phone(user_id, contact.phone_number)
        db_update_state(user_id, 'awaiting_captcha')
        
        await update.message.reply_text("Raqam qabul qilindi ✅", reply_markup=ReplyKeyboardRemove())
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
    
    db_set_verified(user_id)
    ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    
    db_user = db_get_user(user_id)
    referrer_id = db_user[3]
    
    if referrer_id:
        invited_name = db_user[1]
        invited_username = f"@{current_user.username}" if current_user.username else ""
        try:
            await context.bot.send_message(
                chat_id=referrer_id,
                text=f"👏 Siz {invited_name} - {invited_username} do'stingizni taklif qildingiz!"
            )
        except Exception as e:
            logger.error(f"Referrerga xabar yuborishda xato: {e}")

    await update.message.reply_text(
        f"✅ Tabriklaymiz! Ro'yxatdan o'tdingiz!\n\n"
        f"📌 Sizning referral linkingiz:\n`{ref_link}`\n\n"
        f"Do'stlaringizni taklif qiling va sovg'alar yuting!",
        parse_mode='Markdown'
    )
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Agar callback_query bo'lsa (A'zo bo'ldim tugmasidan kelgan bo'lsa)
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

Book Club tomonidan o'tkazilayotgan Yangi yil konkursiga xush kelibsiz! 🎉
G‘oliblari quyidagicha taqdirlanadi:

1-o'rin - 5ta kitob + Bunker
2-o'rin - 5ta kitob + Mafia 
3-o'rin - 3ta kitob + Blaknot +Uno 
4-o'rin - 3 kitob + 1kg banan + bookmark 
5-o'rin - 3 kitob + Uno + bookmark 
6-o'rin - 3 kitob + bookmark 
7-o'rin - 2ta kitob + Yangi yil surprise + bookmark 
8-o'rin - 2ta kitob + bookmark
9-o'rin - 2ta kitob + bookmark
10-o'rin - 2ta kitob + bookmark 
11-o'rin - 60k so'm 
12-o'rin - 40k so'm 
13-o'rin - 1ta kitob 
14-o'rin - 30k soʻm 
15-o'rin - 20k so'm 

✅ G‘oliblar 12.18.2025 da e'lon qilinadi.
Viktorinada ishtirok etish👇
{ref_link}"""

    kb = [[InlineKeyboardButton("🔗 Linkni ulashish", url=f"https://t.me/share/url?url={ref_link}")]]
    
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
    text = "🏆 REYTING (TOP 15):\n\n"

    if not top_users:
        text += "Hozircha natijalar yo'q."
    else:
        for idx, (uid, count) in enumerate(top_users, 1):
            name = db_get_name(uid)
            prize = prizes[idx - 1] if idx <= len(prizes) else "Sovg'a"
            text += f"{idx}-o'rin - {name} - {count} ball - {prize}\n"

    await update.message.reply_text(text)

async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Admin: {ADMIN_USER}")

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_subscription$"))
    application.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot muvaffaqiyatli ishga tushdi...")
    application.run_polling()

if __name__ == "__main__":
    main()