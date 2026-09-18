"""Manual check: confirms executor.execute() catches ALL Playwright errors
(not just timeouts) and wraps them as ActionExecutionError instead of
crashing uncaught.

Run from the project root (so the `src` package resolves):
    python -m tests.manual_check_playwright_error_handling
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from src.agent.actions import Action
from src.agent.executor import ActionExecutionError, execute


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.saucedemo.com/")
        page.close()  # closed page -> any action now raises a non-timeout Playwright error

        try:
            execute(page, Action(name="click", args={"locator": "[data-test='login-button']"}))
            print("FAIL: expected ActionExecutionError, nothing was raised")
        except ActionExecutionError as exc:
            print(f"PASS: correctly wrapped as ActionExecutionError: {exc}")
        except Exception as exc:
            print(f"FAIL: wrong exception type escaped: {type(exc).__name__}: {exc}")

        browser.close()


if __name__ == "__main__":
    main()
