# -*- coding: utf-8 -*-
"""
神秘游戏 a1.1.10 — Streamlit Cloud UI (fix pack)

满足你最新 5 条要求：
1) 页面不整体滚动；角色区 & 日志区各自独立滚动（像窗口）。
2) 名字显示逻辑严格复刻桌面版：显示实名 / 显示首字母 互斥，且都可都关。
3) 日志富文本：淘汰相关行标红；所有出现的角色名加粗；【角色】块名加粗。
4) 状态标签颜色：鱼/净化/护盾/祝福/封印/霜冻/雷霆/腐化/隐身 等。
5) 角色栏与日志中，名字后的 (数字) 一律移除。

依赖：engine_core.py（无 tkinter 版）
"""

from __future__ import annotations

import html
import re
import time
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

REALNAME_MAP: Dict[str, str] = {'更西部': '高鑫博', 'Sunnydayorange': '秦添城', '施博理': '施博文', '释延能': '邵煜楠', '牵寒': '黄芊涵', 'mls': '孟真', '放烟花': '范雨涵', '合议庭': '黄煜婷', '藕禄': '欧鹭', '梅雨神': '董玫妤', '豆进天之父': '胡喆', '钟无艳': '章文元', 'hewenx': '何文馨', '豆进天': '窦竞天', '书法家': '孙凡珺', '路济阳': '陆嘉翊', '增进舒': '曾靖舒', '找自称': '赵梓琛', '郑孑健': '郑子健', '左右脑': '甄艺诺'}
INITIALS_MAP: Dict[str, str] = {'朱昊泽': 'zhz', '蒋骐键': 'jqj', '李知雨': 'lzy', '朱诚': 'zc', '邵煜楠': 'syn', '陈心如': 'cxr', '俞守衡': 'ysh', '施禹谦': 'syq', '虞劲枫': 'yjf', '范一诺': 'fyn', '孙凡珺': 'sfj', '严雅': 'yy', '陆嘉翊': 'ljy', '甄艺诺': 'zyn', '黄煜婷': 'hyt', '赵梓琛': '赵zc', '卞一宸': 'byc', '章文元': 'zyw', '施沁皓': 'sqh', '秦添城': 'qtc', '季任杰': 'jrj', '黄伶俐': 'hll', '高鑫博': 'gxb', '郑子健': 'zzj', '金逸阳': 'jyy', '范雨涵': 'fyh', '胡喆': 'hz', '谢承哲': 'xcz', '何文馨': 'hwx', '沈澄婕': 'scj', '张志成': '张zc', '孟真': 'mz', '黄梓睿': 'hzr', '冷雨霏': 'lyf', '黄芊涵': 'hqh', '欧鹭': 'ol', '姚舒馨': 'ysx', '施博文': 'sbw', '曾靖舒': 'zjs', '董玫妤': 'dmy', '陆泽灏': 'lzh', '戚银潞': 'qyl', '窦竞天': 'djt'}

st.set_page_config(page_title="神秘游戏 a1.1.10", layout="wide")

@st.cache_resource(show_spinner=False)
def load_engine():
    import importlib
    try:
        core = importlib.import_module("engine_core")
    except Exception:
        import importlib.util
        here = Path(__file__).resolve().parent
        p = here / "engine_core.py"
        spec = importlib.util.spec_from_file_location("engine_core", str(p))
        if spec is None or spec.loader is None:
            raise
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)  # type: ignore[attr-defined]
    return getattr(core, 'GameEngine', getattr(core, 'Engine'))()

engine = load_engine()
with st.sidebar.expander("Debug", expanded=False):
    try:
        import engine_core as _core
        st.write("ENGINE_VERSION:", getattr(_core, "ENGINE_VERSION", "unknown"))
        st.write("Engine class:", type(engine).__name__)
    except Exception as e:
        st.error(f"Debug info failed: {e}")


def _ss_init():
    ss = st.session_state
    ss.setdefault("cursor", 0)
    ss.setdefault("revealed_lines", [])
    ss.setdefault("current_snap", None)
    ss.setdefault("current_highlights", [])
    ss.setdefault("playing", False)

    ss.setdefault("auto_skip_turn", False)
    ss.setdefault("invincible_mode", False)
    ss.setdefault("preserve_history", True)

    ss.setdefault("show_realname", False)
    ss.setdefault("show_initials", False)

    ss.setdefault("speed_slider", 0.25)

