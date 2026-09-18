"""Structured JSON-lines step logging for discovery runs.

Log shape is kept artifact-writer-friendly: the sequence of step records is
the raw material the future /src/artifact writer will consume to build a
replayable JSON artifact.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

EVIDENCE_DIR = Path(__file__).resolve().parent.parent.parent / "evidence"


def _next_run_number() -> int:
    EVIDENCE_DIR.mkdir(exist_ok=True)
    existing = list(EVIDENCE_DIR.glob("discovery_run_*.log"))
    numbers = []
    for path in existing:
        try:
            numbers.append(int(path.stem.rsplit("_", 1)[-1]))
        except ValueError:
            continue
    return max(numbers, default=0) + 1


class StepLogger:
    def __init__(self):
        EVIDENCE_DIR.mkdir(exist_ok=True)
        self.run_number = _next_run_number()
        self.path = EVIDENCE_DIR / f"discovery_run_{self.run_number}.log"
        self._fh = self.path.open("a", encoding="utf-8")

    def capture_screenshot(self, page: Page, step_index: int) -> str | None:
        """Capture a screenshot as richer evidence for a failure or a
        business-outcome event (e.g. finish(), max-steps exhausted). Returns
        the saved path, or None if the capture itself fails (e.g. page
        already closed)."""
        path = EVIDENCE_DIR / f"discovery_run_{self.run_number}_step_{step_index}.png"
        try:
            page.screenshot(path=str(path))
            return str(path)
        except Exception:
            return None

    def log_step(
        self,
        step_index: int,
        observation: dict[str, Any],
        action_name: str,
        action_args: dict[str, Any],
        execution_result: str,
        page_url: str,
        error: str | None = None,
        screenshot_path: str | None = None,
    ) -> None:
        record = {
            "step_index": step_index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "page_url": page_url,
            "observation_summary": {
                "url": observation.get("url"),
                "title": observation.get("title"),
                "element_count": len(observation.get("elements", [])),
            },
            "llm_action": {"name": action_name, "args": action_args},
            "execution_result": execution_result,
            "error": error,
            "screenshot": screenshot_path,
        }
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def log_blocked(
        self,
        step_index: int,
        locator: str | None,
        reason: str,
        screenshot_path: str | None = None,
    ) -> None:
        """Final log entry for an AgentBlocked stop - a hard/unrecoverable
        failure, as opposed to the ordinary success/failure finish() outcome
        recorded by log_outcome."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "blocked": {
                "step_index": step_index,
                "locator": locator,
                "reason": reason,
                "screenshot": screenshot_path,
            },
        }
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def log_outcome(
        self,
        llm_claimed_outcome: str,
        verified_outcome: str,
        reason: str,
        screenshot_path: str | None = None,
    ) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "final_outcome": {
                "llm_claimed": llm_claimed_outcome,
                "verified": verified_outcome,
                "reason": reason,
                "screenshot": screenshot_path,
            },
        }
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()
