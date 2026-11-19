"""
Module 10 — Centralized AI Pricing and Cost Estimation Service.

Computes conservative usage cost in integer cents based on verified token metrics.
Avoids hardcoded magic numbers across adapters.
"""

from typing import Dict, Any, Tuple


# Pricing table: (input_price_per_million_usd, output_price_per_million_usd)
MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    # Google Gemini
    "gemini-3.6-flash": (0.10, 0.40),
    "gemini-3.8-flash": (0.10, 0.40),
    "gemini-3.7-flash": (0.10, 0.40),
    "gemini-3.5-flash": (0.10, 0.40),
    "gemini-3.5-flash-lite": (0.075, 0.30),
    "gemini-2.5-flash": (0.10, 0.40),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),

    # OpenAI GPT
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "o3-mini": (1.10, 4.40),

    # Anthropic Claude
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-opus-20240229": (15.00, 75.00),
}

DEFAULT_PRICING: Tuple[float, float] = (1.00, 3.00)


def calculate_cost_cents(model: str, tokens_in: int, tokens_out: int) -> int:
    """
    Calculate estimated cost in USD cents for an AI request.
    Enforces a minimum of 1 cent on non-zero token consumption to ensure
    budget tracking is conservative and never bypassable with fractions.
    """
    in_price_m, out_price_m = MODEL_PRICING.get(model, DEFAULT_PRICING)

    in_cost_usd = (tokens_in / 1_000_000.0) * in_price_m
    out_cost_usd = (tokens_out / 1_000_000.0) * out_price_m
    total_usd = in_cost_usd + out_cost_usd

    # Convert to cents
    cents = int(round(total_usd * 100))
    if total_usd > 0 and cents == 0:
        cents = 1
    return cents
