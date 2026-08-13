# All prices are in CENTS per 1,000,000 units, and all costs are computed and
# returned in CENTS as integers — never floats. This matches the brief's rule:
# money is stored/calculated as integers, because floats introduce rounding
# errors that are unacceptable in a billing system.

PRICE_PER_MILLION_CENTS = {
    "input": 200,          # $2.00 / 1M tokens
    "cached_input": 50,    # $0.50 / 1M tokens — cheaper, per the brief's rule
    "output": 800,         # $8.00 / 1M tokens
    "reasoning": 800,      # reasoning tokens are billed at the OUTPUT rate, not a separate category
}

API_CALL_PRICE_CENTS = 1  # flat 1 cent per API call, for this capstone's simplified scope


def token_cost_cents(token_category: str, quantity: int) -> int:
    """Cost for a single token category. reasoning is deliberately mapped onto
    the 'output' price on lookup — it is NOT a separate priced category, it
    just gets counted as output for billing purposes."""
    lookup_category = "output" if token_category == "reasoning" else token_category
    if lookup_category not in PRICE_PER_MILLION_CENTS:
        raise ValueError(f"Unknown token category: {token_category}")

    price = PRICE_PER_MILLION_CENTS[lookup_category]
    return (quantity * price) // 1_000_000


def total_ai_token_cost_cents(usage_by_category: dict) -> int:
    """Takes a dict like {"input": 500_000, "cached_input": 200_000, "output": 100_000,
    "reasoning": 50_000} and returns total cost in cents.

    Critically, this does NOT sum all the quantities together and price them as
    one bucket — the brief is explicit that 'token categories cannot simply be
    added together'. Each category is priced separately at its own rate, THEN
    the resulting costs are summed."""
    total = 0
    for category, quantity in usage_by_category.items():
        total += token_cost_cents(category, quantity)
    return total


def api_call_cost_cents(call_count: int) -> int:
    return call_count * API_CALL_PRICE_CENTS