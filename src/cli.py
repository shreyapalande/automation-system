"""CLI entrypoints: `run-agent` (discovery) and `replay` (stub, not built yet)."""
from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from src.agent.llm_client import LLMClient
from src.agent.loop import run_agent_loop, AgentBlocked

DEFAULT_USERNAME = "standard_user"
DEFAULT_PASSWORD = "secret_sauce"


def _parse_params(pairs: list[str]) -> dict[str, str]:
    params = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--param must be KEY=VALUE, got: {pair}")
        key, value = pair.split("=", 1)
        params[key] = value
    return params


def _fill_goal(goal: str, params: dict[str, str]) -> str:
    for key, value in params.items():
        goal = goal.replace(f"[{key}]", value)
    return goal


def run_agent(args: argparse.Namespace) -> int:
    # Fail fast, before opening a browser, if the LLM can't be reached.
    try:
        LLMClient()
    except RuntimeError as exc:
        print(f"Cannot start agent: {exc}", file=sys.stderr)
        return 1

    params = _parse_params(args.param or [])
    goal = _fill_goal(args.goal, params)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(args.url)

            # Login is a fixed prerequisite step for every saucedemo flow,
            # not part of the LLM-discovered goal.
            page.locator("[data-test='username']").fill(DEFAULT_USERNAME)
            page.locator("[data-test='password']").fill(DEFAULT_PASSWORD)
            page.locator("[data-test='login-button']").click()

            result = run_agent_loop(page, goal=goal, max_steps=args.max_steps)
        except AgentBlocked as exc:
            print(f"Agent blocked: {exc}", file=sys.stderr)
            return 1
        finally:
            browser.close()

        print(f"LLM-claimed outcome: {result.llm_claimed_outcome}")
        print(f"Verified outcome: {result.verified_outcome}")
        print(f"Reason: {result.reason}")
        print(f"Steps taken: {result.steps_taken}")
        print(f"Log: {result.log_path}")

        return 0 if result.verified_outcome == "success" else 1


def replay(args: argparse.Namespace) -> int:
    print("replay: not implemented yet", file=sys.stderr)
    return 1


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run-agent", help="Run the discovery agent loop")
    run_parser.add_argument("--goal", required=True)
    run_parser.add_argument("--url", required=True)
    run_parser.add_argument("--param", action="append", help="KEY=VALUE, repeatable")
    run_parser.add_argument("--max-steps", type=int, default=25)
    run_parser.set_defaults(func=run_agent)

    replay_parser = subparsers.add_parser("replay", help="Replay a saved artifact (not implemented)")
    replay_parser.set_defaults(func=replay)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
