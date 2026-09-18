"""Integration check (real loop.py entrypoint, real executor.py, real
Playwright) for the severity-based error handling design:

  - An ordinary action failure (element not found) is logged with a
    screenshot and the loop retries.
  - The SAME action failing MAX_CONSECUTIVE_SAME_FAILURE times in a row is
    treated as pointless to keep retrying: the loop raises AgentBlocked
    instead of burning through the rest of max_steps.

Only the LLM decide() call is stubbed, to make the scenario deterministic
and avoid Gemini rate limits - run_agent_loop, executor.execute(), and
StepLogger all run unmodified and for real. The scripted LLM below
repeatedly returns a click on a locator hint that does not exist on the
saucedemo inventory page, so every execute() call raises a genuine
Playwright timeout -> ActionExecutionError, for real.

Run from the project root:
    python -m tests.manual_check_loop_error_integration
"""
from __future__ import annotations

import json
import os

from playwright.sync_api import sync_playwright

import src.agent.loop as loop_module
from src.agent.actions import Action
from src.agent.loop import MAX_CONSECUTIVE_SAME_FAILURE, AgentBlocked, run_agent_loop

BAD_LOCATOR = "[data-test='this-element-does-not-exist']"


class RepeatBadActionLLM:
    """Stands in for LLMClient: always returns the same failing click."""

    def decide(self, goal, observation, history):
        return Action(name="click", args={"locator": BAD_LOCATOR})


def main() -> None:
    original_llm_client = loop_module.LLMClient
    loop_module.LLMClient = lambda: RepeatBadActionLLM()

    blocked_exc: AgentBlocked | None = None
    log_path: str | None = None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://www.saucedemo.com/")
            page.locator("[data-test='username']").fill("standard_user")
            page.locator("[data-test='password']").fill("secret_sauce")
            page.locator("[data-test='login-button']").click()

            # This is the exact scenario: run_agent_loop is called directly
            # (the real loop.py entrypoint), same as cli.py's run_agent()
            # calls it. If it ever let a raw Playwright/Python exception
            # escape uncaught, this try/except AgentBlocked would not be
            # what stops us - a traceback would print instead.
            try:
                run_agent_loop(page, goal="irrelevant, scripted", max_steps=10)
                print("FAIL: run_agent_loop returned normally, expected AgentBlocked")
            except AgentBlocked as exc:
                blocked_exc = exc
                # This mirrors exactly what cli.py's run_agent() does: catch
                # AgentBlocked and print a clean message. No traceback.
                print(f"Agent blocked (clean, non-crashing): {exc}")

            browser.close()
    finally:
        loop_module.LLMClient = original_llm_client

    # Find the log file this run wrote (StepLogger auto-increments run
    # numbers, so recover it from the exception context by scanning for
    # the most recently modified discovery_run_*.log).
    evidence_dir = os.path.join(os.path.dirname(__file__), "..", "evidence")
    logs = sorted(
        (os.path.join(evidence_dir, f) for f in os.listdir(evidence_dir) if f.endswith(".log")),
        key=os.path.getmtime,
    )
    log_path = logs[-1]

    with open(log_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]

    last_line = lines[-1]
    blocked_record = last_line.get("blocked")

    checks = {
        "no raw traceback reached this point (AgentBlocked was caught)": blocked_exc is not None,
        "final log entry is a 'blocked' record": blocked_record is not None,
        "blocked record has correct step_index (== threshold)": (
            blocked_record is not None and blocked_record.get("step_index") == MAX_CONSECUTIVE_SAME_FAILURE
        ),
        "blocked record includes the locator": (
            blocked_record is not None and blocked_record.get("locator") == BAD_LOCATOR
        ),
        "blocked record has a non-empty reason": (
            blocked_record is not None and bool(blocked_record.get("reason"))
        ),
        "blocked record references a screenshot path": (
            blocked_record is not None and bool(blocked_record.get("screenshot"))
        ),
        "that screenshot file actually exists on disk": (
            blocked_record is not None
            and blocked_record.get("screenshot") is not None
            and os.path.exists(blocked_record["screenshot"])
        ),
        "there are exactly MAX_CONSECUTIVE_SAME_FAILURE prior step entries, all erroring on the same locator": (
            len(lines) - 1 == MAX_CONSECUTIVE_SAME_FAILURE
            and all(
                line.get("llm_action", {}).get("args", {}).get("locator") == BAD_LOCATOR
                and line.get("error")
                for line in lines[:-1]
            )
        ),
    }

    print(f"\nlog_path: {log_path}")
    print("\n--- checks ---")
    all_passed = True
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
        all_passed = all_passed and passed

    print("\n--- final ('blocked') log record ---")
    print(json.dumps(last_line, indent=2))

    print("\nOVERALL:", "PASS" if all_passed else "FAIL")


if __name__ == "__main__":
    main()
