import html
import logging
from typing import Any, Optional
from post_formatter import format_context_length, format_price

logger = logging.getLogger(__name__)

# Standard reference models for benchmarking and comparisons
REFERENCE_BENCHMARK_MODELS = [
    {"id": "openai/gpt-4o-mini", "name": "GPT-4o-mini", "role": "Fast Budget Standard"},
    {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "role": "Open-Weights Standard"},
    {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet", "role": "Frontier Standard"},
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "role": "High-Efficiency Standard"},
]


def make_mini_bar(val: float | None, max_val: float = 100, length: int = 7) -> str:
    """Create a clean visual score bar (e.g. [█████░░] 72)."""
    if val is None or val <= 0:
        return "N/A"
    clamped = min(max(val, 0), max_val)
    filled = int(round((clamped / max_val) * length))
    empty = length - filled
    return f"{'█' * filled}{'░' * empty} {val:.1f}"


def get_token_pricing_numeric(pricing_dict: Optional[dict[str, Any]], key: str) -> Optional[float]:
    """Extract numeric price per 1M tokens."""
    if not pricing_dict:
        return None
    val = pricing_dict.get(key)
    if val is None:
        return None
    try:
        return float(val) * 1_000_000
    except (ValueError, TypeError):
        return None


def format_pricing_advantage(price_a: Optional[float], price_b: Optional[float], name_a: str, name_b: str) -> str:
    """Compare pricing between two models and return a clear advantage string."""
    if price_a is None or price_b is None:
        return "Pricing data not fully available."
    if price_a == 0 and price_b == 0:
        return "Both models are 100% Free!"
    if price_a == 0:
        return f"<b>{html.escape(name_a)}</b> is completely <b>Free</b>!"
    if price_b == 0:
        return f"<b>{html.escape(name_b)}</b> is completely <b>Free</b>!"
    if abs(price_a - price_b) < 0.01:
        return "Virtually identical pricing."

    if price_a < price_b:
        ratio = price_b / price_a
        diff_pct = ((price_b - price_a) / price_b) * 100
        return f"<b>{html.escape(name_a)}</b> is <b>{ratio:.1f}x cheaper</b> (~{diff_pct:.0f}% savings)"
    else:
        ratio = price_a / price_b
        diff_pct = ((price_a - price_b) / price_a) * 100
        return f"<b>{html.escape(name_b)}</b> is <b>{ratio:.1f}x cheaper</b> (~{diff_pct:.0f}% savings)"


def get_model_benchmarks(model: dict[str, Any]) -> dict[str, Optional[float]]:
    """Extract standard Artificial Analysis benchmark scores if present."""
    bench = model.get("benchmarks") or {}
    aa = bench.get("artificial_analysis") or {}
    return {
        "intelligence": aa.get("intelligence_index"),
        "coding": aa.get("coding_index"),
        "agentic": aa.get("agentic_index"),
    }


