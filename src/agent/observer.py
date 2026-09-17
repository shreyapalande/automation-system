"""Observes the current page state and serializes it into a compact,
LLM-friendly structure of interactable elements.

Prefers data-test attributes (used throughout saucedemo.com) as the primary
locator hint, falling back to role + accessible name.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from playwright.sync_api import Page

INTERACTABLE_SELECTOR = "button, a, input, select, textarea, [role='button'], [role='link'], [role='checkbox']"

MAX_ELEMENTS = 60
MAX_TEXT_LEN = 80


@dataclass
class ElementSnapshot:
    tag: str
    role: str | None
    name: str | None
    data_test: str | None
    input_type: str | None
    text: str | None
    locator_hint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _truncate(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > MAX_TEXT_LEN:
        return value[:MAX_TEXT_LEN] + "..."
    return value


def _locator_hint(data_test: str | None, tag: str, role: str | None, name: str | None) -> str:
    if data_test:
        return f"[data-test={data_test!r}]"
    if role and name:
        return f"role={role} name={name!r}"
    return f"tag={tag}"


def observe(page: Page) -> dict[str, Any]:
    """Return a structured snapshot of the current page's interactable elements."""
    elements: list[ElementSnapshot] = []

    handles = page.query_selector_all(INTERACTABLE_SELECTOR)
    for handle in handles[:MAX_ELEMENTS]:
        try:
            if not handle.is_visible():
                continue
            tag = handle.evaluate("el => el.tagName.toLowerCase()")
            role = handle.get_attribute("role") or _implicit_role(tag)
            data_test = handle.get_attribute("data-test")
            input_type = handle.get_attribute("type") if tag == "input" else None
            name = (
                handle.get_attribute("aria-label")
                or handle.get_attribute("placeholder")
                or handle.inner_text()
                or handle.get_attribute("value")
            )
            text = handle.inner_text() if tag not in ("input", "textarea") else None

            elements.append(
                ElementSnapshot(
                    tag=tag,
                    role=role,
                    name=_truncate(name),
                    data_test=data_test,
                    input_type=input_type,
                    text=_truncate(text),
                    locator_hint=_locator_hint(data_test, tag, role, _truncate(name)),
                )
            )
        except Exception:
            # Element may have detached between query and read; skip it.
            continue

    return {
        "url": page.url,
        "title": page.title(),
        "elements": [e.to_dict() for e in elements],
    }


def _implicit_role(tag: str) -> str | None:
    return {
        "button": "button",
        "a": "link",
        "input": "textbox",
        "select": "combobox",
        "textarea": "textbox",
    }.get(tag)
