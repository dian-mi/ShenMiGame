# -*- coding: utf-8 -*-
"""
把 Tkinter 版本的“26人规则版推演模拟器”改造成可在手机浏览器访问的网页应用（Streamlit）。

运行方式（本地）：
  pip install streamlit
  streamlit run streamlit_app.py

部署方式（线上）：
  - Streamlit Community Cloud（最省事）：把本项目推到 GitHub，然后在 Streamlit Cloud 里一键部署
  - 或 Render / Railway 等：用同样的启动命令 `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`
"""
import time  # 放到文件顶部 import 区
import importlib.util
from pathlib import Path
import streamlit as st

# ---- 1) 动态加载你原来的 .py（文件名包含中文也没关系）----
BASE_DIR = Path(__file__).resolve().parent
GAME_PATH = BASE_DIR / "神秘游戏.py"   # 确保与你的原文件放在同一目录

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

engine: Engine = st.session_state.engine

# ---- 3) 辅助渲染 ----
def snapshot_rank_and_status(snap):
    rank = snap["rank"]
    status_map = snap["status"]
    rows = []
    for i, cid in enumerate(rank, start=1):
        info = status_map[cid]
        brief = info.get("brief", "")
        rows.append((i, f'{info["name"]}({cid})', brief))
    return rows

def show_rank(snap):
    st.subheader(f"存活排名（回合 {snap['turn']}）")
    rows = snapshot_rank_and_status(snap)
    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            0: st.column_config.NumberColumn("名次"),
            1: st.column_config.TextColumn("角色"),
            2: st.column_config.TextColumn("状态"),
        },
    )

def show_log(lines):
    st.subheader("战报（逐行回放）")
    if not lines:
        st.info("还没有回放内容。点“开始回合”生成本回合逐行回放，然后点“下一行”。")
        return
    st.code("\n".join(lines), language="text")

# ---- 4) 页面 ----
st.title("神秘游戏 presented by dian_mi")

col_btn1, col_btn2, col_btn3, col_btn4, col_btn5 = st.columns([1,1,1,1,2])

with col_btn1:
    if st.button("新开局", use_container_width=True):
        engine.new_game()
        st.session_state.cursor = 0
        st.session_state.revealed_lines = []
        st.session_state.current_snap = None
        st.rerun()

with col_btn2:
    if st.button("开始回合（生成回放）", use_container_width=True):
        engine.tick_alive_turns()
        engine.next_turn()
        st.session_state.cursor = 0
        st.session_state.revealed_lines = []
        st.session_state.current_snap = None
        # 默认先展示第一行
        if engine.replay_frames:
            frame = engine.replay_frames[0]
            st.session_state.cursor = 1
            st.session_state.revealed_lines.append(frame["text"])
            st.session_state.current_snap = frame["snap"]
        st.rerun()

with col_btn3:
    if st.button("下一行", use_container_width=True):
        frames = engine.replay_frames
        cur = st.session_state.cursor
        if cur < len(frames):
            frame = frames[cur]
            st.session_state.cursor += 1
            st.session_state.revealed_lines.append(frame["text"])
            st.session_state.current_snap = frame["snap"]
        st.rerun()

with col_btn4:
    # 自动播放开关
    label = "停止自动播放" if st.session_state.autoplay else "自动播放"
    if st.button(label, use_container_width=True):
        st.session_state.autoplay = not st.session_state.autoplay
        st.rerun()

with col_btn5:
    st.session_state.autoplay_ms = st.slider(
        "播放速度（毫秒/行）",
        min_value=100,
        max_value=2000,
        value=st.session_state.autoplay_ms,
        step=50
    )
    st.write("made by dian_mi")

if "autoplay" not in st.session_state:
    st.session_state.autoplay = False
if "autoplay_ms" not in st.session_state:
    st.session_state.autoplay_ms = 400  # 默认 0.4 秒/行

# 右侧：快速操作
with col_btn4:
    st.write("手机端建议横屏使用")

# ---- 5) 主体两栏 ----
left, right = st.columns([1.2, 1])

snap = st.session_state.current_snap
if snap is None:
    # 如果还没开始回放，就展示当前引擎快照（用内部方法 _snapshot）
    snap = engine._snapshot()

if st.session_state.autoplay:
    frames = engine.replay_frames
    cur = st.session_state.cursor

    # 如果还没生成回放（没点“开始回合”），就先停掉自动播放
    if not frames:
        st.session_state.autoplay = False
    else:
        # 还有下一行就继续推进；到末尾就自动停止
        if cur < len(frames):
            time.sleep(st.session_state.autoplay_ms / 1000.0)
            frame = frames[cur]
            st.session_state.cursor += 1
            st.session_state.revealed_lines.append(frame["text"])
            st.session_state.current_snap = frame["snap"]
            st.rerun()
        else:
            st.session_state.autoplay = False

with left:
    show_rank(snap)

with right:
    show_log(st.session_state.revealed_lines)
