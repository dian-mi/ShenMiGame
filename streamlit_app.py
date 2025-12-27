# -*- coding: utf-8 -*-
import importlib
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# IMPORTANT: set_page_config must be the first Streamlit command.
st.set_page_config(page_title="神秘游戏", layout="wide")

UI_VERSION = "v4-2025-12-27"

# ----------------------------
# CSS: emulate a1.1.10 (3 panels, list rows, separators, selected yellow)
# No page scrolling; panels scroll internally.
# ----------------------------
st.markdown(f"""
<style>
  :root{{
    --bg: #efefef;
    --panel: #f7f7f7;
    --line: #d7d7d7;
    --text: #111;
    --muted: #666;
    --select: #fff3b0;
  }}
  html, body, [data-testid="stAppViewContainer"] {{ height: 100%; overflow: hidden; background: var(--bg); }}
  [data-testid="stAppViewContainer"] > .main {{ height: 100%; overflow: hidden; background: var(--bg); }}
  .block-container {{ padding-top: 0.35rem; padding-bottom: 0.35rem; max-width: 100%; }}
  header {{ visibility: hidden; height: 0px; }}
  [data-testid="stToolbar"] {{ visibility: visible; }}

  .nb-wrap {{ height: calc(100vh - 150px); }}
  .nb-panel {{
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 0px;
    height: 100%;
    overflow: hidden;
  }}
  .nb-panel-title{{
    font-weight: 700;
    padding: 8px 10px;
    border-bottom: 1px solid var(--line);
    color: var(--text);
    background: #f3f3f3;
  }}
  .nb-scroll{{
    height: calc(100% - 41px);
    overflow-y: auto;
  }}

  /* Role rows */
  .role-row{{
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding: 6px 10px;
    border-bottom: 1px solid var(--line);
    font-size: 16px;
    color: var(--text);
    background: transparent;
  }}
  .role-left{{
    display:flex;
    gap: 8px;
    align-items:center;
    min-width: 0;
  }}
  .role-idx{{ width: 30px; color: var(--text); font-weight: 700; }}
  .role-name{{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .role-right{{ display:flex; gap: 10px; align-items:center; }}
  .sttok{{
    display:inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 14px;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(0,0,0,0.03);
    color: var(--text);
  }}
  .selected{{ background: var(--select); }}
  .dead{{ opacity: 0.45; text-decoration: line-through; }}

  /* Log */
  .log-line{{
    padding: 3px 10px;
    font-size: 16px;
    line-height: 1.25;
    color: var(--text);
    white-space: pre-wrap;
  }}
  .log-empty{{ color: var(--muted); }}

  /* Slightly tighter buttons like desktop */
  .stButton>button {{
    height: 42px;
    border-radius: 6px;
  }}
</style>
""", unsafe_allow_html=True)

# ----------------------------
# Engine
# ----------------------------
@st.cache_resource
def load_engine():
    core = importlib.import_module("engine_core")
    EngineCls = getattr(core, "GameEngine", None) or getattr(core, "Engine", None)
    if EngineCls is None:
        raise AttributeError("engine_core.py must define Engine or GameEngine")
    return EngineCls()

engine = load_engine()

# ----------------------------
# Session state
# ----------------------------
if "speed" not in st.session_state:
    st.session_state.speed = 0.25
if "selected_cid" not in st.session_state:
    st.session_state.selected_cid = None

# Animation state (non-blocking, avoids time.sleep)
if "playing" not in st.session_state:
    st.session_state.playing = False
if "frame_i" not in st.session_state:
    st.session_state.frame_i = 0
if "turn_start_log_len" not in st.session_state:
    st.session_state.turn_start_log_len = 0
if "turn_frames" not in st.session_state:
    st.session_state.turn_frames = []