_ss_init()

# ---- name toggles: desktop-like mutual exclusion, but both can be off ----
def _toggle_realname():
    if st.session_state.get("show_realname") and st.session_state.get("show_initials"):
        st.session_state["show_initials"] = False

def _toggle_initials():
    if st.session_state.get("show_initials") and st.session_state.get("show_realname"):
        st.session_state["show_realname"] = False

def display_name_from_raw(raw_name: str) -> str:
    name = (raw_name or "").strip()
    if st.session_state.get("show_realname"):
        return REALNAME_MAP.get(name, name).strip()
    if st.session_state.get("show_initials"):
        real = REALNAME_MAP.get(name, name).strip()
        return INITIALS_MAP.get(real, real).strip()
    return name

def strip_cid_suffix(text: str) -> str:
    # Name(12) / Name（12）
    return re.sub(r"([\u4e00-\u9fffA-Za-z0-9_\-·\.\s]{1,40})[\(（]\s*\d+\s*[\)）]", lambda m: m.group(1).strip(), text)

def rewrite_names_in_text(text: str, cid_to_rawname: Dict[int, str]) -> str:
    if not text:
        return ""
    pat = re.compile(r"([\u4e00-\u9fffA-Za-z0-9_\-·\.\s]{1,40})[\(（]\s*(\d+)\s*[\)）]")
    def repl(m):
        cid = int(m.group(2))
        raw = cid_to_rawname.get(cid, m.group(1).strip())
        return display_name_from_raw(raw)
    out = pat.sub(repl, text)
    return strip_cid_suffix(out)

# ---- status colors ----
COLOR_GOLD = "#D4AF37"
COLOR_RED = "#E53935"
COLOR_GREEN = "#2E7D32"
COLOR_BLUE = "#1E40AF"
COLOR_FROST = "#7EC8FF"
COLOR_PURPLE = "#8E44AD"
COLOR_GRAY = "#64748b"

def status_color(token: str) -> str:
    t = (token or "").strip()
    if not t:
        return COLOR_GRAY
    if t in ("鱼", "咸鱼"):
        return COLOR_BLUE
    if t in ("净化",):
        return COLOR_GREEN
    if t in ("隐身",):
        return COLOR_PURPLE
    if t in ("护盾", "祝福", "辩护", "防线"):
        return COLOR_GOLD
    if t in ("封印", "遗忘", "厄运", "黄昏", "留痕", "禁盾", "集火", "孤傲"):
        return COLOR_RED
    if t.startswith("雷霆"):
        return COLOR_BLUE
    if t.startswith("霜冻"):
        return COLOR_FROST
    if t.startswith("腐化"):
        return COLOR_PURPLE
    return COLOR_GRAY

# ---- rich log formatting ----
KILL_KEYWORDS = ("被击败", "淘汰", "出局", "死亡", "斩杀", "击败", "阵亡")

def bold_all_role_names(escaped_text: str, all_names: List[str]) -> str:
    names = sorted({n for n in all_names if n}, key=len, reverse=True)
    out = escaped_text
    for n in names:
        esc = html.escape(n)
        out = re.sub(rf"(?<![\w>]){re.escape(esc)}(?![\w<])", rf"<b>{esc}</b>", out)
    return out

def format_log_lines(lines: List[str], cid_to_rawname: Dict[int, str], all_display_names: List[str]) -> str:
    if not lines:
        return "<div class='hint'>（暂无日志）</div>"
    out: List[str] = []
    for raw in lines:
        line = (raw or "").rstrip("\n")
        line = rewrite_names_in_text(line, cid_to_rawname)

        esc = html.escape(line)
        esc = bold_all_role_names(esc, all_display_names)
        esc = re.sub(r"【([^】]+)】", lambda m: "【<b>" + m.group(1) + "</b>】", esc)

        is_kill = any(k in line for k in KILL_KEYWORDS)
        cls = "logline kill" if is_kill else "logline"
        out.append(f"<div class='{cls}'>{esc}</div>")
    return "\n".join(out)

# ---- gameplay controls ----
def apply_invincible():
    try:
        if hasattr(engine, "set_invincible"):
            engine.set_invincible(25, bool(st.session_state.get("invincible_mode", False)))
    except Exception:
        pass

