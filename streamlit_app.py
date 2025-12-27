# -*- coding: utf-8 -*-
"""
神秘游戏（Streamlit 版 UI，尽量对齐 a1.1.10 桌面版）
布局目标（默认不需要整页下滑）：
- 左侧两栏：角色排名（自动按人数拆分成两列）
- 右侧一栏：战报逐行回放（容器内滚动）
- 顶部“菜单”：包含 a1.1.10 的常用选项（说明 / 快速跑 / 日志输出 / 自动跳过回合 / 找自称无敌 / 保留历史 / 显示实名/首字母 / 字体放大/缩小）
- 底部：新开局 / 下一回合 / 下一行 / 自动播放 / 暂停 / 播放速度

运行：
  pip install -r requirements.txt
  streamlit run streamlit_app.py
"""

from __future__ import annotations

import html
import importlib.util
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
# 2) Session State 初始化
# =============================================================================

def _ss_init():
    if "engine" not in st.session_state:
        st.session_state.engine = Engine(seed=None)

    # 回放
    st.session_state.setdefault("cursor", 0)
    st.session_state.setdefault("revealed_lines", [])
    st.session_state.setdefault("current_snap", None)
    st.session_state.setdefault("current_highlights", [])

    # 播放
    st.session_state.setdefault("autoplay", False)
    st.session_state.setdefault("autoplay_ms", 250)  # 0.25s/行
    st.session_state.setdefault("auto_skip_turn", False)  # 回合结束后5秒自动下一回合
    st.session_state.setdefault("auto_skip_deadline", None)  # epoch seconds

    # 菜单选项
    st.session_state.setdefault("write_error_log", False)
    st.session_state.setdefault("invincible_25", False)  # 找自称无敌模式（如引擎支持）
    st.session_state.setdefault("keep_history", True)     # 保留历史记录
    st.session_state.setdefault("name_mode", "full")      # full / initial
    st.session_state.setdefault("font_scale", 1.0)        # 字体缩放

    # 快速跑统计结果
    st.session_state.setdefault("fast_run_result", None)


def _reset_replay(clear_history: bool = True):
    st.session_state.cursor = 0
    if clear_history:
        st.session_state.revealed_lines = []
    st.session_state.current_snap = None
    st.session_state.current_highlights = []
    st.session_state.autoplay = False
    st.session_state.pop("autoplay_tick", None)

    # 自动跳过回合计时器清空
    st.session_state.auto_skip_deadline = None
    st.session_state.pop("autoskip_tick", None)


_ss_init()
engine: Any = st.session_state.engine


# =============================================================================
# 3) 工具函数：错误日志
# =============================================================================

