import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL
import requests
import json

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text('مرحباً! أنا المساعد الأكاديمي للجامعة. كيف يمكنني مساعدتك اليوم؟')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_text = """
يمكنني مساعدتك في:
- معرفة معلومات عن المواد الدراسية
- عرض جدول المحاضرات
- معرفة المعدل التراكمي
- عرض المواد المسجلة
- الإجابة على الأسئلة الأكاديمية

ما الذي تريد معرفته؟
    """
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and forward them to Rasa."""
    try:
        # Get the message text
        message = update.message.text
        
        # Forward the message to Rasa
        rasa_response = requests.post(
            "http://localhost:5005/webhooks/rest/webhook",
            json={"message": message, "sender": str(update.effective_user.id)}
        )
        
        # Get the response from Rasa
        rasa_response_json = rasa_response.json()
        
        # Send the response back to the user
        for response in rasa_response_json:
            if 'text' in response:
                await update.message.reply_text(response['text'])
            if 'image' in response:
                await update.message.reply_photo(response['image'])
                
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        await update.message.reply_text("عذراً، حدث خطأ في معالجة رسالتك. يرجى المحاولة مرة أخرى.")

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()