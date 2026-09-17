"""Fixed action schema the LLM is allowed to choose from each step.

Exposed to Gemini as function declarations. The LLM must call exactly one
of these per turn; the agent loop validates and executes it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from google.genai import types

ActionName = Literal["click", "type", "goto", "wait_for", "finish"]

SENSITIVE_DATA_TEST_HINTS = {"password"}


@dataclass
class Action:
    name: ActionName
    args: dict[str, Any]

    @classmethod
    def from_function_call(cls, function_call: Any) -> "Action":
        name = function_call.name
        if name not in ("click", "type", "goto", "wait_for", "finish"):
            raise ValueError(f"Unknown action: {name}")
        return cls(name=name, args=dict(function_call.args or {}))

    def is_sensitive(self) -> bool:
        if self.name != "type":
            return False
        locator = str(self.args.get("locator", "")).lower()
        return any(hint in locator for hint in SENSITIVE_DATA_TEST_HINTS)

    def redacted_args(self) -> dict[str, Any]:
        if self.is_sensitive():
            return {**self.args, "text": "***"}
        return self.args


ACTION_DECLARATIONS = [
    types.FunctionDeclaration(
        name="click",
        description="Click an element identified by its locator hint.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "locator": types.Schema(
                    type="STRING",
                    description="The locator_hint string exactly as given in the observation.",
                )
            },
            required=["locator"],
        ),
    ),
    types.FunctionDeclaration(
        name="type",
        description="Type text into an input/textarea identified by its locator hint.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "locator": types.Schema(
                    type="STRING",
                    description="The locator_hint string exactly as given in the observation.",
                ),
                "text": types.Schema(type="STRING", description="Text to type into the field."),
            },
            required=["locator", "text"],
        ),
    ),
    types.FunctionDeclaration(
        name="goto",
        description="Navigate the browser to an absolute URL. Only valid as the very first action.",
        parameters=types.Schema(
            type="OBJECT",
            properties={"url": types.Schema(type="STRING")},
            required=["url"],
        ),
    ),
    types.FunctionDeclaration(
        name="wait_for",
        description="Wait for an element identified by its locator hint to appear before continuing.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "locator": types.Schema(
                    type="STRING",
                    description="The locator_hint string exactly as given in the observation.",
                )
            },
            required=["locator"],
        ),
    ),
    types.FunctionDeclaration(
        name="finish",
        description="Declare that the goal has been met or cannot be met. This ends the run.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "outcome": types.Schema(type="STRING", enum=["success", "failure"]),
                "reason": types.Schema(type="STRING", description="Why you believe this outcome."),
            },
            required=["outcome", "reason"],
        ),
    ),
]
