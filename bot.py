import os
import logging
from google import genai  # Updated for 2026 SDK
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================== SETTINGS =====================
# Railway will pull these from your "Variables" tab
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
CHANNEL_ID = -1003761357687 

# Initialize the 2026 Gemini Client
client = genai.Client(api_key=GEMINI_KEY)

# Simple in-memory storage (Resets when Railway redeploys)
GUIDES_DB = {} 

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== AI GENERATOR =====================
def generate_guide(title: str):
    prompt = f"Write a clear, step-by-step IT guide for: {title}. Include numbered steps."
    # Gemini 2.0 Flash is the best free-tier model for 2026
    response = client.models.generate_content(
        model='gemini-1.5-flash', 
        contents=prompt
    )
    return response.text

# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is online on Railway! Use /guide <topic> to start.")

async def create_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /guide <title>")
        return

    title = " ".join(args)
    status_msg = await update.message.reply_text("✍️ Gemini is writing...")

    try:
        guide_text = generate_guide(title)
        GUIDES_DB[title] = {"text": guide_text}

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Approve & Post ✅", callback_data=f"approve|{title}")],
            [InlineKeyboardButton("Cancel ❌", callback_data=f"cancel|{title}")]
        ])
        
        await update.message.reply_text(f"📝 *Draft: {title}*\n\n{guide_text}", parse_mode='Markdown', reply_markup=keyboard)
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Error. Check Railway logs for details.")

# ===================== CALLBACKS =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, title = query.data.split("|", 1)

    if action == "approve" and title in GUIDES_DB:
        guide = GUIDES_DB[title]
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📝 *{title}*\n\n{guide['text']}", parse_mode='Markdown')
        await query.edit_message_text(f"✅ Posted '{title}' to channel!")
    elif action == "cancel":
        await query.edit_message_text("❌ Cancelled.")

# ===================== RUN BOT =====================
def main():
    if not BOT_TOKEN:
        print("CRITICAL ERROR: BOT_TOKEN is missing!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("guide", create_guide))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot is starting up...")
    app.run_polling()

if __name__ == "__main__":
    main()

