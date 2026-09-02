import asyncio
import logging
import os
import sys
import uuid
from typing import Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import Config
from database import Database
from openrouter_client import OpenRouterClient
from post_formatter import create_template_post, format_context_length, format_price

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OpenRouterBot")

# Initialize core services
db = Database()
or_client = OpenRouterClient()

# In-memory session tracking for admin actions
# user_id -> {"state": "waiting_refine" | "waiting_edit", "draft_id": str}
user_sessions: dict[int, dict] = {}


def admin_only(func):
    """Decorator to restrict handler to authorized admins only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or not Config.is_admin(user.id):
            if update.callback_query:
                await update.callback_query.answer("⛔ Access denied. You are not authorized.", show_alert=True)
            elif update.message:
                await update.message.reply_text("⛔ <b>Access Denied</b>. This bot is private.", parse_mode=ParseMode.HTML)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


async def get_active_ai_model() -> str:
    """Get active AI model for post generation (from DB or Config)."""
    saved = await db.get_setting("ai_model")
    return saved or Config.DEFAULT_AI_MODEL


async def is_auto_post_enabled() -> bool:
    """Check if auto-post to channel is enabled."""
    saved = await db.get_setting("auto_post")
    if saved is not None:
        return saved.lower() in ("1", "true", "yes")
    return Config.AUTO_POST_TO_CHANNEL


def make_draft_keyboard(draft_id: str) -> InlineKeyboardMarkup:
    """Generate interactive action buttons for a post draft."""
    keyboard = [
        [
            InlineKeyboardButton("🚀 Publish to Channel", callback_data=f"pub:{draft_id}"),
            InlineKeyboardButton("✨ AI Refine", callback_data=f"refine:{draft_id}"),
        ],
        [
            InlineKeyboardButton("✏️ Manual Edit", callback_data=f"edit:{draft_id}"),
            InlineKeyboardButton("🔄 Template Reset", callback_data=f"tmpl:{draft_id}"),
        ],
        [
            InlineKeyboardButton("🗑️ Discard", callback_data=f"del:{draft_id}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_post_message(
    bot,
    chat_id: int | str,
    text: str,
    image_url: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    """Send a Telegram post as a photo with caption, with automatic fallback to text message."""
    if image_url:
        try:
            # Telegram photo caption max length is 1024 chars
            caption_text = text if len(text) <= 1024 else text[:1020] + "..."
            return await bot.send_photo(
                chat_id=chat_id,
                photo=image_url,
                caption=caption_text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.warning("Failed sending as photo (%s). Falling back to text message.", e)

    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
        disable_web_page_preview=False,
    )


CATEGORIES_INFO = {
    "video": {"name": "Video Generators & Models", "emoji": "🎥", "desc": "Video Generation & Video Understanding Models"},
    "audio": {"name": "Voice & Audio Generators", "emoji": "🎙️", "desc": "Voice Synthesis, Text-to-Speech & Speech Models"},
    "image": {"name": "Image & Vision Models", "emoji": "🎨", "desc": "Image Generation, Diffusion & Vision Models"},
    "reasoning": {"name": "Reasoning & Deep Thought", "emoji": "🧩", "desc": "Chain of Thought, Math & Logic Reasoning"},
    "code": {"name": "Coding Specialists", "emoji": "💻", "desc": "Software Engineering & Code Generation"},
    "free": {"name": "100% Free Models", "emoji": "🆓", "desc": "Completely free models on OpenRouter"},
}


def make_categories_menu_keyboard() -> InlineKeyboardMarkup:
    """Generate interactive category selection buttons."""
    keyboard = [
        [
            InlineKeyboardButton("🎥 Video Generators", callback_data="cat:video:0"),
            InlineKeyboardButton("🎙️ Voice & Audio", callback_data="cat:audio:0"),
        ],
        [
            InlineKeyboardButton("🎨 Image & Vision", callback_data="cat:image:0"),
            InlineKeyboardButton("🧩 Reasoning (CoT)", callback_data="cat:reasoning:0"),
        ],
        [
            InlineKeyboardButton("💻 Coding Models", callback_data="cat:code:0"),
            InlineKeyboardButton("🆓 100% Free Models", callback_data="cat:free:0"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def render_category_page(category_key: str, page: int = 0, page_size: int = 6):
    """Render paginated category view with model drafts and navigation buttons."""
    cat_info = CATEGORIES_INFO.get(category_key, {"name": category_key.capitalize(), "emoji": "📂"})
    models = await or_client.filter_by_category(category_key)
    total = len(models)

    if total == 0:
        text = f"{cat_info['emoji']} <b>{cat_info['name']}</b>\n\nNo models found in this category at this time."
        keyboard = [[InlineKeyboardButton("📂 Back to Categories", callback_data="show_cats")]]
        return text, InlineKeyboardMarkup(keyboard)

    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start_idx = page * page_size
    page_models = models[start_idx : start_idx + page_size]

    text = (
        f"{cat_info['emoji']} <b>{cat_info['name']}</b>\n"
        f"<i>Page {page + 1}/{total_pages} • Total: {total} models</i>\n\n"
    )

    keyboard = []
    for i, m in enumerate(page_models, start=start_idx + 1):
        m_id = m.get("id", "")
        name = m.get("name", m_id)
        ctx = format_context_length(m.get("context_length"))
        pricing = m.get("pricing") or {}
        p_in = format_price(pricing.get("prompt"))
        p_out = format_price(pricing.get("completion"))

        text += (
            f"<b>{i}. {name}</b>\n"
            f"   ID: <code>{m_id}</code>\n"
            f"   Context: <code>{ctx}</code> | Price: {p_in} / {p_out}\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"✨ Draft: {name[:18]}", callback_data=f"genpost:{m_id}"),
            InlineKeyboardButton("ℹ️ Details", callback_data=f"minfo:{m_id}"),
        ])

    # Navigation buttons
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"cat:{category_key}:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton("📂 All Categories", callback_data="show_cats"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"cat:{category_key}:{page + 1}"))

    keyboard.append(nav_buttons)
    return text, InlineKeyboardMarkup(keyboard)


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message and bot status."""
    total_models = await db.get_total_seen_count()
    auto_post = await is_auto_post_enabled()
    ai_model = await get_active_ai_model()
    channel = Config.TELEGRAM_CHANNEL_ID or "<i>Not configured</i>"

    text = (
        "🤖 <b>OpenRouter Model Monitor & Channel Bot</b>\n\n"
        "Welcome! This bot automatically tracks new models on OpenRouter, "
        "generates stylish channel posts, and allows interactive AI refinement.\n\n"
        "📊 <b>Current Status:</b>\n"
        f"• <b>Tracked Models:</b> <code>{total_models}</code>\n"
        f"• <b>Channel Target:</b> <code>{channel}</code>\n"
        f"• <b>Auto-Post Mode:</b> {'🟢 Direct to Channel' if auto_post else '🟡 Admin Approval Drafts'}\n"
        f"• <b>AI Generator Model:</b> <code>{ai_model}</code>\n"
        f"• <b>Check Interval:</b> <code>{Config.CHECK_INTERVAL_MINUTES} min</code>\n\n"
        "🛠 <b>Available Commands:</b>\n"
        "• /categories - Browse by Category (🎥 Video, 🎙️ Voice, 🎨 Vision, 💻 Code, 🆓 Free)\n"
        "• /search <code>&lt;query&gt;</code> - Search models or keywords\n"
        "• /latest - Show recent additions\n"
        "• /check - Trigger a check for new models now\n"
        "• /model <code>&lt;id&gt;</code> - View model details and make post\n"
        "• /setmodel <code>&lt;model_id&gt;</code> - Change AI generator model\n"
        "• /settings - Open settings menu\n"
        "• /help - Show this guide"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=make_categories_menu_keyboard())