def new_game():
    apply_invincible()
    if hasattr(engine, "new_game"):
        engine.new_game()
    elif hasattr(engine, "reset"):
        engine.reset()

    st.session_state.cursor = 0
    if not st.session_state.get("preserve_history", True):
        st.session_state.revealed_lines = []
    st.session_state.current_snap = None
    st.session_state.current_highlights = []
    st.session_state.playing = False

    frames = getattr(engine, "replay_frames", None)
    if isinstance(frames, list) and frames:
        step_line()

def next_turn():
    apply_invincible()
    if hasattr(engine, "next_turn"):
        engine.next_turn()
    elif hasattr(engine, "step_turn"):
        engine.step_turn()

    st.session_state.cursor = 0
    if not st.session_state.get("preserve_history", True):
        st.session_state.revealed_lines = []
    st.session_state.current_snap = None
    st.session_state.current_highlights = []
    st.session_state.playing = False

    frames = getattr(engine, "replay_frames", None)
    if isinstance(frames, list) and frames:
        step_line()

def step_line():
    frames = getattr(engine, "replay_frames", []) or []
    cur = int(st.session_state.cursor)
    if cur >= len(frames):
        st.session_state.playing = False
        st.session_state.pop("autoplay_tick", None)
        return
    frame = frames[cur] or {}
    st.session_state.cursor = cur + 1
    st.session_state.revealed_lines.append(frame.get("text", ""))
    st.session_state.current_snap = frame.get("snap")
    st.session_state.current_highlights = frame.get("highlights", []) or []

# ---- CSS: no page scroll; internal windows scroll ----
st.markdown(
    """
<style>
html, body, [data-testid="stAppViewContainer"] { height: 100%; overflow: hidden; }
[data-testid="stAppViewContainer"] > .main { height: 100%; overflow: hidden; }
.main .block-container {
  height: 100vh; max-width: 2000px;
  padding-top: .30rem; padding-bottom: .30rem;
  overflow: hidden;
}

div[data-testid="stVerticalBlock"] { gap: .25rem; }

.window {
  height: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.winhead {
  padding: .45rem .6rem;
  border-bottom: 1px solid #e5e7eb;
  font-weight: 800;
}
.winbody {
  height: calc(100% - 42px);
  overflow-y: auto;
  padding: .5rem .55rem;
}

.rolecard {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: .4rem .5rem;
  margin-bottom: .45rem;
}
.rolecard .name { font-weight: 800; }
.dead { opacity: .55; }

.badge {
  display: inline-block;
  padding: 2px 8px;
  margin-right: 6px;
  border-radius: 999px;
  border: 1px solid;
  font-size: 12px;
  line-height: 18px;
}

.logline {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  white-space: pre-wrap;
  line-height: 1.35;
}
.logline b { font-weight: 900; }
.logline.kill { color: #E53935; font-weight: 900; }

.hint { color: #6b7280; }

/* main area height: reserve space for top+bottom */
#mainpane { height: calc(100vh - 170px); min-height: 560px; }

.bottombar button[kind] { padding: .35rem .75rem; }
</style>
""",
    unsafe_allow_html=True,
)

# ---- Top row ----
top = st.columns([1.2, 1, 1, 1, 1, 1], vertical_alignment="center")
with top[0]:
    st.markdown("### 神秘游戏 a1.1.10")
with top[1]:
    st.toggle("显示实名", key="show_realname", on_change=_toggle_realname)
with top[2]:
    st.toggle("显示首字母", key="show_initials", on_change=_toggle_initials)
with top[3]:
    st.toggle("找自称无敌", key="invincible_mode")
with top[4]:
    st.toggle("自动跳回合", key="auto_skip_turn")
with top[5]:
    st.toggle("保留历史", key="preserve_history")

# ---- ensure started ----
if st.session_state.current_snap is None and getattr(engine, "replay_frames", None) is None:
    new_game()
if st.session_state.current_snap is None and getattr(engine, "replay_frames", []):
    if st.session_state.cursor == 0:
        step_line()

snap: Dict[str, Any] = st.session_state.current_snap or { "rank": [], "status": {} }
rank: List[int] = list(snap.get("rank") or [])
status_map: Dict[int, Dict[str, Any]] = snap.get("status") or {}

# ---- name dictionaries ----
cid_to_rawname: Dict[int, str] = {}
for cid, role in getattr(engine, "roles", {}).items():
    try:
        cid_to_rawname[int(cid)] = getattr(role, "name", "").strip()
    except Exception:
        pass

def display_name_from_cid(cid: int) -> str:
    return display_name_from_raw(cid_to_rawname.get(cid, str(cid)))

