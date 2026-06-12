import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes
)
from supabase import create_client, Client

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_CHAT_ID = 1180120574

# Проверка переменных окружения
if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    logger.error("❌ Ошибка: не все переменные окружения заданы!")
    exit(1)

# Инициализация Supabase
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase подключен успешно")
except Exception as e:
    logger.error(f"❌ Ошибка подключения к Supabase: {e}")
    exit(1)

async def get_user_ip(update: Update) -> str:
    return f"telegram_{update.effective_user.id}"

async def register_user(user_id: int, username: str, ip: str):
    try:
        existing = supabase.table("users").select("*").eq("user_id", user_id).execute()
        
        if not existing.data:
            supabase.table("users").insert({
                "user_id": user_id,
                "username": username or "no_username",
                "ip_address": ip,
                "registered_at": datetime.now().isoformat()
            }).execute()
            logger.info(f"✅ Новый пользователь: {user_id} (@{username})")
    except Exception as e:
        logger.error(f"❌ Ошибка регистрации: {e}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ip = await get_user_ip(update)
    await register_user(user.id, user.username, ip)
    
    welcome_text = """
╔══════════════════════════════════╗
║     🤖 *ДОБРО ПОЖАЛОВАТЬ В*       ║
║     🔥 *HACK.NET* 🔥              ║
╚══════════════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

💎 *Ваш надёжный магазин*  
🛡️ *Программного обеспечения*

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

📋 *Доступные команды:*

🔹 `/list` - 📦 Список товаров
🔹 `/redeem` - 🎫 Активировать ключ  
🔹 `/tech` - 🛠 Техническая поддержка

────────────────────────────────

✅ *Приобретайте только качественное ПО!*
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# Команда /list
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        products = supabase.table("products").select("*").execute()
        
        if not products.data:
            await update.message.reply_text("❌ *Товаров пока нет в наличии*", parse_mode="Markdown")
            return
        
        keyboard = []
        for product in products.data:
            button = InlineKeyboardButton(
                f"📦 {product['name']} — {product['price']} ⭐",
                callback_data=f"buy_{product['id']}"
            )
            keyboard.append([button])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = """
╔════════════════════════╗
║     🛒 *КАТАЛОГ ТОВАРОВ*    ║
╚════════════════════════╝

🎯 *Выберите товар для покупки:*
"""
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"❌ Ошибка в /list: {e}")
        await update.message.reply_text("❌ *Ошибка загрузки товаров*", parse_mode="Markdown")

# Обработка нажатия на товар
async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split("_")[1])
    
    product = supabase.table("products").select("*").eq("id", product_id).execute()
    
    if not product.data:
        await query.edit_message_text("❌ *Товар не найден*", parse_mode="Markdown")
        return
    
    product = product.data[0]
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"Покупка {product['name']}",
        description=f"Приобретение лицензии на {product['name']}",
        payload=f"payment_{product_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=product['name'], amount=product['price'])],
        need_name=False,
        need_phone_number=False,
        need_email=False
    )

# Обработка предпроверки платежа
async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

# Обработка успешной оплаты
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    
    product = supabase.table("products").select("*").eq("id", product_id).execute()
    
    if product.data:
        product = product.data[0]
        
        success_text = f"""
╔════════════════════════════╗
║     ✅ *ОПЛАТА ПРОШЛА*       ║
║     ✅ *УСПЕШНО!*            ║
╚════════════════════════════╝

🎁 *Ваш товар:* {product['name']}

🔗 *Ссылка для скачивания:*
`{product['download_link']}`

💾 *Сохраните ссылку!*

────────────────────────

🙏 *Спасибо за покупку!*
"""
        await update.message.reply_text(success_text, parse_mode="Markdown")
        
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"💎 *НОВАЯ ПОКУПКА!*\n\n"
            f"👤 *Пользователь:* @{user.username} ({user.id})\n"
            f"📦 *Товар:* {product['name']}\n"
            f"⭐ *Сумма:* {payment.total_amount} звезд\n"
            f"🕐 *Время:* {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )

# Команда /redeem
async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
╔═══════════════════════════╗
║     🎫 *АКТИВАЦИЯ КЛЮЧА*     ║
╚═══════════════════════════╝

📝 *Введите ваш ключ активации:*
"""
    await update.message.reply_text(text, parse_mode="Markdown")
    context.user_data['awaiting_key'] = True

# Обработка ввода ключа
async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_key'):
        return
    
    key = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    try:
        key_data = supabase.table("redeem_keys").select("*").eq("key_code", key).execute()
        
        if not key_data.data:
            await update.message.reply_text("❌ *Неверный ключ активации*", parse_mode="Markdown")
            context.user_data['awaiting_key'] = False
            return
        
        key_info = key_data.data[0]
        
        if key_info['is_used']:
            await update.message.reply_text("❌ *Этот ключ уже был использован*", parse_mode="Markdown")
            context.user_data['awaiting_key'] = False
            return
        
        existing = supabase.table("activations").select("*").eq("user_id", user_id).eq("product_id", key_info['product_id']).execute()
        
        if existing.data:
            await update.message.reply_text("❌ *Вы уже активировали этот товар ранее*", parse_mode="Markdown")
            context.user_data['awaiting_key'] = False
            return
        
        supabase.table("redeem_keys").update({
            "is_used": True,
            "used_by": user_id,
            "used_at": datetime.now().isoformat()
        }).eq("key_code", key).execute()
        
        supabase.table("activations").insert({
            "user_id": user_id,
            "product_id": key_info['product_id'],
            "activated_at": datetime.now().isoformat()
        }).execute()
        
        product = supabase.table("products").select("*").eq("id", key_info['product_id']).execute()
        
        if product.data:
            success_text = f"""
╔═══════════════════════════╗
║  ✅ *КЛЮЧ АКТИВИРОВАН*      ║
╚═══════════════════════════╝

🎁 *Ваш товар:* {product.data[0]['name']}

🔗 *Ссылка для скачивания:*
`{product.data[0]['download_link']}`

💾 *Сохраните ссылку!*
"""
            await update.message.reply_text(success_text, parse_mode="Markdown")
        else:
            await update.message.reply_text("✅ *Ключ активирован! Товар получен.*", parse_mode="Markdown")
        
        context.user_data['awaiting_key'] = False
        
    except Exception as e:
        logger.error(f"❌ Ошибка активации ключа: {e}")
        await update.message.reply_text("❌ *Ошибка активации ключа*", parse_mode="Markdown")

# Команда /tech
async def tech_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
╔═══════════════════════════╗
║   🛠 *ТЕХНИЧЕСКАЯ ПОДДЕРЖКА* ║
╚═══════════════════════════╝

📝 *Опишите вашу проблему*

✏️ *Отправьте одним сообщением*

────────────────────────

⏳ *Ожидайте ответа администратора*
"""
    await update.message.reply_text(text, parse_mode="Markdown")
    context.user_data['awaiting_tech'] = True

# Обработка сообщения в техподдержку (ИСПРАВЛЕНО!)
async def handle_tech_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_tech'):
        return
    
    user = update.effective_user
    message_text = update.message.text
    
    # Формируем красивое сообщение для админа
    admin_message = f"""
╔═══════════════════════════════╗
║   🛠 *НОВОЕ ОБРАЩЕНИЕ В ТП*     ║
╚═══════════════════════════════╝

👤 *Пользователь:* @{user.username}
🆔 *ID:* `{user.id}`
👣 *Имя:* {user.first_name or "Не указано"}

───────────────────────────

📝 *Сообщение:*
{message_text}

───────────────────────────

🕐 *Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    # Отправляем админу
    try:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            admin_message,
            parse_mode="Markdown"
        )
        logger.info(f"✅ Отправлено сообщение в ТП от @{user.username} (ID: {user.id})")
        
        # Подтверждение пользователю
        confirm_text = """
╔═══════════════════════════╗
║   ✅ *СООБЩЕНИЕ ОТПРАВЛЕНО*  ║
╚═══════════════════════════╝

👨‍💻 *Администратор свяжется с вами*

⏳ *Ожидайте ответа в ближайшее время*

────────────────────────

🙏 *Спасибо за обращение!*
"""
        await update.message.reply_text(confirm_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке сообщения админу: {e}")
        await update.message.reply_text(
            "❌ *Ошибка при отправке сообщения.*\nПопробуйте позже или свяжитесь напрямую с администратором.",
            parse_mode="Markdown"
        )
    
    context.user_data['awaiting_tech'] = False

# Диагностическая команда для проверки (только для админа)
async def check_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    await update.message.reply_text(
        f"📊 *Информация о чате*\n\n"
        f"🆔 Ваш Chat ID: `{update.effective_chat.id}`\n"
        f"👤 Ваш User ID: `{update.effective_user.id}`\n\n"
        f"⚙️ ADMIN_CHAT_ID в боте: `{ADMIN_CHAT_ID}`\n\n"
        f"*Если значения отличаются, измени ADMIN_CHAT_ID в коде бота*",
        parse_mode="Markdown"
    )

async def main():
    application = Application.builder().token(TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("redeem", redeem_key))
    application.add_handler(CommandHandler("tech", tech_support))
    application.add_handler(CommandHandler("checkid", check_chat_id))  # Диагностическая команда
    
    # Обработчики
    application.add_handler(CallbackQueryHandler(product_callback, pattern="^buy_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tech_message))
    
    # Платежи
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    logger.info("🚀 Бот успешно запущен!")
    logger.info(f"👨‍💼 Администратор: {ADMIN_CHAT_ID}")
    
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