@admin_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Alias for /start."""
    await cmd_start(update, context)


@admin_only
async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually check for new models on OpenRouter."""
    msg = await update.message.reply_text("🔄 Checking OpenRouter for new models...")
    new_models = await check_for_new_models(context.bot)
    if new_models:
        await msg.edit_text(f"✅ Check complete! Discovered <b>{len(new_models)}</b> new model(s).", parse_mode=ParseMode.HTML)
    else:
        await msg.edit_text("✅ Check complete! No new models found at this time.", parse_mode=ParseMode.HTML)


@admin_only
async def cmd_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Browse OpenRouter models by category (Video, Voice, Vision, Code, Reasoning, Free)."""
    if context.args:
        user_cat = context.args[0].lower().strip()
        # Map common aliases
        alias_map = {
            "video": "video",
            "videos": "video",
            "voice": "audio",
            "audio": "audio",
            "tts": "audio",
            "speech": "audio",
            "image": "image",
            "vision": "image",
            "images": "image",
            "code": "code",
            "coding": "code",
            "reasoning": "reasoning",
            "reason": "reasoning",
            "free": "free",
        }
        matched_cat = alias_map.get(user_cat)
        if matched_cat:
            status_msg = await update.message.reply_text("📂 Loading models in category...")
            text, markup = await render_category_page(matched_cat, page=0)
            await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            return

    text = (
        "📂 <b>OpenRouter Model Categories</b>\n\n"
        "Select a category below to browse models, inspect technical details, or generate channel post drafts:"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=make_categories_menu_keyboard())


@admin_only
async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Search for models on OpenRouter."""
    if not context.args:
        await update.message.reply_text(
            "🔍 Usage: <code>/search &lt;name or keyword&gt;</code>\n"
            "Example: <code>/search llama-3.3</code> or <code>/search claude</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🔍 Searching for <i>'{query}'</i>...")

    try:
        results = await or_client.search_models(query)
    except Exception as e:
        logger.error("Search failed: %s", e)
        await status_msg.edit_text(f"❌ Error searching models: {e}")
        return

    if not results:
        await status_msg.edit_text(f"No models found matching <b>'{query}'</b>.", parse_mode=ParseMode.HTML)
        return

    # Show up to top 8 matches
    top_matches = results[:8]
    text = f"🎯 Found <b>{len(results)}</b> models matching <i>'{query}'</i>:\n\n"
    keyboard = []

    for i, m in enumerate(top_matches, 1):
        m_id = m.get("id", "")
        name = m.get("name", m_id)
        ctx = format_context_length(m.get("context_length"))
        pricing = m.get("pricing") or {}
        p_in = format_price(pricing.get("prompt"))
        p_out = format_price(pricing.get("completion"))

        text += (
            f"<b>{i}. {name}</b>\n"
            f"   ID: <code>{m_id}</code>\n"
            f"   Context: <code>{ctx}</code> | Price: {p_in} / {p_out}\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"✨ Post Draft: {name[:20]}", callback_data=f"genpost:{m_id}"),
            InlineKeyboardButton("ℹ️ Details", callback_data=f"minfo:{m_id}"),
        ])

    if len(results) > 8:
        text += f"<i>(Showing 8 of {len(results)} matches)</i>\n"

    await status_msg.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


