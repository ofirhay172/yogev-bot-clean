"""
Main entry point for the Calorico nutrition bot.

This module initializes and runs the Telegram bot with all necessary handlers
and conversation flows for nutrition management.
"""

import asyncio
import json
import logging
import os
import datetime
import requests

# Load environment variables from .env file (if available)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, continue without it
    pass

from telegram import Update
from telegram.ext import CallbackQueryHandler
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from config import (
    ACTIVITY,
    ACTIVITY_TYPE,
    ACTIVITY_FREQUENCY,
    ACTIVITY_DURATION,
    TRAINING_TIME,
    CARDIO_GOAL,
    STRENGTH_GOAL,
    SUPPLEMENTS,
    SUPPLEMENT_TYPES,
    LIMITATIONS,
    MIXED_ACTIVITIES,
    MIXED_FREQUENCY,
    MIXED_DURATION,
    MIXED_MENU_ADAPTATION,
    ACTIVITY_TYPES_SELECTION,
    ALLERGIES,
    DIET,
    GENDER,
    AGE,
    HEIGHT,
    WEIGHT,
    GOAL,
    BODY_FAT_CURRENT,
    BODY_FAT_TARGET_GOAL,
    WATER_REMINDER_OPT_IN,
    SCHEDULE,
    MENU,
    NAME,
    USERS_FILE,
    DB_NAME,
)
from handlers import (
    start,
    get_name,
    get_gender,
    get_age,
    get_height,
    get_weight,
    get_goal,
    get_body_fat_current,
    get_body_fat_target_goal,
    get_activity,
    get_activity_type,
    get_activity_frequency,
    get_activity_duration,
    get_training_time,
    get_cardio_goal,
    get_strength_goal,
    get_supplements,
    get_supplement_types,
    get_limitations,
    get_mixed_activities,
    get_mixed_frequency,
    get_mixed_duration,
    get_mixed_menu_adaptation,
    handle_activity_types_selection,
    get_diet,
    get_allergies,
    ask_water_reminder_opt_in,
    set_water_reminder_opt_in,
    start_water_reminder_loop_with_buttons,
    send_water_reminder,
    cancel_water_reminders,
    daily_menu,
    eaten,
    handle_daily_choice,
    send_summary,
    schedule_menu,
    check_dessert_permission,
    after_questionnaire,
    handle_free_text_input,
    help_command,
    generate_personalized_menu,
    show_daily_menu,
    water_intake_start,
    water_intake_amount,
    remind_in_10_minutes,
    handle_report_request,
    handle_update_personal_details_response,
    handle_help,
    handle_help_action,
    reset_command,
    handle_reset_confirmation,
)
from utils import build_main_keyboard
from db import NutritionDB

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Initialize database
nutrition_db = NutritionDB()

# File paths
DAILY_MENUS_FILE = "daily_menus.json"


