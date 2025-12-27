# -*- coding: utf-8 -*-
"""
Streamlit bootstrapper (cloud-safe)
- Prefer loading the Streamlit-ready engine file if present:
    神秘游戏_streamlit_ready.py
  Fallback to:
    神秘游戏.py
- If the engine file has a SyntaxError/IndentationError, show the exact message
  in the Streamlit UI instead of Streamlit's redacted error page.
"""

from __future__ import annotations

import importlib.util
import traceback
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="神秘游戏", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
CANDIDATES = [
    BASE_DIR / "神秘游戏_streamlit_ready.py",
    BASE_DIR / "神秘游戏.py",
]

def _load_module_from(path: Path):
    spec = importlib.util.spec_from_file_location("mystery_game", str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module

def load_game_module():
    last_exc = None
    for p in CANDIDATES:
        if not p.exists():
            continue
        try:
            return _load_module_from(p)
        except Exception as e:
            last_exc = (p, e, traceback.format_exc())
    if last_exc is None:
        raise FileNotFoundError("No engine file found. Expected one of: " + ", ".join([c.name for c in CANDIDATES]))
    # Raise the last error
    p, e, tb = last_exc
    raise RuntimeError(f"Failed to import engine from {p.name}: {e}\n\n{tb}")

try:
    game = load_game_module()
except Exception as e:
    st.error("Engine import failed. Here is the full traceback (not redacted):")
    st.code(traceback.format_exc(), language="text")
    st.stop()

# Delegate to the final UI (your a1.1.10 strict-clone UI)
# If you use a different UI filename, change it here.
UI_PATH = BASE_DIR / "streamlit_app_final_a1_1_10.py"

if not UI_PATH.exists():
    st.error("UI file missing: streamlit_app_final_a1_1_10.py")
    st.stop()

# Inject loaded module into globals for the UI file (so it can use Engine directly)
globals()["game"] = game
globals()["Engine"] = game.Engine  # type: ignore[attr-defined]

# Execute UI file in this process, sharing the same Streamlit session_state.
exec(UI_PATH.read_text(encoding="utf-8"), globals(), globals())
