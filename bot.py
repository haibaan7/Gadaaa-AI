import os
import logging
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# ===================== SETTINGS =====================
BOT_TOKEN = "8304164199:AAE3YgLXsdw61IR_U6QgzRih_dyLPp7Txtg"
GEMINI_KEY = "AIzaSyA5AEjwwIw1t9tVlrHxf6xu5tTCJr_cdzg" # Paste your AI Studio key here
CHANNEL_ID = -1003761357687 

ADMIN_ID = 123456789 
STAFF_IDS = [123456789] 

# Database (simple in-memory)
GUIDES_DB = {} 

# NEW: Configure Gemini
genai.configure(api_key=GEMINI_KEY)
# We use gemini-2.5-flash for the best speed/free balance
model = genai.GenerativeModel('gemini-2.5-flash')

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================== AI GUIDE GENERATOR (GEMINI) =====================
def generate_guide(title: str):
    prompt = f"Write a clear, step-by-step IT guide for: {title}. Include numbered steps and simple language."
    
    # Gemini's generation method
    response = model.generate_content(prompt)
    return response.text

# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Anyone can now create IT guides using Gemini AI. Type /guide <topic>.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/guide <title> - Create new guide\n"
        "/search <keyword> - Search drafts\n"
        "/adduser <id> - Admin only"
    )

# ===================== GUIDE CREATION (OPEN TO ALL) =====================
async def create_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /guide <title>")
        return

    title = " ".join(args)
    status_msg = await update.message.reply_text(f"✍️ Gemini is thinking: {title}...")

    try:
        guide_text = generate_guide(title)
        GUIDES_DB[title] = {"text": guide_text, "images": [], "approved": False, "creator": user_id}

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Approve & Post ✅", callback_data=f"approve|{title}")],
            [InlineKeyboardButton("Edit ✏️", callback_data=f"edit|{title}")],
            [InlineKeyboardButton("Add Image 🖼️", callback_data=f"image|{title}")],
            [InlineKeyboardButton("Cancel ❌", callback_data=f"cancel|{title}")]
        ])
        await update.message.reply_text(f"📝 *Draft: {title}*\n\n{guide_text}", parse_mode='Markdown', reply_markup=keyboard)
        await status_msg.delete()
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        await update.message.reply_text("❌ Gemini is currently busy or the API key is invalid.")

# ===================== INLINE CALLBACKS =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, title = query.data.split("|", 1)

    if title not in GUIDES_DB:
        await query.edit_message_text("❌ Draft expired.")
        return

    guide = GUIDES_DB[title]

    if action == "approve":
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📝 *{title}*\n\n{guide['text']}", parse_mode='Markdown')
        if guide["images"]:
            media = [InputMediaPhoto(media=img) for img in guide["images"]]
            await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media)
        await query.edit_message_text(f"✅ Posted '{title}' to channel.")
        
    elif action == "edit":
        await query.edit_message_text(f"✏️ Send the new text for '{title}'.")
        context.user_data["edit_title"] = title
        
    elif action == "image":
        await query.edit_message_text(f"🖼️ Send an image for '{title}'.")
        context.user_data["image_title"] = title
        
    elif action == "cancel":
        del GUIDES_DB[title]
        await query.edit_message_text("❌ Cancelled.")

# ===================== MESSAGE HANDLERS =====================
async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_title" in context.user_data:
        title = context.user_data.pop("edit_title")
        if title in GUIDES_DB:
            GUIDES_DB[title]["text"] = update.message.text
            await update.message.reply_text(f"✅ Text for '{title}' updated.")

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "image_title" in context.user_data:
        title = context.user_data["image_title"]
        if title in GUIDES_DB:
            GUIDES_DB[title]["images"].append(update.message.photo[-1].file_id)
            await update.message.reply_text(f"🖼️ Image added to '{title}'.")

# ===================== RUN BOT =====================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("guide", create_guide))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), receive_text))
    app.add_handler(MessageHandler(filters.PHOTO, receive_image))
    
    print("Bot is running on Gemini...")
    app.run_polling()

if __name__ == "__main__":
    main()
