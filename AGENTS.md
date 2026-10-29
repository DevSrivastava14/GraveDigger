# Gravedigger: agent rules

## What this project is
A CLI that digs through a git repo's history, finds files that were deleted,
and renders them as tombstones in a self-contained HTML graveyard. A small
local LLM (Ollama, qwen3.5:2b) writes the epitaphs. Facts come from git;
only creative text comes from the LLM.

## Before every session
Read project_progress.md first. It says what is done, what is broken, and
what to do next.

## Working rules
1. Before writing code for a task, state your plan in a few lines and wait
   for confirmation.
2. Do only what the task asks. Do not add features, files or dependencies
   that were not requested.
3. Keep modules small with a single responsibility. Add type hints.
4. Every module starts with a short docstring: what it does and why it exists.
5. Comment the WHY of non-obvious decisions, not the what.
6. Everything must run offline. Never send repo content to any network
   service. The only allowed endpoint is local Ollama at http://localhost:11434.
7. The project runs on Windows (PowerShell). Use pathlib, never hardcode "/"
   in paths. Call git via subprocess with argument lists (never shell=True)
   and encoding="utf-8". Do not use grep, head, or other Unix-only commands.
8. Tests use pytest. Run them after every change and fix failures before
   reporting done.
9. At the end of every task, append to project_progress.md: what changed,
   why, and anything left broken.

## Out of scope unless asked
GitPython, web frameworks, databases, CDN assets in the HTML output.