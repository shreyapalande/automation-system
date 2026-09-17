"""Thin wrapper around the Gemini API for the agent loop's decide step."""
from __future__ import annotations

import os
from typing import Any

from google import genai
from google.genai import types

from .actions import ACTION_DECLARATIONS, Action

MODEL_NAME = "gemini-3.5-flash-lite"

SYSTEM_PROMPT = """You are a web automation agent. You are given a goal, the current \
page observation (interactable elements with locator hints), and the history of \
actions taken so far. Choose exactly one action per turn by calling one of the \
provided functions. Always use the locator_hint values exactly as given in the \
observation - do not invent your own locators. Call finish(outcome, reason) once \
the goal is met or you believe it cannot be met (e.g. after repeated failures on \
the same step)."""


class LLMClient:
    def __init__(self, api_key: str | None = None):
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=api_key)

    def decide(self, goal: str, observation: dict[str, Any], history: list[str]) -> Action:
        history_text = "\n".join(history) if history else "(no actions taken yet)"
        prompt = (
            f"Goal: {goal}\n\n"
            f"Current page observation (JSON):\n{observation}\n\n"
            f"Action history so far:\n{history_text}\n\n"
            "Choose the next action."
        )

        response = self._client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=[types.Tool(function_declarations=ACTION_DECLARATIONS)],
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(mode="ANY")
                ),
            ),
        )

        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.function_call:
                return Action.from_function_call(part.function_call)

        raise RuntimeError(f"Model did not return a function call: {response}")
