from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler
from app.config import settings
import asyncio


async def start_command(update, context):
    """Обработчик команды /start"""
    keyboard = [[InlineKeyboardButton(
        "Открыть магазин",
        web_app={'url': settings.frontend_url}
    )]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        'Добро пожаловать в магазин одежды!',
        reply_markup=reply_markup
    )


async def init_bot():
    """Инициализация Telegram бота"""
    application = Application.builder().token(settings.telegram_bot_token).build()
    
    application.add_handler(CommandHandler("start", start_command))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("Telegram bot started")
    return application


def run_bot():
    """Запуск бота в отдельном потоке"""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(init_bot())
        loop.run_forever()
    except Exception as e:
        print(f"Bot error: {e}")
        loop.close()

