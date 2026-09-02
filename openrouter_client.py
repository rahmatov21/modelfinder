import json
import logging
from typing import Any, Optional
import httpx
from config import Config
from logos import get_model_logo_url
from post_formatter import AI_POST_SYSTEM_PROMPT, create_template_post, format_price, format_context_length

logger = logging.getLogger(__name__)


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.OPENROUTER_API_KEY
        self.timeout = 30.0

    async def fetch_models(self) -> list[dict[str, Any]]:
        """Fetch all models from OpenRouter API."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(Config.OPENROUTER_MODELS_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])

    async def search_models(self, query: str, models: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        """Search models by name, ID, or description."""
        if models is None:
            models = await self.fetch_models()

        q = query.lower().strip()
        matched = []
        for m in models:
            m_id = m.get("id", "").lower()
            m_name = m.get("name", "").lower()
            m_desc = m.get("description", "").lower()
            if q in m_id or q in m_name or q in m_desc:
                matched.append(m)
        return matched

    async def get_model_by_id(self, model_id: str, models: Optional[list[dict[str, Any]]] = None) -> Optional[dict[str, Any]]:
        """Get model metadata by exact ID or case-insensitive match."""
        if models is None:
            models = await self.fetch_models()

        target = model_id.strip().lower()
        for m in models:
            if m.get("id", "").lower() == target:
                return m
        return None

    async def filter_by_category(self, category: str, models: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
        """Filter OpenRouter models by category (video, audio/voice, image/vision, code, reasoning, free)."""
        if models is None:
            models = await self.fetch_models()

        cat = category.lower().strip()
        filtered = []

        for m in models:
            m_id = m.get("id", "").lower()
            name = m.get("name", "").lower()
            desc = m.get("description", "").lower()
            arch = m.get("architecture") or {}
            mod = (arch.get("modality") or "").lower()
            inp = [str(x).lower() for x in (arch.get("input_modalities") or [])]
            out = [str(x).lower() for x in (arch.get("output_modalities") or [])]

            if cat in ("video", "video-gen", "video_generation"):
                # Video understanding & video generation models
                if "video" in inp or "video" in out or "video" in mod or "video" in desc or "video" in m_id or "motion" in desc:
                    filtered.append(m)

            elif cat in ("audio", "voice", "speech", "tts", "voice-gen"):
                # Voice synthesis, audio generation, TTS, speech recognition
                if "audio" in inp or "audio" in out or "audio" in mod or "voice" in desc or "tts" in desc or "speech" in desc or m.get("supported_voices"):
                    filtered.append(m)

            elif cat in ("image", "vision", "image-gen", "image_generation"):
                # Image generation & multimodal vision models
                if "image" in inp or "image" in out or "image" in mod or "vision" in desc or "image" in desc or "flux" in m_id or "diffusion" in desc:
                    filtered.append(m)

            elif cat in ("code", "coding", "programming"):
                # Coding and software engineering models
                benchmarks = m.get("benchmarks") or {}
                has_code_bench = bool(benchmarks.get("artificial_analysis", {}).get("coding_index"))
                if "code" in m_id or "coder" in m_id or "coding" in desc or has_code_bench:
                    filtered.append(m)

            elif cat in ("reasoning", "reason", "cot"):
                # Reasoning / Chain of Thought models
                reasoning_info = m.get("reasoning") or {}
                if reasoning_info.get("default_enabled") or reasoning_info.get("supported_efforts") or "reasoning" in desc or "r1" in m_id or "thinking" in desc:
                    filtered.append(m)

            elif cat in ("free", "free-tier"):
                # 100% Free models
                pricing = m.get("pricing") or {}
                if ":free" in m_id or (pricing.get("prompt") == "0" and pricing.get("completion") == "0"):
                    filtered.append(m)

        return filtered

    async def get_model_image_url(self, model_id: str, hugging_face_id: Optional[str] = None) -> str:
        """Get the clean model/provider logo icon URL."""
        return get_model_logo_url(model_id)

    async def _call_chat_completion(self, messages: list[dict[str, str]], preferred_model: str) -> str:
        """Call OpenRouter chat completions with automatic fallback to free models."""
        if not self.api_key:
            raise ValueError("OpenRouter API key is missing. Please set OPENROUTER_API_KEY in .env.")

        # Fallback model chain (all 100% free models on OpenRouter)
        models_to_try = [preferred_model]
        backup_models = ["openrouter/free", "minimax/minimax-m3:free", "google/gemma-4-31b-it:free"]
        for bm in backup_models:
            if bm != preferred_model and bm not in models_to_try:
                models_to_try.append(bm)

        last_error_msg = ""

        for model in models_to_try:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        Config.OPENROUTER_CHAT_URL,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://github.com/openrouter-telegram-bot",
                            "X-Title": "OpenRouter Telegram Post Generator",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "temperature": 0.5,
                        },
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"].strip()
                        if content.startswith("```html"):
                            content = content[7:]
                        if content.startswith("```"):
                            content = content[3:]
                        if content.endswith("```"):
                            content = content[:-3]
                        return content.strip()

                    # Check error details
                    error_data = {}
                    try:
                        error_data = resp.json().get("error", {})
                    except Exception:
                        pass

                    last_error_msg = error_data.get("message") or resp.text
                    logger.warning("Model %s returned HTTP %d: %s. Trying next fallback model...", model, resp.status_code, last_error_msg)

            except Exception as e:
                last_error_msg = str(e)
                logger.warning("Model %s request error: %s. Trying next fallback model...", model, e)

        raise RuntimeError(f"All AI models failed or are busy. Last error: {last_error_msg}")

    async def generate_post_with_ai(
        self,
        model_data: dict[str, Any],
        custom_instructions: Optional[str] = None,
        ai_model: Optional[str] = None,
        is_new: bool = False,
    ) -> str:
        """
        Generate a Telegram post using OpenRouter AI.
        If all AI models fail or are rate-limited, automatically falls back to the deterministic template post!
        """
        target_model = ai_model or Config.DEFAULT_AI_MODEL

        # Summarize key facts for AI input
        pricing = model_data.get("pricing") or {}
        context = format_context_length(model_data.get("context_length"))
        prompt_cost = format_price(pricing.get("prompt"))
        comp_cost = format_price(pricing.get("completion"))

        user_content = f"""Model ID: {model_data.get('id')}
