# -*- coding: utf-8 -*-
"""
把 Tkinter 版本的“26人规则版推演模拟器”改造成可在手机浏览器访问的网页应用（Streamlit）。

运行方式（本地）：
  pip install streamlit
  streamlit run streamlit_app.py

部署方式（线上）：
  - Streamlit Community Cloud：把本项目推到 GitHub，然后在 Streamlit Cloud 里一键部署
  - 或 Render / Railway 等：启动命令 `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
"""

import html
import importlib.util
import re
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---- 1) 动态加载你原来的 .py（文件名包含中文也没关系）----
BASE_DIR = Path(__file__).resolve().parent
GAME_PATH = BASE_DIR / "神秘游戏.py"  # 确保与你的原文件放在同一目录


def load_game_module():
    spec = importlib.util.spec_from_file_location("mystery_game", str(GAME_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore
    return module


game = load_game_module()
Engine = game.Engine  # 原文件里的引擎（与 Tkinter UI 无关）

# ---- 2) Streamlit 状态 ----
st.set_page_config(page_title="神秘游戏", layout="wide")

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

# 自动播放相关状态（必须先初始化，按钮里会读）
if "autoplay" not in st.session_state:
    st.session_state.autoplay = False
if "autoplay_ms" not in st.session_state:
    st.session_state.autoplay_ms = 400  # 默认 0.4 秒/行

engine: Engine = st.session_state.engine

# ---- 3) 与“神秘游戏”本体一致的高亮底色（replay_frames 里提供 highlights）----
ROW_HL_BG = "#FFF2A8"  # 本体 UI 使用的高亮底色

# ---- 4) 状态颜色（按“神秘游戏”状态文本来匹配）----
# 说明：本体 rank 列表里状态来自 Status.brief()，形如：护盾2；封印1；遗忘2；集火；永久失效；黄昏3；留痕(目标随机)；厄运(翻倍)；禁得盾；孤傲
# 颜色与 Tkinter 本体保持一致
COLOR_THUNDER = "#0B3D91"  # 深蓝：雷霆
COLOR_FROST   = "#7EC8FF"  # 浅蓝：霜冻
COLOR_POS     = "#D4AF37"  # 正面（护盾/祝福）
COLOR_NEG     = "#E53935"  # 负面/限制
COLOR_PURPLE  = "#8E44AD"  # 紫：腐化

POS_KEYWORDS = ("护盾", "祝福")
NEG_KEYWORDS = ("雷霆", "霜冻", "封印", "遗忘", "遗策", "黄昏", "留痕", "厄运", "禁盾", "禁得盾", "集火", "孤傲")

def _status_color(part: str) -> str:
    p = part.strip()
    if not p:
        return "#64748b"

    # 🔴 死亡：最高优先级，强制红色
    # （不管后面还有没有别的状态）
    if "死亡" in p:
        return COLOR_NEG

    # 特殊前缀：单独颜色
    if p.startswith("雷霆"):
        return COLOR_THUNDER
    if p.startswith("霜冻"):
        return COLOR_FROST
    if p.startswith("腐化"):
        return COLOR_PURPLE

    # 正面
    if p.startswith(POS_KEYWORDS):
        return COLOR_POS

    # 负面 / 限制
    if p.startswith(NEG_KEYWORDS):
        return COLOR_NEG

    # 未知状态：中性灰
    return "#64748b"



def _render_status_badges(brief: str) -> str:
    if not brief:
        return "<span style='color:#94a3b8'>—</span>"
    parts = [p.strip() for p in brief.split("；") if p.strip()]
    chips = []
    for p in parts:
        c = _status_color(p)
        p2 = html.escape(p)
        chips.append(
            f"<span style='display:inline-block;padding:2px 8px;margin:0 6px 6px 0;"
            f"border-radius:999px;border:1px solid {c};color:{c};"
            f"font-size:12px;line-height:18px;'>"
            f"{p2}</span>"
        )
    return "".join(chips)


def show_rank(snap):
    st.subheader(f"存活排名（回合 {snap['turn']}）")
    rank = snap["rank"]
    status_map = snap["status"]

    highlights = set(st.session_state.get("current_highlights", []) or [])

    for i, cid in enumerate(rank, start=1):
        info = status_map[cid]
        name = info["name"]
        brief = info.get("brief", "")
        bg = ROW_HL_BG if cid in highlights else "transparent"

        c1, c2 = st.columns([0.45, 0.55])
        with c1:
            st.markdown(
                f"<div style='padding:6px 8px;border-radius:10px;background:{bg};'>"
                f"<b>{i:>2}. {html.escape(name)}({cid})</b>"
                f"</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div style='padding:6px 8px;border-radius:10px;background:{bg};'>"
                f"{_render_status_badges(brief)}"
                f"</div>",
                unsafe_allow_html=True,
            )


def show_log(lines):
    st.subheader("战报（逐行回放）")
    if not lines:
        st.info("还没有回放内容。点“开始回合”生成本回合逐行回放，然后点“下一行”或开启“自动播放”。")
        return
    st.code("\n".join(lines), language="text")


# ---- 5) 页面 ----
st.title("神秘游戏（东滩乱斗）")

col_btn1, col_btn2, col_btn3, col_btn4, col_btn5 = st.columns([1, 1, 1, 1, 2])

with col_btn1:
    if st.button("新开局", use_container_width=True):
        engine.new_game()
        st.session_state["cursor"] = 0
        st.session_state["revealed_lines"] = []
        st.session_state["current_snap"] = None
        st.session_state["current_highlights"] = []
        st.session_state["autoplay"] = False
        st.session_state.pop("autoplay_tick", None)
        st.rerun()

with col_btn2:
    if st.button("开始回合", use_container_width=True):
        engine.tick_alive_turns()
        engine.next_turn()

        st.session_state["cursor"] = 0
        st.session_state["revealed_lines"] = []
        st.session_state["current_snap"] = None
        st.session_state["current_highlights"] = []

        # 默认先展示第一行
        if engine.replay_frames:
            frame = engine.replay_frames[0]
            st.session_state["cursor"] = 1
            st.session_state["revealed_lines"].append(frame["text"])
            st.session_state["current_snap"] = frame["snap"]
            st.session_state["current_highlights"] = frame.get("highlights", [])

        # ✅ 开始回合后默认自动播放
        st.session_state["autoplay"] = True
        st.session_state.pop("autoplay_tick", None)

        st.rerun()

with col_btn3:
    if st.button("下一行", use_container_width=True):
        frames = engine.replay_frames
        cur = st.session_state["cursor"]
        if cur < len(frames):
            frame = frames[cur]
            st.session_state["cursor"] += 1
            st.session_state["revealed_lines"].append(frame["text"])
            st.session_state["current_snap"] = frame["snap"]
            st.session_state["current_highlights"] = frame.get("highlights", [])
        st.rerun()

with col_btn4:
    label = "停止自动播放" if st.session_state["autoplay"] else "自动播放"
    if st.button(label, use_container_width=True):
        st.session_state["autoplay"] = not st.session_state["autoplay"]
        if not st.session_state["autoplay"]:
            st.session_state.pop("autoplay_tick", None)
        st.rerun()
    st.caption("顺便帮我测试一下bug（")

with col_btn5:
    st.session_state["autoplay_ms"] = st.slider(
        "播放速度（毫秒/行）",
        min_value=100,
        max_value=2000,
        value=st.session_state["autoplay_ms"],
        step=50,
    )
    st.write("made by dian_mi（好吧其实是GPT大人神力）")

# ---- 6) 主体两栏 ----
left, right = st.columns([1.2, 1])

snap = st.session_state["current_snap"]
if snap is None:
    # 如果还没开始回放，就展示当前引擎快照（用内部方法 _snapshot）
    snap = engine._snapshot()

# ---- 7) 自动播放：用定时刷新逐行推进（避免 sleep 导致“后台跑完前台不更新”）----
if st.session_state["autoplay"]:
    st_autorefresh(interval=st.session_state["autoplay_ms"], key="autoplay_tick")

    frames = engine.replay_frames
    cur = st.session_state["cursor"]

    # 如果还没生成回放（没点“开始回合”），就先停掉自动播放
    if not frames:
        st.session_state["autoplay"] = False
    else:
        # 每次刷新推进一行
        if cur < len(frames):
            frame = frames[cur]
            st.session_state["cursor"] += 1
            st.session_state["revealed_lines"].append(frame["text"])
            st.session_state["current_snap"] = frame["snap"]
            st.session_state["current_highlights"] = frame.get("highlights", [])
        else:
            # 到末尾自动停止
            st.session_state["autoplay"] = False

with left:
    show_rank(snap)

with right:
    show_log(st.session_state["revealed_lines"])
