import os
import asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from supabase import create_client, Client

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

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Функция получения IP пользователя (приблизительно через Telegram)
async def get_user_ip(update: Update) -> str:
    """Получение IP пользователя (если доступно)"""
    try:
        # В Telegram нет прямого доступа к IP, используем заглушку
        # Можно добавить через вебхук или сервис
        return f"telegram_{update.effective_user.id}"
    except:
        return "unknown"

# Регистрация пользователя в БД
async def register_user(user_id: int, username: str, ip: str):
    """Регистрирует пользователя если его нет в БД"""
    try:
        # Проверяем существует ли пользователь
        existing = supabase.table("users").select("*").eq("user_id", user_id).execute()
        
        if not existing.data:
            # Создаем нового пользователя
            supabase.table("users").insert({
                "user_id": user_id,
                "username": username,
                "ip_address": ip
            }).execute()
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

# Команда /list - вывод товаров кнопками
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем товары из БД
        products = supabase.table("products").select("*").execute()
        
        if not products.data:
            await update.message.reply_text("❌ Товаров пока нет")
            return
        
        keyboard = []
        for product in products.data:
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
    
    # Получаем товар из БД
    product = supabase.table("products").select("*").eq("id", product_id).execute()
    
    if not product.data:
        await query.edit_message_text("❌ Товар не найден")
        return
    
    product = product.data[0]
    
    # Создаем инвойс для оплаты звездами
    await query.edit_message_text(
        f"💎 *Оплата товара:* {product['name']}\n"
        f"💰 Цена: {product['price']} ⭐\n\n"
        f"Для оплаты нажмите кнопку ниже:",
        parse_mode="Markdown"
    )
    
    # Отправляем счет на оплату звездами
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=f"Покупка {product['name']}",
        description=f"Приобретение лицензии на {product['name']}",
        payload=f"payment_{product_id}",
        provider_token="",  # Для звезд оставляем пустым
        currency="XTR",  # XTR = Telegram Stars
        prices=[{"label": product['name'], "amount": product['price']}],
        need_name=False,
        need_phone_number=False,
        need_email=False
    )

# Обработка успешной оплаты
async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    
    # Получаем товар
    product = supabase.table("products").select("*").eq("id", product_id).execute()
    
    if product.data:
        product = product.data[0]
        # Отправляем ссылку на товар
        await update.message.reply_text(
            f"✅ *Оплата прошла успешно!*\n\n"
            f"🎁 Ваш товар: *{product['name']}*\n"
            f"🔗 Ссылка для скачивания:\n`{product['download_link']}`\n\n"
            f"Спасибо за покупку!",
            parse_mode="Markdown"
        )
        
        # Логируем покупку в админ-чат
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 Новая покупка!\n"
            f"Пользователь: @{user.username} ({user.id})\n"
            f"Товар: {product['name']}\n"
            f"Сумма: {payment.total_amount} ⭐"
        )

# Команда /redeem - активация ключа
async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎫 *Активация ключа*\n\n"
        "Введите ваш ключ активации:",
        parse_mode="Markdown"
    )
    # Устанавливаем состояние ожидания ключа
    context.user_data['awaiting_key'] = True

# Обработка ввода ключа
async def handle_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_key'):
        return
    
    key = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    # Ищем ключ в БД
    try:
        key_data = supabase.table("redeem_keys").select("*").eq("key_code", key).execute()
        
        if not key_data.data:
            await update.message.reply_text("❌ Неверный ключ активации")
            context.user_data['awaiting_key'] = False
            return
        
        key_info = key_data.data[0]
        
        # Проверяем использован ли ключ
        if key_info['is_used']:
            await update.message.reply_text("❌ Этот ключ уже был использован")
            context.user_data['awaiting_key'] = False
            return
        
        # Проверяем не активировал ли пользователь уже этот товар
        existing = supabase.table("activations").select("*").eq("user_id", user_id).eq("product_id", key_info['product_id']).execute()
        
        if existing.data:
            await update.message.reply_text("❌ Вы уже активировали этот товар ранее")
            context.user_data['awaiting_key'] = False
            return
        
        # Активируем ключ
        supabase.table("redeem_keys").update({
            "is_used": True,
            "used_by": user_id
        }).eq("key_code", key).execute()
        
        # Добавляем в активации
        supabase.table("activations").insert({
            "user_id": user_id,
            "product_id": key_info['product_id']
        }).execute()
        
        # Получаем ссылку на товар
        product = supabase.table("products").select("*").eq("id", key_info['product_id']).execute()
        
        if product.data:
            await update.message.reply_text(
                f"✅ *Ключ успешно активирован!*\n\n"
                f"🎁 Ваш товар: *{product.data[0]['name']}*\n"
                f"🔗 Ссылка:\n`{product.data[0]['download_link']}`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("✅ Ключ активирован! Товар получен.")
        
        context.user_data['awaiting_key'] = False
        
    except Exception as e:
        logger.error(f"Ошибка активации ключа: {e}")
        await update.message.reply_text("❌ Ошибка активации")

# Команда /tech - техподдержка
async def tech_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛠 *Техническая поддержка*\n\n"
        "Опишите вашу проблему одним сообщением.\n"
        "Я передам её администратору.",
        parse_mode="Markdown"
    )
    context.user_data['awaiting_tech'] = True

# Обработка сообщения в техподдержку
async def handle_tech_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_tech'):
        return
    
    user = update.effective_user
    message_text = update.message.text
    
    # Отправляем админу
    await context.bot.send_message(
        ADMIN_CHAT_ID,
        f"🛠 *Новое обращение в ТП*\n"
        f"👤 Пользователь: @{user.username} ({user.id})\n"
        f"📝 Сообщение:\n{message_text}",
        parse_mode="Markdown"
    )
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено администратору.\n"
        "Ответ ожидайте в ближайшее время."
    )
    
    context.user_data['awaiting_tech'] = False

# Команда для обновления товаров (для админа)
async def admin_update_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    await update.message.reply_text("✅ Бот обновит список товаров при следующем /list")

async def main():
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
    
    # Оплата
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    
    # Запуск
    await application.run_polling()

if __name__ == "__main__":
    from telegram.ext import PreCheckoutQueryHandler
    asyncio.run(main())