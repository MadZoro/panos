import os
import asyncio
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes
)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_CHAT_ID = 1180120574

# Headers для запросов к Supabase
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

# Функция запроса к Supabase REST API
def supabase_request(method: str, table: str, params: dict = None, data: dict = None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if method == "get":
        response = requests.get(url, headers=SUPABASE_HEADERS, params=params)
    elif method == "post":
        response = requests.post(url, headers=SUPABASE_HEADERS, json=data)
    elif method == "patch":
        response = requests.patch(url, headers=SUPABASE_HEADERS, params=params, json=data)
    else:
        raise ValueError("Unsupported method")
    
    if response.status_code >= 400:
        logger.error(f"Supabase error {response.status_code}: {response.text}")
        return None
    return response.json()

# Функция получения IP пользователя
async def get_user_ip(update: Update) -> str:
    return f"telegram_{update.effective_user.id}"

# Регистрация пользователя
async def register_user(user_id: int, username: str, ip: str):
    try:
        existing = supabase_request("get", "users", params={"user_id": f"eq.{user_id}"})
        if not existing:
            supabase_request("post", "users", data={
                "user_id": user_id,
                "username": username or "no_username",
                "ip_address": ip,
                "registered_at": datetime.now().isoformat()
            })
            logger.info(f"Новый пользователь: {user_id} ({username})")
    except Exception as e:
        logger.error(f"Ошибка регистрации: {e}")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ip = await get_user_ip(update)
    await register_user(user.id, user.username, ip)
    
    welcome_text = """
🤖 *Добро пожаловать в HACK.NET*

Ваш надёжный магазин программного обеспечения.

*Доступные команды:*
/list - 📦 Список товаров
/redeem - 🎫 Активировать ключ
/tech - 🛠 Техническая поддержка

Приобретайте только качественное ПО!
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# Команда /list
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        products = supabase_request("get", "products")
        if not products:
            await update.message.reply_text("❌ Товаров пока нет")
            return
        
        keyboard = []
        for product in products:
            button = InlineKeyboardButton(
                f"📦 {product['name']} - {product['price']}⭐",
                callback_data=f"buy_{product['id']}"
            )
            keyboard.append([button])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛒 *Доступные товары:*\nВыберите товар для покупки:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка в /list: {e}")
        await update.message.reply_text("❌ Ошибка загрузки товаров")

# Обработка нажатия на товар
async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split("_")[1])
    
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    if not product_data:
        await query.edit_message_text("❌ Товар не найден")
        return
    
    product = product_data[0]
    
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
    await update.pre_checkout_query.answer(ok=True)

# Обработка успешной оплаты
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    if product_data:
        product = product_data[0]
        await update.message.reply_text(
            f"✅ *Оплата прошла успешно!*\n\n"
            f"🎁 Ваш товар: *{product['name']}*\n"
            f"🔗 Ссылка для скачивания:\n`{product['download_link']}`\n\n"
            f"Спасибо за покупку!",
            parse_mode="Markdown"
        )
        
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 Новая покупка!\n"
            f"Пользователь: @{user.username} ({user.id})\n"
            f"Товар: {product['name']}\n"
            f"Сумма: {payment.total_amount} ⭐"
        )

# Команда /redeem
async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎫 *Активация ключа*\n\nВведите ваш ключ активации:",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_key'] = True

# Обработка ввода ключа
async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_key'):
        return
    
    key = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    try:
        key_data = supabase_request("get", "redeem_keys", params={"key_code": f"eq.{key}"})
        if not key_data:
            await update.message.reply_text("❌ Неверный ключ активации")
            context.user_data['awaiting_key'] = False
            return
        
        key_info = key_data[0]
        
        if key_info['is_used']:
            await update.message.reply_text("❌ Этот ключ уже был использован")
            context.user_data['awaiting_key'] = False
            return
        
        existing = supabase_request("get", "activations", params={"user_id": f"eq.{user_id}", "product_id": f"eq.{key_info['product_id']}"})
        if existing:
            await update.message.reply_text("❌ Вы уже активировали этот товар ранее")
            context.user_data['awaiting_key'] = False
            return
        
        supabase_request("patch", "redeem_keys", params={"key_code": f"eq.{key}"}, data={"is_used": True, "used_by": user_id, "used_at": datetime.now().isoformat()})
        supabase_request("post", "activations", data={"user_id": user_id, "product_id": key_info['product_id'], "activated_at": datetime.now().isoformat()})
        
        product_data = supabase_request("get", "products", params={"id": f"eq.{key_info['product_id']}"})
        if product_data:
            await update.message.reply_text(
                f"✅ *Ключ успешно активирован!*\n\n"
                f"🎁 Ваш товар: *{product_data[0]['name']}*\n"
                f"🔗 Ссылка:\n`{product_data[0]['download_link']}`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("✅ Ключ активирован! Товар получен.")
        
        context.user_data['awaiting_key'] = False
        
    except Exception as e:
        logger.error(f"Ошибка активации ключа: {e}")
        await update.message.reply_text("❌ Ошибка активации")

# Команда /tech
async def tech_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *Техническая поддержка*\n\nОпишите вашу проблему одним сообщением.\nЯ передам её администратору.",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_tech'] = True

# Обработка сообщения в техподдержку
async def handle_tech_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_tech'):
        return
    
    user = update.effective_user
    message_text = update.message.text
    
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"🛠 *Новое обращение в ТП*\n"
        f"👤 Пользователь: @{user.username} ({user.id})\n"
        f"📝 Сообщение:\n{message_text}",
        parse_mode="Markdown"
    )
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено администратору.\nОтвет ожидайте в ближайшее время."
    )
    context.user_data['awaiting_tech'] = False

def run_bot():
    """Функция для запуска бота с правильной обработкой event loop"""
    try:
        # Создаем приложение
        application = Application.builder().token(TOKEN).build()
        
        # Команды
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("list", list_products))
        application.add_handler(CommandHandler("redeem", redeem_key))
        application.add_handler(CommandHandler("tech", tech_support))
        
        # Обработчики
        application.add_handler(CallbackQueryHandler(product_callback, pattern="^buy_"))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_input))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tech_message))
        
        # Платежи
        application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
        
        logger.info("🚀 Бот запущен и готов к работе!")
        
        # Запускаем polling
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except RuntimeError as e:
        if "already running" in str(e):
            logger.warning("Event loop already running, using get_running_loop()")
            # Альтернативный способ запуска
            loop = asyncio.get_running_loop()
            application = Application.builder().token(TOKEN).build()
            # Добавляем обработчики (те же самые)
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("list", list_products))
            application.add_handler(CommandHandler("redeem", redeem_key))
            application.add_handler(CommandHandler("tech", tech_support))
            application.add_handler(CallbackQueryHandler(product_callback, pattern="^buy_"))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_input))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tech_message))
            application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
            application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
            
            loop.create_task(application.initialize())
            loop.create_task(application.start())
            loop.create_task(application.updater.start_polling())
        else:
            raise e

if __name__ == "__main__":
    run_bot()