def generate_comparison_post(model_a: dict[str, Any], model_b: dict[str, Any]) -> str:
    """Generate a clean, beautiful Telegram HTML comparison post between two models."""
    id_a = model_a.get("id", "Unknown")
    name_a = model_a.get("name", id_a)
    id_b = model_b.get("id", "Unknown")
    name_b = model_b.get("name", id_b)

    ctx_a = format_context_length(model_a.get("context_length"))
    ctx_b = format_context_length(model_b.get("context_length"))

    p_a = model_a.get("pricing") or {}
    p_b = model_b.get("pricing") or {}

    in_a_str = format_price(p_a.get("prompt"))
    out_a_str = format_price(p_a.get("completion"))
    in_b_str = format_price(p_b.get("prompt"))
    out_b_str = format_price(p_b.get("completion"))

    in_a_num = get_token_pricing_numeric(p_a, "prompt")
    in_b_num = get_token_pricing_numeric(p_b, "prompt")
    out_a_num = get_token_pricing_numeric(p_a, "completion")
    out_b_num = get_token_pricing_numeric(p_b, "completion")

    price_summary = format_pricing_advantage(in_a_num, in_b_num, name_a, name_b)

    # Benchmarks
    bench_a = get_model_benchmarks(model_a)
    bench_b = get_model_benchmarks(model_b)

    has_benchmarks = any(v is not None for v in bench_a.values()) or any(v is not None for v in bench_b.values())

    # Modalities
    arch_a = model_a.get("architecture") or {}
    arch_b = model_b.get("architecture") or {}
    in_mods_a = ", ".join(arch_a.get("input_modalities") or ["text"]).capitalize()
    out_mods_a = ", ".join(arch_a.get("output_modalities") or ["text"]).capitalize()
    in_mods_b = ", ".join(arch_b.get("input_modalities") or ["text"]).capitalize()
    out_mods_b = ", ".join(arch_b.get("output_modalities") or ["text"]).capitalize()

    # Reasoning
    reason_a = bool(model_a.get("reasoning", {}).get("default_enabled") or model_a.get("reasoning", {}).get("supported_efforts"))
    reason_b = bool(model_b.get("reasoning", {}).get("default_enabled") or model_b.get("reasoning", {}).get("supported_efforts"))

    # Escape HTML
    s_name_a = html.escape(name_a)
    s_name_b = html.escape(name_b)

    lines = [
        f"⚖️ <b>AI Model Comparison: {s_name_a} vs {s_name_b}</b>",
        "",
        f"🔹 <b>{s_name_a}</b>",
        f"  • ID: <code>{html.escape(id_a)}</code>",
        f"  • Context Window: <code>{ctx_a}</code>",
        f"  • Pricing: {in_a_str} (in) / {out_a_str} (out)",
        f"  • Modalities: {in_mods_a} ➔ {out_mods_a}",
        f"  • Reasoning: {'Yes (CoT)' if reason_a else 'Standard'}",
        "",
        f"🔸 <b>{s_name_b}</b>",
        f"  • ID: <code>{html.escape(id_b)}</code>",
        f"  • Context Window: <code>{ctx_b}</code>",
        f"  • Pricing: {in_b_str} (in) / {out_b_str} (out)",
        f"  • Modalities: {in_mods_b} ➔ {out_mods_b}",
        f"  • Reasoning: {'Yes (CoT)' if reason_b else 'Standard'}",
        "",
        "📊 <b>Head-to-Head Analysis:</b>",
        f"  • 💰 <b>Cost:</b> {price_summary}",
    ]

    # Context comparison
    raw_ctx_a = model_a.get("context_length") or 0
    raw_ctx_b = model_b.get("context_length") or 0
    if raw_ctx_a != raw_ctx_b and raw_ctx_a > 0 and raw_ctx_b > 0:
        if raw_ctx_a > raw_ctx_b:
            lines.append(f"  • 📜 <b>Context:</b> <b>{s_name_a}</b> has larger window ({ctx_a} vs {ctx_b})")
        else:
            lines.append(f"  • 📜 <b>Context:</b> <b>{s_name_b}</b> has larger window ({ctx_b} vs {ctx_a})")

    # Benchmarks comparison
    if has_benchmarks:
        lines.append("")
        lines.append("📈 <b>Benchmark Scores (Artificial Analysis):</b>")
        if bench_a["intelligence"] is not None or bench_b["intelligence"] is not None:
            lines.append(f"  • <b>Intelligence:</b>")
            lines.append(f"    - {s_name_a[:15]}: <code>{make_mini_bar(bench_a['intelligence'])}</code>")
            lines.append(f"    - {s_name_b[:15]}: <code>{make_mini_bar(bench_b['intelligence'])}</code>")
        if bench_a["coding"] is not None or bench_b["coding"] is not None:
            lines.append(f"  • <b>Coding Index:</b>")
            lines.append(f"    - {s_name_a[:15]}: <code>{make_mini_bar(bench_a['coding'])}</code>")
            lines.append(f"    - {s_name_b[:15]}: <code>{make_mini_bar(bench_b['coding'])}</code>")

    # Links
    url_a = f"https://openrouter.ai/{id_a}"
    url_b = f"https://openrouter.ai/{id_b}"
    lines.extend([
        "",
        f'🔗 <a href="{url_a}">View {s_name_a}</a> | <a href="{url_b}">View {s_name_b}</a>',
        "",
        "#AIComparison #ModelBattle #OpenRouter #LLM",
    ])

    return "\n".join(lines)


def build_model_market_comparison_snippet(model: dict[str, Any]) -> str:
    """
    Generate an aesthetic comparison snippet to embed inside the main model post.
    Gives readers instant context on how this model compares to industry standards.
    """
    m_id = model.get("id", "")
    pricing = model.get("pricing") or {}
    benchmarks = get_model_benchmarks(model)
    in_num = get_token_pricing_numeric(pricing, "prompt")

    # Benchmark string if available
    bench_items = []
    if benchmarks["intelligence"]:
        bench_items.append(f"Intel: {benchmarks['intelligence']:.0f}")
    if benchmarks["coding"]:
        bench_items.append(f"Code: {benchmarks['coding']:.0f}")

    bench_str = f" • Scores: ({', '.join(bench_items)})" if bench_items else ""

    # Estimate tier and relative comparison
    if in_num == 0 or ":free" in m_id:
        return f"⚖️ <b>Market Tier:</b> 🆓 100% Free OpenRouter Tier{bench_str}"

    if in_num and in_num <= 0.30:
        return f"⚖️ <b>Market Tier:</b> Ultra-Budget (Comparable to GPT-4o-mini){bench_str}"
    elif in_num and in_num <= 1.50:
        return f"⚖️ <b>Market Tier:</b> Mid-Weight Workhorse (Comparable to Llama 3.3 70B){bench_str}"
    else:
        return f"⚖️ <b>Market Tier:</b> Frontier / High-Capacity Model{bench_str}"
