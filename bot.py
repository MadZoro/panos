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
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 ПЕРЕЙТИ В МАГАЗИН 🛒", url=SHOP_LINK)]
    ])
    
    welcome_text = (
        "🔥 **H A C K . N E T** 🔥\n\n"
        "💎 *Элитный магазин программного обеспечения*\n\n"
        "📋 **Доступные команды:**\n"
        "▫️ `/list` — 📦 Каталог товаров\n"
        "▫️ `/redeem` — 🎫 Активировать ключ\n"
        "▫️ `/tech` — 🛠️ Техническая поддержка\n\n"
        "👇 **Наш официальный магазин:**"
    )
    
    await update.message.reply_text(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

async def list_products(update, context):
    try:
        products = supabase_request("get", "products")
        
        if not products:
            await update.message.reply_text("📦 *Каталог временно пуст*", parse_mode="Markdown")
            return
        
        keyboard = []
        for product in products:
            button = InlineKeyboardButton(
                f"📦 {product['name']} — {product['price']} ⭐",
                callback_data=f"buy_{product['id']}"
            )
            keyboard.append([button])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🛍️ *КАТАЛОГ HACK.NET* 🛍️\n\n"
            f"▫️ *Доступно товаров:* {len(products)}\n"
            f"▫️ *Выберите позицию для покупки:*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка в /list: {e}")
        await update.message.reply_text("❌ *Ошибка загрузки каталога*", parse_mode="Markdown")

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
    """ПОСЛЕ ОПЛАТЫ: ГЕНЕРИРУЕМ КЛЮЧ, СОХРАНЯЕМ В БД, ОТДАЁМ ПОЛЬЗОВАТЕЛЮ"""
    user = update.effective_user
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    
    if product_data:
        product = product_data[0]
        
        # ГЕНЕРИРУЕМ НОВЫЙ КЛЮЧ
        new_key = generate_key()
        
        # СОХРАНЯЕМ КЛЮЧ В БД (связываем с пользователем и товаром)
        supabase_request("post", "user_keys", data={
            "user_id": user.id,
            "product_id": product_id,
            "key_code": new_key,
            "is_activated": False,
            "created_at": datetime.now().isoformat()
        })
        
        # ОТПРАВЛЯЕМ КЛЮЧ ПОЛЬЗОВАТЕЛЮ
        await update.message.reply_text(
            f"✅ *Оплата прошла успешно!*\n\n"
            f"🎁 *Товар:* {product['name']}\n"
            f"🔑 *Ваш ключ активации:*\n`{new_key}`\n\n"
            f"💡 *Используйте команду* `/redeem` *для активации ключа*\n\n"
            f"🙏 *Спасибо за покупку в HACK.NET!*",
            parse_mode="Markdown"
        )
        
        # Уведомление админу
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 *НОВАЯ ПОКУПКА!*\n"
            f"👤 *Пользователь:* @{user.username} ({user.id})\n"
            f"📦 *Товар:* {product['name']}\n"
            f"⭐ *Сумма:* {payment.total_amount} звезд\n"
            f"🔑 *Сгенерирован ключ:* `{new_key}`",
            parse_mode="Markdown"
        )

async def redeem_key(update, context):
    await update.message.reply_text(
        "🎫 *Активация ключа*\n\n"
        "Введите ваш ключ активации:",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_key'] = True

async def handle_key_input(update, context):
    if not context.user_data.get('awaiting_key'):
        return
    
    key = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    # Ищем ключ в таблице user_keys
    key_data = supabase_request("get", "user_keys", params={"key_code": f"eq.{key}"})
    
    if not key_data:
        await update.message.reply_text("❌ *Неверный ключ активации*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    key_info = key_data[0]
    
    # Проверяем принадлежит ли ключ этому пользователю
    if key_info['user_id'] != user_id:
        await update.message.reply_text("❌ *Этот ключ не принадлежит вам*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    # Проверяем не активирован ли уже ключ
    if key_info.get('is_activated'):
        await update.message.reply_text("❌ *Этот ключ уже был активирован*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    # Получаем товар
    product_data = supabase_request("get", "products", params={"id": f"eq.{key_info['product_id']}"})
    
    if product_data:
        product = product_data[0]
        
        # Активируем ключ в БД
        supabase_request("patch", "user_keys",
            params={"key_code": f"eq.{key}"},
            data={"is_activated": True, "activated_at": datetime.now().isoformat()}
        )
        
        await update.message.reply_text(
            f"✅ *Ключ успешно активирован!*\n\n"
            f"🎁 *Ваш товар:* {product['name']}\n"
            f"🔗 *Ссылка для скачивания:*\n`{product['download_link']}`\n\n"
            f"💾 *Сохраните ссылку!*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("✅ *Ключ активирован!*", parse_mode="Markdown")
    
    context.user_data['awaiting_key'] = False

async def tech_support(update, context):
    await update.message.reply_text(
        "🛠️ *Техническая поддержка*\n\n"
        "✏️ *Опишите вашу проблему одним сообщением.*\n"
        "👨‍💻 *Мы свяжемся с вами в ближайшее время.*",
        parse_mode="Markdown"
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

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_products))
    application.add_handler(CommandHandler("redeem", redeem_key))
    application.add_handler(CommandHandler("tech", tech_support))
    application.add_handler(CommandHandler("check", check))
    application.add_handler(CommandHandler("reply", reply_user))
    
    # Обработчики
    application.add_handler(CallbackQueryHandler(product_callback, pattern="^buy_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Платежи
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    logger.info("🚀 HACK.NET бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
