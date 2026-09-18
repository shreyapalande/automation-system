"""Test 2: discovery agent loop correctly fails for a nonexistent product.

Goal asks for a "Pink Backpack", which does not exist in the saucedemo
inventory (only "Sauce Labs Backpack" exists, and it isn't pink).

Expected: the loop does not hallucinate a click on the wrong product - it
recognizes the product is unavailable and reports failure, and the
independently-verified outcome agrees (no order confirmation reached).
"""
from __future__ import annotations

from src.agent.loop import run_agent_loop

GOAL = (
    "Login, add Pink Backpack to cart, go to checkout, "
    "fill the req info, and place the order."
)


def test_checkout_fails_for_nonexistent_product(logged_in_page):
    result = run_agent_loop(logged_in_page, goal=GOAL, max_steps=25)

    assert result.verified_outcome == "failure"
    assert result.llm_claimed_outcome == "failure"
    assert "checkout-complete.html" not in logged_in_page.url