# ----------------------------
# Status color map
# ----------------------------
STATUS_COLOR = {
    "护盾": "#f2c14e",
    "净化": "#2ecc71",
    "雷霆": "#2c7be5",
    "感电": "#2c7be5",
    "氧化": "#2ecc71",
    "还原": "#2ecc71",
    "集火": "#e74c3c",
    "封印": "#2c7be5",
    "遗忘": "#2c7be5",
    "隐身": "#7f8c8d",
    "辩护": "#f2c14e",
    "圣辉": "#f2c14e",
    "神威": "#f2c14e",
    "防线": "#f2c14e",
    "附生": "#2ecc71",
    "越挫越勇": "#f2c14e",
    "厄运": "#e74c3c",
    "炸弹": "#e74c3c",
    "濒亡": "#e74c3c",
}

def token_html(token: str):
    key = token
    for k in STATUS_COLOR.keys():
        if token.startswith(k):
            key = k
            break
    color = STATUS_COLOR.get(key, "#bfc5cc")
    return f'<span class="sttok" style="color:{color}; border-color:{color}77; background:{color}14;">{token}</span>'

def parse_brief(brief: str):
    if not brief:
        return []
    return [p.strip() for p in brief.split("；") if p.strip()]

def build_roles_map_from_engine():
    roles_map = {}
    for cid in getattr(engine, "rank", []):
        r = engine.roles.get(cid)
        if not r:
            continue
        roles_map[cid] = {
            "alive": bool(getattr(r, "alive", True)),
            "brief": r.status.brief() if hasattr(r, "status") else "",
            "name": getattr(r, "name", str(cid)),
        }
    return roles_map

def merge_snap_with_engine(snap):
    """Ensure snap has proper role names and status strings even if snap is minimal."""
    if not isinstance(snap, dict):
        snap = {}
    snap.setdefault("rank", list(getattr(engine, "rank", [])))
    snap.setdefault("roles", {})
    eng_map = build_roles_map_from_engine()
    for cid, info in eng_map.items():
        snap["roles"].setdefault(cid, {})
        for k in ("alive", "brief", "name"):
            snap["roles"][cid].setdefault(k, info.get(k))
    return snap

def render_role_list(numbered_slice, roles_map, selected_cid=None):
    rows = []
    for i, cid in numbered_slice:
        info = roles_map.get(cid, {})
        alive = info.get("alive", True)
        name = info.get("name", str(cid))
        brief = info.get("brief", "")
        cls = "role-row"
        if selected_cid == cid:
            cls += " selected"
        if not alive:
            cls += " dead"
        toks = parse_brief(brief)[:2]
        right = "".join(token_html(t) for t in toks)
        rows.append(
            f"""<div class="{cls}">
                <div class="role-left">
                    <div class="role-idx">{i}.</div>
                    <div class="role-name">{name}</div>
                </div>
                <div class="role-right">{right}</div>
            </div>"""
        )
    return "\n".join(rows) if rows else "<div class='log-line log-empty'>（空）</div>"

def render_log_lines(lines):
    html = []
    for s in lines:
        if not s:
            html.append("<div class='log-line log-empty'> </div>")
        else:
            html.append(f"<div class='log-line'>{s}</div>")
    return "\n".join(html) if html else "<div class='log-line log-empty'>暂无日志</div>"

def get_current_snap():
    # Prefer latest frame snap if playing
    if st.session_state.playing and st.session_state.turn_frames:
        fi = min(st.session_state.frame_i, len(st.session_state.turn_frames)-1)
        fr = st.session_state.turn_frames[fi]
        snap = fr.get("snap") if isinstance(fr, dict) else None
        return merge_snap_with_engine(snap or {})
    # Otherwise, last frame from engine if exists
    frames = getattr(engine, "replay_frames", None) or []
    if frames:
        last = frames[-1]
        if isinstance(last, dict) and last.get("snap"):
            return merge_snap_with_engine(last["snap"])
    # Fallback: engine state
    return merge_snap_with_engine({})

def get_selected_from_frame(fr, snap_roles):
    highlights = fr.get("highlights") if isinstance(fr, dict) else None
    if highlights:
        for h in highlights:
            if isinstance(h, dict) and h.get("cid") in snap_roles:
                return h["cid"]
    return st.session_state.selected_cid

def start_play_one_turn():
    # Advance one turn and capture frames for this turn
    before_len = len(getattr(engine, "log", []))
    engine.next_turn()
    frames = getattr(engine, "replay_frames", None) or []
    st.session_state.turn_frames = frames
    st.session_state.turn_start_log_len = before_len
    st.session_state.frame_i = 0
    st.session_state.playing = True

