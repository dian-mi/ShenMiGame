# -*- coding: utf-8 -*-
"""
神秘游戏（Streamlit UI）— 严格复刻 a1.1.10 桌面版行为与布局

对齐点（来自 a1.1.10 Tk UI）：
- 【下一回合】：
  1) 若不保留历史：清空逐行展示缓存
  2) engine.tick_alive_turns() 然后 engine.next_turn()
  3) play_cursor=0，playing=False，current_snap/current_highlights 清空
  4) 若 replay_frames 非空：默认“立刻显示第一行并继续自动播放一行”（相当于连续 step 两次），然后进入自动播放循环
  5) 若播完且开启“自动跳回合”：5秒后自动推进下一回合
- 回放结束：若 game_over，禁用推进/播放按钮，只保留【新开局】

布局：
- 左侧两栏角色（自动按人数一分为二）
- 右侧一栏日志（容器内滚动）
- 页面整体尽量不出现整页滚动条（overflow hidden）

运行：
  pip install -r requirements.txt
  streamlit run streamlit_app.py
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

# =============================================================================
# 0) 加载引擎（中文文件名）
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
# 1) Session State
# =============================================================================


def _ss_init():
    if "engine" not in st.session_state:
        st.session_state.engine = Engine(seed=None)

    st.session_state.setdefault("cursor", 0)
    st.session_state.setdefault("revealed_lines", [])
    st.session_state.setdefault("current_snap", None)
    st.session_state.setdefault("current_highlights", [])

    st.session_state.setdefault("playing", False)  # 是否自动播放中（桌面版 playing）
    st.session_state.setdefault("autoplay_ms", 250)  # 0.25s/行（桌面版默认 0.25）

    # 菜单项（与桌面版一致）
    st.session_state.setdefault("export_error_log", False)  # 输出异常日志到脚本目录
    st.session_state.setdefault("auto_skip_turn", False)    # 回合结束后5秒自动下一回合
    st.session_state.setdefault("invincible_mode", False)   # 找自称无敌模式（cid=25）
    st.session_state.setdefault("preserve_history", True)   # 保留历史记录
    st.session_state.setdefault("show_realname", False)     # 显示实名
    st.session_state.setdefault("show_initials", False)     # 显示首字母

    # 字体缩放（桌面版有字体放大/缩小）
    st.session_state.setdefault("font_scale", 1.0)

    # 自动跳回合计时器
    st.session_state.setdefault("auto_skip_deadline", None)


_ss_init()
engine: Any = st.session_state.engine

# 将“输出异常日志”也同步到引擎（若引擎字段存在）
if hasattr(engine, "export_error_log"):
    try:
        engine.export_error_log = bool(st.session_state.export_error_log)
    except Exception:
        pass


# =============================================================================
# 2) 错误日志输出（error_log.txt）
# =============================================================================

def _append_error_log(exc: BaseException):
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


# =============================================================================
# 3) 名字显示（实名/首字母）— 复刻桌面版的互斥逻辑
# =============================================================================

def _to_initial(s: str) -> str:
    s = (s or "").strip()
    return s[0] if s else "?"


def _display_name(name: str) -> str:
    # 桌面版里“显示实名 / 显示首字母”是两个开关，但实战上用户只会开一个；
    # 这里按优先级：首字母 > 实名
    if st.session_state.get("show_initials", False):
        return _to_initial(name)
    return name


# =============================================================================
# 4) 状态 badge（桌面版配色）
# =============================================================================

ROW_HL_BG = "#FFF2A8"
COLOR_THUNDER = "#0B3D91"
COLOR_FROST = "#7EC8FF"
COLOR_POS = "#D4AF37"
COLOR_NEG = "#E53935"
COLOR_PURPLE = "#8E44AD"

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
        return "<span class='hint'>—</span>"
    parts = [p.strip() for p in str(brief).split("；") if p.strip()]
    chips = []
    for p in parts:
        c = _status_color(p)
        chips.append(
            f"<span class='badge' style='border-color:{c};color:{c};'>{html.escape(p)}</span>"
        )
    return "".join(chips)


# =============================================================================
# 5) 日志渲染（击杀/被击败格式）
# =============================================================================

KILL_RE = re.compile(r"(.*?)(【击杀】)(.+?)(\s*→\s*)(.+?)(（.*)")
DEFEATED_RE = re.compile(r"(.*?)(\b\S+\(\d+\))(\s+被击败[:：].*)")


def _format_log_line(line: str) -> str:
    raw = (line or "").rstrip("\n")

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
        return "<div class='mono'>【新开局】已生成初始排名</div>"
    return "\n".join(_format_log_line(ln) for ln in lines)


# =============================================================================
# 6) 引擎动作：新开局 / 下一回合 / 下一行（严格对齐桌面版）
# =============================================================================

def _cancel_pending_autoskip():
    st.session_state.auto_skip_deadline = None
    st.session_state.pop("autoskip_tick", None)


def _new_game():
    _cancel_pending_autoskip()
    st.session_state.playing = False
    st.session_state.pop("autoplay_tick", None)

    try:
        engine.new_game()
    except Exception as e:
        _append_error_log(e)
        raise

    # 桌面版新开局：右侧日志从头开始
    st.session_state.cursor = 0
    st.session_state.revealed_lines = []
    st.session_state.current_snap = None
    st.session_state.current_highlights = []


def _apply_invincible_mode():
    # a1.1.10 角色表里 25 是“找自称” fileciteturn2file4L4-L6
    if not st.session_state.get("invincible_mode", False):
        return
    try:
        if hasattr(engine, "set_invincible"):
            engine.set_invincible(25, True)  # type: ignore[call-arg]
        else:
            if hasattr(engine, "roles") and 25 in engine.roles:
                engine.roles[25].mem["invincible"] = True
    except Exception:
        pass


def _build_turn():
    """
    复刻桌面版 on_build_turn：
    - 若 game_over：直接返回
    - 若不保留历史：清空逐行缓存
    - tick_alive_turns -> next_turn
    - play_cursor=0, playing=False, current_snap/current_highlights 清空
    - 若有 replay_frames：step 一次，playing=True，再 step 一次（启动自动播放）
    """
    _cancel_pending_autoskip()

    if getattr(engine, "game_over", False):
        return

    # 新回合开始：如果不保留历史，就清空“逐行展示缓存” fileciteturn2file2L39-L43
    if not st.session_state.get("preserve_history", True):
        st.session_state.revealed_lines = []

    try:
        if hasattr(engine, "tick_alive_turns"):
            engine.tick_alive_turns()  # fileciteturn2file2L44-L45
        _apply_invincible_mode()
        engine.next_turn()  # fileciteturn2file2L44-L46
    except Exception as e:
        _append_error_log(e)
        raise

    st.session_state.cursor = 0
    st.session_state.playing = False
    st.session_state.current_snap = None
    st.session_state.current_highlights = []

    frames = getattr(engine, "replay_frames", []) or []
    if frames:
        _step_line()               # 默认显示第一行 fileciteturn2file2L50-L54
        st.session_state.playing = True
        _step_line()               # 继续自动播放一行 fileciteturn2file2L50-L54
    else:
        # 无回放帧：只刷新（Streamlit 下相当于保持快照即可）
        pass


def _step_line():
    frames = getattr(engine, "replay_frames", []) or []
    cur = int(st.session_state.cursor)

    if cur >= len(frames):
        st.session_state.playing = False
        st.session_state.pop("autoplay_tick", None)

        # 回放播完：若 game_over，禁用按钮；否则按设置启动自动跳回合（5秒） fileciteturn2file2L67-L78
        if not getattr(engine, "game_over", False) and st.session_state.get("auto_skip_turn", False) and len(frames) > 0:
            st.session_state.auto_skip_deadline = time.time() + 5
        return

    frame = frames[cur]
    st.session_state.cursor = cur + 1
    st.session_state.revealed_lines.append(frame.get("text", ""))

    st.session_state.current_snap = frame.get("snap")
    st.session_state.current_highlights = frame.get("highlights", []) or []


# =============================================================================
# 7) 页面 & CSS（避免整页滚动）
# =============================================================================

st.set_page_config(page_title="神秘游戏", layout="wide")

fs = float(st.session_state.get("font_scale", 1.0))
rank_font = int(15 * fs)
log_font = int(14 * fs)
badge_font = int(12 * fs)

st.markdown(
    f"""
