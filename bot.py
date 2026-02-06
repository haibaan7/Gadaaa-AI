import os
import logging
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# Railway Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_KEY") # Add this in Railway Variables
CHANNEL_ID = -1003761357687 

# Initialize Groq Client
client = Groq(api_key=GROQ_KEY)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

async def create_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /guide <topic>")
        return

    title = " ".join(context.args)
    status_msg = await update.message.reply_text("⚡ Groq is generating your guide...")

    try:
        # Using Llama 3.3 (Fast & Free)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are an IT expert. Create clear, numbered guides."},
                {"role": "user", "content": f"Write a step-by-step IT guide for: {title}"}
            ]
        )
        
        guide_text = completion.choices[0].message.content
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Approve & Post ✅", callback_data=f"post|{title}")]])
        
        # Save to context for the callback
        context.user_data[title] = guide_text
        await update.message.reply_text(f"📝 *Draft*\n\n{guide_text}", parse_mode='Markdown', reply_markup=keyboard)
        await status_msg.delete()

    except Exception as e:
        await update.message.reply_text(f"❌ Groq Error: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action, title = query.data.split("|", 1)
    if action == "post" and title in context.user_data:
        text = context.user_data[title]
        await context.bot.send_message(chat_id=CHANNEL_ID, text=f"📝 *{title}*\n\n{text}", parse_mode='Markdown')
        await query.edit_message_text(f"✅ Posted to channel!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("guide", create_guide))
    app.add_handler(CallbackQueryHandler(button_callback))
    # This clears the conflict by telling Telegram to reset your session
    app.bot.delete_webhook(drop_pending_updates=True)
    app.run_polling()

if __name__ == "__main__":
    main()


