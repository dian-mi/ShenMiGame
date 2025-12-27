# -*- coding: utf-8 -*-
import html
import importlib.util
import re
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="神秘游戏 a1.1.10（Streamlit）", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
GAME_PATH = BASE_DIR / "engine_core.py"

def load_game_module():
    spec = importlib.util.spec_from_file_location("engine_core", str(GAME_PATH))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module

game = load_game_module()

def ensure_engine():
    if "engine" not in st.session_state:
        st.session_state.engine = game.Engine(seed=None, fast_mode=False)
        # first tick so act_23 etc has alive_turns
        try:
            st.session_state.engine.tick_alive_turns()
        except Exception:
            pass
    return st.session_state.engine

def css():
    st.markdown(
        """<style>
        /* Reduce padding to fit everything on one screen */
        .block-container {padding-top: 0.6rem; padding-bottom: 0.6rem; max-width: 1600px;}
        div[data-testid="stVerticalBlock"] {gap: 0.35rem;}
        /* Compact tables */
        .role-card {border: 1px solid rgba(49,51,63,0.2); border-radius: 10px; padding: 8px 10px; margin-bottom: 8px;}
        .role-name {font-weight: 700;}
        .role-meta {opacity: 0.85; font-size: 0.92rem; line-height: 1.15rem;}
        .role-dead {opacity: 0.45;}
        .logbox {border: 1px solid rgba(49,51,63,0.2); border-radius: 10px; padding: 8px 10px; height: 72vh; overflow: auto; background: rgba(0,0,0,0.02);}
        .small {font-size: 0.9rem;}
        /* Make buttons less tall */
        .stButton>button {padding: 0.35rem 0.65rem;}
        </style>""",
        unsafe_allow_html=True,
    )

def short_status(s: str) -> str:
    return s if s else "—"

def render_role(engine, cid: int):
    r = engine.roles[cid]
    rn = engine.rank_no(cid)
    stt = r.status.brief()
    dead_cls = " role-dead" if not r.alive else ""
    st.markdown(
        f"""<div class="role-card{dead_cls}">
            <div class="role-name">{html.escape(r.name)}({cid})</div>
            <div class="role-meta">排名：{rn if rn is not None else "—"}　|　状态：{html.escape(short_status(stt))}</div>
        </div>""",
        unsafe_allow_html=True,
    )

def render_roles_column(engine, ids):
    for cid in ids:
        render_role(engine, cid)

def render_log(engine):
    # show last ~200 lines
    logs = engine.log[-220:] if hasattr(engine, "log") else []
    safe = "<br/>".join(html.escape(x) for x in logs)
    st.markdown(f'<div class="logbox small">{safe}</div>', unsafe_allow_html=True)

css()
engine = ensure_engine()

# --- Header / Menu bar ---
top = st.container()
with top:
    cols = st.columns([2.2, 2.2, 2.6, 1.2], gap="small")
    with cols[0]:
        st.markdown("### 神秘游戏 a1.1.10")
        st.caption("左两栏：角色　|　右栏：日志（尽量无需下滑）")
    with cols[1]:
        seed = st.text_input("Seed（可空）", value=st.session_state.get("seed_str",""), label_visibility="collapsed", placeholder="Seed（可空）")
        st.session_state.seed_str = seed
    with cols[2]:
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            if st.button("新开局", use_container_width=True):
                s = None
                if st.session_state.seed_str.strip():
                    try:
                        s = int(st.session_state.seed_str.strip())
                    except Exception:
                        s = st.session_state.seed_str.strip()
                st.session_state.engine = game.Engine(seed=s, fast_mode=False)
                try:
                    st.session_state.engine.tick_alive_turns()
                except Exception:
                    pass
                st.rerun()
        with c2:
            if st.button("下一回合", use_container_width=True, disabled=getattr(engine, "game_over", False)):
                engine.next_turn()
                try:
                    engine.tick_alive_turns()
                except Exception:
                    pass
                st.rerun()
        with c3:
            if st.button("连跑10回合", use_container_width=True, disabled=getattr(engine, "game_over", False)):
                for _ in range(10):
                    if getattr(engine, "game_over", False):
                        break
                    engine.next_turn()
                    try:
                        engine.tick_alive_turns()
                    except Exception:
                        pass
                st.rerun()
        with c4:
            engine.joke_mode = st.toggle("玩笑模式", value=getattr(engine, "joke_mode", False))
    with cols[3]:
        st.markdown("#### 快捷操作")
        inv25 = st.toggle("找自称(25)无敌", value=False)
        try:
            engine.set_invincible(25, inv25)
        except Exception:
            pass

# --- Main 3 columns: roles/roles/log ---
alive_rank = [cid for cid in engine.rank if engine.roles[cid].alive]
dead_rank = [cid for cid in engine.rank if not engine.roles[cid].alive]

# Keep order consistent with engine.rank; show alive first then dead
display_ids = alive_rank + dead_rank
mid = (len(display_ids) + 1) // 2
left_ids = display_ids[:mid]
mid_ids = display_ids[mid:]

colL, colM, colR = st.columns([1.15, 1.15, 1.55], gap="small")

with colL:
    st.markdown("#### 角色（1/2）")
    render_roles_column(engine, left_ids)

with colM:
    st.markdown("#### 角色（2/2）")
    render_roles_column(engine, mid_ids)

with colR:
    st.markdown("#### 日志")
    render_log(engine)

# footer hints
with st.expander("说明/排查（不影响游戏）", expanded=False):
    st.write("如果你在 Streamlit Cloud 部署：请确保仓库里有 engine_core.py，并让 streamlit_app.py 引用它。")
    st.write("桌面版仍可使用原 Tk 文件（见我给你的 desktop 文件）。")
