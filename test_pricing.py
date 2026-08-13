from app.pricing import token_cost_cents, total_ai_token_cost_cents, api_call_cost_cents


def test_input_token_cost():
    # 1,000,000 input tokens at 200 cents/1M = exactly 200 cents
    assert token_cost_cents("input", 1_000_000) == 200


def test_cached_input_is_cheaper_than_input():
    # Same quantity, cached should cost less than regular input
    input_cost = token_cost_cents("input", 1_000_000)
    cached_cost = token_cost_cents("cached_input", 1_000_000)
    assert cached_cost < input_cost
    assert cached_cost == 50


def test_reasoning_tokens_billed_as_output():
    # reasoning tokens must cost the SAME as output tokens, same quantity
    reasoning_cost = token_cost_cents("reasoning", 1_000_000)
    output_cost = token_cost_cents("output", 1_000_000)
    assert reasoning_cost == output_cost == 800


def test_categories_priced_separately_not_summed_then_priced():
    # This is the core "can't just be added together" rule.
    # If someone incorrectly summed 1M input + 1M output = 2M tokens and priced
    # them all at the input rate, they'd get 400 cents. The CORRECT answer prices
    # each category separately: 200 (input) + 800 (output) = 1000 cents.
    usage = {"input": 1_000_000, "output": 1_000_000}
    correct_total = total_ai_token_cost_cents(usage)
    wrong_total_if_summed_first = token_cost_cents("input", 2_000_000)  # the bug this test catches

    assert correct_total == 1000
    assert correct_total != wrong_total_if_summed_first


def test_full_mixed_usage_total():
    # A realistic mixed request: some fresh input, some cached input,
    # some output, some reasoning tokens.
    usage = {
        "input": 500_000,       # 500,000 * 200 / 1,000,000 = 100 cents
        "cached_input": 200_000,  # 200,000 * 50 / 1,000,000 = 10 cents
        "output": 100_000,      # 100,000 * 800 / 1,000,000 = 80 cents
        "reasoning": 50_000,    # 50,000 * 800 / 1,000,000 = 40 cents
    }
    # total = 100 + 10 + 80 + 40 = 230 cents
    assert total_ai_token_cost_cents(usage) == 230


def test_api_call_cost():
    assert api_call_cost_cents(1000) == 1000  # 1 cent per call, flat


def test_unknown_category_raises():
    import pytest
    with pytest.raises(ValueError):
        token_cost_cents("made_up_category", 1000)