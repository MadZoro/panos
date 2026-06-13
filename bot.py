import os
import logging
import requests
import random
import string
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
SHOP_LINK = "https://t.me/hackdotnet7"

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

def generate_key():
    """Генерация случайного ключа активации"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def send_response(update, context, text, reply_markup=None):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def start(update, context):
    user = update.effective_user
    
    # Логика работы с Supabase
    existing = supabase_request("get", "users", params={"user_id": f"eq.{user.id}"})
    if not existing:
        supabase_request("post", "users", data={
            "user_id": user.id,
            "username": user.username or "no_username",
            "ip_address": f"telegram_{user.id}",
            "registered_at": datetime.now().isoformat()
        })
        logger.info(f"Новый пользователь: {user.id}")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 Каталог товаров", callback_data="list")],
        [InlineKeyboardButton("🎫 Активировать ключ", callback_data="redeem")],
        [InlineKeyboardButton("🛠 Техподдержка", callback_data="tech")],
        [InlineKeyboardButton("🛒 ПЕРЕЙТИ В МАГАЗИН 🛒", url=SHOP_LINK)]
    ])
    
    welcome_text = (
        "🔥 **H A C K . N E T** 🔥\n\n"
        "💎 *Элитный магазин вредоносного программного обеспечения*\n\n"
        "👇 **Выберите действие:**"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

async def list_products(update, context):
    try:
        products = supabase_request("get", "products")
        if not products:
            await send_response(update, context, "📦 *Каталог временно пуст*")
            return
        
        keyboard = []
        for product in products:
            button = InlineKeyboardButton(f"📦 {product['name']} — {product['price']} ⭐", callback_data=f"buy_{product['id']}")
            keyboard.append([button])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await send_response(update, context,
            f"🛍️ *КАТАЛОГ HACK.NET* 🛍️\n\n"
            f"▫️ *Доступно товаров:* {len(products)}\n"
            f"▫️ *Выберите позицию для покупки:*",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в /list: {e}")
        await send_response(update, context, "❌ *Ошибка загрузки каталога*")

async def product_callback(update, context):
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.split("_")[1])
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    
    if not product_data:
        await query.edit_message_text("❌ *Товар не найден*", parse_mode="Markdown")
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
        new_key = generate_key()
        
        # СОХРАНЯЕМ В ТАБЛИЦУ redeem_keys (других таблиц нет!)
        key_data = {
            "key_code": new_key,
            "product_id": product_id,
            "is_used": False,
            "used_by": user.id,
            "created_at": datetime.now().isoformat()
        }
        
        result = supabase_request("post", "redeem_keys", data=key_data)
        
        if result is not None:
            await update.message.reply_text(
                f"✅ *Оплата прошла!*\n\n"
                f"🎁 *Товар:* {product['name']}\n"
                f"🔑 *Ключ:* `{new_key}`\n\n"
                f"💡 *Используйте* `/redeem` *для активации*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *Ошибка сохранения ключа!*\nСообщите администратору",
                parse_mode="Markdown"
            )

async def redeem_key(update, context):
    await send_response(update, context, "🎫 *Активация ключа*\n\nВведите ваш ключ активации:")
    context.user_data['awaiting_key'] = True

async def handle_key_input(update, context):
    if not context.user_data.get('awaiting_key'):
        return
    
    key = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    # Ищем ключ ТОЛЬКО в redeem_keys
    key_data = supabase_request("get", "redeem_keys", params={"key_code": f"eq.{key}"})
    
    if not key_data:
        await update.message.reply_text("❌ *Неверный ключ*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    key_info = key_data[0]
    
    # Проверяем использован ли
    if key_info.get('is_used'):
        await update.message.reply_text("❌ *Ключ уже использован*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    # Получаем товар
    product_data = supabase_request("get", "products", params={"id": f"eq.{key_info['product_id']}"})
    
    if product_data:
        product = product_data[0]
        
        # Активируем
        supabase_request("patch", "redeem_keys",
            params={"key_code": f"eq.{key}"},
            data={"is_used": True, "used_at": datetime.now().isoformat()}
        )
        
        await update.message.reply_text(
            f"✅ *Ключ активирован!*\n\n"
            f"🎁 *Товар:* {product['name']}\n"
            f"🔗 *Ссылка:* `{product['download_link']}`",
            parse_mode="Markdown"
        )
    
    context.user_data['awaiting_key'] = False

async def tech_support(update, context):
    await send_response(update, context,
        "🛠️ *Техническая поддержка*\n\n"
        "✏️ *Опишите вашу проблему одним сообщением.*\n"
        "👨‍💻 *Мы свяжемся с вами в ближайшее время.*"
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
            text=f"🛠 *НОВОЕ ОБРАЩЕНИЕ*\n\n"
                 f"👤 *Пользователь:* @{user.username}\n"
                 f"🆔 *ID:* `{user.id}`\n\n"
                 f"💬 *Сообщение:*\n{message_text}\n\n"
                 f"✅ *Ответ:* `/reply {user.id}`",
            parse_mode="Markdown"
        )
        
        await update.message.reply_text(
            "✅ *Сообщение отправлено администратору!*\n"
            "👨‍💻 *Ответ придет в ближайшее время.*",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке админу: {e}")
        await update.message.reply_text("❌ *Ошибка при отправке сообщения*", parse_mode="Markdown")
    
    context.user_data['awaiting_tech'] = False

async def reply_user(update, context):
    if update.effective_user.id != ADMIN_CHAT_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "📝 *Использование:*\n`/reply USER_ID сообщение`",
            parse_mode="Markdown"
        )
        return

    try:
        user_id = int(context.args[0])
        message = " ".join(context.args[1:])

        await context.bot.send_message(
            chat_id=user_id,
            text=f"📩 *Ответ поддержки HACK.NET*\n\n{message}",
            parse_mode="Markdown"
        )

        await update.message.reply_text("✅ *Ответ успешно отправлен!*", parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Reply error: {e}")
        await update.message.reply_text("❌ *Ошибка отправки ответа*", parse_mode="Markdown")

async def handle_text(update, context):
    if context.user_data.get("awaiting_key"):
        await handle_key_input(update, context)
        return
    
    if context.user_data.get("awaiting_tech"):
        await handle_tech_message(update, context)
        return

async def check(update, context):
    response = requests.get(f"{SUPABASE_URL}/rest/v1/products?select=*", headers=SUPABASE_HEADERS)
    
    if response.status_code == 200:
        products = response.json()
        await update.message.reply_text(
            f"📊 *Диагностика HACK.NET*\n\n"
            f"✅ *Статус:* Работает\n"
            f"📦 *Товаров в БД:* {len(products)} шт.\n"
            f"👨‍💼 *Admin ID:* {ADMIN_CHAT_ID}\n"
            f"👤 *Твой ID:* {update.effective_user.id}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❌ *Ошибка подключения к Supabase*\n"
            f"📡 *Статус:* {response.status_code}\n"
            f"📝 *Ответ:* {response.text[:200]}",
            parse_mode="Markdown"
        )

async def main_menu_callback(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "list":
        # Эмулируем вызов функции /list
        await list_products(update, context)
        
    elif query.data == "redeem":
        # Эмулируем вызов функции /redeem
        await redeem_key(update, context)
        
    elif query.data == "tech":
        # Эмулируем вызов функции /tech
        await tech_support(update, context)

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("redeem", redeem_key))
    application.add_handler(CommandHandler("tech", tech_support))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("reply", reply_user))
    
    # ОБРАБОТЧИКИ КНОПОК
    # Сначала проверяем покупку, потом общее меню
    application.add_handler(CallbackQueryHandler(product_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(main_menu_callback)) 
    
    # Остальное
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    application.run_polling()

if __name__ == "__main__":
    main()