@admin_only
async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recently discovered models."""
    limit = 5
    if context.args and context.args[0].isdigit():
        limit = min(int(context.args[0]), 15)

    recent = await db.get_recently_discovered(limit=limit)
    if not recent:
        await update.message.reply_text("No models recorded in database yet. Run /check to fetch models.")
        return

    text = f"🆕 <b>Latest {len(recent)} Discovered Models:</b>\n\n"
    keyboard = []

    for i, m in enumerate(recent, 1):
        m_id = m.get("id")
        name = m.get("name", m_id)
        raw = m.get("raw", {})
        ctx = format_context_length(raw.get("context_length"))
        disc_at = str(m.get("discovered_at", ""))[:19]

        text += (
            f"<b>{i}. {name}</b>\n"
            f"   ID: <code>{m_id}</code>\n"
            f"   Context: <code>{ctx}</code>\n"
            f"   Discovered: <code>{disc_at}</code>\n\n"
        )
        keyboard.append([
            InlineKeyboardButton(f"✨ Draft Post: {name[:22]}", callback_data=f"genpost:{m_id}")
        ])

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


@admin_only
async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View model details and offer draft generation."""
    if not context.args:
        await update.message.reply_text("Usage: <code>/model &lt;model_id&gt;</code>\nExample: <code>/model meta-llama/llama-3.3-70b-instruct</code>", parse_mode=ParseMode.HTML)
        return

    model_id = context.args[0].strip()
    status_msg = await update.message.reply_text(f"🔍 Fetching info for <code>{model_id}</code>...", parse_mode=ParseMode.HTML)

    model_data = await or_client.get_model_by_id(model_id)
    if not model_data:
        await status_msg.edit_text(f"❌ Model <code>{model_id}</code> not found on OpenRouter.", parse_mode=ParseMode.HTML)
        return

    preview = create_template_post(model_data, is_new=False)
    keyboard = [
        [
            InlineKeyboardButton("✨ Generate AI Post", callback_data=f"genpost:{model_id}"),
            InlineKeyboardButton("📄 Use Template As-Is", callback_data=f"gentmpl:{model_id}"),
        ]
    ]
    await status_msg.edit_text(preview, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


@admin_only
async def cmd_setmodel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change the OpenRouter model used for generating/refining posts."""
    if not context.args:
        curr = await get_active_ai_model()
        await update.message.reply_text(
            f"🧠 <b>Current AI Generator Model:</b> <code>{curr}</code>\n\n"
            "To change, specify a model ID:\n"
            "<code>/setmodel google/gemini-2.5-flash</code>\n"
            "<code>/setmodel openai/gpt-4o-mini</code>\n"
            "<code>/setmodel anthropic/claude-3.5-sonnet</code>\n"
            "<code>/setmodel deepseek/deepseek-chat</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    new_model = context.args[0].strip()
    await db.set_setting("ai_model", new_model)
    await update.message.reply_text(f"✅ AI Generator model updated to: <code>{new_model}</code>", parse_mode=ParseMode.HTML)


@admin_only
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open interactive settings menu."""
    auto_post = await is_auto_post_enabled()
    ai_model = await get_active_ai_model()
    channel = Config.TELEGRAM_CHANNEL_ID or "Not set"

    text = (
        "⚙️ <b>Bot Settings</b>\n\n"
        f"• <b>Auto-Post to Channel:</b> {'🟢 ENABLED' if auto_post else '🔴 DISABLED (Approval Drafts)'}\n"
        f"• <b>AI Generator Model:</b> <code>{ai_model}</code>\n"
        f"• <b>Channel:</b> <code>{channel}</code>\n"
        f"• <b>Polling Interval:</b> <code>{Config.CHECK_INTERVAL_MINUTES} mins</code>\n\n"
        "Click below to toggle settings:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "Toggle Auto-Post: " + ("ON 🟢" if auto_post else "OFF 🔴"),
                callback_data="toggle_autopost",
            )
        ],
        [
            InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_settings"),
        ],
    ]

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))


