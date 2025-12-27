# -*- coding: utf-8 -*-
"""
Shenmi Game Streamlit UI — a1.1.10 desktop-clone (Cloud-safe) — v4

Fixes:
1) Minimize page scrolling: single top menu row + single bottom control bar.
   Main content uses fixed viewport-height area; columns scroll internally only.
2) Remove StreamlitDuplicateElementId by assigning explicit unique keys for ALL widgets.
3) Log panel rendered as a "window" using st.text_area (own scroll), not as long HTML.
4) Layout: 3 role columns + 1 log column (~1/4).

Requires engine_core.py in same folder.
"""

from __future__ import annotations

import importlib.util
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from streamlit_autorefresh import st_autorefresh

UI_VERSION = "v4"

# ---------------- Engine load (cloud-safe) ----------------
BASE_DIR = Path(__file__).resolve().parent
ENGINE_PATH = BASE_DIR / "engine_core.py"

def load_engine():
    spec = importlib.util.spec_from_file_location("engine_core", str(ENGINE_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module

engine_mod = load_engine()
Engine = engine_mod.Engine  # type: ignore[attr-defined]

# ---------------- Session state ----------------
def ss_init():
    if "engine" not in st.session_state:
        st.session_state.engine = Engine(seed=None, fast_mode=False)
        try:
            st.session_state.engine.new_game()
        except Exception:
            pass

    st.session_state.setdefault("cursor", 0)
    st.session_state.setdefault("revealed_lines", [])
    st.session_state.setdefault("current_snap", None)
    st.session_state.setdefault("current_highlights", [])
    st.session_state.setdefault("playing", False)
    st.session_state.setdefault("autoplay_ms", 250)

    st.session_state.setdefault("export_error_log", False)
    st.session_state.setdefault("auto_skip_turn", False)
    st.session_state.setdefault("invincible_mode", False)
    st.session_state.setdefault("preserve_history", True)
    st.session_state.setdefault("name_mode", "full")  # full / initial
    st.session_state.setdefault("font_scale", 0.92)
    st.session_state.setdefault("auto_skip_deadline", None)

ss_init()
engine: Any = st.session_state.engine

# ---------------- Helpers ----------------
def append_error_log(exc: BaseException):
    if not st.session_state.get("export_error_log", False):
        return
    try:
        p = BASE_DIR / "error_log.txt"
        with p.open("a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass

def to_initial(name: str) -> str:
    name = (name or "").strip()
    return name[0] if name else "?"

def display_name(name: str) -> str:
    return to_initial(name) if st.session_state.get("name_mode") == "initial" else name

# Status badge colors
ROW_HL_BG = "#FFF2A8"
COLOR_THUNDER = "#0B3D91"
COLOR_FROST = "#7EC8FF"
COLOR_POS = "#D4AF37"
COLOR_NEG = "#E53935"
COLOR_PURPLE = "#8E44AD"

POS_KEYWORDS = ("护盾", "祝福")
NEG_PREFIX = ("雷霆", "霜冻", "封印", "遗忘", "遗策", "黄昏", "留痕", "厄运", "禁盾", "禁得盾", "集火", "孤傲", "腐化")

def status_color(part: str) -> str:
    p = part.strip()
    if not p:
        return "#64748b"
    if p.startswith("雷霆"):
        return COLOR_THUNDER
    if p.startswith("霜冻"):
        return COLOR_FROST
    if p.startswith("腐化"):
        return COLOR_PURPLE
    if p.startswith(POS_KEYWORDS):
        return COLOR_POS
    if p.startswith(NEG_PREFIX):
        return COLOR_NEG
    return "#64748b"

def split_brief(brief: str) -> List[str]:
    if not brief:
        return []
    s = str(brief).replace(";", "；")
    return [p.strip() for p in s.split("；") if p.strip()]

# Log formatting
KILL_RE = re.compile(r"(【击杀】)\s*(.+?)\s*(→|->|⇒)\s*(.+?)(（.*|$)")
DEFEATED_RE = re.compile(r"(\S+\(\d+\))(\s+被击败[:：].*)")

def fmt_log(line: str) -> str:
    raw = (line or "").rstrip("\n")

    km = KILL_RE.search(raw)
    if km:
        tag, killer, arrow, victim, rest = km.groups()
        # bold killer, red victim
        return f"{tag} {killer} {arrow} 【{victim}】{rest}"

    dm = DEFEATED_RE.search(raw)
    if dm:
        victim, rest = dm.groups()
        return f"【{victim}】{rest}"

    return raw

def render_log_text(lines: List[str]) -> str:
    if not lines:
        return "【新开局】已生成初始排名"
    # keep last N lines
    view = lines[-500:]
    return "\n".join(fmt_log(x) for x in view)

def cancel_autoskip():
    st.session_state.auto_skip_deadline = None
    st.session_state.pop("autoskip_tick", None)

def new_game():
    cancel_autoskip()
    st.session_state.playing = False
    st.session_state.pop("autoplay_tick", None)
    try:
        engine.new_game()
    except Exception as e:
        append_error_log(e)
        raise
    st.session_state.cursor = 0
    st.session_state.revealed_lines = []
    st.session_state.current_snap = None
    st.session_state.current_highlights = []

def apply_invincible():
    try:
        if hasattr(engine, "set_invincible"):
            engine.set_invincible(25, bool(st.session_state.get("invincible_mode", False)))
    except Exception:
        pass

def build_turn():
    cancel_autoskip()
    if getattr(engine, "game_over", False):
        return

    if not st.session_state.get("preserve_history", True):
        st.session_state.revealed_lines = []

    try:
        if hasattr(engine, "tick_alive_turns"):
            engine.tick_alive_turns()
        apply_invincible()
        engine.next_turn()
    except Exception as e:
        append_error_log(e)
        raise

    st.session_state.cursor = 0
    st.session_state.playing = False
    st.session_state.current_snap = None
    st.session_state.current_highlights = []

    frames = getattr(engine, "replay_frames", []) or []
    if frames:
        step_line()
        st.session_state.playing = True
        step_line()

def step_line():
    frames = getattr(engine, "replay_frames", []) or []
    cur = int(st.session_state.cursor)

    if cur >= len(frames):
        st.session_state.playing = False
        st.session_state.pop("autoplay_tick", None)
        if (not getattr(engine, "game_over", False)) and st.session_state.get("auto_skip_turn", False) and len(frames) > 0:
            st.session_state.auto_skip_deadline = time.time() + 5
        return

    frame = frames[cur]
    st.session_state.cursor = cur + 1
    st.session_state.revealed_lines.append(frame.get("text", ""))
    st.session_state.current_snap = frame.get("snap")
    st.session_state.current_highlights = frame.get("highlights", []) or []

# ---------------- Page / CSS ----------------
st.set_page_config(page_title=f"神秘游戏 a1.1.10 ({UI_VERSION})", layout="wide")

fs = float(st.session_state.get("font_scale", 1.0))
rank_font = int(13 * fs)
badge_font = int(11 * fs)

st.markdown(
    f"""
<style>
.main .block-container{{ padding-top:.06rem; padding-bottom:.06rem; max-width: 2000px; }}
footer{{visibility:hidden;}} header{{visibility:hidden;}}
div[data-testid="stVerticalBlock"]{{ gap: .14rem; }}

/* Strongly discourage full-page scroll; panes scroll internally */
html, body, [data-testid="stAppViewContainer"]{{ height: 100%; overflow: hidden; }}
[data-testid="stAppViewContainer"] > .main{{ height: 100%; overflow: hidden; }}
.main .block-container{{ height: 100vh; overflow: hidden; }}

/* Main pane height leaves room for top row and bottom bar */
#mainpane{{ height: calc(100vh - 92px); min-height: 520px; }}

/* Internal scroll panes */
.pane{{ height: 100%; overflow: hidden; }}
.scrollbox{{ height: 100%; overflow-y: auto; padding-right: 6px; }}

/* Role rows */
.rank-row{{ padding: 4px 6px; border-radius: 8px; margin: 3px 0; border: 1px solid rgba(49,51,63,0.18); }}
.rankname{{ font-size: {rank_font}px; line-height: 1.1; }}
.badge{{ display:inline-block; padding:0px 6px; margin:0 5px 4px 0; border-radius:999px; border:1px solid; font-size:{badge_font}px; line-height:18px; }}
.hint{{ color:#64748b; font-size:{badge_font}px; }}

/* Make buttons smaller */
.stButton>button{{ padding: .16rem .48rem; }}
label[data-testid="stWidgetLabel"]{{ font-size: 0.9rem; }}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------- Top row (single line, compact) ----------------
top = st.columns([1.2, 1.5, 1.1, 1.1, 1.1, 1.0], gap="small")

with top[0]:
    st.markdown("**神秘游戏 a1.1.10**")
    st.caption("三栏角色｜一栏日志（窗口）")

with top[1]:
    # Name mode visible
    nm = st.radio(
        "名字显示",
        options=["显示实名", "显示首字母"],
        horizontal=True,
        index=0 if st.session_state.name_mode == "full" else 1,
        key="name_mode_radio",
    )
    st.session_state.name_mode = "full" if nm == "显示实名" else "initial"

with top[2]:
    st.toggle("找自称(25)无敌", key="invincible_mode")

with top[3]:
    st.toggle("自动跳回合", key="auto_skip_turn")

with top[4]:
    st.toggle("保留历史", key="preserve_history")

with top[5]:
    with st.popover("菜单", use_container_width=True):
        st.checkbox("输出异常日志(error_log.txt)", key="export_error_log")
        fs_new = st.slider("字体", 0.75, 1.15, float(st.session_state.font_scale), 0.05, key="font_slider")
        if abs(fs_new - float(st.session_state.font_scale)) > 1e-9:
            st.session_state.font_scale = fs_new
            st.rerun()

# ---------------- Autoplay / autoskip timers ----------------
if st.session_state.playing:
    st_autorefresh(interval=int(st.session_state.autoplay_ms), key="autoplay_tick")
    step_line()

deadline = st.session_state.get("auto_skip_deadline")
if deadline is not None:
    st_autorefresh(interval=1000, key="autoskip_tick")
    if time.time() >= float(deadline):
        st.session_state.auto_skip_deadline = None
        build_turn()
        st.rerun()

# ---------------- Snapshot ----------------
snap: Dict[str, Any]
if st.session_state.current_snap is None:
    snap = engine._snapshot()
else:
    snap = st.session_state.current_snap or engine._snapshot()

rank: List[int] = snap.get("rank", []) or []
status_map: Dict[int, Dict[str, Any]] = snap.get("status", {}) or {}
highlights = set(st.session_state.get("current_highlights", []) or [])

# Split into 3 columns
n = len(rank)
a = (n + 2) // 3
b = (n + 1) // 3
rank_1 = rank[:a]
rank_2 = rank[a:a+b]
rank_3 = rank[a+b:]

def render_rank_column(rank_ids: List[int], start_index: int) -> str:
    out: List[str] = []
    for i, cid in enumerate(rank_ids, start=start_index):
        info = status_map.get(cid, {"name": str(cid), "brief": ""})
        name = display_name(str(info.get("name", cid)))
        brief = str(info.get("brief", ""))

        bg = ROW_HL_BG if cid in highlights else "transparent"
        parts = split_brief(brief)
        if parts:
            chips = []
            for p in parts:
                c = status_color(p)
                chips.append(f"<span class='badge' style='border-color:{c};color:{c};'>{html.escape(p)}</span>")
            badges = "".join(chips)
        else:
            badges = "<span class='hint'>—</span>"

        out.append(
            f"""
<div class="rank-row" style="background:{bg};">
  <div class="rankname"><b>{i:>2}. {html.escape(name)}({cid})</b></div>
  <div style="margin-top:2px;">{badges}</div>
</div>
"""
        )
    return "\n".join(out) if out else "<div class='hint'>—</div>"

start2 = 1 + len(rank_1)
start3 = start2 + len(rank_2)

# ---------------- Main panes ----------------
st.markdown("<div id='mainpane'>", unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.0, 1.05], gap="small")

with c1:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown(f"**回合 {snap.get('turn', 0)}**")
    st.markdown(render_rank_column(rank_1, 1), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c2:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("&nbsp;")
    st.markdown(render_rank_column(rank_2, start2), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c3:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("&nbsp;")
    st.markdown(render_rank_column(rank_3, start3), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c4:
    # Log as "window": text_area with internal scrolling
    # Height: approximate (fits common screens); page itself should not scroll.
    log_text = render_log_text(st.session_state.revealed_lines)
    st.text_area(
        "日志（窗口）",
        value=log_text,
        height=740,
        disabled=True,
        key="log_text_area",
    )

st.markdown("</div>", unsafe_allow_html=True)

# ---------------- Bottom bar (single, unique keys) ----------------
bar = st.columns([1.0, 1.0, 1.0, 1.0, 0.9, 2.8], gap="small")
game_over = bool(getattr(engine, "game_over", False))

with bar[0]:
    if st.button("新开局", use_container_width=True, key="btn_new_game"):
        new_game()
        st.rerun()

with bar[1]:
    if st.button("下一回合", use_container_width=True, disabled=game_over, key="btn_next_turn"):
        build_turn()
        st.rerun()

with bar[2]:
    if st.button("下一行", use_container_width=True, disabled=game_over, key="btn_next_line"):
        cancel_autoskip()
        step_line()
        st.rerun()

with bar[3]:
    if st.button("自动播放", use_container_width=True, disabled=game_over, key="btn_autoplay"):
        cancel_autoskip()
        frames = getattr(engine, "replay_frames", []) or []
        if frames and st.session_state.cursor < len(frames):
            st.session_state.playing = True
            st.session_state.pop("autoplay_tick", None)
        st.rerun()

with bar[4]:
    if st.button("暂停", use_container_width=True, disabled=game_over, key="btn_pause"):
        st.session_state.playing = False
        st.session_state.pop("autoplay_tick", None)
        st.rerun()

with bar[5]:
    st.session_state.autoplay_ms = st.slider(
        "播放速度",
        min_value=100,
        max_value=2000,
        value=int(st.session_state.autoplay_ms),
        step=50,
        key="slider_speed",
    )
