# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository currently contains only `specs.txt` — the project has not been implemented yet. There is no build, lint, or test tooling to run. When implementation begins, this file should be updated with actual commands (setup, run, test) and any architectural decisions that diverge from the spec below.

## What this project is

An LLM-driven web automation system with a "discover once, replay deterministically" model, targeting https://www.saucedemo.com/ (login: `standard_user` / `secret_sauce`) as the demo app.

Core idea: an LLM agent uses Playwright to figure out how to complete a task in a web app by observing pages and deciding actions (click, type). Once it succeeds, the full sequence of steps is recorded as a JSON "artifact." Future runs of the same task replay that artifact directly via Playwright — no LLM call — executing deterministically and reporting success/failure based on expected outcomes, not LLM judgment.

Discovery goal used for the demo flow: "Login, add [PRODUCT_NAME] to cart, go to checkout, fill the req info, and place the order."

## Intended tech stack (per specs.txt)

- Language: Python
- Browser automation: Playwright
- Storage: flat JSON files (no database)
- Architecture: single process, CLI-driven (no queues/services/scaling infra)
- LLM provider/model: not yet decided — check specs.txt or ask before assuming one

## Intended architecture

Two execution modes share an artifact format:

1. **Discovery (agent loop)** — observes the current page via Playwright locators, calls the LLM with the goal and the set of actions available in that state, decides an action, and acts (click/type). Repeats until the goal is met or a stopping condition is hit. Every step is logged.
2. **Replay engine** — given a saved artifact + input params, replays the recorded steps directly with Playwright, with no LLM involved. Success/failure is determined by the artifact's recorded expected outcomes, not by LLM interpretation.

Supporting components:

- **Artifact schema + log** — after a successful discovery run, the full step sequence is serialized into a JSON artifact that the replay engine can consume.
- **Guardrails** — an allowlist of permitted domains/routes and action types, a safe-vs-risky/irreversible action classifier, and redaction of secrets/PII before anything is written to logs or artifacts. This sits in the path of both discovery and replay — any new action type or target domain must be checked against it.
- **Escalation & handoff** — on a hard failure or a blocked risky action, automation pauses, an `intervention_request.json` is written (goal, step, screenshot, reason), and the browser is left open (non-headless) on the same session for a human to intervene. Automation resumes via a CLI command once the human signals completion. This means discovery/replay cannot assume headless execution — the browser session must stay alive across a pause.
- **Evidence/logging** — structured JSON step log for every run (discovery or replay); screenshots captured on any failure or business-outcome event.

## Intended repo layout (not yet created)

```
/README.md
/REPORT.md
/evidence/              — run logs and artifacts (e.g. discovery_run_1.log, artifact_check_balance_v1.json)
/src
  /agent                — discovery loop (LLM observe/decide/act)
  /replay                — deterministic executor
  /artifact              — schema + save/load
  /guardrails            — allowlist + risk classification
  /escalation            — pause/handoff mechanism
  /target-app            — mock target app, if self-built
  /cli.py                — entrypoints: `run-agent`, `replay`
```

## Explicit non-goals

No multi-tenant support, no desktop app support, no real-time co-browsing operator console, no queues/services/scaling infrastructure, no stretch goals beyond the spec above. Don't add these even if they seem like natural extensions.
