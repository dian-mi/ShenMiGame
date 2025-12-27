# -*- coding: utf-8 -*-
"""
Streamlit app — a1.1.10 strict desktop-clone (cloud-safe)

Fixes requested:
1) Try to avoid full-page scroll: fixed-height main area + internal scrolling panes; compact header/footer
2) "显示实名 / 显示首字母" works (radio selector, reruns, applied to rank list)
3) Status color chips + log formatting (bold killer, red victim, defeated red) improved; more robust parsing
4) Layout: LEFT roles = 3 columns, RIGHT log = 1 column (about 1/4 width)

Engine:
- Must be placed as engine_core.py in the same folder (no tkinter)
"""

from __future__ import annotations

import html
import importlib.util
import re
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------------- Engine load (cloud-safe) ----------------
BASE_DIR = Path(__file__).resolve().parent
GAME_PATH = BASE_DIR / "engine_core.py"

def load_game_module():
    spec = importlib.util.spec_from_file_location("engine_core", str(GAME_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module

game = load_game_module()
Engine = game.Engine  # type: ignore[attr-defined]

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

    # menu toggles
    st.session_state.setdefault("export_error_log", False)
    st.session_state.setdefault("auto_skip_turn", False)
    st.session_state.setdefault("invincible_mode", False)
    st.session_state.setdefault("preserve_history", True)
    st.session_state.setdefault("name_mode", "full")  # full / initial
    st.session_state.setdefault("font_scale", 0.95)

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

# status badge colors (match desktop feel)
ROW_HL_BG = "#FFF2A8"
COLOR_THUNDER = "#0B3D91"  # 雷霆
COLOR_FROST = "#7EC8FF"    # 霜冻
COLOR_POS = "#D4AF37"      # 护盾/祝福等
COLOR_NEG = "#E53935"      # 负面
COLOR_PURPLE = "#8E44AD"   # 腐化

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
    parts = [p.strip() for p in s.split("；") if p.strip()]
    return parts

def render_badges(brief: str) -> str:
    parts = split_brief(brief)
    if not parts:
        return "<span class='hint'>—</span>"
    chips = []
    for p in parts:
        c = status_color(p)
        chips.append(f"<span class='badge' style='border-color:{c};color:{c};'>{html.escape(p)}</span>")
    return "".join(chips)

# log highlight formatting (more robust: supports spaces and varied punctuation)
KILL_RE = re.compile(r"(.*?)(【击杀】)\s*(.+?)\s*(→|->|⇒)\s*(.+?)(（.*|$)")
DEFEATED_RE = re.compile(r"(.*?)(\S+\(\d+\))(\s+被击败[:：].*)")

def format_log_line(line: str) -> str:
    raw = (line or "").rstrip("\n")

    km = KILL_RE.match(raw)
    if km:
        prefix, tag, killer, arrow, victim, rest = km.groups()
        return (
            "<div class='mono'>"
            f"{html.escape(prefix)}{html.escape(tag)} "
            f"<b>{html.escape(killer.strip())}</b> "
            f"{html.escape(arrow)} "
            f"<span class='killvictim'>{html.escape(victim.strip())}</span>"
            f"{html.escape(rest)}"
            "</div>"
        )

    dm = DEFEATED_RE.match(raw)
    if dm:
        prefix, victim, rest = dm.groups()
        return (
            "<div class='mono'>"
            f"{html.escape(prefix)}"
            f"<span class='killvictim'>{html.escape(victim)}</span>"
            f"{html.escape(rest)}"
            "</div>"
        )

    # emphasize 【回合开始】/【回合结束】 markers
    if "回合开始" in raw or "回合结束" in raw:
        return f"<div class='mono turnmark'><b>{html.escape(raw)}</b></div>"

    return f"<div class='mono'>{html.escape(raw)}</div>"

def render_log(lines: List[str]) -> str:
    if not lines:
        return "<div class='mono'><b>【新开局】</b> 已生成初始排名</div>"
    return "\n".join(format_log_line(ln) for ln in lines[-400:])

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
        step_line()                 # show first line
        st.session_state.playing = True
        step_line()                 # immediately proceed 1 more line (desktop feel)

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
st.set_page_config(page_title="神秘游戏 a1.1.10", layout="wide")

fs = float(st.session_state.get("font_scale", 1.0))
rank_font = int(13 * fs)
log_font = int(12.5 * fs)
badge_font = int(11.5 * fs)

st.markdown(
    f"""
<style>
/* Compact overall padding */
.main .block-container{{ padding-top:.12rem; padding-bottom:.12rem; max-width: 1800px; }}
footer{{visibility:hidden;}} header{{visibility:hidden;}}

/* Avoid whole-page scrolling as much as possible */
html, body, [data-testid="stAppViewContainer"]{{ height: 100%; overflow: hidden; }}

/* Reduce gaps */
div[data-testid="stVerticalBlock"]{{ gap: .25rem; }}

/* Main pane height: leave room for top bar + bottom bar (more aggressive) */
#mainpane{{ height: calc(100vh - 118px); min-height: 520px; }}

/* Internal scroll panes */
.pane{{ height: 100%; overflow: hidden; }}
.scrollbox{{ height: 100%; overflow-y: auto; padding-right: 6px; }}

/* Role rows (compact, listbox-like) */
.rank-row{{
  padding: 4px 6px;
  border-radius: 8px;
  margin: 3px 0;
  border: 1px solid rgba(49,51,63,0.18);
}}
.rankname{{ font-size: {rank_font}px; line-height: 1.1; }}
.badge{{ display:inline-block; padding:0px 6px; margin:0 5px 4px 0; border-radius:999px; border:1px solid; font-size:{badge_font}px; line-height:18px; }}
.hint{{ color:#64748b; font-size:{badge_font}px; }}

/* Log */
.mono{{ white-space: pre-wrap; font-family: ui-monospace, Menlo, Consolas, monospace; font-size:{log_font}px; line-height:1.25; }}
.killvictim{{ color: {COLOR_NEG}; font-weight: 700; }}
.turnmark{{ opacity: 0.92; }}

/* Buttons smaller */
.stButton>button{{ padding: .22rem .55rem; }}
/* Slider label smaller */
label[data-testid="stWidgetLabel"]{{ font-size: 0.9rem; }}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------- Top bar (very compact) ----------------
bar = st.columns([0.9, 2.6, 1.9, 2.6], gap="small")

with bar[0]:
    with st.popover("菜单", use_container_width=True):
        st.checkbox("输出异常日志(error_log.txt)", key="export_error_log")
        st.checkbox("自动跳回合（回合结束后5秒）", key="auto_skip_turn")
        st.checkbox("找自称无敌模式", key="invincible_mode")
        st.checkbox("保留历史记录", key="preserve_history")
        st.divider()
        st.radio("名字显示", options=["显示实名", "显示首字母"], index=0 if st.session_state.name_mode=="full" else 1, key="__name_radio")
        st.session_state.name_mode = "full" if st.session_state.__name_radio == "显示实名" else "initial"
        st.divider()
        fs_new = st.slider("字体", 0.7, 1.2, float(st.session_state.font_scale), 0.05)
        if abs(fs_new - float(st.session_state.font_scale)) > 1e-9:
            st.session_state.font_scale = fs_new
            st.rerun()

with bar[1]:
    st.markdown("**神秘游戏 a1.1.10（Streamlit）**")
    st.caption("左：角色三栏｜右：日志（不下滑，栏内滚动）")

with bar[2]:
    # quick toggles like desktop checkbox area
    st.toggle("找自称(25)无敌", key="invincible_mode")

with bar[3]:
    # quick actions (top) — keeps bottom bar for full controls
    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        if st.button("新开局", use_container_width=True):
            new_game()
            st.rerun()
    with c2:
        if st.button("下一回合", use_container_width=True, disabled=bool(getattr(engine, "game_over", False))):
            build_turn()
            st.rerun()
    with c3:
        if st.button("暂停", use_container_width=True, disabled=bool(getattr(engine, "game_over", False))):
            st.session_state.playing = False
            st.session_state.pop("autoplay_tick", None)
            st.rerun()

# ---------------- Autoplay & autoskip timers ----------------
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
        out.append(
            f"""
<div class="rank-row" style="background:{bg};">
  <div class="rankname"><b>{i:>2}. {html.escape(name)}({cid})</b></div>
  <div style="margin-top:2px;">{render_badges(brief)}</div>
</div>
"""
        )
    return "\n".join(out) if out else "<div class='hint'>—</div>"

start2 = 1 + len(rank_1)
start3 = start2 + len(rank_2)

# ---------------- Main 4 panes: 3 roles + 1 log ----------------
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
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("**日志**")
    st.markdown(render_log(st.session_state.revealed_lines), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# ---------------- Bottom control bar (compact) ----------------
st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
game_over = bool(getattr(engine, "game_over", False))
disable_adv = game_over

bcols = st.columns([1.0, 1.0, 1.0, 1.0, 0.9, 2.8], gap="small")

with bcols[0]:
    if st.button("新开局", use_container_width=True):
        new_game()
        st.rerun()

with bcols[1]:
    if st.button("下一回合", use_container_width=True, disabled=disable_adv):
        build_turn()
        st.rerun()

with bcols[2]:
    if st.button("下一行", use_container_width=True, disabled=disable_adv):
        cancel_autoskip()
        step_line()
        st.rerun()

with bcols[3]:
    if st.button("自动播放", use_container_width=True, disabled=disable_adv):
        cancel_autoskip()
        frames = getattr(engine, "replay_frames", []) or []
        if frames and st.session_state.cursor < len(frames):
            st.session_state.playing = True
            st.session_state.pop("autoplay_tick", None)
        st.rerun()

with bcols[4]:
    if st.button("暂停", use_container_width=True, disabled=disable_adv):
        st.session_state.playing = False
        st.session_state.pop("autoplay_tick", None)
        st.rerun()

with bcols[5]:
    st.session_state.autoplay_ms = st.slider(
        "播放速度",
        min_value=100,
        max_value=2000,
        value=int(st.session_state.autoplay_ms),
        step=50,
    )
    st.markdown(
        f"<div class='hint' style='text-align:right;'>{st.session_state.autoplay_ms/1000:.2f}s/行</div>",
        unsafe_allow_html=True,
    )