async def daily_menu_scheduler(context):
    """שולח תפריט יומי למשתמשים שנרשמו לכך, בשעה שנבחרה."""
    try:
        now = datetime.datetime.now()
        current_hour = now.strftime("%H:00")
        current_date = now.date().isoformat()
        
        # קבל את כל המשתמשים מהמסד
        all_users = nutrition_db.get_all_users()
        
        for user_id, user_data in all_users.items():
            try:
                # בדוק אם המשתמש השלים את הסקר
                if not user_data.get("flow", {}).get("setup_complete", False):
                    logger.info(f"User {user_id} has not completed setup, skipping daily menu")
                    continue
                
                # בדוק אם המשתמש רשום לתפריט אוטומטי
                if not user_data.get("daily_menu_enabled", False):
                    continue
                    
                # בדוק אם השעה מתאימה
                preferred_hour = user_data.get("preferred_menu_hour")
                if preferred_hour != current_hour:
                    continue
                
                # בדוק אם כבר נשלח היום
                last_menu_sent = user_data.get("last_menu_sent")
                if last_menu_sent:
                    try:
                        last_sent_date = datetime.datetime.fromisoformat(last_menu_sent).date()
                        if last_sent_date >= now.date():
                            logger.info(f"Menu already sent today for user {user_id}")
                            continue
                    except Exception as e:
                        logger.error(f"Error parsing last_menu_sent for user {user_id}: {e}")
                
                # בדוק אם המשתמש בחר "מעדיף לבקש לבד"
                if preferred_hour == "מעדיף לבקש לבד":
                    continue
                
                # שלח תקציב קלוריות
                calorie_budget = user_data.get("calorie_budget", 0)
                calorie_msg = f"📌 תקציב הקלוריות היומי שלך: {calorie_budget} קלוריות"
                
                try:
                    calorie_message = await context.bot.send_message(
                        chat_id=user_id,
                        text=calorie_msg,
                    )
                    
                    # הצמד הודעה
                    try:
                        chat = await context.bot.get_chat(user_id)
                        await chat.pin_message(calorie_message.message_id)
                    except Exception as e:
                        logger.error(f"Error pinning calorie message for user {user_id}: {e}")
                        
                except Exception as e:
                    logger.error(f"Error sending calorie message to user {user_id}: {e}")
                    continue
                
                # שלח הודעת תפריט יומי
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text="🍽️ התפריט היומי שלך מוכן! לחץ על 'לקבלת תפריט יומי מותאם אישית'",
                        reply_markup=build_main_keyboard(),
                    )
                except Exception as e:
                    logger.error(f"Error sending menu notification to user {user_id}: {e}")
                    continue
                
                # עדכן את מספר היום
                current_day = user_data.get("flow", {}).get("day_count", 0)
                user_data["flow"] = {
                    "stage": "tracking", 
                    "setup_complete": True,
                    "day_count": current_day + 1
                }
                
                # תעד מועד שליחה במסד
                user_data["last_menu_sent"] = now.isoformat()
                # איפוס כפתור התפריט היומי כדי שיופיע מחר
                user_data["menu_sent_today"] = True
                user_data["menu_sent_date"] = now.date().isoformat()
                nutrition_db.save_user(user_id, user_data)
                
                logger.info(f"Sent daily menu to user {user_id}")
                
            except Exception as e:
                logger.error(f"Error processing user {user_id} in daily menu scheduler: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error in daily menu scheduler: {e}")


def start_scheduler(application):
    """מתחיל את ה-scheduler לשליחת תפריטים אוטומטיים."""
    job_queue = application.job_queue
    
    # הפעל את הבדיקה כל 10 דקות
    job_queue.run_repeating(
        daily_menu_scheduler,
        interval=datetime.timedelta(minutes=10),
        first=datetime.timedelta(seconds=30)  # התחל אחרי 30 שניות
    )
    
    logger.info("Daily menu scheduler started - checking every 10 minutes")


def delete_webhook():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("[ERROR] TELEGRAM_TOKEN not found in environment")
        return
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    response = requests.post(url)
    print(f"[WEBHOOK DELETE] {response.status_code} - {response.text}")


