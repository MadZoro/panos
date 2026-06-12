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
    logger.error("❌ Ошибка: не все переменные окружения заданы!")
    exit(1)

logger.info(f"✅ Бот запущен")
logger.info(f"👨‍💼 Admin ID: {ADMIN_CHAT_ID}")

# Headers для Supabase
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json"
}

def supabase_request(method: str, table: str, params: dict = None, data: dict = None):
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
        return response.json() if response.status_code < 400 else None
    except Exception as e:
        logger.error(f"❌ Request error: {e}")
        return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Регистрация пользователя
    existing = supabase_request("get", "users", params={"user_id": f"eq.{user.id}"})
    if not existing:
        supabase_request("post", "users", data={
            "user_id": user.id,
            "username": user.username or "no_username",
            "ip_address": f"telegram_{user.id}",
            "registered_at": datetime.now().isoformat()
        })
        logger.info(f"✅ Новый пользователь: {user.id} (@{user.username})")
    
    welcome_text = f"""
╔══════════════════════════════════════╗
║                                      ║
║     🔥 *ДОБРО ПОЖАЛОВАТЬ В* 🔥       ║
║     🛡️ *H A C K . N E T* 🛡️         ║
║                                      ║
║   *Ваш надёжный магазин*             ║
║   *программного обеспечения*         ║
║                                      ║
╚══════════════════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

📋 *Доступные команды:*

🔹 `/list` - 📦 Список товаров
🔹 `/redeem` - 🎫 Активировать ключ  
🔹 `/tech` - 🛠️ Техническая поддержка

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

💎 *Приобретайте только качественное ПО!*
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

# Команда /list
async def list_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        products = supabase_request("get", "products")
        
        if not products:
            await update.message.reply_text(
                "❌ *В каталоге пока нет товаров*\n\n"
                "Загляните позже! 🔄",
                parse_mode="Markdown"
            )
            return
        
        keyboard = []
        for product in products:
            button = InlineKeyboardButton(
                f"📦 {product['name']} — {product['price']} ⭐",
                callback_data=f"buy_{product['id']}"
            )
            keyboard.append([button])
        
        text = f"""
╔════════════════════════════╗
║      🛒 *КАТАЛОГ ТОВАРОВ*     ║
║      📦 *HACK.NET STORE*      ║
╚════════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

📌 *Всего товаров:* {len(products)} шт.

🎯 *Выберите товар для покупки:*
"""
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /list: {e}")
        await update.message.reply_text("❌ *Ошибка загрузки товаров*", parse_mode="Markdown")

# Команда /redeem
async def redeem_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
╔═══════════════════════════╗
║     🎫 *АКТИВАЦИЯ КЛЮЧА*     ║
║     🔑 *HACK.NET*            ║
╚═══════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

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
    
    key_data = supabase_request("get", "redeem_keys", params={"key_code": f"eq.{key}"})
    
    if not key_data:
        await update.message.reply_text("❌ *Неверный ключ активации*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    key_info = key_data[0]
    
    if key_info.get('is_used'):
        await update.message.reply_text("❌ *Этот ключ уже был использован*", parse_mode="Markdown")
        context.user_data['awaiting_key'] = False
        return
    
    existing = supabase_request("get", "activations", params={
        "user_id": f"eq.{user_id}",
        "product_id": f"eq.{key_info['product_id']}"
    })
    
    if existing:
        await update.message.reply_text("❌ *Вы уже активировали этот товар ранее*", parse_mode="Markdown")
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
        success_text = f"""
╔═══════════════════════════╗
║    ✅ *КЛЮЧ АКТИВИРОВАН*     ║
║    🎉 *HACK.NET*            ║
╚═══════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

🎁 *Товар:* {product['name']}

🔗 *Ссылка для скачивания:*
`{product['download_link']}`

💾 *Сохраните ссылку!*

🙏 *Спасибо за покупку в HACK.NET!*
"""
        await update.message.reply_text(success_text, parse_mode="Markdown")
    else:
        await update.message.reply_text("✅ *Ключ активирован!*", parse_mode="Markdown")
    
    context.user_data['awaiting_key'] = False

# Команда /tech
async def tech_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
╔═══════════════════════════╗
║   🛠️ *ТЕХНИЧЕСКАЯ ПОДДЕРЖКА* ║
║   💬 *HACK.NET HELP*         ║
╚═══════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

📝 *Опишите вашу проблему*

✏️ *Отправьте одним сообщением*

────────────────────────────

⏳ *Ожидайте ответа администратора*

💡 *Напишите как можно подробнее:*
• Что вы хотели купить?
• Какая ошибка возникла?
• Скриншот (если есть)
"""
    await update.message.reply_text(text, parse_mode="Markdown")
    context.user_data['awaiting_tech'] = True
    logger.info(f"📝 Пользователь {update.effective_user.id} начал обращение в ТП")