all_display_names = [display_name_from_cid(c) for c in cid_to_rawname.keys()]

# ---- role helpers ----
def role_badges_for_cid(cid: int) -> List[str]:
    info = status_map.get(cid) or {}
    badges = info.get("badges") or info.get("brief_parts") or info.get("brief") or info.get("tags")
    if isinstance(badges, str):
        parts = re.split(r"[\s\|｜，,]+", badges.strip())
        return [p for p in parts if p]
    if isinstance(badges, list):
        return [str(x).strip() for x in badges if str(x).strip()]
    return []

def is_alive(cid: int) -> bool:
    info = status_map.get(cid) or {}
    if "alive" in info:
        return bool(info.get("alive"))
    r = getattr(engine, "roles", {}).get(cid)
    return bool(getattr(r, "alive", True)) if r is not None else True

def render_role_card(idx: int, cid: int) -> str:
    name = display_name_from_cid(cid)
    alive = is_alive(cid)
    badges = role_badges_for_cid(cid)
    if badges:
        chips: List[str] = []
        for b in badges:
            c = status_color(b)
            chips.append(f"<span class='badge' style='border-color:{c};color:{c};'>{html.escape(b)}</span>")
        badge_html = "".join(chips)
    else:
        badge_html = "<span class='hint'>—</span>"
    cls = "rolecard" + ("" if alive else " dead")
    return f"<div class='{cls}'><div class='name'>{idx}. {html.escape(name)}</div><div style='margin-top:4px;'>{badge_html}</div></div>"

# ---- rank split ----
if not rank:
    rank = list(getattr(engine, "rank", []) or [])
n = len(rank)
c1 = rank[: (n + 2)//3]
c2 = rank[(n + 2)//3 : (2*n + 2)//3]
c3 = rank[(2*n + 2)//3 :]

left, right = st.columns([3, 1], gap="large")
with left:
    st.markdown("<div id='mainpane'>", unsafe_allow_html=True)
    r1, r2, r3 = st.columns(3, gap="medium")
    for title, col, data, offset in [
        ("角色（1/3）", r1, c1, 1),
        ("角色（2/3）", r2, c2, 1 + len(c1)),
        ("角色（3/3）", r3, c3, 1 + len(c1) + len(c2)),
    ]:
        with col:
            cards = [render_role_card(i, cid) for i, cid in enumerate(data, start=offset)]
            st.markdown(
                f"<div class='window'><div class='winhead'>{title}</div><div class='winbody'>{''.join(cards)}</div></div>",
                unsafe_allow_html=True,
            )
with right:
    log_html = format_log_lines(st.session_state.revealed_lines, cid_to_rawname, all_display_names)
    st.markdown(
        f"<div class='window'><div class='winhead'>日志</div><div class='winbody'>{log_html}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

# ---- Bottom controls (spaced) ----
st.markdown("<div class='bottombar'>", unsafe_allow_html=True)

row1 = st.columns([1,1,1,1], gap="medium")
with row1[0]:
    if st.button("新开局", use_container_width=True, key="btn_new"):
        new_game()
        st.rerun()
with row1[1]:
    if st.button("下一回合", use_container_width=True, key="btn_turn"):
        next_turn()
        st.rerun()
with row1[2]:
    if st.button("下一行", use_container_width=True, key="btn_line"):
        step_line()
        st.rerun()
with row1[3]:
    if st.button("自动播放" if not st.session_state.get("playing") else "暂停", use_container_width=True, key="btn_play"):
        st.session_state.playing = not st.session_state.get("playing", False)
        if st.session_state.playing:
            st.session_state.autoplay_tick = time.time()
        st.rerun()

row2 = st.columns([1,3], gap="medium")
with row2[0]:
    st.slider("播放速度（秒/行）", 0.05, 1.0, float(st.session_state.get("speed_slider", 0.25)), 0.05, key="speed_slider")
with row2[1]:
    st.caption("页面本身不滚动；角色与日志是独立滚动窗口。")

st.markdown("</div>", unsafe_allow_html=True)

# ---- autoplay driver ----
if st.session_state.get("playing", False):
    delay = float(st.session_state.get("speed_slider", 0.25))
    now = time.time()
    last = float(st.session_state.get("autoplay_tick", 0.0))
    if now - last >= delay:
        st.session_state.autoplay_tick = now
        step_line()
        st.rerun()
