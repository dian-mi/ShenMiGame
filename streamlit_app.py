# -*- coding: utf-8 -*-
import time
import importlib
import streamlit as st

st.set_page_config(page_title="神秘游戏", layout="wide")

# ----------------------------
# CSS: emulate a1.1.10 (3 panels, list rows, separators, selected yellow)
# No page scrolling; panels scroll internally.
# ----------------------------
st.markdown("""
<style>
  :root{
    --bg: #efefef;
    --panel: #f7f7f7;
    --line: #d7d7d7;
    --text: #111;
    --muted: #666;
    --select: #fff3b0;
  }
  html, body, [data-testid="stAppViewContainer"] { height: 100%; overflow: hidden; background: var(--bg); }
  [data-testid="stAppViewContainer"] > .main { height: 100%; overflow: hidden; background: var(--bg); }
  .block-container { padding-top: 0.4rem; padding-bottom: 0.4rem; max-width: 100%; }
  header { visibility: hidden; height: 0px; }

  .nb-wrap { height: calc(100vh - 130px); }
  .nb-panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 0px;
    height: 100%;
    overflow: hidden;
  }
  .nb-panel-title{
    font-weight: 700;
    padding: 8px 10px;
    border-bottom: 1px solid var(--line);
    color: var(--text);
    background: #f3f3f3;
  }
  .nb-scroll{
    height: calc(100% - 41px);
    overflow-y: auto;
  }

  /* Role rows */
  .role-row{
    display:flex;
    align-items:center;
    justify-content:space-between;
    padding: 6px 10px;
    border-bottom: 1px solid var(--line);
    font-size: 16px;
    color: var(--text);
    background: transparent;
  }
  .role-left{
    display:flex;
    gap: 8px;
    align-items:center;
    min-width: 0;
  }
  .role-idx{ width: 28px; color: var(--text); font-weight: 700; }
  .role-name{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .role-right{ display:flex; gap: 10px; align-items:center; }
  .sttok{
    display:inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 14px;
    border: 1px solid rgba(0,0,0,0.08);
    background: rgba(0,0,0,0.03);
    color: var(--text);
  }
  .selected{ background: var(--select); }
  .dead{ opacity: 0.45; text-decoration: line-through; }

  /* Log */
  .log-line{
    padding: 3px 10px;
    font-size: 16px;
    line-height: 1.25;
    color: var(--text);
    white-space: pre-wrap;
  }
  .log-empty{ color: var(--muted); }

  /* Control bar */
  .ctrlbar{
    display:flex;
    gap: 8px;
    align-items:center;
    padding: 6px 0 2px 0;
  }
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
if "snap" not in st.session_state:
    st.session_state.snap = None
if "selected_cid" not in st.session_state:
    st.session_state.selected_cid = None

# ----------------------------
# Status color map (close to tk version feeling)
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
    base = token
    key = token
    for k in STATUS_COLOR.keys():
        if token.startswith(k):
            key = k
            break
    color = STATUS_COLOR.get(key, "#bfc5cc")
    return f'<span class="sttok" style="color:{color}; border-color:{color}55; background:{color}12;">{base}</span>'

def parse_brief(brief: str):
    if not brief:
        return []
    return [p.strip() for p in brief.split("；") if p.strip()]

def current_snapshot():
    """Use last replay frame snap if present; else build from engine state."""
    if st.session_state.snap is not None:
        return st.session_state.snap
    # build minimal snap
    roles = {}
    for cid in getattr(engine, "rank", []):
        r = engine.roles.get(cid)
        if not r:
            continue
        roles[cid] = {"alive": bool(getattr(r, "alive", True)), "brief": r.status.brief() if hasattr(r, "status") else "", "name": getattr(r, "name", str(cid))}
    return {"turn": getattr(engine, "turn", 0), "rank": list(getattr(engine, "rank", [])), "roles": roles}

def render_role_list(rank_slice, roles_map, selected_cid=None):
    rows = []
    for i, cid in rank_slice:
        info = roles_map.get(cid, {})
        alive = info.get("alive", True)
        name = info.get("name", str(cid))
        brief = info.get("brief", "")
        cls = "role-row"
        if selected_cid == cid:
            cls += " selected"
        if not alive:
            cls += " dead"
        toks = parse_brief(brief)
        # TK-like: show up to 2 tokens on the right (keep list tidy)
        toks = toks[:2]
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

def render_log_lines(log_lines):
    html = []
    for s in log_lines:
        if not s:
            html.append("<div class='log-line log-empty'> </div>")
        else:
            html.append(f"<div class='log-line'>{s}</div>")
    return "\n".join(html) if html else "<div class='log-line log-empty'>暂无日志</div>"

def set_snap(snap):
    st.session_state.snap = snap
    # pick selected from highlights if available
    # try: first highlight cid in snap roles that exists
    # otherwise keep previous
    return

def play_turn_animation(log_box, left_box, mid_box):
    frames = getattr(engine, "replay_frames", None) or []
    if not frames:
        snap = current_snapshot()
        set_snap(snap)
        log_box.markdown(render_log_lines(getattr(engine, "log", [])[-400:]), unsafe_allow_html=True)
        rerender_roles(left_box, mid_box, snap)
        return

    full_log = getattr(engine, "log", [])
    start_index = max(0, len(full_log) - len(frames))

    # During animation, use each frame's snap + highlights to emulate selection
    for i, fr in enumerate(frames):
        snap = fr.get("snap")
        highlights = fr.get("highlights") or []
        if snap:
            set_snap(snap)
        # choose selected
        sel = st.session_state.selected_cid
        for h in highlights:
            if isinstance(h, dict) and h.get("cid") in (snap or {}).get("roles", {}):
                sel = h["cid"]
                break
        st.session_state.selected_cid = sel

        subset = full_log[: start_index + i + 1]
        log_box.markdown(render_log_lines(subset[-400:]), unsafe_allow_html=True)
        rerender_roles(left_box, mid_box, snap or current_snapshot(), selected_cid=sel)
        time.sleep(float(st.session_state.speed))

def rerender_roles(left_box, mid_box, snap, selected_cid=None):
    rank = snap.get("rank", [])
    roles_map = snap.get("roles", {})
    # only show alive roles as in tk list
    alive_rank = []
    for cid in rank:
        info = roles_map.get(cid, {})
        if info.get("alive", True):
            alive_rank.append(cid)

    # Assign numbering 1..N by alive order (tk version)
    numbered = list(enumerate(alive_rank, start=1))
    left_part = numbered[:13]
    mid_part = numbered[13:26]

    left_html = render_role_list(left_part, roles_map, selected_cid=selected_cid)
    mid_html  = render_role_list(mid_part, roles_map, selected_cid=selected_cid)

    left_box.markdown(left_html, unsafe_allow_html=True)
    mid_box.markdown(mid_html, unsafe_allow_html=True)

# ----------------------------
# Controls (top like tk bottom bar; streamlit can't truly pin bottom reliably)
# ----------------------------
c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 1.2, 1.7, 2.0], gap="small")

with c1:
    new_clicked = st.button("新开局", use_container_width=True)
with c2:
    next_clicked = st.button("下一回合", use_container_width=True)
with c3:
    play_clicked = st.button("自动播放（单回合）", use_container_width=True)
with c4:
    st.session_state.speed = st.slider("播放速度（秒/行）", 0.05, 0.80, float(st.session_state.speed), 0.05)
with c5:
    st.caption("目标：尽量复刻 a1.1.10 的三栏 UI（角色/角色/日志）。")

if new_clicked:
    engine.new_game()
    st.session_state.snap = None
    st.session_state.selected_cid = None
    st.rerun()

# ----------------------------
# Main 3 panels: Roles(1..13) | Roles(14..26) | Log
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

# Initial render from snapshot
snap = current_snapshot()
rerender_roles(left_box, mid_box, snap, selected_cid=st.session_state.selected_cid)
log_box.markdown(render_log_lines(getattr(engine, "log", [])[-400:]), unsafe_allow_html=True)

# Actions
if next_clicked:
    engine.next_turn()
    # update to latest snap if available
    if getattr(engine, "replay_frames", None):
        last = engine.replay_frames[-1]
        if isinstance(last, dict) and last.get("snap"):
            st.session_state.snap = last["snap"]
    st.rerun()

if play_clicked:
    engine.next_turn()
    play_turn_animation(log_box, left_box, mid_box)
    # final render
    snap = current_snapshot()
    rerender_roles(left_box, mid_box, snap, selected_cid=st.session_state.selected_cid)
    log_box.markdown(render_log_lines(getattr(engine, "log", [])[-400:]), unsafe_allow_html=True)
