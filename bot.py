import os
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_CHAT_ID = 1180120574

# Проверка переменных
if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    logger.error("Ошибка: не все переменные окружения заданы!")
    exit(1)

logger.info(f"Бот запущен")
logger.info(f"Admin ID: {ADMIN_CHAT_ID}")

# Headers для Supabase
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def supabase_request(method, table, params=None, data=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        if method == "get":
            response = requests.get(url, headers=SUPABASE_HEADERS, params=params)
        elif method == "post":
            response = requests.post(url, headers=SUPABASE_HEADERS, json=data)
        elif method == "patch":
            response = requests.patch(url, headers=SUPABASE_HEADERS, params=params, json=data)
        else:
            return None
        
        if response.status_code >= 400:
            logger.error(f"Supabase error {response.status_code}: {response.text}")
            return None
        
        return response.json()
    except Exception as e:
        logger.error(f"Request error: {e}")
        return None

async def start(update, context):
    user = update.effective_user
    
    existing = supabase_request("get", "users", params={"user_id": f"eq.{user.id}"})
    if not existing:
        supabase_request("post", "users", data={
            "user_id": user.id,
            "username": user.username or "no_username",
            "ip_address": f"telegram_{user.id}",
            "registered_at": datetime.now().isoformat()
        })
        logger.info(f"Новый пользователь: {user.id}")
    
    welcome_text = """
🔥 ДОБРО ПОЖАЛОВАТЬ В HACK.NET 🔥

Ваш надёжный магазин программного обеспечения.

Доступные команды:
/list - Список товаров
/redeem - Активировать ключ
/tech - Техническая поддержка

Приобретайте только качественное ПО!
"""
    await update.message.reply_text(welcome_text)

async def list_products(update, context):
    try:
        products = supabase_request("get", "products")
        
        if not products:
            await update.message.reply_text("В каталоге пока нет товаров")
            return
        
        keyboard = []
        for product in products:
            button = InlineKeyboardButton(
                f"{product['name']} - {product['price']} звезд",
                callback_data=f"buy_{product['id']}"
            )
            keyboard.append([button])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Каталог товаров ({len(products)} шт.):",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в /list: {e}")
        await update.message.reply_text("Ошибка загрузки товаров")

async def product_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split("_")[1])
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    
    if not product_data:
        await query.edit_message_text("Товар не найден")
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

async def pre_checkout_query(update, context):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update, context):
    user = update.effective_user
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    
    if product_data:
        product = product_data[0]
        await update.message.reply_text(
            f"Оплата прошла успешно!\n\n"
            f"Ваш товар: {product['name']}\n"
            f"Ссылка для скачивания: {product['download_link']}\n\n"
            f"Спасибо за покупку!"
        )
        
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"Новая покупка!\n"
            f"Пользователь: @{user.username} ({user.id})\n"
            f"Товар: {product['name']}\n"
            f"Сумма: {payment.total_amount} звезд"
        )

async def redeem_key(update, context):
    await update.message.reply_text("Введите ваш ключ активации:")
    context.user_data['awaiting_key'] = True

async def handle_key_input(update, context):
    if not context.user_data.get('awaiting_key'):
        return
    
    key = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    key_data = supabase_request("get", "redeem_keys", params={"key_code": f"eq.{key}"})
    
    if not key_data:
        await update.message.reply_text("Неверный ключ активации")
        context.user_data['awaiting_key'] = False
        return
    
    key_info = key_data[0]
    
    if key_info.get('is_used'):
        await update.message.reply_text("Этот ключ уже был использован")
        context.user_data['awaiting_key'] = False
        return
    
    existing = supabase_request("get", "activations", params={
        "user_id": f"eq.{user_id}",
        "product_id": f"eq.{key_info['product_id']}"
    })
    
    if existing:
        await update.message.reply_text("Вы уже активировали этот товар ранее")
        context.user_data['awaiting_key'] = False
        return
    
    supabase_request("patch", "redeem_keys", 
        params={"key_code": f"eq.{key}"},
        data={"is_used": True, "used_by": user_id, "used_at": datetime.now().isoformat()}
    )
    
    supabase_request("post", "activations", data={
        "user_id": user_id,
        "product_id": key_info['product_id'],
        "activated_at": datetime.now().isoformat()
    })
    
    product_data = supabase_request("get", "products", params={"id": f"eq.{key_info['product_id']}"})
    
    if product_data:
        product = product_data[0]
        await update.message.reply_text(
            f"Ключ успешно активирован!\n\n"
            f"Ваш товар: {product['name']}\n"
            f"Ссылка: {product['download_link']}"
        )
    else:
        await update.message.reply_text("Ключ активирован!")
    
    context.user_data['awaiting_key'] = False

async def tech_support(update, context):
    await update.message.reply_text(
        "Техническая поддержка\n\n"
        "Опишите вашу проблему одним сообщением.\n"
        "Я передам её администратору."
    )
    context.user_data['awaiting_tech'] = True

async def handle_tech_message(update, context):
    if not context.user_data.get('awaiting_tech'):
        return
    
    user = update.effective_user
    message_text = update.message.text
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"НОВОЕ ОБРАЩЕНИЕ В ТП\n\n"
                 f"Пользователь: @{user.username} (ID: {user.id})\n"
                 f"Сообщение: {message_text}\n\n"
                 f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        await update.message.reply_text(
            "Сообщение отправлено администратору!\n"
            "Ответ придет в ближайшее время."
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке админу: {e}")
        await update.message.reply_text("Ошибка при отправке сообщения")
    
    context.user_data['awaiting_tech'] = False

async def check(update, context):
    response = requests.get(f"{SUPABASE_URL}/rest/v1/products?select=*", headers=SUPABASE_HEADERS)
    
    if response.status_code == 200:
        products = response.json()
        await update.message.reply_text(
            f"Диагностика:\n\n"
            f"Статус: Работает\n"
            f"Товаров в БД: {len(products)} шт.\n"
            f"Admin ID: {ADMIN_CHAT_ID}\n"
            f"Твой ID: {update.effective_user.id}"
        )
    else:
        await update.message.reply_text(
            f"Ошибка подключения к Supabase\n"
            f"Статус: {response.status_code}\n"
            f"Ответ: {response.text[:200]}"
        )

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("redeem", redeem_key))
    application.add_handler(CommandHandler("tech", tech_support))
    application.add_handler(CommandHandler("check", check))
    
    application.add_handler(CallbackQueryHandler(product_callback, pattern="^buy_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_key_input))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_tech_message))
    
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    logger.info("Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