def step_frame_if_playing():
    if not st.session_state.playing:
        return
    if st.session_state.frame_i >= max(0, len(st.session_state.turn_frames)-1):
        # Done
        st.session_state.playing = False
        return
    st.session_state.frame_i += 1

# ----------------------------
# Controls
# ----------------------------
st.caption(f"UI VERSION: {UI_VERSION}")

c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 1.3, 1.7, 2.0], gap="small")
with c1:
    new_clicked = st.button("新开局", use_container_width=True, disabled=st.session_state.playing)
with c2:
    next_clicked = st.button("下一回合", use_container_width=True, disabled=st.session_state.playing)
with c3:
    play_clicked = st.button("自动播放（单回合）", use_container_width=True, disabled=st.session_state.playing)
with c4:
    st.session_state.speed = st.slider("播放速度（秒/行）", 0.05, 0.80, float(st.session_state.speed), 0.05)
with c5:
    if st.session_state.playing:
        st.info("正在播放中…（无阻塞）")
    else:
        st.caption("目标：尽量复刻 a1.1.10 的三栏 UI（角色/角色/日志）。")

if new_clicked:
    engine.new_game()
    st.session_state.selected_cid = None
    st.session_state.playing = False
    st.session_state.turn_frames = []
    st.session_state.frame_i = 0
    st.rerun()

if next_clicked:
    engine.next_turn()
    st.rerun()

if play_clicked:
    start_play_one_turn()
    st.rerun()

# ----------------------------
# If playing, auto-rerun at interval (animation)
# ----------------------------
if st.session_state.playing:
    interval_ms = int(max(50, float(st.session_state.speed) * 1000))
    st_autorefresh(interval=interval_ms, key="anim_tick")
    # advance one frame per tick
    step_frame_if_playing()

# ----------------------------
# Main 3 panels
# ----------------------------
colA, colB, colC = st.columns([1.0, 1.0, 1.15], gap="small")

with colA:
    st.markdown('<div class="nb-panel"><div class="nb-panel-title">角色</div><div class="nb-scroll">', unsafe_allow_html=True)
    left_box = st.container()
    st.markdown('</div></div>', unsafe_allow_html=True)

with colB:
    st.markdown('<div class="nb-panel"><div class="nb-panel-title">角色</div><div class="nb-scroll">', unsafe_allow_html=True)
    mid_box = st.container()
    st.markdown('</div></div>', unsafe_allow_html=True)

with colC:
    st.markdown('<div class="nb-panel"><div class="nb-panel-title">日志</div><div class="nb-scroll">', unsafe_allow_html=True)
    log_box = st.container()
    st.markdown('</div></div>', unsafe_allow_html=True)

snap = get_current_snap()
rank = snap.get("rank", [])
roles_map = snap.get("roles", {})

# alive ordering like tk
alive_rank = [cid for cid in rank if roles_map.get(cid, {}).get("alive", True)]
numbered = list(enumerate(alive_rank, start=1))
left_part = numbered[:13]
mid_part = numbered[13:26]

# selection follow highlights during playing
if st.session_state.playing and st.session_state.turn_frames:
    fi = min(st.session_state.frame_i, len(st.session_state.turn_frames)-1)
    fr = st.session_state.turn_frames[fi]
    st.session_state.selected_cid = get_selected_from_frame(fr, roles_map)

left_box.markdown(render_role_list(left_part, roles_map, selected_cid=st.session_state.selected_cid), unsafe_allow_html=True)
mid_box.markdown(render_role_list(mid_part, roles_map, selected_cid=st.session_state.selected_cid), unsafe_allow_html=True)

# log subset during animation: show only turn's progressive lines
full_log = getattr(engine, "log", [])
if st.session_state.playing and st.session_state.turn_frames:
    # show progressive length based on frame_i
    shown = st.session_state.turn_start_log_len + st.session_state.frame_i + 1
    log_lines = full_log[:shown][-400:]
else:
    log_lines = full_log[-400:]

log_box.markdown(render_log_lines(log_lines), unsafe_allow_html=True)
