"""Shared page factory for the dev tools: honours TCC_THEME. Dev tooling.

    $env:TCC_THEME = 'classic'; python frontend/tools/measure_ui.py

The theme is written to localStorage BEFORE the app boots, which is the last
override `applyTheme` consults (src/brand.config.js). Without the variable the
build default (modern) applies, so every tool still runs unchanged.
"""
from __future__ import annotations

import os


def theme() -> str | None:
    value = os.environ.get("TCC_THEME")
    return value if value in ("modern", "classic") else None


def new_page(browser, width: int = 1024, height: int = 768):
    context = browser.new_context(viewport={"width": width, "height": height})
    chosen = theme()
    if chosen:
        context.add_init_script(f"window.localStorage.setItem('tcc-theme', '{chosen}')")
    return context.new_page()
