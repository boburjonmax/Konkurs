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
TOKEN = "8109025019:AAHd-BHJefKFq3TgQKxCX3sPw9r8gde5imQ"  # BotFather bergan token
CHANNEL_1 = "@tsuebookclub"
CHANNEL_2 = "@MantiqLab"
CHANNEL_3 = "@Edu_Corner"
ADMIN_USER = "@okgoo"
BOT_USERNAME = "bookclub_konkursS_bot"  # Yangi username
PHOTO_URL = "https://ibb.co/k2Hhm9P3"
ADMIN_ID = 1814162588

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- MA'LUMOTLAR BAZASI (SQLite) ---
DB_PATH = 'konkurs.db'
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    phone TEXT,
    referrer_id INTEGER,
    verified BOOLEAN DEFAULT 0,
    state TEXT,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Bot xabarlarini saqlash uchun jadval
cursor.execute('''
CREATE TABLE IF NOT EXISTS bot_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    message_id INTEGER,
    user_id INTEGER,
    message_type TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, message_id)
)
''')
conn.commit()

# --- FUNKSIYALAR ---
def save_bot_message(chat_id, message_id, user_id, message_type="text"):
    """Bot yuborgan xabarni saqlash"""
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO bot_messages (chat_id, message_id, user_id, message_type)
            VALUES (?, ?, ?, ?)
        ''', (chat_id, message_id, user_id, message_type))
        conn.commit()
    except Exception as e:
        logger.error(f"Xabarni saqlashda xato: {e}")

def get_last_bot_messages(chat_id, limit=50):
    """Botning chatdagi oxirgi xabarlarini olish"""
    cursor.execute('''
        SELECT message_id FROM bot_messages 
        WHERE chat_id = ? 
        ORDER BY message_id DESC 
        LIMIT ?
    ''', (chat_id, limit))
    return [row[0] for row in cursor.fetchall()]

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

def is_admin(user):
    if user.username and f"@{user.username}" == ADMIN_USER:
        return True
    if user.id == ADMIN_ID:
        return True
    return False

# 1. /delete_last - Oxirgi bot xabarlarini o'chirish
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
                if count > 100:  # Limit
                    count = 100
            except ValueError:
                await update.message.reply_text("❌ Noto'g'ri son format. Masalan: `/delete_last 5`", parse_mode='Markdown')
                return
        
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        await update.message.reply_text(f"⏳ Oxirgi {count} ta bot xabarini o'chirish...")
        
        # Botning saqlangan xabarlarini olish
        message_ids = get_last_bot_messages(chat_id, count * 2)  # Buffer bilan
        
        deleted_count = 0
        failed_count = 0
        
        for msg_id in message_ids[:count]:
            try:
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=msg_id
                )
                deleted_count += 1
                logger.info(f"✅ Xabar {msg_id} o'chirildi")
                
                # Database dan ham o'chirish
                cursor.execute('DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?', 
                             (chat_id, msg_id))
                conn.commit()
                
            except BadRequest as e:
                if "message to delete not found" in str(e):
                    logger.info(f"⚠️ Xabar {msg_id} topilmadi (allaqachon o'chirilgan)")
                    # Database dan o'chirish
                    cursor.execute('DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?', 
                                 (chat_id, msg_id))
                    conn.commit()
                else:
                    logger.error(f"❌ Xabar {msg_id} o'chirishda xato: {e}")
                    failed_count += 1
            except Exception as e:
                logger.error(f"❌ Xatolik: {e}")
                failed_count += 1
        
        # Natijani chiqarish
        result_text = (
            f"✅ **Xabar o'chirish tugadi:**\n\n"
            f"📊 **Natijalar:**\n"
            f"✅ O'chirildi: {deleted_count} ta\n"
            f"❌ Xatolik: {failed_count} ta\n"
            f"📝 Soralgan: {count} ta"
        )
        
        if deleted_count == 0 and count > 0:
            result_text += "\n\n⚠️ **Sabablar:**\n"
            result_text += "1. Bot admin emas\n"
            result_text += "2. Xabarlar 48 soatdan oshgan\n"
            result_text += "3. Hali xabar saqlanmagan\n"
            result_text += "4. Database'da xabar ID lari yo'q"
        
        await update.message.reply_text(result_text, parse_mode='Markdown')
        
        # Log yozish
        logger.warning(f"👮 Admin {user_id} chat {chat_id} da {deleted_count} ta xabar o'chirdi")
        
    except Exception as e:
        logger.error(f"❌ Admin delete_last da xato: {e}")
        await update.message.reply_text(f"❌ Xatolik: {str(e)[:200]}")

# 2. /delete_msg - Maxsus xabarni ID bo'yicha o'chirish
async def admin_delete_specific_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xabar ID si bo'yicha o'chirish"""
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "❌ Xabar ID sini kiriting.\n"
            "Masalan: `/delete_msg 12345`\n\n"
            "⚠️ Xabar ID sini olish uchun:\n"
            "1. Xabarni forward qiling @RawDataBot ga\n"
            "2. Yoki xabarni reply qilib /id buyrug'ini yuboring",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    
    try:
        deleted_count = 0
        failed_count = 0
        results = []
        
        for msg_id_str in context.args:
            try:
                msg_id = int(msg_id_str)
                
                # Xabarni o'chirish
                await context.bot.delete_message(
                    chat_id=chat_id,
                    message_id=msg_id
                )
                deleted_count += 1
                results.append(f"✅ {msg_id}: O'chirildi")
                
                # Database dan o'chirish
                cursor.execute('DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?', 
                             (chat_id, msg_id))
                conn.commit()
                
            except BadRequest as e:
                if "message to delete not found" in str(e):
                    results.append(f"❌ {msg_id}: Topilmadi")
                    # Database dan o'chirish
                    cursor.execute('DELETE FROM bot_messages WHERE chat_id = ? AND message_id = ?', 
                                 (chat_id, msg_id))
                    conn.commit()
                else:
                    results.append(f"❌ {msg_id}: {str(e)[:30]}")
                failed_count += 1
            except ValueError:
                results.append(f"❌ {msg_id_str}: Noto'g'ri format")
                failed_count += 1
            except Exception as e:
                results.append(f"❌ {msg_id_str}: {str(e)[:30]}")
                failed_count += 1
        
        # Natijalarni chiqarish
        result_text = f"📊 **Xabar o'chirish natijalari:**\n\n"
        result_text += f"✅ O'chirildi: {deleted_count} ta\n"
        result_text += f"❌ Xatolik: {failed_count} ta\n\n"
        
        if results:
            result_text += "**Batafsil:**\n"
            for result in results[:10]:
                result_text += result + "\n"
            if len(results) > 10:
                result_text += f"\n... va yana {len(results)-10} ta"
        
        await update.message.reply_text(result_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ Delete specific message da xato: {e}")
        await update.message.reply_text(f"❌ Xatolik: {str(e)[:200]}")

# 3. /id - Xabar ID sini olish
async def admin_get_message_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xabar ID sini olish"""
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    if update.message.reply_to_message:
        msg_id = update.message.reply_to_message.message_id
        chat_id = update.effective_chat.id
        
        await update.message.reply_text(
            f"📊 **Xabar ma'lumotlari:**\n\n"
            f"📌 Chat ID: `{chat_id}`\n"
            f"📌 Xabar ID: `{msg_id}`\n\n"
            f"🔗 O'chirish uchun:\n"
            f"`/delete_msg {msg_id}`",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "ℹ️ Xabar ID sini olish uchun:\n\n"
            "1. ID sini bilmoqchi bo'lgan xabarga reply bosing\n"
            "2. `/id` deb yozing\n\n"
            "Yoki:\n"
            "1. Xabarni forward qiling @RawDataBot ga\n"
            "2. U sizga barcha ma'lumotlarni beradi",
            parse_mode='Markdown'
        )

# 4. /clear_all - Barcha bot xabarlarini o'chirish
async def admin_clear_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha bot xabarlarini o'chirish"""
    if not is_admin(update.effective_user): 
        await update.message.reply_text("❌ Ruxsat yo'q")
        return
    
    try:
        chat_id = update.effective_chat.id
        
        # Tasdiqlash
        keyboard = [
            [
                InlineKeyboardButton("✅ HA, o'chirish", callback_data="confirm_delete_all"),
                InlineKeyboardButton("❌ BEKOR QILISH", callback_data="cancel_delete")
            ]
        ]
        
        await update.message.reply_text(
            "⚠️ **DIQQAT: BU BUYRUQ ORQASIGA QAYTISH YO'Q!**\n\n"
            "Siz chatdagi BARCHA bot xabarlarini o'chirmoqchisiz.\n\n"
            "Bu amalni bekor qilib bo'lmaydi!\n\n"
            "Rostdan ham davom etishni istaysizmi?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Clear all da xato: {e}")

# 5. Tasdiqlash callback
async def handle_delete_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasdiqlash callback lari"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_delete_all":
        chat_id = query.message.chat_id
        
        # Loading
        await query.edit_message_text("⏳ Barcha bot xabarlarini o'chirish...")
        
        # Barcha saqlangan xabar ID larini olish
        cursor.execute('SELECT message_id FROM bot_messages WHERE chat_id = ?', (chat_id,))
        all_messages = [row[0] for row in cursor.fetchall()]
        
        deleted_count = 0
        failed_count = 0
        
        for msg_id in all_messages:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                deleted_count += 1
                
                # Har 10 ta xabardan keyin yangilash
                if deleted_count % 10 == 0:
                    await query.edit_message_text(
                        f"⏳ {deleted_count}/{len(all_messages)} xabar o'chirildi..."
                    )
                    
            except Exception as e:
                failed_count += 1
        
        # Database dan o'chirish
        cursor.execute('DELETE FROM bot_messages WHERE chat_id = ?', (chat_id,))
        conn.commit()
        
        # Natija
        await query.edit_message_text(
            f"✅ **Barcha bot xabarlari o'chirildi!**\n\n"
            f"📊 **Natijalar:**\n"
            f"✅ O'chirildi: {deleted_count} ta\n"
            f"❌ Xatolik: {failed_count} ta\n"
            f"📝 Jami: {len(all_messages)} ta",
            parse_mode='Markdown'
        )
        
    elif query.data == "cancel_delete":
        await query.edit_message_text("✅ Bekor qilindi. Hech narsa o'chirilmadi.")

# 6. XABAR YUBORGANDA SAQLASH
async def save_message_on_send(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Xabar yuborilganda saqlash"""
    try:
        if message:
            save_bot_message(
                chat_id=message.chat_id,
                message_id=message.message_id,
                user_id=context.bot.id,
                message_type="text"
            )
    except Exception as e:
        logger.error(f"Xabarni saqlashda xato: {e}")

# 7. START COMMAND (yangilangan)
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

# 8. REPLY MESSAGE YUBORGANDAN SAQLASH
async def send_message_and_save(context, chat_id, text, **kwargs):
    """Xabar yuborib, saqlash"""
    message = await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
    save_bot_message(
        chat_id=chat_id,
        message_id=message.message_id,
        user_id=context.bot.id,
        message_type="text"
    )
    return message

# ASOSIY BOT KODI (qisqartirilgan)
async def check_channels(user_id, context):
    # ... sizning check_channels funksiyangiz ...
    pass

async def send_subscription_message(update):
    # ... sizning send_subscription_message funksiyangiz ...
    pass

async def show_main_menu(update, context):
    # ... sizning show_main_menu funksiyangiz ...
    pass

# MAIN FUNCTION
def main():
    application = Application.builder().token(TOKEN).build()

    # Start handler
    application.add_handler(CommandHandler("start", start))
    
    # Admin handlers
    admin_commands = [
        ("delete_last", admin_delete_last_messages),
        ("delete_msg", admin_delete_specific_message),
        ("id", admin_get_message_id),
        ("clear_all", admin_clear_all_messages),
        ("clean", admin_delete_last_messages),  # Qisqa nom
    ]
    
    for cmd, func in admin_commands:
        application.add_handler(CommandHandler(cmd, func))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(handle_delete_callbacks, pattern="^(confirm_delete_all|cancel_delete)$"))
    
    # Ishga tushirish
    logger.info("🤖 Yangi bot ishga tushdi...")
    application.run_polling()

if __name__ == "__main__":
    main()
