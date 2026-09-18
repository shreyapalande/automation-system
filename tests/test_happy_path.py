"""Test 1: discovery agent loop completes a full checkout for a real product.

Goal: Login, add Sauce Labs Backpack to cart, go to checkout, fill the req
info, and place the order.

Expected: the loop reaches saucedemo's order confirmation page, and the
independently-verified outcome (not just the LLM's claim) is "success".
"""
from __future__ import annotations

from src.agent.loop import run_agent_loop

GOAL = (
    "Login, add Sauce Labs Backpack to cart, go to checkout, "
    "fill the req info, and place the order."
)


def test_checkout_succeeds_for_real_product(logged_in_page):
    result = run_agent_loop(logged_in_page, goal=GOAL, max_steps=25)

    assert result.verified_outcome == "success"
    assert result.llm_claimed_outcome == "success"
    assert "checkout-complete.html" in logged_in_page.url
