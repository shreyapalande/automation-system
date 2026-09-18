"""Resolves locator hints to live Playwright locators and executes actions.

Locators are re-resolved at execution time (not cached from the observation
step) since the page may have re-rendered between observe and act.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.sync_api import Page, Locator, Error as PlaywrightError

from .actions import Action

DATA_TEST_RE = re.compile(r"^\[data-test=(['\"])(.*)\1\]$")
ROLE_NAME_RE = re.compile(r"^role=(\S+) name=(['\"])(.*)\2$")

DEFAULT_TIMEOUT_MS = 5000

# Minimal domain allowlist guardrail: goto() may only navigate within these
# domains (and their subdomains). Full risk classification / allowlist
# config lives in the future /src/guardrails component - this is a
# stand-in so the agent loop can't be steered off-target by the LLM.
ALLOWED_DOMAINS = {"saucedemo.com"}


class ActionExecutionError(Exception):
    """Raised when an action cannot be executed (locator not found, etc.).

    Treated as recoverable by the agent loop: logged with a screenshot, fed
    back into LLM history, and the run continues so the LLM can retry a
    different approach.
    """


class GuardrailViolation(ActionExecutionError):
    """Raised when an action is blocked by a guardrail (e.g. disallowed domain)."""


class FatalPlaywrightError(ActionExecutionError):
    """Raised when the browser session itself is unusable (page/context/
    browser closed, or the browser process crashed) - no further action can
    possibly succeed, so the agent loop should stop immediately instead of
    logging-and-continuing.
    """


# Substrings Playwright uses in its own error messages for session-fatal
# conditions. Matched case-insensitively rather than importing Playwright's
# internal (non-public) exception classes, since those aren't part of its
# stable public API across versions.
_FATAL_ERROR_MARKERS = (
    "has been closed",
    "target closed",
    "browser has crashed",
    "page crashed",
)


def _is_fatal(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _FATAL_ERROR_MARKERS)


def _check_domain_allowed(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if not host or not any(host == d or host.endswith(f".{d}") for d in ALLOWED_DOMAINS):
        raise GuardrailViolation(
            f"Blocked navigation to disallowed domain: {url!r} "
            f"(allowed: {', '.join(sorted(ALLOWED_DOMAINS))})"
        )


def resolve_locator(page: Page, locator_hint: str) -> Locator:
    match = DATA_TEST_RE.match(locator_hint)
    if match:
        return page.locator(f"[data-test='{match.group(2)}']")

    match = ROLE_NAME_RE.match(locator_hint)
    if match:
        role, _, name = match.groups()
        return page.get_by_role(role, name=name)

    raise ActionExecutionError(f"Could not parse locator hint: {locator_hint!r}")


def execute(page: Page, action: Action) -> str:
    """Execute the action against the page. Returns a short human-readable result string."""
    try:
        if action.name == "goto":
            _check_domain_allowed(action.args["url"])
            page.goto(action.args["url"], timeout=DEFAULT_TIMEOUT_MS * 3)
            return f"navigated to {action.args['url']}"

        if action.name == "click":
            locator = resolve_locator(page, action.args["locator"])
            locator.click(timeout=DEFAULT_TIMEOUT_MS)
            return f"clicked {action.args['locator']}"

        if action.name == "type":
            locator = resolve_locator(page, action.args["locator"])
            locator.fill(action.args["text"], timeout=DEFAULT_TIMEOUT_MS)
            return f"typed into {action.args['locator']}"

        if action.name == "wait_for":
            locator = resolve_locator(page, action.args["locator"])
            locator.wait_for(timeout=DEFAULT_TIMEOUT_MS * 2)
            return f"waited for {action.args['locator']}"

        if action.name == "finish":
            return f"finish({action.args.get('outcome')}): {action.args.get('reason')}"

        raise ActionExecutionError(f"Unhandled action: {action.name}")

    except PlaywrightError as exc:
        message = f"Playwright error executing {action.name}({action.redacted_args()}): {exc}"
        if _is_fatal(exc):
            raise FatalPlaywrightError(message) from exc
        raise ActionExecutionError(message) from exc
