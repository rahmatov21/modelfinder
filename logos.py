import logging
from typing import Optional

logger = logging.getLogger(__name__)

# High-resolution official PNG logos for AI providers and model families
KNOWN_PROVIDER_LOGOS: dict[str, str] = {
    # OpenAI & ChatGPT
    "openai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/openai.png",
    # Anthropic & Claude
    "anthropic": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/claude-color.png",
    "~anthropic": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/claude-color.png",
    # Google & Gemini / Gemma
    "google": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/gemini-color.png",
    "~google": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/gemini-color.png",
    # Meta & Llama
    "meta": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/meta-color.png",
    "meta-llama": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/meta-color.png",
    # DeepSeek
    "deepseek": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/deepseek-color.png",
    "~deepseek": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/deepseek-color.png",
    # Mistral AI
    "mistralai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/mistral-color.png",
    "mistral": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/mistral-color.png",
    # Qwen / Alibaba
    "qwen": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/qwen-color.png",
    "alibaba": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/qwen-color.png",
    # xAI & Grok
    "x-ai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/grok.png",
    "~x-ai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/grok.png",
    # Cohere & Command
    "cohere": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/cohere-color.png",
    # Perplexity
    "perplexity": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/perplexity-color.png",
    # Microsoft & Phi
    "microsoft": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/microsoft-color.png",
    # Amazon & Nova / Bedrock
    "amazon": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/aws-color.png",
    # NVIDIA
    "nvidia": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/nvidia-color.png",
    # MiniMax
    "minimax": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/minimax-color.png",
    # ByteDance / Seed
    "bytedance": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/bytedance-color.png",
    "bytedance-seed": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/bytedance-color.png",
    # Moonshot AI / Kimi
    "moonshotai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/moonshot.png",
    "~moonshotai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/moonshot.png",
    # Upstage / Solar
    "upstage": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/upstage-color.png",
    # 01-AI / Yi
    "01-ai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/yi-color.png",
    # Baichuan
    "baichuan": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/baichuan-color.png",
    # StepFun
    "stepfun": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/stepfun-color.png",
    # Reka AI
    "rekaai": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/reka-color.png",
    # Hugging Face / Open source models
    "huggingface": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/huggingface-color.png",
    # Default OpenRouter logo
    "openrouter": "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/openrouter-color.png",
}

DEFAULT_LOGO = "https://cdn.jsdelivr.net/npm/@lobehub/icons-static-png@latest/dark/openrouter-color.png"


def get_model_logo_url(model_id: str) -> str:
    """
    Get the official clean logo icon URL for a given model ID.
    Example: 'meta-llama/llama-3.3-70b-instruct' -> Meta Llama logo
    Example: 'anthropic/claude-3.5-sonnet' -> Claude logo
    """
    if not model_id:
        return DEFAULT_LOGO

    clean_id = model_id.lower().strip()
    provider = clean_id.split("/")[0] if "/" in clean_id else clean_id

    # 1. Direct provider match
    if provider in KNOWN_PROVIDER_LOGOS:
        return KNOWN_PROVIDER_LOGOS[provider]

    # 2. Check prefix / keyword matches
    for key, url in KNOWN_PROVIDER_LOGOS.items():
        if key in provider or key in clean_id:
            return url

    # 3. If it's a known open source or community provider (e.g. nousresearch, thedrummer, etc.)
    if "/" in clean_id:
        # Fallback to OpenRouter logo
        return DEFAULT_LOGO

    return DEFAULT_LOGO
