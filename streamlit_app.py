# -*- coding: utf-8 -*-
import importlib
import re
import html
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

# IMPORTANT: set_page_config must be the first Streamlit command.
st.set_page_config(page_title="神秘游戏", layout="wide")

UI_VERSION = "v5-2025-12-27"

# ----------------------------
# CSS: match a1.1.10 (3 columns: role / role / log)
# - No global page scroll; each panel scrolls
# - Role rows separated, selected = yellow
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
  .block-container { padding-top: 0.35rem; padding-bottom: 0.35rem; max-width: 100%; }
  header { visibility: hidden; height: 0px; }
  [data-testid="stToolbar"] { visibility: visible; }

  /* Buttons */
  .stButton>button { height: 42px; border-radius: 6px; }

  /* Panel html */
  .nb-panel{
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 0px;
    height: calc(100vh - 150px);
    overflow: hidden;
  }
  .nb-title{
    font-weight: 700;
    padding: 8px 10px;
    border-bottom: 1px solid var(--line);
    color: var(--text);
    background: #f3f3f3;
    font-size: 18px;
  }
  .nb-scroll{
    height: calc(100% - 41px);
    overflow-y: auto;
  }

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
  .role-left{ display:flex; gap: 8px; align-items:center; min-width: 0; }
  .role-idx{ width: 30px; color: var(--text); font-weight: 700; }
  .role-name{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .role-right{ display:flex; gap: 10px; align-items:center; }
  .sttok{
    display:inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 14px;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(0,0,0,0.03);
    color: var(--text);
    white-space: nowrap;
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
    word-break: break-word;
  }
  .log-empty{ color: var(--muted); }
  .log-hr{ padding: 6px 10px; font-weight: 700; color:#333; }
  .log-name{ font-weight: 800; }
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
def ss_init():
    st.session_state.setdefault("speed", 0.25)
    st.session_state.setdefault("selected_cid", None)

    # playback
    st.session_state.setdefault("playing", False)
    st.session_state.setdefault("frame_i", 0)
    st.session_state.setdefault("turn_frames", [])
    st.session_state.setdefault("turn_start_log_len", 0)
    st.session_state.setdefault("turn_log_lines", [])  # progressive
    st.session_state.setdefault("log_autoscroll_nonce", 0)

ss_init()

# ----------------------------
# Status color map (used by role tokens + log highlighting)
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
    tok = html.escape(token)
    return f'<span class="sttok" style="color:{color}; border-color:{color}77; background:{color}14;">{tok}</span>'

def parse_brief(brief: str):
    if not brief:
        return []
    return [p.strip() for p in str(brief).split("；") if p.strip()]

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

# ----------------------------
# Log formatting (bold names + color statuses)
# ----------------------------
_name_pat = re.compile(r"【([^】]+)】")
_status_pat = re.compile(r"（([^）]+)）|\[([^\]]+)\]")

def format_log_line(s: str) -> str:
    if not s:
        return '<div class="log-line log-empty"> </div>'

    s = str(s)

    # separators / round headers
    if ("========" in s) or s.startswith("——"):
        return f'<div class="log-hr">{html.escape(s)}</div>'

    esc = html.escape(s)

    # bold 【Name】
    esc = _name_pat.sub(lambda m: f'【<span class="log-name">{m.group(1)}</span>】', esc)

    # color [Status] or （Status）
    def _colorize(m):
        token = m.group(1) or m.group(2) or ""
        raw = token
        key = raw
        for k in STATUS_COLOR.keys():
            if raw.startswith(k):
                key = k
                break
        color = STATUS_COLOR.get(key)
        if not color:
            return m.group(0)
        return m.group(0).replace(raw, f'<span style="color:{color}; font-weight:700">{raw}</span>')

    esc = _status_pat.sub(_colorize, esc)

    return f'<div class="log-line">{esc}</div>'

def render_log_html(lines):
    if not lines:
        return '<div class="log-line log-empty">暂无日志</div>'
    return "\n".join(format_log_line(x) for x in lines)

def render_roles_html(numbered_slice, roles_map, selected_cid=None):
    if not numbered_slice:
        return "<div class='log-line log-empty'>（空）</div>"

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
                    <div class="role-name">{html.escape(str(name))}</div>
                  </div>
                  <div class="role-right">{right}</div>
                </div>"""
        )
    return "\n".join(rows)

def panel_html(title: str, body_html: str, scroll_to_bottom: bool = False, nonce: int = 0) -> str:
    # If scroll_to_bottom, JS will push scroll to end on every nonce change.
    js = ""
    if scroll_to_bottom:
        js = f"""
<script>
(function(){{
  const panel = document.getElementById("nb-scroll-{nonce}");
  if(panel){{ panel.scrollTop = panel.scrollHeight; }}
}})();
</script>
"""
    return f"""
<div class="nb-panel">
  <div class="nb-title">{html.escape(title)}</div>
  <div class="nb-scroll" id="nb-scroll-{nonce}">
    {body_html}
  </div>
</div>
{js}
"""

# ----------------------------
# Playback: use engine.replay_frames[text] for smooth line-by-line
# ----------------------------
def start_play_one_turn():
    before_len = len(getattr(engine, "log", []))
    engine.next_turn()
    frames = getattr(engine, "replay_frames", None) or []
    st.session_state.turn_frames = frames
    st.session_state.turn_start_log_len = before_len
    st.session_state.frame_i = 0
    st.session_state.playing = True
    st.session_state.turn_log_lines = getattr(engine, "log", [])[:before_len]  # start from old log

def step_frame_if_playing():
    if not st.session_state.playing:
        return

    frames = st.session_state.turn_frames
    if not frames:
        st.session_state.playing = False
        return

    i = st.session_state.frame_i
    if i >= len(frames):
        st.session_state.playing = False
        return

    fr = frames[i]
    # Append this frame's text to progressive lines
    txt = fr.get("text") if isinstance(fr, dict) else None
    if txt is not None:
        st.session_state.turn_log_lines.append(txt)

    # Follow highlight selection
    snap = fr.get("snap") if isinstance(fr, dict) else None
    snap = merge_snap_with_engine(snap or {})
    highlights = fr.get("highlights") if isinstance(fr, dict) else None
    if highlights:
        for h in highlights:
            if isinstance(h, dict) and h.get("cid") in snap.get("roles", {}):
                st.session_state.selected_cid = h["cid"]
                break

    # advance
    st.session_state.frame_i += 1

    # autoscroll trigger
    st.session_state.log_autoscroll_nonce += 1

    # stop after last frame appended
    if st.session_state.frame_i >= len(frames):
        st.session_state.playing = False

def get_current_snap():
    # If playing, use last snap from frame_i-1
    if st.session_state.playing and st.session_state.turn_frames:
        fi = max(0, min(st.session_state.frame_i - 1, len(st.session_state.turn_frames) - 1))
        fr = st.session_state.turn_frames[fi]
        snap = fr.get("snap") if isinstance(fr, dict) else None
        return merge_snap_with_engine(snap or {})
    # Otherwise last frame snap
    frames = getattr(engine, "replay_frames", None) or []
    if frames:
        last = frames[-1]
        if isinstance(last, dict) and last.get("snap"):
            return merge_snap_with_engine(last["snap"])
    return merge_snap_with_engine({})

# ----------------------------
# Controls
# ----------------------------
st.caption(f"UI VERSION: {UI_VERSION}")

c1, c2, c3, c4, c5 = st.columns([1.1, 1.1, 1.35, 1.7, 2.0], gap="small")
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
        st.info("正在播放中…")
    else:
        st.caption("目标：尽量复刻 a1.1.10 的三栏 UI（角色/角色/日志）。")

if new_clicked:
    engine.new_game()
    st.session_state.selected_cid = None
    st.session_state.playing = False
    st.session_state.turn_frames = []
    st.session_state.frame_i = 0
    st.session_state.turn_log_lines = []
    st.session_state.log_autoscroll_nonce += 1
    st.rerun()

if next_clicked:
    engine.next_turn()
    st.session_state.log_autoscroll_nonce += 1
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
    step_frame_if_playing()

# ----------------------------
# Main 3 panels (render with components.html to avoid Streamlit DOM nesting bugs)
# ----------------------------
snap = get_current_snap()
rank = snap.get("rank", [])
roles_map = snap.get("roles", {})

# alive ordering like tk
alive_rank = [cid for cid in rank if roles_map.get(cid, {}).get("alive", True)]
numbered = list(enumerate(alive_rank, start=1))
left_part = numbered[:13]
mid_part = numbered[13:26]

role_left_html = render_roles_html(left_part, roles_map, selected_cid=st.session_state.selected_cid)
role_mid_html = render_roles_html(mid_part, roles_map, selected_cid=st.session_state.selected_cid)

# log: if playing use progressive lines, else full engine log
if st.session_state.playing:
    log_lines = st.session_state.turn_log_lines[-400:]
    nonce = st.session_state.log_autoscroll_nonce
else:
    log_lines = (getattr(engine, "log", []) or [])[-400:]
    nonce = st.session_state.log_autoscroll_nonce

log_html = render_log_html(log_lines)

colA, colB, colC = st.columns([1.0, 1.0, 1.15], gap="small")
with colA:
    components.html(panel_html("角色", role_left_html, scroll_to_bottom=False, nonce=0), height=650, scrolling=False)
with colB:
    components.html(panel_html("角色", role_mid_html, scroll_to_bottom=False, nonce=1), height=650, scrolling=False)
with colC:
    # autoscroll for log
    components.html(panel_html("日志", log_html, scroll_to_bottom=True, nonce=nonce), height=650, scrolling=False)
