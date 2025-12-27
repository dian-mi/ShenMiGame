# -*- coding: utf-8 -*-
"""
神秘游戏（Streamlit UI）
目标：尽量贴近 a1.1.10 的桌面版体验：
- 左侧两栏：26人存活排名与状态（无需页面下滑即可一览）
- 右侧一栏：战报逐行回放（容器内滚动）
- 顶部操作区：说明 / 新开局 / 下一回合 / 下一行 / 自动播放 / 暂停 / 速度
"""

from __future__ import annotations

import html
import importlib.util
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# =============================================================================
# 1) 动态加载引擎（允许中文文件名）
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
GAME_PATH = BASE_DIR / "神秘游戏.py"


def load_game_module():
    spec = importlib.util.spec_from_file_location("mystery_game", str(GAME_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


game = load_game_module()
Engine = game.Engine  # type: ignore[attr-defined]


# =============================================================================
# 2) 页面基础样式：尽量避免整页滚动，让内容在视口内完成展示
# =============================================================================

st.set_page_config(page_title="神秘游戏", layout="wide")

st.markdown(
    """
<style>
/* 尽量压缩 Streamlit 默认留白，减少“需要下滑”概率 */
.main .block-container{
    padding-top: .6rem;
    padding-bottom: .4rem;
    max-width: 1400px;
}

/* 隐藏底部“Made with Streamlit”空隙对视口的占用 */
footer {visibility: hidden;}
header {visibility: hidden;}

/* 让页面主体尽量不出现整体滚动条（各自容器内部滚动） */
html, body, [data-testid="stAppViewContainer"]{
    height: 100%;
    overflow: hidden;
}

/* 主布局容器（我们用一个固定高度区域承载三列） */
#mainpane{
    height: calc(100vh - 110px); /* 预留顶部控件区高度 */
    min-height: 520px;
}

/* 列容器内部滚动 */
.pane{
    height: 100%;
    overflow: hidden;
}
.scrollbox{
    height: 100%;
    overflow-y: auto;
    padding-right: 6px;
}

/* 行样式 */
.rank-row{
    padding: 6px 8px;
    border-radius: 10px;
    margin: 4px 0;
}
.mono{
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: 13px;
    line-height: 1.35;
}
.badge{
    display: inline-block;
    padding: 2px 8px;
    margin: 0 6px 6px 0;
    border-radius: 999px;
    border: 1px solid;
    font-size: 12px;
    line-height: 18px;
}
.smallhint{
    color: #64748b;
    font-size: 12px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# 3) 颜色（对齐 Tkinter 版）
# =============================================================================

ROW_HL_BG = "#FFF2A8"

COLOR_THUNDER = "#0B3D91"  # 深蓝：雷霆
COLOR_FROST = "#7EC8FF"  # 浅蓝：霜冻
COLOR_POS = "#D4AF37"  # 正面（护盾/祝福）
COLOR_NEG = "#E53935"  # 负面/限制
COLOR_PURPLE = "#8E44AD"  # 紫：腐化

POS_KEYWORDS = ("护盾", "祝福")
NEG_KEYWORDS = ("雷霆", "霜冻", "封印", "遗忘", "遗策", "黄昏", "留痕", "厄运", "禁盾", "禁得盾", "集火", "孤傲")


def _status_color(part: str) -> str:
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
    if p.startswith(NEG_KEYWORDS):
        return COLOR_NEG
    return "#64748b"


def _render_status_badges(brief: str) -> str:
    if not brief:
        return "<span class='smallhint'>—</span>"
    parts = [p.strip() for p in brief.split("；") if p.strip()]
    chips = []
    for p in parts:
        c = _status_color(p)
        chips.append(
            f"<span class='badge' style='border-color:{c};color:{c};'>{html.escape(p)}</span>"
        )
    return "".join(chips)


# =============================================================================
# 4) 日志格式化：与旧 Streamlit 版一致（击杀/被击败高亮）
# =============================================================================

KILL_RE = re.compile(r"(.*?)(【击杀】)(.+?)(\s*→\s*)(.+?)(（.*)")
DEFEATED_RE = re.compile(r"(.*?)(\b\S+\(\d+\))(\s+被击败[:：].*)")


def _format_log_line(line: str) -> str:
    raw = line.rstrip("\n")

    km = KILL_RE.match(raw)
    if km:
        prefix, tag, killer, arrow, victim, rest = km.groups()
        return (
            "<div class='mono'>"
            f"{html.escape(prefix)}{html.escape(tag)}"
            f"<b>{html.escape(killer.strip())}</b>"
            f"{html.escape(arrow)}"
            f"<span style='color:{COLOR_NEG};'>{html.escape(victim.strip())}</span>"
            f"{html.escape(rest)}"
            "</div>"
        )

    dm = DEFEATED_RE.match(raw)
    if dm:
        prefix, victim, rest = dm.groups()
        return (
            "<div class='mono'>"
            f"{html.escape(prefix)}"
            f"<span style='color:{COLOR_NEG};'>{html.escape(victim)}</span>"
            f"{html.escape(rest)}"
            "</div>"
        )

    return f"<div class='mono'>{html.escape(raw)}</div>"


def _render_log(lines: List[str]) -> str:
    if not lines:
        return (
            "<div class='mono'>"
            "还没有回放内容。\n"
            "点击【下一回合】生成本回合逐行回放；也可以点击【下一行】手动播放。"
            "</div>"
        )
    return "\n".join(_format_log_line(ln) for ln in lines)


# =============================================================================
# 5) Session State
# =============================================================================

def _init_state():
    if "engine" not in st.session_state:
        st.session_state.engine = Engine(seed=None)
    if "cursor" not in st.session_state:
        st.session_state.cursor = 0
    if "revealed_lines" not in st.session_state:
        st.session_state.revealed_lines = []
    if "current_snap" not in st.session_state:
        st.session_state.current_snap = None
    if "current_highlights" not in st.session_state:
        st.session_state.current_highlights = []
    if "autoplay" not in st.session_state:
        st.session_state.autoplay = False
    if "autoplay_ms" not in st.session_state:
        st.session_state.autoplay_ms = 250  # 贴近桌面版默认 0.25s/行
    if "show_help" not in st.session_state:
        st.session_state.show_help = False


def _reset_replay_state():
    st.session_state.cursor = 0
    st.session_state.revealed_lines = []
    st.session_state.current_snap = None
    st.session_state.current_highlights = []
    st.session_state.autoplay = False
    st.session_state.pop("autoplay_tick", None)


def _advance_one_line(engine: Any) -> None:
    frames = getattr(engine, "replay_frames", [])
    cur = st.session_state.cursor
    if cur < len(frames):
        frame = frames[cur]
        st.session_state.cursor += 1
        st.session_state.revealed_lines.append(frame["text"])
        st.session_state.current_snap = frame["snap"]
        st.session_state.current_highlights = frame.get("highlights", [])
    else:
        st.session_state.autoplay = False


_init_state()
engine: Any = st.session_state.engine

# =============================================================================
# 6) 顶部控制区（尽量贴近桌面版：说明 / 新开局 / 下一回合 / 下一行 / 自动播放 / 暂停 / 速度）
# =============================================================================

st.markdown("## 神秘游戏")

ctrl = st.columns([1.0, 1.2, 1.2, 1.0, 1.0, 2.6])

with ctrl[0]:
    # Streamlit 原生弹层：popover 更接近“说明”按钮
    with st.popover("说明", use_container_width=True):
        st.markdown(
            """
**made by dian_mi**  
但是其实基本都是 ChatGPT 写的  
欢迎大家游玩
"""
        )

with ctrl[1]:
    if st.button("新开局", use_container_width=True):
        engine.new_game()
        _reset_replay_state()
        st.rerun()

with ctrl[2]:
    if st.button("下一回合", use_container_width=True):
        # 桌面版逻辑：回合推进前先 tick_alive_turns
        engine.tick_alive_turns()
        engine.next_turn()

        # 重置回放，并默认显示第1行，然后开启自动播放（更贴近 Tk 版体验）
        st.session_state.cursor = 0
        st.session_state.revealed_lines = []
        st.session_state.current_snap = None
        st.session_state.current_highlights = []

        if getattr(engine, "replay_frames", []):
            _advance_one_line(engine)

        st.session_state.autoplay = True
        st.session_state.pop("autoplay_tick", None)
        st.rerun()

with ctrl[3]:
    if st.button("下一行", use_container_width=True):
        _advance_one_line(engine)
        st.rerun()

with ctrl[4]:
    if st.button("自动播放", use_container_width=True):
        # 开启自动播放（若没有回放则不做事）
        if getattr(engine, "replay_frames", []):
            st.session_state.autoplay = True
            st.session_state.pop("autoplay_tick", None)
        st.rerun()

with ctrl[5]:
    # 速度 + 暂停
    sub = st.columns([2.2, 1.0])
    with sub[0]:
        st.session_state.autoplay_ms = st.slider(
            "播放速度（毫秒/行）",
            min_value=100,
            max_value=2000,
            value=int(st.session_state.autoplay_ms),
            step=50,
            label_visibility="visible",
        )
    with sub[1]:
        if st.button("暂停", use_container_width=True):
            st.session_state.autoplay = False
            st.session_state.pop("autoplay_tick", None)
            st.rerun()

st.markdown("<div class='smallhint'>提示：手机端建议横屏；右侧战报在框内滚动，不会带动整页下滑。</div>", unsafe_allow_html=True)

# =============================================================================
# 7) 自动播放：定时刷新推进一行（避免 sleep）
# =============================================================================

if st.session_state.autoplay:
    st_autorefresh(interval=int(st.session_state.autoplay_ms), key="autoplay_tick")
    # 每次刷新推进一行；到末尾自动停止
    if getattr(engine, "replay_frames", []):
        _advance_one_line(engine)
    else:
        st.session_state.autoplay = False

# =============================================================================
# 8) 主体三列：左两栏角色 + 右一栏日志
# =============================================================================

# 当前快照：若还没回放则展示引擎当前状态
snap: Dict[str, Any]
if st.session_state.current_snap is None:
    snap = engine._snapshot()
else:
    snap = st.session_state.current_snap

rank: List[int] = snap.get("rank", [])
status_map: Dict[int, Dict[str, Any]] = snap.get("status", {})
highlights = set(st.session_state.get("current_highlights", []) or [])

# 分成两栏（13+13），减少高度
mid = (len(rank) + 1) // 2
rank_left = rank[:mid]
rank_right = rank[mid:]


def _render_rank_column(rank_ids: List[int], start_index: int) -> str:
    out = []
    for i, cid in enumerate(rank_ids, start=start_index):
        info = status_map.get(cid, {"name": str(cid), "brief": ""})
        name = info.get("name", str(cid))
        brief = info.get("brief", "")
        bg = ROW_HL_BG if cid in highlights else "transparent"
        out.append(
            f"""
<div class='rank-row' style='background:{bg};'>
  <div><b>{i:>2}. {html.escape(str(name))}({cid})</b></div>
  <div style='margin-top:4px;'>{_render_status_badges(str(brief))}</div>
</div>
"""
        )
    return "\n".join(out) if out else "<div class='smallhint'>—</div>"


st.markdown("<div id='mainpane'>", unsafe_allow_html=True)
c1, c2, c3 = st.columns([1.15, 1.15, 1.7], gap="small")

with c1:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown(f"### 存活排名（回合 {snap.get('turn', 0)}）")
    st.markdown(_render_rank_column(rank_left, 1), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c2:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("### \u00a0")  # 对齐左列标题高度
    st.markdown(_render_rank_column(rank_right, len(rank_left) + 1), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c3:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("### 战报（逐行回放）")
    st.markdown(_render_log(st.session_state.revealed_lines), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)
