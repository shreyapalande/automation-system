"""The discovery agent loop: observe -> decide (LLM) -> act, repeated until
the goal is met or a stopping condition hits.
"""
from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import Page

from . import observer
from .actions import Action
from .executor import execute, ActionExecutionError, FatalPlaywrightError
from .llm_client import LLMClient
from .logger import StepLogger

DEFAULT_MAX_STEPS = 25

# If the same (action, locator) pair fails this many times in a row, further
# retries are treated as pointless and the run is blocked rather than
# burning through the rest of max_steps repeating the same failure.
MAX_CONSECUTIVE_SAME_FAILURE = 3

# Text that indicates the saucedemo checkout actually completed. Independent
# of whatever the LLM reports via finish() - the loop verifies this itself.
SUCCESS_CONFIRMATION_TEXT = "Thank you for your order"


class AgentBlocked(Exception):
    """Raised when the loop hits an unrecoverable condition.

    This is a placeholder for the future escalation/handoff component
    (/src/escalation) - for now it just surfaces the block to the caller.
    """


@dataclass
class RunResult:
    llm_claimed_outcome: str | None
    verified_outcome: str
    reason: str
    steps_taken: int
    log_path: str


def _verify_outcome(page: Page) -> bool:
    try:
        return SUCCESS_CONFIRMATION_TEXT.lower() in page.content().lower()
    except Exception:
        return False


def run_agent_loop(
    page: Page,
    goal: str,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> RunResult:
    llm = LLMClient()
    step_logger = StepLogger()
    history: list[str] = []

    llm_claimed_outcome: str | None = None
    reason = ""
    final_screenshot_path: str | None = None
    last_failure_key: tuple[str, str | None] | None = None
    consecutive_failures = 0

    try:
        for step_index in range(1, max_steps + 1):
            observation = observer.observe(page)

            try:
                action = llm.decide(goal=goal, observation=observation, history=history)
            except Exception as exc:
                screenshot_path = step_logger.capture_screenshot(page, step_index)
                error = str(exc)
                step_logger.log_step(
                    step_index,
                    observation,
                    "decide_error",
                    {},
                    "",
                    page.url,
                    error=error,
                    screenshot_path=screenshot_path,
                )
                blocked_reason = f"LLM decide step failed at step {step_index}: {error}"
                step_logger.log_blocked(step_index, None, blocked_reason, screenshot_path)
                raise AgentBlocked(blocked_reason) from exc

            if action.name == "finish":
                llm_claimed_outcome = action.args.get("outcome", "unknown")
                reason = action.args.get("reason", "")
                # finish() is a business-outcome event regardless of
                # success/failure - capture evidence either way.
                final_screenshot_path = step_logger.capture_screenshot(page, step_index)
                step_logger.log_step(
                    step_index,
                    observation,
                    action.name,
                    action.redacted_args(),
                    f"finish requested: {llm_claimed_outcome}",
                    page.url,
                    screenshot_path=final_screenshot_path,
                )
                history.append(f"finish({llm_claimed_outcome}): {reason}")
                break

            try:
                result = execute(page, action)
            except FatalPlaywrightError as exc:
                # The session itself is unusable (page/context/browser
                # closed, or crashed) - no further action can possibly
                # succeed, so stop immediately instead of logging-and-continuing.
                error = str(exc)
                screenshot_path = step_logger.capture_screenshot(page, step_index)
                step_logger.log_step(
                    step_index,
                    observation,
                    action.name,
                    action.redacted_args(),
                    "",
                    page.url,
                    error=error,
                    screenshot_path=screenshot_path,
                )
                blocked_reason = f"Fatal Playwright error at step {step_index}: {error}"
                step_logger.log_blocked(
                    step_index, action.args.get("locator"), blocked_reason, screenshot_path
                )
                raise AgentBlocked(blocked_reason) from exc
            except ActionExecutionError as exc:
                error = str(exc)
                screenshot_path = step_logger.capture_screenshot(page, step_index)

                failure_key = (action.name, action.args.get("locator"))
                if failure_key == last_failure_key:
                    consecutive_failures += 1
                else:
                    last_failure_key = failure_key
                    consecutive_failures = 1

                step_logger.log_step(
                    step_index,
                    observation,
                    action.name,
                    action.redacted_args(),
                    "",
                    page.url,
                    error=error,
                    screenshot_path=screenshot_path,
                )

                if consecutive_failures >= MAX_CONSECUTIVE_SAME_FAILURE:
                    # This specific action has failed the same way
                    # repeatedly - retrying further is pointless, so block
                    # instead of burning through the rest of max_steps.
                    blocked_reason = (
                        f"Action {action.name}({action.redacted_args()}) failed "
                        f"{consecutive_failures} times in a row (step {step_index}): {error}"
                    )
                    step_logger.log_blocked(
                        step_index, action.args.get("locator"), blocked_reason, screenshot_path
                    )
                    raise AgentBlocked(blocked_reason) from exc

                history.append(f"{action.name}({action.redacted_args()}) FAILED: {error}")
                continue

            last_failure_key = None
            consecutive_failures = 0
            step_logger.log_step(
                step_index,
                observation,
                action.name,
                action.redacted_args(),
                result,
                page.url,
            )
            history.append(f"{action.name}({action.redacted_args()}) -> {result}")
        else:
            reason = f"max_steps ({max_steps}) exceeded without finish()"
            final_screenshot_path = step_logger.capture_screenshot(page, step_index)

        verified = _verify_outcome(page)
        verified_outcome = "success" if verified else "failure"

        step_logger.log_outcome(
            llm_claimed_outcome=llm_claimed_outcome or "none",
            verified_outcome=verified_outcome,
            reason=reason,
            screenshot_path=final_screenshot_path,
        )

        return RunResult(
            llm_claimed_outcome=llm_claimed_outcome,
            verified_outcome=verified_outcome,
            reason=reason,
            steps_taken=step_index,
            log_path=str(step_logger.path),
        )
    finally:
        step_logger.close()
