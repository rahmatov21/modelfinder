# 🚀 OpenRouter Model Monitor & Telegram Channel Bot

An automated, AI-powered Telegram bot written in Python that tracks new models on [OpenRouter](https://openrouter.ai), formats stylish announcement posts, supports interactive AI-assisted drafting & refinement, and publishes directly to your Telegram channel.

---

## ✨ Key Features

1. 🔍 **Automatic Background Monitoring**: Periodically polls OpenRouter API (configurable interval) and detects newly added models.
2. 🛡️ **Safe Initialization**: On the first launch, it seeds existing models without spamming your channel or chat.
3. 🎨 **Rich & Aesthetic Formatting**:
   - Clean Telegram HTML styling with emojis, bullet points, context length, architecture/modalities, and per-1M token pricing.
   - Fallback deterministic Python template and AI-enhanced post generator.
4. 🧠 **AI Post Generation & Interactive Refinement**:
   - Uses OpenRouter's chat API (with configurable models like `google/gemini-2.5-flash`, `openai/gpt-4o-mini`, `anthropic/claude-3.5-sonnet`, `deepseek/deepseek-chat`).
   - Before publishing, you can click **✨ AI Refine** and give feedback (e.g., *"Make it shorter"*, *"Translate description to Russian"*, *"Highlight benchmark scores"*).
5. 🔒 **Private & Secure**:
   - Only authorized `ADMIN_USER_ID` users can interact with the bot.
6. 📢 **Two Posting Modes**:
   - **Approval Mode (Default)**: Sends new model drafts to the Admin first with inline action buttons (`Publish`, `AI Refine`, `Manual Edit`, `Discard`).
   - **Auto-Post Mode**: Automatically posts newly discovered models directly to your Telegram Channel.
7. 🔎 **Manual Search & Discovery**:
   - Search any model via `/search <query>`.
   - Inspect details and generate post drafts on demand via `/model <id>` or `/latest`.

---

## 📋 Requirements

- Python 3.10+ (Tested on Python 3.13)
- `python-telegram-bot[job-queue]>=21.0`
- `httpx>=0.27.0`
- `aiosqlite>=0.20.0`
- `python-dotenv>=1.0.1`

---

## 🛠️ Quick Setup Guide

### 1. Clone or Open Project Directory
```bash
cd "c:/Users/Abdulaziz/Desktop/All codes/openroutermodels finder"
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Edit the `.env` file (or copy `.env.example` to `.env`):

```env
# 1. Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRstuVWXyz

# 2. Your Telegram User ID (get it from @userinfobot or @raw_data_bot)
ADMIN_USER_ID=123456789

# 3. Target Telegram Channel (e.g. @your_channel or -1001234567890)
TELEGRAM_CHANNEL_ID=@your_channel_username

# 4. OpenRouter API Key (https://openrouter.ai/settings/keys)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxx

# 5. Default AI Model for generating and refining posts
DEFAULT_AI_MODEL=google/gemini-2.5-flash

# 6. Check interval in minutes
CHECK_INTERVAL_MINUTES=15

# 7. Auto-post: false = send draft to admin first; true = publish directly to channel
AUTO_POST_TO_CHANNEL=false
```

> [!IMPORTANT]
> Make sure to add your Telegram Bot to your channel as an **Administrator** with permission to **Post Messages**.

---

## 🚀 Running the Bot

Run the bot with:
```bash
python bot.py
```

You will see:
```text
=======================================================
🚀 OpenRouter Telegram Bot is running!
• Monitoring interval: 15 minutes
• Admins: [123456789]
• Target Channel: @your_channel_username
=======================================================
```

---

## 🎮 Telegram Bot Commands & Usage

| Command | Description |
| :--- | :--- |
| `/start` or `/help` | View bot overview, tracking status, category menu, and command list |
| `/categories` or `/category` | Browse models by category (🎥 Video, 🎙️ Voice & Audio, 🎨 Vision, 🧩 Reasoning, 💻 Code, 🆓 Free) |
| `/compare [m1] [m2]` | Head-to-head model comparison battle (Cost ratio, context, and Artificial Analysis benchmarks) |
| `/category <name>` | Directly view models in a category (e.g. `/category video` or `/category voice`) |
| `/search <query>` | Search models by name, ID, or keywords (e.g. `/search llama-3.3`) |
| `/latest [n]` | View the latest discovered models from OpenRouter |
| `/model <id>` | View details and generate a draft post for a specific model ID |
| `/setmodel <model_id>` | Change the AI model used for generating/refining posts |
| `/settings` | Open interactive settings menu (toggle auto-post, view config) |
| `/cancel` | Abort an ongoing refinement or manual edit action |

---

## 🔄 Interactive Post Refinement Flow

When a new model is discovered or when you generate a draft manually:

1. The bot displays a styled Telegram preview with interactive buttons:
   - `[🚀 Publish to Channel]` - Instantly broadcasts post to your channel.
   - `[✨ AI Refine]` - Prompts you for refinement instructions.
   - `[✏️ Manual Edit]` - Allows you to send custom text.
   - `[🔄 Template Reset]` - Resets to default structured template.
   - `[🗑️ Discard]` - Deletes the draft.
2. Clicking **`✨ AI Refine`**:
   - Send any prompt: e.g. *"Make it punchier with bullet points"*, *"Translate to Arabic/Russian/Uzbek"*, *"Highlight coding capabilities"*.
   - The bot calls OpenRouter AI and sends the updated draft instantly.
3. Click **`🚀 Publish to Channel`** when ready!

---

## 📂 Project Structure

```
├── bot.py                # Main bot application, command & callback handlers
├── config.py             # Environment variables loader & validator
├── database.py           # Async SQLite storage (seen models, drafts, settings)
├── openrouter_client.py  # OpenRouter API client for models & AI completions
├── post_formatter.py     # Deterministic styling template & AI system prompt
├── test_bot.py           # Unit and integration test suite
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
└── README.md             # Documentation
```
