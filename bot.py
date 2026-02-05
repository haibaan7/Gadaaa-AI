import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from openai import OpenAI  # NEW: Updated import for latest OpenAI SDK

# ===================== SETTINGS =====================
# IMPORTANT: Keep these private. Consider using environment variables for safety.
BOT_TOKEN = "8304164199:AAE3YgLXsdw61IR_U6QgzRih_dyLPp7Txtg"
OPENAI_KEY = "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"
CHANNEL_ID = -1003761357687  # Replace with your actual channel ID

# Admin control (restricted features like adding/removing users)
ADMIN_ID = 123456789           # Your Telegram ID (admin)
STAFF_IDS = [123456789]        # List of staff IDs

# Database (simple in-memory)
GUIDES_DB = {}  # key: guide_title, value: dict with text, images

# NEW: Initialize the OpenAI Client
client = OpenAI(api_key=OPENAI_KEY)

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== AI GUIDE GENERATOR =====================
def generate_guide(title: str):
    prompt = f"Write a clear, step-by-step IT guide for: {title}. Include numbered steps, simple language, and make it easy for staff to follow."
    
    # NEW: Updated method for latest OpenAI library (v1.0.0+)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to IT Knowledge AI Bot! Anyone can create guides. Type /guide <topic> to start.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/guide <title> - Create new guide (Public)\n"
        "/search <keyword> - Search existing guides\n"
        "/adduser <telegram_id> - Admin only\n"
        "/removeuser <telegram_id> - Admin only"
    )

# ===================== GUIDE CREATION (OPEN TO ALL) =====================
async def create_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /guide <guide title>")
        return

    title = " ".join(args)
    await update.message.reply_text(f"✍️ Generating guide for: {title}...")

    try:
        # Generate the content using the new client method
        guide_text = generate_guide(title)

        # Store in temp draft
        GUIDES_DB[title] = {"text": guide_text, "images": [], "approved": False, "creator": user_id}

        # Send preview to the user
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Approve & Post ✅", callback_data=f"approve|{title}")],
            [InlineKeyboardButton("Edit ✏️", callback_data=f"edit|{title}")],
            [InlineKeyboardButton("Add Image 🖼️", callback_data=f"image|{title}")],
            [InlineKeyboardButton("Cancel ❌", callback_data=f"cancel|{title}")]
        ])
        await update.message.reply_text(f"📝 *Guide Draft: {title}*\n\n{guide_text}", parse_mode='Markdown', reply_markup=keyboard)
    
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Failed to generate guide. Ensure your OpenAI API key is active and has credits.")

# ===================== INLINE BUTTON CALLBACK =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, title = data.split("|", 1)

    if title not in GUIDES_DB:
        await query.edit_message_text("❌ Guide not found or session expired.")
        return

    guide = GUIDES_DB[title]

    if action == "approve":
        guide["approved"] = True
        # Post text to channel
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📝 *{title}*\n\n{guide['text']}", parse_mode='Markdown')
        # Post images to channel if any
        if guide["images"]:
            media = [InputMediaPhoto(media=img) for img in guide["images"]]
            await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media)
        await query.edit_message_text(f"✅ Guide '{title}' posted to channel.")
        
    elif action == "edit":
        await query.edit_message_text(f"✏️ Send new text to replace the content of '{title}'.")
        context.user_data["edit_title"] = title
        
    elif action == "image":
        await query.edit_message_text(f"🖼️ Send an image to attach to '{title}'.")
        context.user_data["image_title"] = title
        
    elif action == "cancel":
        del GUIDES_DB[title]
        await query.edit_message_text(f"❌ Guide '{title}' cancelled.")

# ===================== MESSAGE HANDLERS =====================
async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_title" in context.user_data:
        title = context.user_data.pop("edit_title")
        if title in GUIDES_DB:
            GUIDES_DB[title]["text"] = update.message.text
            await update.message.reply_text(f"✏️ Guide '{title}' updated! Click 'Approve' on the original draft to post.")

async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "image_title" in context.user_data:
        title = context.user_data["image_title"]
        if title in GUIDES_DB:
            photo_file = update.message.photo[-1].file_id
            GUIDES_DB[title]["images"].append(photo_file)
            await update.message.reply_text(f"🖼️ Image added to '{title}'. You can send more or click Approve.")

async def search_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /search <keyword>")
        return
    keyword = " ".join(args).lower()
    results = [t for t in GUIDES_DB if keyword in t.lower()]
    if not results:
        await update.message.reply_text("❌ No guides found in current memory.")
        return
    await update.message.reply_text("🔎 Found:\n" + "\n".join(results))

# ===================== ADMIN TOOLS =====================
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    try:
        new_id = int(context.args[0])
        if new_id not in STAFF_IDS: STAFF_IDS.append(new_id)
        await update.message.reply_text(f"✅ User {new_id} added.")
    except:
        await update.message.reply_text("❌ Usage: /adduser <id>")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(context.args[0])
        if uid in STAFF_IDS: STAFF_IDS.remove(uid)
        await update.message.reply_text(f"✅ User {uid} removed.")
    except:
        await update.message.reply_text("❌ Usage: /removeuser <id>")

# ===================== RUN BOT =====================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("guide", create_guide))
    app.add_handler(CommandHandler("search", search_guide))
    app.add_handler(CommandHandler("adduser", add_user))
    app.add_handler(CommandHandler("removeuser", remove_user))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), receive_text))
    app.add_handler(MessageHandler(filters.PHOTO, receive_image))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot is live...")
    app.run_polling()

if __name__ == "__main__":
    main()
