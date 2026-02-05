import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
import openai

# ===================== SETTINGS =====================
# WARNING: Keep these tokens secret! Consider using environment variables.
BOT_TOKEN = "8304164199:AAE3YgLXsdw61IR_U6QgzRih_dyLPp7Txtg"
OPENAI_KEY = "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"
CHANNEL_ID = -1001234567890  # Replace with your actual channel ID

# Admin control still exists for user management, but guide creation is now public
ADMIN_ID = 123456789           # Your Telegram ID (admin)
STAFF_IDS = [123456789]        # List of staff (if needed for other restricted features)

# Database (simple in-memory)
GUIDES_DB = {}  # key: guide_title, value: dict with text, images

openai.api_key = OPENAI_KEY

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===================== AI GUIDE GENERATOR =====================
def generate_guide(title: str):
    prompt = f"Write a clear, step-by-step IT guide for: {title}. Include numbered steps, simple language, and make it easy for staff to follow."
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":prompt}]
    )
    return response.choices[0].message.content

# ===================== COMMANDS =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to IT Knowledge AI Bot! Anyone can now create guides. Send a guide request or type /help for commands.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/guide <title> - Create new guide (Available to all)\n"
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
        guide_text = generate_guide(title)

        # Save in temporary draft
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
        logger.error(f"Error generating guide: {e}")
        await update.message.reply_text("❌ Failed to generate guide. Please check the API configuration.")

# ===================== INLINE BUTTON CALLBACK =====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    action, title = data.split("|", 1)

    if title not in GUIDES_DB:
        await query.edit_message_text("❌ Guide not found or expired.")
        return

    guide = GUIDES_DB[title]

    if action == "approve":
        guide["approved"] = True
        # Post to channel
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📝 *{title}*\n\n{guide['text']}", parse_mode='Markdown')
        # Post images if any
        if guide["images"]:
            media = [InputMediaPhoto(media=img) for img in guide["images"]]
            await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media)
        await query.edit_message_text(f"✅ Guide '{title}' approved and posted to the channel.")
        
    elif action == "edit":
        await query.edit_message_text(f"✏️ Send new text to replace guide '{title}'.")
        context.user_data["edit_title"] = title
        
    elif action == "image":
        await query.edit_message_text(f"🖼️ Send image(s) to attach to guide '{title}'.")
        context.user_data["image_title"] = title
        
    elif action == "cancel":
        del GUIDES_DB[title]
        await query.edit_message_text(f"❌ Guide '{title}' cancelled.")

# ===================== RECEIVE TEXT (FOR EDITING) =====================
async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_title" in context.user_data:
        title = context.user_data.pop("edit_title")
        if title in GUIDES_DB:
            GUIDES_DB[title]["text"] = update.message.text
            
            # Show updated preview with buttons again
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Approve & Post ✅", callback_data=f"approve|{title}")],
                [InlineKeyboardButton("Add Image 🖼️", callback_data=f"image|{title}")],
                [InlineKeyboardButton("Cancel ❌", callback_data=f"cancel|{title}")]
            ])
            await update.message.reply_text(f"✏️ Guide '{title}' updated.\n\n{update.message.text}", parse_mode='Markdown', reply_markup=keyboard)

# ===================== RECEIVE IMAGE =====================
async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "image_title" in context.user_data:
        title = context.user_data["image_title"]
        if title in GUIDES_DB:
            photo_file = update.message.photo[-1].file_id
            GUIDES_DB[title]["images"].append(photo_file)
            await update.message.reply_text(f"🖼️ Image added to guide '{title}'. You can send more or click Approve.")

# ===================== SEARCH EXISTING GUIDES =====================
async def search_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /search <keyword>")
        return

    keyword = " ".join(args).lower()
    results = [title for title in GUIDES_DB if keyword in title.lower()]

    if not results:
        await update.message.reply_text("❌ No guides found in current session.")
        return

    reply = "🔎 Found guides:\n" + "\n".join(results)
    await update.message.reply_text(reply)

# ===================== ADMIN USER MANAGEMENT =====================
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /adduser <telegram_id>")
        return
    try:
        new_user = int(context.args[0])
        if new_user not in STAFF_IDS:
            STAFF_IDS.append(new_user)
        await update.message.reply_text(f"✅ Added user {new_user}")
    except ValueError:
        await update.message.reply_text("❌ Invalid Telegram ID.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Only admin can use this command.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeuser <telegram_id>")
        return
    try:
        user = int(context.args[0])
        if user in STAFF_IDS:
            STAFF_IDS.remove(user)
        await update.message.reply_text(f"✅ Removed user {user}")
    except ValueError:
        await update.message.reply_text("❌ Invalid Telegram ID.")

# ===================== MAIN FUNCTION =====================
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

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
