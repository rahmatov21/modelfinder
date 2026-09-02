import asyncio
import os
import sys
import tempfile

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from post_formatter import format_context_length, format_price, create_template_post
from database import Database
from openrouter_client import OpenRouterClient
from logos import get_model_logo_url


async def test_formatter():
    print("Testing post formatter...")
    sample_model = {
        "id": "anthropic/claude-3.5-sonnet",
        "name": "Anthropic: Claude 3.5 Sonnet",
        "description": "Claude 3.5 Sonnet is Anthropic's most intelligent model to date.",
        "context_length": 200000,
        "pricing": {
            "prompt": "0.000003",
            "completion": "0.000015",
        },
        "architecture": {
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
        },
        "reasoning": {
            "default_enabled": False,
        }
    }

    assert format_context_length(200000) == "200K tokens"
    assert format_context_length(1000000) == "1M tokens"
    assert format_context_length(128) == "128 tokens"

    assert format_price("0.000003") == "$3.00 / 1M"
    assert format_price("0.000015") == "$15.00 / 1M"
    assert format_price(0) == "Free"

    # Test Search / Overview post (is_new=False)
    overview_post = create_template_post(sample_model, is_new=False)
    assert "Model Overview:" in overview_post
    assert "New Model on OpenRouter" not in overview_post

    # Test New Discovery post (is_new=True)
    new_post = create_template_post(sample_model, is_new=True)
    assert "New Model on OpenRouter:" in new_post

    print("✅ Formatter tests passed!")


async def test_logos():
    print("Testing clean provider and model logo resolution...")
    models_to_test = [
        ("meta-llama/llama-3.3-70b-instruct", "meta-color.png"),
        ("anthropic/claude-3.5-sonnet", "claude-color.png"),
        ("openai/gpt-4o", "openai.png"),
        ("google/gemini-2.5-flash", "gemini-color.png"),
        ("deepseek/deepseek-chat", "deepseek-color.png"),
        ("mistralai/mistral-large", "mistral-color.png"),
        ("qwen/qwen-2.5-72b-instruct", "qwen-color.png"),
        ("x-ai/grok-2", "grok.png"),
    ]

    for model_id, expected_icon in models_to_test:
        logo_url = get_model_logo_url(model_id)
        assert expected_icon in logo_url, f"Expected {expected_icon} in {logo_url} for {model_id}"

    print("✅ Logos resolution tests passed!")