# Обработка сообщения в техподдержку
async def handle_tech_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_tech'):
        return
    
    user = update.effective_user
    message_text = update.message.text
    
    logger.info(f"📨 Получено сообщение в ТП от @{user.username}")
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"""
🛠️ *НОВОЕ ОБРАЩЕНИЕ В ТП* 
🏪 *HACK.NET*

━━━━━━━━━━━━━━━━━━━━━━

👤 *Пользователь:* @{user.username}
🆔 *ID:* `{user.id}`
👣 *Имя:* {user.first_name or "Не указано"}

━━━━━━━━━━━━━━━━━━━━━━

📝 *Сообщение:*
{message_text}

━━━━━━━━━━━━━━━━━━━━━━

🕐 *Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

💡 *Ответьте в этот чат, бот перешлёт пользователю*
""",
            parse_mode="Markdown"
        )
        logger.info(f"✅ Сообщение отправлено админу {ADMIN_CHAT_ID}")
        
        confirm_text = """
╔═══════════════════════════╗
║   ✅ *СООБЩЕНИЕ ОТПРАВЛЕНО*  ║
║   📬 *HACK.NET SUPPORT*      ║
╚═══════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

👨‍💻 *Администратор свяжется с вами*

⏳ *Ожидайте ответа в ближайшее время*

────────────────────────────

🙏 *Спасибо за обращение в HACK.NET!*
"""
        await update.message.reply_text(confirm_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при отправке админу: {e}")
        await update.message.reply_text(
            "❌ *Ошибка при отправке сообщения*\n\n"
            "Попробуйте позже или свяжитесь напрямую: @hacknet_support",
            parse_mode="Markdown"
        )
    
    context.user_data['awaiting_tech'] = False

# Обработка покупки товара
async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        title=f"Покупка в HACK.NET",
        description=f"{product['name']} - лицензия",
        payload=f"payment_{product_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=product['name'], amount=product['price'])],
        need_name=False,
        need_phone_number=False,
        need_email=False
    )

async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    payment = update.message.successful_payment
    product_id = int(payment.invoice_payload.split("_")[1])
    
    product_data = supabase_request("get", "products", params={"id": f"eq.{product_id}"})
    
    if product_data:
        product = product_data[0]
        
        success_text = f"""
╔════════════════════════════╗
║     ✅ *ОПЛАТА ПРОШЛА*       ║
║     ✅ *УСПЕШНО!*            ║
║     🏪 *HACK.NET*            ║
╚════════════════════════════╝

▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️

🎁 *Ваш товар:* {product['name']}

🔗 *Ссылка для скачивания:*
`{product['download_link']}`

💾 *Сохраните ссылку!*

────────────────────────────

🙏 *Спасибо за покупку в HACK.NET!*
"""
        await update.message.reply_text(success_text, parse_mode="Markdown")
        
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"💰 *НОВАЯ ПОКУПКА!*\n"
            f"🏪 *HACK.NET*\n\n"
            f"👤 *Пользователь:* @{user.username} ({user.id})\n"
            f"📦 *Товар:* {product['name']}\n"
            f"⭐ *Сумма:* {payment.total_amount} звезд",
            parse_mode="Markdown"
        )

# Диагностическая команда
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    products = supabase_request("get", "products")
    products_count = len(products) if products else 0
    
    info = f"""
╔════════════════════════════╗
║     📊 *ДИАГНОСТИКА*         ║
║     🏪 *HACK.NET*            ║
╚════════════════════════════╝

👤 *Ваш ID:* `{user_id}`
👨‍💼 *Admin ID:* `{ADMIN_CHAT_ID}`

📦 *Товаров в БД:* {products_count} шт.

🔄 *Статус:* {'✅ Работает' if products is not None else '❌ Ошибка'}

💡 *Если товаров 0, проверьте:*
• Есть ли данные в таблице 'products'
• RLS политики Supabase
"""
    await update.message.reply_text(info, parse_mode="Markdown")

# ЗАПУСК
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
    
    logger.info("🚀 HACK.NET бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