<style>
.main .block-container{{
  padding-top: .15rem;
  padding-bottom: .15rem;
  max-width: 1650px;
}}
footer {{visibility: hidden;}}
header {{visibility: hidden;}}
html, body, [data-testid="stAppViewContainer"]{{
  height: 100%;
  overflow: hidden;
}}
#mainpane {{
  height: calc(100vh - 155px);
  min-height: 520px;
}}
.pane {{ height: 100%; overflow: hidden; }}
.scrollbox {{ height: 100%; overflow-y: auto; padding-right: 6px; }}

.rank-row {{
  padding: 6px 8px;
  border-radius: 10px;
  margin: 4px 0;
}}
.rankname {{ font-size: {rank_font}px; }}
.mono {{
  white-space: pre-wrap;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: {log_font}px;
  line-height: 1.35;
}}
.badge {{
  display: inline-block;
  padding: 2px 8px;
  margin: 0 6px 6px 0;
  border-radius: 999px;
  border: 1px solid;
  font-size: {badge_font}px;
  line-height: 18px;
}}
.hint {{
  color: #64748b;
  font-size: {badge_font}px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# 8) 顶部菜单（复刻截图的“菜单”下拉）
# =============================================================================

st.markdown("### 神秘游戏  made by dian_mi")

menu_cols = st.columns([0.9, 5.1])
with menu_cols[0]:
    with st.popover("菜单", use_container_width=True):
        st.markdown("**说明**")
        st.write("网页端 UI 严格复刻 a1.1.10：左两栏排名 + 右侧日志；按桌面版逻辑自动播放/自动跳回合。")

        st.divider()
        # 桌面版有“快速跑500/5000/50000”（这里不强行实现复杂统计，保持按钮位；后续可补）
        st.markdown("**快速跑**（待接入 a1.1.10 统计页）")
        st.caption("提示：a1.1.10 桌面版快速跑会输出统计面板；网页端可后续补齐同样统计。")

        st.divider()
        st.checkbox("输出异常日志到脚本目录(error_log.txt)", key="export_error_log")
        st.checkbox("自动跳过回合（回合结束后5秒）", key="auto_skip_turn")
        st.checkbox("找自称无敌模式", key="invincible_mode")
        st.checkbox("保留历史记录", key="preserve_history")

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.checkbox("显示实名", key="show_realname")
        with c2:
            st.checkbox("显示首字母", key="show_initials")

        # 互斥处理：与桌面版“选一个用”体验一致
        if st.session_state.show_initials and st.session_state.show_realname:
            # 默认优先首字母，关掉实名
            st.session_state.show_realname = False

        st.divider()
        f1, f2 = st.columns(2)
        with f1:
            if st.button("字体放大", use_container_width=True):
                st.session_state.font_scale = min(1.8, float(st.session_state.font_scale) + 0.1)
                st.rerun()
        with f2:
            if st.button("字体缩小", use_container_width=True):
                st.session_state.font_scale = max(0.7, float(st.session_state.font_scale) - 0.1)
                st.rerun()

with menu_cols[1]:
    st.caption("提示：手机端建议横屏；右侧战报在框内滚动，不会带动整页下滑。")

# =============================================================================
# 9) 自动播放循环 + 自动跳回合
# =============================================================================

if st.session_state.playing:
    st_autorefresh(interval=int(st.session_state.autoplay_ms), key="autoplay_tick")
    _step_line()

deadline = st.session_state.get("auto_skip_deadline")
if deadline is not None:
    st_autorefresh(interval=1000, key="autoskip_tick")
    if time.time() >= float(deadline):
        st.session_state.auto_skip_deadline = None
        _build_turn()
        st.rerun()

# =============================================================================
# 10) 当前快照（与引擎 _snapshot 对齐）
# _snapshot 返回：{"turn": turn, "rank": alive_rank[:], "status": status_map} fileciteturn2file4L60-L67
# =============================================================================

snap: Dict[str, Any]
if st.session_state.current_snap is None:
    snap = engine._snapshot()
else:
    snap = st.session_state.current_snap or engine._snapshot()

rank: List[int] = snap.get("rank", []) or []
status_map: Dict[int, Dict[str, Any]] = snap.get("status", {}) or {}
highlights = set(st.session_state.get("current_highlights", []) or [])

# 左两栏：按人数拆分（截图是 1-22 / 23-43）
mid = (len(rank) + 1) // 2
rank_left = rank[:mid]
rank_right = rank[mid:]


def _render_rank_column(rank_ids: List[int], start_index: int) -> str:
    out: List[str] = []
    for i, cid in enumerate(rank_ids, start=start_index):
        info = status_map.get(cid, {"name": str(cid), "brief": ""})
        name = _display_name(str(info.get("name", cid)))
        brief = str(info.get("brief", ""))

        bg = ROW_HL_BG if cid in highlights else "transparent"
        out.append(
            f"""
<div class="rank-row" style="background:{bg};">
  <div class="rankname"><b>{i:>2}. {html.escape(name)}({cid})</b></div>
  <div style="margin-top:4px;">{_render_status_badges(brief)}</div>
</div>
"""
        )
    return "\n".join(out) if out else "<div class='hint'>—</div>"


# =============================================================================
# 11) 主体三列（左两栏角色 + 右一栏日志）
# =============================================================================

st.markdown("<div id='mainpane'>", unsafe_allow_html=True)
c1, c2, c3 = st.columns([1.15, 1.15, 1.8], gap="small")

with c1:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown(f"**回合 {snap.get('turn', 0)}**")
    st.markdown(_render_rank_column(rank_left, 1), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c2:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("&nbsp;")
    st.markdown(_render_rank_column(rank_right, len(rank_left) + 1), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c3:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("**战报**")
    st.markdown(_render_log(st.session_state.revealed_lines), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# 12) 底部控制条（复刻截图）
# =============================================================================

st.divider()

game_over = bool(getattr(engine, "game_over", False))
disable_adv = game_over  # 结束局：禁用推进/播放

bcols = st.columns([1.0, 1.0, 1.0, 1.0, 0.9, 3.1], gap="small")

with bcols[0]:
    if st.button("新开局", use_container_width=True, disabled=False):
        _new_game()
        st.rerun()

with bcols[1]:
    if st.button("下一回合", use_container_width=True, disabled=disable_adv):
        _build_turn()
        st.rerun()

with bcols[2]:
    if st.button("下一行", use_container_width=True, disabled=disable_adv):
        _cancel_pending_autoskip()
        _step_line()
        st.rerun()

with bcols[3]:
    if st.button("自动播放", use_container_width=True, disabled=disable_adv):
        _cancel_pending_autoskip()
        # 桌面版 on_auto：仅当有回放且未到末尾才继续
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
