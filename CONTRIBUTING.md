# Contributing to MotionForge

Thanks for helping improve MotionForge. Small, focused contributions are easiest to review.

## Before opening an issue

- Search existing issues for the same problem or request.
- For a bug, include steps to reproduce, expected and actual behavior, Windows/Python versions, and the input type (camera, video, or JSON).
- Attach logs or a short screen recording when useful. Do not share recordings that identify people unless they have agreed to it.

## Development setup

1. Install Python 3.11 and `uv`.
2. Clone the repository and run `uv sync --extra dev`.
3. Start the app with `uv run python src/nexus.py`.
4. Run checks with `uv run python -m compileall -q src tests` and `uv run pytest -q`.

GitHub Actions runs the syntax check and test suite on Windows with Python 3.11 for every push and pull request. Please make sure these checks pass before merging. Ruff can also be run locally with `uv run ruff check .`; the current codebase still has existing lint findings being cleaned up separately.

## Pull requests

- Keep each pull request focused on one change.
- Explain what changed and how you checked it.
- Add or update tests for behavior changes when practical.
- Do not commit `.venv`, recordings, generated exports, or build folders.
- Use clear English for code, comments, and commit messages.

## Scope

MotionForge is an active markerless motion-capture project. Camera and lighting differences affect tracking, so report the source setup when describing quality issues. Avoid claims of calibrated or production-ready motion unless the relevant workflow has been measured and documented.
