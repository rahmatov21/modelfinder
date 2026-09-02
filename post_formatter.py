import html
from typing import Any


def format_context_length(context_length: int | None) -> str:
    """Format context length into human-readable representation (e.g., 128k, 1M)."""
    if not context_length or context_length <= 0:
        return "Unknown"
    if context_length >= 1_000_000:
        val = context_length / 1_000_000
        return f"{val:.1f}M".replace(".0M", "M") + " tokens"
    if context_length >= 1_000:
        val = context_length / 1_000
        return f"{val:.0f}K tokens"
    return f"{context_length} tokens"


def format_price(price_per_token_str: str | float | None) -> str:
    """Convert per-token price string to price per 1M tokens."""
    if price_per_token_str is None:
        return "N/A"
    try:
        price_per_token = float(price_per_token_str)
        if price_per_token == 0:
            return "Free"
        # OpenRouter pricing is per single token, so multiply by 1,000,000
        price_per_million = price_per_token * 1_000_000
        if price_per_million < 0.001:
            return f"${price_per_million:.4f} / 1M"
        elif price_per_million < 0.01:
            return f"${price_per_million:.3f} / 1M"
        else:
            return f"${price_per_million:.2f} / 1M"
    except (ValueError, TypeError):
        return "N/A"


def clean_description(desc: str | None, max_len: int = 300) -> str:
    """Sanitize and truncate description."""
    if not desc:
        return "No description available."
    cleaned = desc.strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rsplit(" ", 1)[0] + "..."
    return cleaned


def create_template_post(model: dict[str, Any], is_new: bool = False) -> str:
    """Generate a clean, aesthetic Telegram HTML post directly from model metadata."""
    model_id = model.get("id", "Unknown")
    name = model.get("name", model_id)
    description = clean_description(model.get("description", ""))
    context_length = format_context_length(model.get("context_length"))

    # Pricing
    pricing = model.get("pricing") or {}
    prompt_price = format_price(pricing.get("prompt"))
    completion_price = format_price(pricing.get("completion"))

    # Architecture & Modalities
    arch = model.get("architecture") or {}
    input_mods = arch.get("input_modalities") or ["text"]
    output_mods = arch.get("output_modalities") or ["text"]
    modality_str = f"{', '.join(m.capitalize() for m in input_mods)} ➔ {', '.join(m.capitalize() for m in output_mods)}"

    # Reasoning / Special features
    reasoning_info = model.get("reasoning") or {}
    has_reasoning = reasoning_info.get("default_enabled", False) or (reasoning_info.get("supported_efforts") is not None)

    # Provider
    provider = model_id.split("/")[0] if "/" in model_id else "OpenRouter"

    # URL
    openrouter_url = f"https://openrouter.ai/{model_id}"

    # Escape HTML text
    safe_name = html.escape(name)
    safe_id = html.escape(model_id)
    safe_provider = html.escape(provider.capitalize())
    safe_desc = html.escape(description)
    safe_modalities = html.escape(modality_str)

    # Header changes depending on whether model was just discovered or searched manually
    header = f"🚀 <b>New Model on OpenRouter: {safe_name}</b>" if is_new else f"🤖 <b>Model Overview: {safe_name}</b>"

    # Build post HTML
    lines = [
        header,
        "",
        f"🆔 <code>{safe_id}</code>",
        f"🏢 <b>Provider:</b> {safe_provider}",
        f"🧠 <b>Context Window:</b> <code>{context_length}</code>",
        f"⚡ <b>Modalities:</b> {safe_modalities}",
    ]

    if has_reasoning:
        lines.append("🧩 <b>Reasoning Support:</b> Yes (CoT / Thought tokens)")

    lines.extend([
        "",
        "💰 <b>Pricing (per 1M tokens):</b>",
        f"  • <b>Input:</b> {prompt_price}",
        f"  • <b>Output:</b> {completion_price}",
        "",
        "📝 <b>Overview:</b>",
        f"<i>{safe_desc}</i>",
        "",
        f'🔗 <a href="{openrouter_url}">View on OpenRouter</a>',
        "",
        f"#{provider.replace('-', '_')} #OpenRouter #AI #LLM",
    ])

    return "\n".join(lines)


# AI System Prompt for generating and refining Telegram channel posts
AI_POST_SYSTEM_PROMPT = """You are an expert AI Telegram Channel Content Creator and Tech Journalist.
Your task is to write or refine high-engagement, aesthetically formatted Telegram posts for AI models available on OpenRouter.

FORMATTING RULES:
1. Output ONLY valid Telegram HTML formatting tags: <b>bold</b>, <i>italic</i>, <code>code</code>, <pre>code</pre>, <a href="url">link</a>.
2. Do NOT use Markdown (no **, ``, or # headers). Use ONLY HTML tags!
3. Structure the post cleanly with attractive emojis, clear sections, and concise bullet points.
4. Header Rule:
   - If this is a NEW model announcement: Use a title like: 🚀 <b>New Model: Model Name</b>
   - If this is a MODEL OVERVIEW / SPOTLIGHT of an existing model: Use a title like: 🤖 <b>Model Spotlight: Model Name</b> or ⚡ <b>Model Overview: Model Name</b>. Do NOT claim it is newly released if it is an existing model spotlight.
5. Include:
   - Model ID in <code> tags
   - Key specifications: Context length, Modalities, Pricing (Input / Output per 1M tokens), Provider
   - Brief 1-2 sentence overview highlighting what makes this model special or unique
   - Direct OpenRouter Link: <a href="https://openrouter.ai/{model_id}">Open in OpenRouter</a>
   - Relevant hashtags at the bottom (e.g. #Provider #OpenRouter #AI)
6. LENGTH REQUIREMENT: Keep the entire post concise (under 900 characters) so it fits as a Telegram photo caption.
7. Do NOT include greetings, intro, or outro notes. Output ONLY the Telegram post content.
"""