async def test_database():
    print("Testing database operations...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        db = Database(db_path=tmp_path)
        await db.init_db()

        # Check initial empty
        ids = await db.get_all_seen_model_ids()
        assert len(ids) == 0

        # Mark model seen
        model = {"id": "test/model-1", "name": "Test Model 1", "created": 123456}
        await db.mark_model_seen(model)

        ids = await db.get_all_seen_model_ids()
        assert "test/model-1" in ids
        assert await db.get_total_seen_count() == 1

        # Bulk mark
        bulk_models = [
            {"id": "test/model-2", "name": "Test Model 2"},
            {"id": "test/model-3", "name": "Test Model 3"},
        ]
        await db.mark_models_seen_bulk(bulk_models)
        assert await db.get_total_seen_count() == 3

        # Drafts test with image_url
        await db.save_draft("d1", "test/model-1", "<b>Draft Content</b>", image_url="https://example.com/logo.png")
        draft = await db.get_draft("d1")
        assert draft is not None
        assert draft["content"] == "<b>Draft Content</b>"
        assert draft["image_url"] == "https://example.com/logo.png"

        await db.delete_draft("d1")
        assert await db.get_draft("d1") is None

        # Settings test
        await db.set_setting("auto_post", "true")
        assert await db.get_setting("auto_post") == "true"

        print("✅ Database tests passed!")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


async def test_openrouter_search():
    print("Testing OpenRouter client search...")
    client = OpenRouterClient()
    mock_models = [
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "description": "Flagship open source model"},
        {"id": "openai/gpt-4o", "name": "GPT-4o", "description": "Omni model from OpenAI"},
        {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash", "description": "High speed multimodal model"},
    ]

    res = await client.search_models("llama", models=mock_models)
    assert len(res) == 1
    assert res[0]["id"] == "meta-llama/llama-3.3-70b-instruct"

    res = await client.search_models("multimodal", models=mock_models)
    assert len(res) == 1
    assert res[0]["id"] == "google/gemini-2.5-flash"

    m = await client.get_model_by_id("openai/gpt-4o", models=mock_models)
    assert m is not None
    assert m["name"] == "GPT-4o"

    print("✅ Search client tests passed!")


async def test_categories():
    print("Testing category filtering (Video, Voice/Audio, Vision, Code, Reasoning, Free)...")
    client = OpenRouterClient()
    mock_models = [
        {"id": "video-gen/cogvideo-x", "name": "CogVideoX", "architecture": {"modality": "text->video", "input_modalities": ["text"], "output_modalities": ["video"]}},
        {"id": "meta/voice-audio-1", "name": "VoiceGen", "description": "TTS speech synthesis and voice generator", "architecture": {"input_modalities": ["text"], "output_modalities": ["audio"]}},
        {"id": "qwen/qwen-coder-32b", "name": "Qwen Coder", "description": "Code generation specialist"},
        {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "reasoning": {"default_enabled": True}},
        {"id": "free/test-model:free", "name": "Free Model", "pricing": {"prompt": "0", "completion": "0"}},
    ]

    video_models = await client.filter_by_category("video", models=mock_models)
    assert len(video_models) == 1
    assert video_models[0]["id"] == "video-gen/cogvideo-x"

    audio_models = await client.filter_by_category("audio", models=mock_models)
    assert len(audio_models) == 1
    assert audio_models[0]["id"] == "meta/voice-audio-1"

    code_models = await client.filter_by_category("code", models=mock_models)
    assert len(code_models) == 1
    assert code_models[0]["id"] == "qwen/qwen-coder-32b"

    reason_models = await client.filter_by_category("reasoning", models=mock_models)
    assert len(reason_models) == 1
    assert reason_models[0]["id"] == "deepseek/deepseek-r1"

    free_models = await client.filter_by_category("free", models=mock_models)
    assert len(free_models) == 1
    assert free_models[0]["id"] == "free/test-model:free"

    print("✅ Category filtering tests passed!")


async def test_comparator():
    print("Testing model comparisons and benchmark snippets...")
    from comparator import make_mini_bar, format_pricing_advantage, generate_comparison_post, build_model_market_comparison_snippet

    bar = make_mini_bar(75.5, 100, 8)
    assert "█" in bar
    assert "75.5" in bar

    # Pricing advantage
    adv = format_pricing_advantage(0.15, 0.60, "Model A", "Model B")
    assert "cheaper" in adv
    assert "Model A" in adv

    model_1 = {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o-mini",
        "context_length": 128000,
        "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "benchmarks": {"artificial_analysis": {"intelligence_index": 72.0, "coding_index": 75.0}}
    }

    model_2 = {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "name": "Llama 3.3 70B",
        "context_length": 131072,
        "pricing": {"prompt": "0.0000007", "completion": "0.0000007"},
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "benchmarks": {"artificial_analysis": {"intelligence_index": 68.0, "coding_index": 74.0}}
    }

    comp_post = generate_comparison_post(model_1, model_2)
    assert "GPT-4o-mini vs Llama 3.3 70B" in comp_post
    assert "Head-to-Head Analysis" in comp_post
    assert "Benchmark Scores" in comp_post

    snippet = build_model_market_comparison_snippet(model_1)
    assert "Market Tier:" in snippet
    assert "GPT-4o-mini" in snippet

    print("✅ Comparator tests passed!")


async def main():
    await test_formatter()
    await test_logos()
    await test_database()
    await test_openrouter_search()
    await test_categories()
    await test_comparator()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