# ============================================================================
# CALLBACK QUERY HANDLERS
# ============================================================================

@admin_only
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route inline keyboard button callbacks."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if data == "toggle_autopost":
        curr = await is_auto_post_enabled()
        new_val = not curr
        await db.set_setting("auto_post", "true" if new_val else "false")
        await query.answer(f"Auto-post {'enabled' if new_val else 'disabled'}")
        # update message
        ai_model = await get_active_ai_model()
        channel = Config.TELEGRAM_CHANNEL_ID or "Not set"
        text = (
            "⚙️ <b>Bot Settings</b>\n\n"
            f"• <b>Auto-Post to Channel:</b> {'🟢 ENABLED' if new_val else '🔴 DISABLED (Approval Drafts)'}\n"
            f"• <b>AI Generator Model:</b> <code>{ai_model}</code>\n"
            f"• <b>Channel:</b> <code>{channel}</code>\n"
            f"• <b>Polling Interval:</b> <code>{Config.CHECK_INTERVAL_MINUTES} mins</code>\n\n"
            "Click below to toggle settings:"
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    "Toggle Auto-Post: " + ("ON 🟢" if new_val else "OFF 🔴"),
                    callback_data="toggle_autopost",
                )
            ],
            [
                InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_settings"),
            ],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == "refresh_settings":
        auto_post = await is_auto_post_enabled()
        ai_model = await get_active_ai_model()
        channel = Config.TELEGRAM_CHANNEL_ID or "Not set"
        text = (
            "⚙️ <b>Bot Settings</b>\n\n"
            f"• <b>Auto-Post to Channel:</b> {'🟢 ENABLED' if auto_post else '🔴 DISABLED (Approval Drafts)'}\n"
            f"• <b>AI Generator Model:</b> <code>{ai_model}</code>\n"
            f"• <b>Channel:</b> <code>{channel}</code>\n"
            f"• <b>Polling Interval:</b> <code>{Config.CHECK_INTERVAL_MINUTES} mins</code>\n\n"
            "Click below to toggle settings:"
        )
        keyboard = [
            [
                InlineKeyboardButton(
                    "Toggle Auto-Post: " + ("ON 🟢" if auto_post else "OFF 🔴"),
                    callback_data="toggle_autopost",
                )
            ],
            [
                InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh_settings"),
            ],
        ]
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Show category menu: show_cats
    if data == "show_cats":
        text = (
            "📂 <b>OpenRouter Model Categories</b>\n\n"
            "Select a category below to browse models, inspect technical details, or generate channel post drafts:"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=make_categories_menu_keyboard())
        return

    # Category paginated list: cat:<category_key>:<page>
    if data.startswith("cat:"):
        parts = data.split(":")
        category_key = parts[1]
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        text, markup = await render_category_page(category_key, page=page)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return

    # Details inspection: minfo:<model_id>
    if data.startswith("minfo:"):
        model_id = data[6:]
        model = await or_client.get_model_by_id(model_id)
        if not model:
            await query.edit_message_text(f"❌ Model <code>{model_id}</code> not found.", parse_mode=ParseMode.HTML)
            return
        preview = create_template_post(model, is_new=False)
        keyboard = [
            [
                InlineKeyboardButton("✨ Generate AI Post", callback_data=f"genpost:{model_id}"),
                InlineKeyboardButton("📄 Use Template As-Is", callback_data=f"gentmpl:{model_id}"),
            ]
        ]
        await query.message.reply_text(preview, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # Generate AI post: genpost:<model_id>
    if data.startswith("genpost:"):
        model_id = data[8:]
        status_msg = await query.message.reply_text(f"🧠 Generating AI post & logo for <code>{model_id}</code>...", parse_mode=ParseMode.HTML)
        model = await or_client.get_model_by_id(model_id)
        if not model:
            await status_msg.edit_text(f"❌ Model <code>{model_id}</code> not found.", parse_mode=ParseMode.HTML)
            return

        ai_model = await get_active_ai_model()
        post_content = await or_client.generate_post_with_ai(model, ai_model=ai_model, is_new=False)
        image_url = await or_client.get_model_image_url(model_id, model.get("hugging_face_id"))
        draft_id = str(uuid.uuid4())[:8]
        await db.save_draft(draft_id, model_id, post_content, image_url=image_url)

        await status_msg.delete()
        await send_post_message(
            bot=context.bot,
            chat_id=query.message.chat_id,
            text=post_content,
            image_url=image_url,
            reply_markup=make_draft_keyboard(draft_id),
        )
        return

    # Generate Template post: gentmpl:<model_id>
    if data.startswith("gentmpl:"):
        model_id = data[8:]
        model = await or_client.get_model_by_id(model_id)
        if not model:
            await query.message.reply_text(f"❌ Model <code>{model_id}</code> not found.", parse_mode=ParseMode.HTML)
            return

        post_content = create_template_post(model, is_new=False)
        image_url = await or_client.get_model_image_url(model_id, model.get("hugging_face_id"))
        draft_id = str(uuid.uuid4())[:8]
        await db.save_draft(draft_id, model_id, post_content, image_url=image_url)

        await send_post_message(
            bot=context.bot,
            chat_id=query.message.chat_id,
            text=post_content,
            image_url=image_url,
            reply_markup=make_draft_keyboard(draft_id),
        )
        return

    # Publish draft: pub:<draft_id>
    if data.startswith("pub:"):
        draft_id = data[4:]
        draft = await db.get_draft(draft_id)
        if not draft:
            await query.answer("Draft not found or already deleted.", show_alert=True)
            return

        channel_id = Config.TELEGRAM_CHANNEL_ID
        if not channel_id:
            await query.answer("❌ TELEGRAM_CHANNEL_ID is not configured in .env!", show_alert=True)
            return

        try:
            await send_post_message(
                bot=context.bot,
                chat_id=channel_id,
                text=draft["content"],
                image_url=draft.get("image_url"),
            )
            await db.delete_draft(draft_id)
            if query.message.caption:
                await query.edit_message_caption(
                    caption=f"✅ <b>Successfully published to {channel_id}!</b>\n\n{draft['content']}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await query.edit_message_text(
                    f"✅ <b>Successfully published to {channel_id}!</b>\n\n{draft['content']}",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
        except Exception as e:
            logger.error("Failed to publish post: %s", e)
            await query.answer(f"❌ Failed to publish: {e}", show_alert=True)
        return

    # AI Refinement request: refine:<draft_id>
    if data.startswith("refine:"):
        draft_id = data[7:]
        draft = await db.get_draft(draft_id)
        if not draft:
            await query.answer("Draft not found.", show_alert=True)
            return

        user_sessions[user_id] = {
            "state": "waiting_refine",
            "draft_id": draft_id,
            "message_id": query.message.message_id,
        }

        await query.message.reply_text(
            "✨ <b>AI Post Refinement</b>\n\n"
            "Please send a message with your instructions on how to refine this post.\n"
            "<i>Examples:</i>\n"
            "• <i>'Make it shorter and more punchy'</i>\n"
            "• <i>'Translate the description to Russian'</i>\n"
            "• <i>'Add more emphasis on benchmark scores and coding capability'</i>\n"
            "• <i>'Add emojis and format as a bulleted announcement'</i>\n\n"
            "Or send /cancel to abort.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Manual edit: edit:<draft_id>
    if data.startswith("edit:"):
        draft_id = data[5:]
        draft = await db.get_draft(draft_id)
        if not draft:
            await query.answer("Draft not found.", show_alert=True)
            return

        user_sessions[user_id] = {
            "state": "waiting_edit",
            "draft_id": draft_id,
            "message_id": query.message.message_id,
        }

        await query.message.reply_text(
            "✏️ <b>Manual Post Edit</b>\n\n"
            "Please send the complete updated text for this post (Telegram HTML formatting supported).\n\n"
            "Or send /cancel to abort.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Reset to standard template: tmpl:<draft_id>
    if data.startswith("tmpl:"):
        draft_id = data[5:]
        draft = await db.get_draft(draft_id)
        if not draft:
            await query.answer("Draft not found.", show_alert=True)
            return

        model = await or_client.get_model_by_id(draft["model_id"])
        if model:
            new_content = create_template_post(model)
            image_url = draft.get("image_url") or await or_client.get_model_image_url(draft["model_id"], model.get("hugging_face_id"))
            await db.save_draft(draft_id, draft["model_id"], new_content, image_url=image_url)
            await send_post_message(
                bot=context.bot,
                chat_id=query.message.chat_id,
                text=new_content,
                image_url=image_url,
                reply_markup=make_draft_keyboard(draft_id),
            )
            await query.answer("Reset to standard template.")
        else:
            await query.answer("Model metadata not found.", show_alert=True)
        return

    # Discard draft: del:<draft_id>
    if data.startswith("del:"):
        draft_id = data[4:]
        await db.delete_draft(draft_id)
        try:
            if query.message.caption:
                await query.edit_message_caption(caption="🗑️ <i>Draft discarded.</i>", parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text("🗑️ <i>Draft discarded.</i>", parse_mode=ParseMode.HTML)
        except Exception:
            await query.message.reply_text("🗑️ <i>Draft discarded.</i>", parse_mode=ParseMode.HTML)
        return


# ============================================================================
# TEXT MESSAGE HANDLER (FOR REFINEMENT & MANUAL EDIT)
# ============================================================================

@admin_only
async def handle_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input from admin when in a session (refine / edit)."""
    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    if user_text.lower() == "/cancel":
        if user_id in user_sessions:
            del user_sessions[user_id]
            await update.message.reply_text("❌ Action cancelled.")
        return

    session = user_sessions.get(user_id)
    if not session:
        # Default fallback if user types random text: suggest search
        await update.message.reply_text(
            f"Type <code>/search {user_text}</code> to search models or /help for command list.",
            parse_mode=ParseMode.HTML,
        )
        return

    state = session.get("state")
    draft_id = session.get("draft_id")
    draft = await db.get_draft(draft_id)

    if not draft:
        del user_sessions[user_id]
        await update.message.reply_text("❌ Draft expired or not found.")
        return

    image_url = draft.get("image_url")

    if state == "waiting_refine":
        del user_sessions[user_id]
        status_msg = await update.message.reply_text("🧠 Refining post with AI, please wait...")

        try:
            ai_model = await get_active_ai_model()
            refined_text = await or_client.refine_post_with_ai(
                current_post=draft["content"],
                user_instructions=user_text,
                ai_model=ai_model,
            )
            await db.save_draft(draft_id, draft["model_id"], refined_text, image_url=image_url)
            await status_msg.delete()

            await send_post_message(
                bot=context.bot,
                chat_id=update.effective_chat.id,
                text=refined_text,
                image_url=image_url,
                reply_markup=make_draft_keyboard(draft_id),
            )
        except Exception as e:
            logger.error("AI refinement failed: %s", e)
            await status_msg.edit_text(
                f"⚠️ <b>AI Refinement Issue:</b> {e}\n\n"
                "💡 <b>Tips:</b>\n"
                "• Switch AI model: <code>/setmodel openai/gpt-4o-mini</code>\n"
                "• Use <b>✏️ Manual Edit</b> on the draft\n"
                "• Or retry your refinement instruction in a few moments.",
                parse_mode=ParseMode.HTML,
            )
            # Re-present the current draft with action buttons so the user isn't stuck
            await send_post_message(
                bot=context.bot,
                chat_id=update.effective_chat.id,
                text=draft["content"],
                image_url=image_url,
                reply_markup=make_draft_keyboard(draft_id),
            )

    elif state == "waiting_edit":
        del user_sessions[user_id]
        await db.save_draft(draft_id, draft["model_id"], user_text, image_url=image_url)

        await send_post_message(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            text=user_text,
            image_url=image_url,
            reply_markup=make_draft_keyboard(draft_id),
        )


# ============================================================================
# BACKGROUND CHECK & MONITORING JOB
# ============================================================================

async def check_for_new_models(bot) -> list[dict]:
    """Fetch OpenRouter models, detect newly added ones, and handle posting/drafts."""
    try:
        models = await or_client.fetch_models()
    except Exception as e:
        logger.error("Failed to fetch models from OpenRouter: %s", e)
        return []

    seen_ids = await db.get_all_seen_model_ids()

    # If DB is empty, seed all current models without spamming
    if not seen_ids:
        logger.info("First run: Seeding %d existing models into database...", len(models))
        await db.mark_models_seen_bulk(models)
        for admin_id in Config.ADMIN_USER_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🚀 <b>OpenRouter Tracker Initialized!</b>\n\n"
                        f"Seeded <b>{len(models)}</b> existing models into local database.\n"
                        f"The bot is now actively monitoring for any newly added models!"
                    ),
                    parse_mode=ParseMode.HTML,
                )
            except Exception as e:
                logger.error("Failed to notify admin on seed: %s", e)
        return []

    # Find newly added models
    newly_added = [m for m in models if m.get("id") and m.get("id") not in seen_ids]

    if not newly_added:
        return []

    logger.info("Discovered %d new models on OpenRouter!", len(newly_added))
    auto_post = await is_auto_post_enabled()
    ai_model = await get_active_ai_model()

    for model in newly_added:
        # Save to DB so we don't process again
        await db.mark_model_seen(model)
        model_id = model.get("id", "")
        model_name = model.get("name", model_id)

        # Fetch model provider logo
        image_url = await or_client.get_model_image_url(model_id, model.get("hugging_face_id"))

        # Generate post content using AI (or fallback to template) for newly discovered model
        post_content = await or_client.generate_post_with_ai(model, ai_model=ai_model, is_new=True)

        if auto_post and Config.TELEGRAM_CHANNEL_ID:
            # Directly post to channel
            try:
                await send_post_message(
                    bot=bot,
                    chat_id=Config.TELEGRAM_CHANNEL_ID,
                    text=post_content,
                    image_url=image_url,
                )
                logger.info("Auto-posted new model %s to channel %s", model_id, Config.TELEGRAM_CHANNEL_ID)

                # Notify admins
                for admin_id in Config.ADMIN_USER_IDS:
                    try:
                        await bot.send_message(
                            chat_id=admin_id,
                            text=f"📢 <b>Auto-posted new model to channel:</b> <code>{model_name}</code>",
                            parse_mode=ParseMode.HTML,
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.error("Failed auto-posting model %s to channel: %s", model_id, e)
                # Fallback to sending draft to admin
                draft_id = str(uuid.uuid4())[:8]
                await db.save_draft(draft_id, model_id, post_content, image_url=image_url)
                for admin_id in Config.ADMIN_USER_IDS:
                    await send_post_message(
                        bot=bot,
                        chat_id=admin_id,
                        text=f"⚠️ Auto-post failed ({e}). Here is the draft:\n\n{post_content}",
                        image_url=image_url,
                        reply_markup=make_draft_keyboard(draft_id),
                    )
        else:
            # Approval / Draft mode: send to admin with interactive buttons
            draft_id = str(uuid.uuid4())[:8]
            await db.save_draft(draft_id, model_id, post_content, image_url=image_url)

            for admin_id in Config.ADMIN_USER_IDS:
                try:
                    await send_post_message(
                        bot=bot,
                        chat_id=admin_id,
                        text=post_content,
                        image_url=image_url,
                        reply_markup=make_draft_keyboard(draft_id),
                    )
                except Exception as e:
                    logger.error("Failed to send draft to admin %s: %s", admin_id, e)

    return newly_added


async def background_poll_job(context: ContextTypes.DEFAULT_TYPE):
    """Recurring job run by JobQueue."""
    await check_for_new_models(context.bot)


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    """Start the Telegram bot application."""
    missing = Config.validate()
    if missing:
        logger.error(
            "Missing configuration in .env file: %s. Please copy .env.example to .env and configure.",
            ", ".join(missing),
        )
        print(f"\n❌ Error: Missing configuration values in .env: {', '.join(missing)}")
        print("Please check .env file and set TELEGRAM_BOT_TOKEN and ADMIN_USER_ID.\n")
        return

    # Initialize DB schema synchronously on startup
    asyncio.run(db.init_db())

    # Build Telegram Bot Application
    app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("category", cmd_category))
    app.add_handler(CommandHandler("categories", cmd_category))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("setmodel", cmd_setmodel))
    app.add_handler(CommandHandler("settings", cmd_settings))

    # Callback Query & Message Handlers
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_text))

    # Background Job Scheduler for monitoring new models
    interval_seconds = max(Config.CHECK_INTERVAL_MINUTES * 60, 60)
    app.job_queue.run_repeating(
        background_poll_job,
        interval=interval_seconds,
        first=10,  # Run initial check 10 seconds after start
        name="openrouter_model_checker",
    )

    logger.info("Bot started successfully. Monitoring OpenRouter every %d minutes.", Config.CHECK_INTERVAL_MINUTES)
    print("\n=======================================================")
    print("🚀 OpenRouter Telegram Bot is running!")
    print(f"• Monitoring interval: {Config.CHECK_INTERVAL_MINUTES} minutes")
    print(f"• Admins: {Config.ADMIN_USER_IDS}")
    print(f"• Target Channel: {Config.TELEGRAM_CHANNEL_ID or 'None (Draft Mode)'}")
    print("=======================================================\n")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
