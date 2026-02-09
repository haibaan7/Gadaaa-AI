import asyncio
import logging
import os
from html import escape
from typing import Dict

import groq
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ===================== SETTINGS =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN:
    raise RuntimeError("Missing BOT_TOKEN environment variable")
if not GROQ_KEY:
    raise RuntimeError("Missing GROQ_KEY environment variable")
if not CHANNEL_ID:
    raise RuntimeError("Missing CHANNEL_ID environment variable")

CHANNEL_ID_INT = int(CHANNEL_ID)

# Database (simple in-memory)
GUIDES_DB: Dict[str, Dict] = {}

groq_client = groq.Client(api_key=GROQ_KEY)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ===================== AI GUIDE GENERATOR =====================

def _build_prompt(title: str) -> str:
    return (
        "You are an expert IT support specialist writing internal help guides for a "
        "busy hotel/company IT team. Create a professional, step-by-step guide in "
        "clear, concise language. Use numbered steps. Include a short overview, "
        "prerequisites, and a brief troubleshooting section. Keep it practical and "
        "actionable for staff. Title: "
        f"{title}"
    )


def _generate_guide_sync(title: str) -> str:
    prompt = _build_prompt(title)
    response = groq_client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    content = response.choices[0].message.content
    if not content:
        logger.error("Groq API returned empty content for title: %s", title)
        return "Failed to generate guide. Please try again later."
    return content


async def generate_guide(title: str) -> str:
    try:
        return await asyncio.to_thread(_generate_guide_sync, title)
    except Exception as exc:
        logger.exception("Groq API error: %s", exc)
        return "Error generating guide. Please try again later."

# ===================== ACCESS CONTROL =====================


def _is_private_chat(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat and chat.type == "private")


async def _reject_if_not_allowed(update: Update) -> bool:
    if not _is_private_chat(update):
        return True
    return False

# ===================== COMMANDS =====================


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return
    await update.message.reply_text(
        "Welcome to IT Knowledge AI Bot! Use /guide <topic> to generate a guide."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return
    await update.message.reply_text(
        "/guide <title> - Create new guide\n"
        "/search <keyword> - Search existing guides"
    )

# ===================== STAFF GUIDE CREATION =====================


async def create_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /guide <guide title>")
        return

    user_id = update.effective_user.id
    title = " ".join(args).strip()
    await update.message.reply_text(f"Generating guide for: {title}...")

    guide_text = await generate_guide(title)

    GUIDES_DB[title] = {
        "text": guide_text,
        "images": [],
        "approved": False,
        "creator": user_id,
    }

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Approve & Post ✅", callback_data=f"approve|{title}")],
            [InlineKeyboardButton("Edit ✏️", callback_data=f"edit|{title}")],
            [InlineKeyboardButton("Add Image 🖼️", callback_data=f"image|{title}")],
            [InlineKeyboardButton("Cancel ❌", callback_data=f"cancel|{title}")],
        ]
    )

    preview = f"<b>Guide Draft:</b> {escape(title)}\n\n{escape(guide_text)}"
    await update.message.reply_text(preview, parse_mode="HTML", reply_markup=keyboard)

# ===================== INLINE BUTTON CALLBACK =====================


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return

    query = update.callback_query
    await query.answer()

    data = query.data
    action, title = data.split("|", 1)

    if title not in GUIDES_DB:
        await query.edit_message_text("Guide not found or expired.")
        return

    guide = GUIDES_DB[title]

    if action == "approve":
        guide["approved"] = True
        title_html = escape(title)
        text_html = escape(guide["text"])
        message_html = f"<b>{title_html}</b>\n\n{text_html}"

        await context.bot.send_message(
            chat_id=guide["creator"],
            text=message_html,
            parse_mode="HTML",
        )
        await context.bot.send_message(
            chat_id=CHANNEL_ID_INT,
            text=message_html,
            parse_mode="HTML",
        )

        if guide["images"]:
            media = [InputMediaPhoto(media=img) for img in guide["images"]]
            await context.bot.send_media_group(chat_id=CHANNEL_ID_INT, media=media)
            await context.bot.send_media_group(chat_id=guide["creator"], media=media)

        await query.edit_message_text("Guide approved and posted.")

    elif action == "edit":
        context.user_data["edit_title"] = title
        await query.edit_message_text(f"Send new text to replace guide '{title}'.")

    elif action == "image":
        context.user_data["image_title"] = title
        await query.edit_message_text(f"Send image(s) to attach to guide '{title}'.")

    elif action == "cancel":
        GUIDES_DB.pop(title, None)
        await query.edit_message_text(f"Guide '{title}' cancelled.")

# ===================== RECEIVE TEXT (FOR EDITING) =====================


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return

    if "edit_title" in context.user_data:
        title = context.user_data.pop("edit_title")
        if title in GUIDES_DB:
            GUIDES_DB[title]["text"] = update.message.text
            await update.message.reply_text(
                f"Guide '{title}' updated. Click Approve to post."
            )
        return

# ===================== RECEIVE IMAGE =====================


async def receive_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return

    if "image_title" in context.user_data:
        title = context.user_data["image_title"]
        if title in GUIDES_DB:
            photo_file = update.message.photo[-1].file_id
            GUIDES_DB[title]["images"].append(photo_file)
            await update.message.reply_text(
                f"Image added to guide '{title}'. Click Approve to post."
            )

# ===================== SEARCH EXISTING GUIDES =====================


async def search_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _reject_if_not_allowed(update):
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /search <keyword>")
        return

    keyword = " ".join(args).lower()
    results = [title for title in GUIDES_DB if keyword in title.lower()]

    if not results:
        await update.message.reply_text("No guides found.")
        return

    reply = "Found guides:\n" + "\n".join(results)
    await update.message.reply_text(reply)

# ===================== STARTUP HOOK =====================


async def on_startup(app):
    await app.bot.delete_webhook(drop_pending_updates=True)

# ===================== MAIN FUNCTION =====================


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("help", help_command, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("guide", create_guide, filters=filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("search", search_guide, filters=filters.ChatType.PRIVATE))

    app.add_handler(
        MessageHandler(
            filters.TEXT & (~filters.COMMAND) & filters.ChatType.PRIVATE, receive_text
        )
    )
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, receive_image))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