Name: {model_data.get('name')}
Context Length: {context}
Pricing: Input {prompt_cost}, Output {comp_cost}
Architecture & Modalities: {json.dumps(model_data.get('architecture', {}))}
Reasoning: {json.dumps(model_data.get('reasoning', {}))}
Description: {model_data.get('description', 'N/A')}
Links: https://openrouter.ai/{model_data.get('id')}
"""
        if custom_instructions:
            user_content += f"\nSpecial User Instructions:\n{custom_instructions}"

        prompt_action = (
            "Create an announcement post for this NEW model newly added to OpenRouter:"
            if is_new
            else "Create a model spotlight / overview post for this model available on OpenRouter (Note: This is an existing model spotlight, NOT a new release announcement):"
        )

        messages = [
            {"role": "system", "content": AI_POST_SYSTEM_PROMPT},
            {"role": "user", "content": f"{prompt_action}\n\n{user_content}"},
        ]

        try:
            return await self._call_chat_completion(messages, target_model)
        except Exception as e:
            logger.warning("All AI models were rate-limited or unavailable (%s). Auto-filling template post!", e)
            return create_template_post(model_data, is_new=is_new)

    async def refine_post_with_ai(
        self,
        current_post: str,
        user_instructions: str,
        ai_model: Optional[str] = None,
    ) -> str:
        """Refine an existing post based on admin feedback."""
        if not self.api_key:
            return current_post

        target_model = ai_model or Config.DEFAULT_AI_MODEL

        messages = [
            {"role": "system", "content": AI_POST_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Here is the current Telegram post draft:\n\n"
                    f"{current_post}\n\n"
                    f"Please refine and edit this post according to the following instructions:\n"
                    f"{user_instructions}\n\n"
                    f"Remember: Output ONLY the revised post using valid Telegram HTML tags."
                ),
            },
        ]

        return await self._call_chat_completion(messages, target_model)
