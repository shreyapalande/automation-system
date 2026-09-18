"""Shared fixtures for end-to-end agent loop tests.

These are real integration tests: they launch a live browser, hit the
actual saucedemo.com site, and call the real Gemini API. They require
GEMINI_API_KEY to be set (e.g. via .env).
"""
from __future__ import annotations

import pytest
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

SAUCEDEMO_URL = "https://www.saucedemo.com/"
USERNAME = "standard_user"
PASSWORD = "secret_sauce"

load_dotenv()


@pytest.fixture
def logged_in_page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(SAUCEDEMO_URL)
        page.locator("[data-test='username']").fill(USERNAME)
        page.locator("[data-test='password']").fill(PASSWORD)
        page.locator("[data-test='login-button']").click()
        yield page
        browser.close()