def _log_error_to_file(exc: BaseException):
    if not st.session_state.get("write_error_log", False):
        return
    try:
        p = BASE_DIR / "error_log.txt"
        with p.open("a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            f.write("Exception:\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        # 写日志失败就静默，不影响游戏
        pass


# =============================================================================
# 4) 名字显示模式
# =============================================================================

def _to_initial(name: str) -> str:
    name = (name or "").strip()
    if not name:
        return "?"
    # 英文/数字：取首字符
    # 中文：取第一个字
    return name[0]


def _display_name(name: str) -> str:
    if st.session_state.get("name_mode") == "initial":
        return _to_initial(name)
    return name


# =============================================================================
# 5) 状态 badge（尽量保持旧版配色）
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
# 6) 日志渲染（击杀/被击败高亮）
# =============================================================================

import re
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
# 7) 回放推进（单行）
# =============================================================================

def _advance_one_line() -> None:
    frames = getattr(engine, "replay_frames", []) or []
    cur = int(st.session_state.cursor)
    if cur < len(frames):
        frame = frames[cur]
        st.session_state.cursor = cur + 1
        st.session_state.revealed_lines.append(frame.get("text", ""))

        st.session_state.current_snap = frame.get("snap")
        st.session_state.current_highlights = frame.get("highlights", []) or []
    else:
        st.session_state.autoplay = False

        # 若开启“自动跳过回合”，则在回合回放结束后启动5秒倒计时
        if st.session_state.get("auto_skip_turn", False) and frames:
            st.session_state.auto_skip_deadline = time.time() + 5


# =============================================================================
# 8) “下一回合”与“新开局”封装（带可选错误日志）
# =============================================================================

def _do_new_game():
    try:
        engine.new_game()
    except Exception as e:
        _log_error_to_file(e)
        raise

    # 新开局默认清历史（桌面版右侧日志通常也清）
    _reset_replay(clear_history=True)


def _do_next_turn():
    try:
        # 贴近桌面版：回合推进前 tick_alive_turns
        if hasattr(engine, "tick_alive_turns"):
            engine.tick_alive_turns()
        engine.next_turn()

        # invincible_25 若引擎支持，可以在回合开始时同步
        if st.session_state.get("invincible_25", False):
            # 兼容写法：如果引擎提供开关/钩子就用它，否则尝试在角色状态里打标记
            if hasattr(engine, "set_invincible"):
                engine.set_invincible(25, True)  # type: ignore[call-arg]
            else:
                # 尝试：给 roles[25].mem 标记，具体逻辑取决于你 a1.1.10 引擎如何读取
                try:
                    if hasattr(engine, "roles") and 25 in engine.roles:
                        engine.roles[25].mem["invincible"] = True
                except Exception:
                    pass

    except Exception as e:
        _log_error_to_file(e)
        raise

    # 回合切换：根据“保留历史记录”决定是否清空右侧日志
    keep = bool(st.session_state.get("keep_history", True))
    _reset_replay(clear_history=(not keep))

    # 默认显示第1行，并开启自动播放（贴近桌面版：下一回合后自动播）
    if getattr(engine, "replay_frames", []) or []:
        _advance_one_line()
        st.session_state.autoplay = True
        st.session_state.pop("autoplay_tick", None)


# =============================================================================
# 9) 快速跑（500/5000/50000）
# =============================================================================

def _fast_run(n_games: int):
    """
    尽量通用：每局 new_game -> while not game_over: tick_alive_turns/next_turn
    统计 winner cid/name（若引擎提供 winner 字段/日志解析则更准；否则用存活最后一名兜底）
    """
    prog = st.progress(0)
    status = st.empty()
    winners: Counter[str] = Counter()

    for i in range(n_games):
        e = Engine(seed=None)
        # 同步无敌模式（如果希望快速跑也遵循）
        if st.session_state.get("invincible_25", False):
            try:
                if hasattr(e, "set_invincible"):
                    e.set_invincible(25, True)  # type: ignore[call-arg]
                elif hasattr(e, "roles") and 25 in e.roles:
                    e.roles[25].mem["invincible"] = True
            except Exception:
                pass

        e.new_game()

        guard = 0
        while True:
            guard += 1
            if guard > 10000:
                # 防止异常死循环
                break
            if hasattr(e, "tick_alive_turns"):
                e.tick_alive_turns()
            e.next_turn()

            if getattr(e, "game_over", False):
                break

        # winner 兜底：alive_ids 最后一个
        winner_name = "Unknown"
        try:
            if hasattr(e, "winner"):
                w = getattr(e, "winner")
                if isinstance(w, int) and hasattr(e, "roles") and w in e.roles:
                    winner_name = e.roles[w].name
                elif isinstance(w, str):
                    winner_name = w
            else:
                alive = e.alive_ids() if hasattr(e, "alive_ids") else []
                if alive and hasattr(e, "roles") and alive[0] in e.roles:
                    # 通常只剩1人
                    winner_name = e.roles[alive[0]].name
        except Exception:
            pass

        winners[winner_name] += 1

        if (i + 1) % max(1, n_games // 200) == 0:
            prog.progress((i + 1) / n_games)
            status.write(f"快速跑：{i+1}/{n_games}")

    prog.progress(1.0)
    status.write("完成。")

    top = winners.most_common(20)
    st.session_state.fast_run_result = {"n": n_games, "top": top}


# =============================================================================
# 10) 页面 & CSS：尽量贴近桌面版“固定视口 + 内部滚动”
# =============================================================================

st.set_page_config(page_title="神秘游戏", layout="wide")

font_scale = float(st.session_state.get("font_scale", 1.0))
rank_font_px = int(15 * font_scale)
log_font_px = int(14 * font_scale)

st.markdown(
    f"""
<style>
.main .block-container{{
    padding-top: .25rem;
    padding-bottom: .25rem;
    max-width: 1600px;
}}
footer {{visibility: hidden;}}
header {{visibility: hidden;}}
html, body, [data-testid="stAppViewContainer"]{{
    height: 100%;
    overflow: hidden;  /* 整页尽量不滚动 */
}}
#mainpane {{
    height: calc(100vh - 150px); /* 给顶部菜单+底部控制留空间 */
    min-height: 520px;
}}
.pane {{
    height: 100%;
    overflow: hidden;
}}
.scrollbox {{
    height: 100%;
    overflow-y: auto;
    padding-right: 6px;
}}
.rank-row {{
    padding: 6px 8px;
    border-radius: 10px;
    margin: 4px 0;
}}
.mono {{
    white-space: pre-wrap;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    font-size: {log_font_px}px;
    line-height: 1.35;
}}
.rankname {{
    font-size: {rank_font_px}px;
}}
.badge {{
    display: inline-block;
    padding: 2px 8px;
    margin: 0 6px 6px 0;
    border-radius: 999px;
    border: 1px solid;
    font-size: {int(12*font_scale)}px;
    line-height: 18px;
}}
.hint {{
    color: #64748b;
    font-size: {int(12*font_scale)}px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# 11) 顶部“菜单”（模拟 Tk 菜单）
# =============================================================================

st.markdown("### 神秘游戏  made by dian_mi")

menu_cols = st.columns([0.9, 5.1])
with menu_cols[0]:
    with st.popover("菜单", use_container_width=True):
        st.markdown("**说明**")
        st.write("（网页版 UI 复刻 a1.1.10：左两栏角色，右一栏日志，容器内滚动）")

        st.divider()
        st.markdown("**快速跑**（统计胜者）")
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("快速跑500局", use_container_width=True):
                _fast_run(500)
        with b2:
            if st.button("快速跑5000局", use_container_width=True):
                _fast_run(5000)
        with b3:
            if st.button("快速跑50000局", use_container_width=True):
                _fast_run(50000)

        st.divider()
        st.checkbox("输出异常日志到脚本目录(error_log.txt)", key="write_error_log")
        st.checkbox("自动跳过回合（回合结束后5秒）", key="auto_skip_turn")
        st.checkbox("找自称无敌模式", key="invincible_25")
        st.checkbox("保留历史记录", key="keep_history")

        st.divider()
        nm1, nm2 = st.columns(2)
        with nm1:
            if st.button("显示实名", use_container_width=True):
                st.session_state.name_mode = "full"
        with nm2:
            if st.button("显示首字母", use_container_width=True):
                st.session_state.name_mode = "initial"

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
    # 快速跑结果展示（可收起）
    if st.session_state.get("fast_run_result"):
        with st.expander(f"胜率统计（{st.session_state.fast_run_result['n']} 局）", expanded=False):
            for i, (name, cnt) in enumerate(st.session_state.fast_run_result["top"], start=1):
                st.write(f"{i:>2}. {name}：{cnt}")

# =============================================================================
# 12) 自动播放 & 自动跳过回合
# =============================================================================

if st.session_state.autoplay:
    st_autorefresh(interval=int(st.session_state.autoplay_ms), key="autoplay_tick")
    _advance_one_line()

# 自动跳过回合：回放结束后启动 1s 刷新，到了 deadline 自动触发下一回合
deadline = st.session_state.get("auto_skip_deadline")
if deadline is not None:
    st_autorefresh(interval=1000, key="autoskip_tick")
    if time.time() >= float(deadline):
        st.session_state.auto_skip_deadline = None
        _do_next_turn()
        st.rerun()

# =============================================================================
# 13) 当前快照（无回放则用引擎当前状态）
# =============================================================================

snap: Dict[str, Any]
if st.session_state.current_snap is None:
    snap = engine._snapshot()
else:
    snap = st.session_state.current_snap or engine._snapshot()

rank: List[int] = snap.get("rank", []) or []
status_map: Dict[int, Dict[str, Any]] = snap.get("status", {}) or {}
highlights = set(st.session_state.get("current_highlights", []) or [])

# 角色人数不固定：按一半拆两列（和截图类似：1-22 / 23-43）
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
# 14) 主体三列：左两栏角色 + 右一栏日志（容器内滚动）
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
    st.markdown("&nbsp;")  # 对齐
    st.markdown(_render_rank_column(rank_right, len(rank_left) + 1), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

with c3:
    st.markdown("<div class='pane'><div class='scrollbox'>", unsafe_allow_html=True)
    st.markdown("**战报**")
    st.markdown(_render_log(st.session_state.revealed_lines), unsafe_allow_html=True)
    st.markdown("</div></div>", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# =============================================================================
# 15) 底部控制条（模拟桌面版）
# =============================================================================

st.divider()
bcols = st.columns([1.0, 1.0, 1.0, 1.0, 0.9, 3.1], gap="small")

with bcols[0]:
    if st.button("新开局", use_container_width=True):
        _do_new_game()
        st.rerun()

with bcols[1]:
    if st.button("下一回合", use_container_width=True):
        _do_next_turn()
        st.rerun()

with bcols[2]:
    if st.button("下一行", use_container_width=True):
        _advance_one_line()
        st.rerun()

with bcols[3]:
    if st.button("自动播放", use_container_width=True):
        if getattr(engine, "replay_frames", []) and st.session_state.cursor < len(engine.replay_frames):
            st.session_state.autoplay = True
            st.session_state.pop("autoplay_tick", None)
        st.rerun()

with bcols[4]:
    if st.button("暂停", use_container_width=True):
        st.session_state.autoplay = False
        st.session_state.pop("autoplay_tick", None)
        st.rerun()

with bcols[5]:
    # 与桌面版“播放速度”相似
    st.session_state.autoplay_ms = st.slider(
        "播放速度",
        min_value=100,
        max_value=2000,
        value=int(st.session_state.autoplay_ms),
        step=50,
    )
    st.markdown(f"<div class='hint' style='text-align:right;'>{st.session_state.autoplay_ms/1000:.2f}s/行</div>", unsafe_allow_html=True)