def main():
    delete_webhook()  # שלב 1: מחיקת webhook
    logger.info("[MAIN] Bot main() started")
    logger.info(f"[MAIN] Environment: TELEGRAM_TOKEN={'SET' if os.getenv('TELEGRAM_TOKEN') else 'NOT_SET'}")
    logger.info(f"[MAIN] Environment: OPENAI_API_KEY={'SET' if os.getenv('OPENAI_API_KEY') else 'NOT_SET'}")
    
    # Get bot token from environment
    bot_token = os.getenv("TELEGRAM_TOKEN")
    if not bot_token or bot_token == "your_telegram_bot_token_here":
        logger.error("TELEGRAM_TOKEN not found or not properly configured in environment variables")
        logger.error("Please set TELEGRAM_TOKEN in your .env file or environment variables")
        raise ValueError("TELEGRAM_TOKEN not configured")

    # Get OpenAI API key from environment
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.warning("OPENAI_API_KEY not found in environment variables - GPT features will not work")

    # Create application
    try:
        application = Application.builder().token(bot_token).build()
    except Exception as e:
        logger.error(f"Failed to create application: {e}")
        raise

    # ConversationHandler חייב להיות קודם כדי לתפוס הודעות טקסט בזמן השאלון
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gender)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_goal)],
            BODY_FAT_CURRENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_body_fat_current)],
            BODY_FAT_TARGET_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_body_fat_target_goal)],
            ACTIVITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity)],
            ACTIVITY_TYPES_SELECTION: [CallbackQueryHandler(handle_activity_types_selection)],
            ACTIVITY_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity_type)],
            ACTIVITY_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity_frequency)],
            ACTIVITY_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_activity_duration)],
            TRAINING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_training_time)],
            CARDIO_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cardio_goal)],
            STRENGTH_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_strength_goal)],
            SUPPLEMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_supplements)],
            SUPPLEMENT_TYPES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_supplement_types)],
            LIMITATIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_limitations)],
            MIXED_ACTIVITIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mixed_activities)],
            MIXED_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mixed_frequency)],
            MIXED_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mixed_duration)],
            MIXED_MENU_ADAPTATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mixed_menu_adaptation)],
            DIET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_diet)],
            ALLERGIES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_allergies),
                CallbackQueryHandler(get_allergies),
            ],
            WATER_REMINDER_OPT_IN: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_water_reminder_opt_in)],
            SCHEDULE: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_menu)],
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("help", help_command)]
    )
    application.add_handler(conv_handler)

    # Add handlers for main menu options
    menu_regex = r"^(לקבלת תפריט יומי מותאם אישית|מה אכלתי היום|בניית ארוחה לפי מה שיש לי בבית|קבלת דוח|תזכורות על שתיית מים)$"
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(menu_regex),
            handle_daily_choice))

    # Handler לכפתור 'סיימתי להיום' או 'סיימתי' (כולל וריאציות)
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^✅ סיימתי להיום$|^סיימתי( להיום)?[.!]?$"),
            send_summary
        )
    )

    # Add handler for report menu callback
    application.add_handler(CallbackQueryHandler(handle_report_request, pattern=r"^report_(daily|weekly|monthly|smart_feedback)$"))
    
    # Add handler for reset confirmation
    application.add_handler(CallbackQueryHandler(handle_reset_confirmation, pattern=r"^reset_(confirm|cancel)$"))

    # Add handler for help button ("עזרה")
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^עזרה$"),
            handle_help
        )
    )

    # Add handler for help action buttons
    help_action_regex = r"^(שאל שאלה חופשית|שאלי שאלה חופשית|מעבר לשאלון אישי)$"
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(help_action_regex),
            handle_help_action
        )
    )

    # Add handler לכפתור עדכון פרטים אישיים (חייב להיות לפני free text)
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r"^(כן|לא)$"),
            handle_update_personal_details_response
        )
    )

    # Add command handlers
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", show_daily_menu))
    application.add_handler(CommandHandler("reset", reset_command))

    # Add handler for free text input (רק אחרי כל ההנדלרים הספציפיים)
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(menu_regex) & ~filters.Regex(help_action_regex) & ~filters.Regex(r"^(כן|לא)$"),
            handle_free_text_input
        )
    )

    # Handler כללי שמדפיס כל update שמתקבל (רק אחד!)
    async def log_update(update, context):
        logger.info(f"[UPDATE] Received update: {update.update_id} from user {update.effective_user.id if update.effective_user else 'Unknown'}")
    application.add_handler(MessageHandler(filters.ALL, log_update), group=0)

    # Add global error handler
    async def global_error_handler(update, context):
        logger.error("Unhandled exception", exc_info=context.error)
    application.add_error_handler(global_error_handler)

    # Initialize scheduler
    try:
        start_scheduler(application)
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    logger.info("[MAIN] Bot initialized, starting with polling...")
    try:
        logger.info("[MAIN] Starting application with polling...")
        # Use run_polling() which handles everything internally
        application.run_polling()
        logger.info("[MAIN] Application started successfully with polling")
    except Exception as e:
        logger.error(f"[MAIN] Exception in main loop: {e}")
        raise
    finally:
        logger.info("[MAIN] main() is exiting, cleaning up...")
        try:
            # Note: Cannot call async methods in non-async context
            logger.info("[MAIN] Cleanup completed")
        except Exception as e:
            logger.error(f"[MAIN] Error during cleanup: {e}")


if __name__ == "__main__":
    main()
