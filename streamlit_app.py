# -*- coding: utf-8 -*-
import re
import importlib
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh
import math

st.set_page_config(page_title="神秘游戏", layout="wide")
UI_VERSION = "v9-2025-12-27"

# Keep big UI framework unchanged; only extend role list beyond 26 (supports 43+).
st.markdown("""
<style>
  html, body, [data-testid="stAppViewContainer"] { height: 100%; overflow: hidden; }
  [data-testid="stAppViewContainer"] > .main { height: 100%; overflow: hidden; }
  .block-container { padding-top: 0.35rem; padding-bottom: 0.35rem; max-width: 100%; }
  header { visibility: hidden; height: 0px; }
  .stButton>button { height: 42px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def load_engine():
    core = importlib.import_module("engine_core")
    EngineCls = getattr(core, "GameEngine", None) or getattr(core, "Engine", None)
    if EngineCls is None:
        raise AttributeError("engine_core.py must define Engine or GameEngine")
    return EngineCls()

engine = load_engine()

# ----------------------------
# State (a1.1.10 playback: 下一回合 triggers playback for that turn)
# ----------------------------
if "speed" not in st.session_state:
    st.session_state.speed = 0.25

if "did_tick" not in st.session_state:
    st.session_state.did_tick = False

if "focus_cid" not in st.session_state:
    st.session_state.focus_cid = None
if "playing" not in st.session_state:
    st.session_state.playing = False
if "frame_i" not in st.session_state:
    st.session_state.frame_i = 0
if "turn_frames" not in st.session_state:
    st.session_state.turn_frames = []
if "turn_start_log_len" not in st.session_state:
    st.session_state.turn_start_log_len = 0
if "selected_cid" not in st.session_state:
    st.session_state.selected_cid = None

# ----------------------------
# Status colors (match a1.1.10 Tkinter exactly)
# ----------------------------
# a1.1.10 palette:
#   color_thunder = "#0B3D91", color_pos = "#D4AF37", color_neg = "#E53935", color_purple = "#8E44AD"
def status_color(part: str) -> str:
    part = (part or "").strip()
    if not part:
        return "#000000"
    # Keep order consistent with a1.1.10 _set_rank_row
    if part.startswith("雷霆"):
        return "#0B3D91"
    elif part.startswith("腐化"):
        return "#8E44AD"
    elif part.startswith("隐身"):
        return "#A0A0A0"
    elif part.startswith("鱼"):
        return "#2E86C1"
    elif part.startswith("濒亡"):
        return "#E53935"
    elif part.startswith("炸弹"):
        return "#E53935"
    elif part.startswith("越挫越勇"):
        return "#8B4513"
    elif part.startswith("神威"):
        return "#D4AF37"
    elif part.startswith("洪伟之赐"):
        return "#D4AF37"
    elif part.startswith("雷霆手腕"):
        return "#0B3D91"
    elif part.startswith("氧化") or part.startswith("还原"):
        return "#006400"
    elif part.startswith("附生"):
        return "#F7DC6F"
    elif part.startswith("孤军奋战"):
        return "#D4AF37"
    elif part.startswith("特异性免疫"):
        return "#2ECC71"
    elif part.startswith("净化"):
        return "#7DCEA0"  # 浅绿色
    elif part.startswith("圣辉"):
        return "#D4AF37"  # 金色
    elif part.startswith("感电"):
        return "#85C1E9"  # 浅蓝色
    elif part.startswith("乘胜追击"):
        return "#F5B041"  # 浅橙色
    elif part.startswith("目击"):
        return "#8B4513"  # 棕色
    elif part.startswith("辩护"):
        return "#D4AF37"  # 金色
    elif part.startswith("静默"):
        return "#7D3C98"  # 灰紫
    elif part.startswith("迂回"):
        return "#76D7C4"  # 浅青
    elif part.startswith("防线"):
        return "#1E8449"  # 深绿
    elif part.startswith("护盾"):
        return "#D4AF37"
    else:
        # a1.1.10 default: negative red
        return "#E53935"

NAME_IN_BRACKETS = re.compile(r"【([^】]+)】")
NAME_WITH_NUM = re.compile(r"^(.*?)(\(\d+\))$")

def strip_name_num(s: str) -> str:
    m = NAME_WITH_NUM.match(s.strip())
    return m.group(1) if m else s

def token_html(token: str) -> str:
    color = status_color(token)
    return f'<span class="sttok" style="color:{color}; border-color:{color}77; background:{color}18;">{token}</span>'

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

def _normalize_snap(snap):
    """Engine replay_frames store snapshots as {'rank': [...], 'status': {cid:{alive,brief,name}}}.
    Streamlit UI expects 'roles' mapping. This helper converts/normalizes both shapes."""
    if not isinstance(snap, dict):
        snap = {}
    # If snapshot uses 'status' (engine format), convert to 'roles'
    if "roles" not in snap and isinstance(snap.get("status"), dict):
        roles = {}
        for k, v in snap.get("status", {}).items():
            try:
                cid = int(k)
            except Exception:
                cid = k
            if isinstance(v, dict):
                roles[cid] = {
                    "alive": bool(v.get("alive", True)),
                    "brief": v.get("brief", ""),
                    "name": v.get("name", str(cid)),
                }
        snap = dict(snap)  # shallow copy
        snap["roles"] = roles
    # If roles keys came as strings, normalize to int where possible
    if isinstance(snap.get("roles"), dict):
        norm_roles = {}
        for k, v in snap["roles"].items():
            try:
                cid = int(k)
            except Exception:
                cid = k
            norm_roles[cid] = v if isinstance(v, dict) else {}
        snap = dict(snap)
        snap["roles"] = norm_roles
    # Rank keys normalize
    if isinstance(snap.get("rank"), list):
        norm_rank = []
        for x in snap["rank"]:
            try:
                norm_rank.append(int(x))
            except Exception:
                norm_rank.append(x)
        snap = dict(snap)
        snap["rank"] = norm_rank
    return snap

def merge_snap_with_engine(snap):
    """Merge a snapshot with current engine data.
    IMPORTANT: snapshot wins (so role panel matches the currently shown log line).
    Engine is only used as a fallback for missing fields / newly spawned NPCs."""
    snap = _normalize_snap(snap)
    snap.setdefault("rank", list(getattr(engine, "rank", [])))
    snap.setdefault("roles", {})
    eng = build_roles_map_from_engine()
    for cid, info in eng.items():
        snap["roles"].setdefault(cid, {})
        for k in ("alive", "brief", "name"):
            snap["roles"][cid].setdefault(k, info.get(k))
    return snap

def get_current_snap():
    if st.session_state.playing and st.session_state.turn_frames:
        fi = min(st.session_state.frame_i, len(st.session_state.turn_frames)-1)
        fr = st.session_state.turn_frames[fi]
        snap = fr.get("snap") if isinstance(fr, dict) else None
        return merge_snap_with_engine(snap or {})
    frames = getattr(engine, "replay_frames", None) or []
    if frames:
        last = frames[-1]
        if isinstance(last, dict) and last.get("snap"):
            return merge_snap_with_engine(last["snap"])
    return merge_snap_with_engine({})

def get_selected_from_frame(fr, roles_map):
    hs = fr.get("highlights") if isinstance(fr, dict) else None
    if isinstance(hs, list) and hs:
        for h in hs:
            # engine_core uses List[int]; some variants may use dicts
            if isinstance(h, int) and h in roles_map:
                return h
            if isinstance(h, dict) and h.get("cid") in roles_map:
                return h["cid"]
    return st.session_state.selected_cid


def get_focus_from_frame(fr, roles_map):
    """Return primary triggering role cid for current frame.
    engine_core: highlights is List[int] parsed from current log line."""
    hs = fr.get("highlights") if isinstance(fr, dict) else None
    if isinstance(hs, list) and hs:
        for h in hs:
            if isinstance(h, int) and h in roles_map:
                return h
            if isinstance(h, dict) and h.get("cid") in roles_map:
                return h.get("cid")
    return None

def format_log_line(line: str) -> str:
    if not line:
        return "<div class='log-line log-empty'> </div>"
    esc = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    if "====" in esc or "【新开局】" in esc:
        esc = NAME_IN_BRACKETS.sub(lambda m: f"<span class='log-section'>【{strip_name_num(m.group(1))}】</span>", esc)
        return f"<div class='log-line log-section'>{esc}</div>"
    if esc.startswith("·") or esc.startswith("•"):
        esc = f"<span class='log-bullet'>·</span>{esc[1:]}"
    esc = NAME_IN_BRACKETS.sub(lambda m: f"<span class='log-name'>【{strip_name_num(m.group(1))}】</span>", esc)
    if any(k in esc for k in ["淘汰", "击杀", "斩杀"]):
        esc = esc.replace("class='log-name'", "class='log-name log-kill'")
    return f"<div class='log-line'>{esc}</div>"

def start_next_turn_playback():
    before_len = len(getattr(engine, "log", []))
    engine.next_turn()
    st.session_state.turn_frames = getattr(engine, "replay_frames", None) or []
    st.session_state.turn_start_log_len = before_len
    st.session_state.frame_i = 0
    st.session_state.playing = True

def step_playback():
    if not st.session_state.playing:
        return
    if st.session_state.frame_i >= max(0, len(st.session_state.turn_frames)-1):
        st.session_state.playing = False
        return
    st.session_state.frame_i += 1

# ----------------------------
# Controls (match a1.1.10)
# ----------------------------
st.caption(f"UI VERSION: {UI_VERSION}")

# Tk a1.1.10 has: 新开局 / 下一回合 / 下一行 / 自动播放 / 暂停 / 播放速度
# Streamlit keeps them on top (per your request) but the behavior matches:
# - 下一回合: advances engine.next_turn(), then immediately reveals 2 lines (if available) and starts auto-play for the rest
# - 下一行: reveals exactly 1 more line (manual step; does not force auto-play)
# - 自动播放: starts auto-play from current position (does not advance turn)
# - 暂停: stops auto-play at current line
def _build_turn_like_a1110():
    # Similar to UI.on_build_turn() in a1.1.10:
    # tick_alive_turns() -> next_turn() -> reveal 2 lines immediately (if possible) -> continue auto-play
    before_len = len(getattr(engine, "log", []))
    tick = getattr(engine, "tick_alive_turns", None)
    if callable(tick):
        tick()
    engine.next_turn()
    frames = getattr(engine, "replay_frames", None) or []
    st.session_state.turn_frames = frames
    st.session_state.turn_start_log_len = before_len

    if not frames:
        st.session_state.frame_i = 0
        st.session_state.playing = False
        return

    # Reveal the first line, then immediately reveal one more line and enter auto-play (old behavior).
    st.session_state.frame_i = min(1, len(frames) - 1)
    st.session_state.playing = True

def _step_one_line():
    frames = st.session_state.turn_frames or []
    if not frames:
        return
    if st.session_state.frame_i >= max(0, len(frames) - 1):
        return
    st.session_state.frame_i += 1

def _auto_play():
    frames = st.session_state.turn_frames or []
    if not frames:
        return
    # Avoid stacking (same as tk)
    if st.session_state.playing:
        return
    st.session_state.playing = True
    # Match tk: clicking auto-play should immediately advance 1 line.
    _step_one_line()

def _pause():
    st.session_state.playing = False

def _recommended_interval_ms():
    # Match tk: if "触发随机事件：" appears, pause at least 3s for readability.
    base = int(max(0.1, min(2.0, float(st.session_state.speed))) * 1000)
    frames = st.session_state.turn_frames or []
    if st.session_state.playing and frames:
        nxt_i = min(st.session_state.frame_i + 1, len(frames) - 1)
        try:
            txt = (frames[nxt_i] or {}).get("text", "")
            if "触发随机事件：" in txt:
                base = max(base, 3000)
        except Exception:
            pass
    return max(80, base)

# Buttons row (top, but same semantics as Tk bottom bar)
c1, c2, c3, c4, c5, c6 = st.columns([1.05, 1.05, 1.05, 1.05, 1.05, 1.75], gap="small")
with c1:
    new_clicked = st.button("新开局", use_container_width=True)
with c2:
    next_turn_clicked = st.button("下一回合", use_container_width=True)
with c3:
    next_line_clicked = st.button("下一行", use_container_width=True)
with c4:
    auto_clicked = st.button("自动播放", use_container_width=True)
with c5:
    pause_clicked = st.button("暂停", use_container_width=True)
with c6:
    st.session_state.speed = st.slider("播放速度（秒/行）", 0.10, 2.00, float(st.session_state.speed), 0.05)

if new_clicked:
    engine.new_game()
    st.session_state.selected_cid = None
    st.session_state.playing = False
    st.session_state.turn_frames = []
    st.session_state.frame_i = 0
    st.session_state.turn_start_log_len = 0
    st.rerun()

if next_turn_clicked:
    _build_turn_like_a1110()
    st.rerun()

if next_line_clicked:
    _step_one_line()
    st.rerun()

if auto_clicked:
    _auto_play()
    st.rerun()

if pause_clicked:
    _pause()
    st.rerun()

# Auto-play tick (one line per tick)
if st.session_state.playing:
    st_autorefresh(interval=_recommended_interval_ms(), key="anim_tick")
    st.session_state.did_tick = True

def _advance_if_playing():
    # Advance exactly one line per autorefresh tick.
    if not st.session_state.playing:
        st.session_state.did_tick = False
        return
    if not st.session_state.did_tick:
        return
    frames = st.session_state.turn_frames or []
    if not frames:
        st.session_state.playing = False
        st.session_state.did_tick = False
        return
    if st.session_state.frame_i >= max(0, len(frames) - 1):
        st.session_state.playing = False
        st.session_state.did_tick = False
        return
    st.session_state.frame_i += 1
    st.session_state.did_tick = False

_advance_if_playing()


if st.session_state.playing:
    st.info("自动播放中…（暂停可停止）")

# ----------------------------
# Panels
# ----------------------------
snap = get_current_snap()
rank = snap.get("rank", [])
roles_map = snap.get("roles", {})

if st.session_state.playing and st.session_state.turn_frames:
    fi = min(st.session_state.frame_i, len(st.session_state.turn_frames)-1)
    fr = st.session_state.turn_frames[fi]
    st.session_state.selected_cid = get_selected_from_frame(fr, roles_map)
    st.session_state.focus_cid = get_focus_from_frame(fr, roles_map)
    st.session_state.focus_cid = get_focus_from_frame(fr, roles_map)
else:
    st.session_state.focus_cid = None

alive_rank = [cid for cid in rank if roles_map.get(cid, {}).get("alive", True)]
numbered = list(enumerate(alive_rank, start=1))

# IMPORTANT CHANGE (v9):
# Split all alive roles (43+) into two columns evenly, instead of truncating to 26.
half = int(math.ceil(len(numbered) / 2)) if numbered else 0
left_part = numbered[:half]
mid_part  = numbered[half:]

def render_role_rows(slice_):
    rows = []
    for i, cid in slice_:
        info = roles_map.get(cid, {})
        cls = "role-row"
        if st.session_state.focus_cid == cid:
            cls += " focus"
        if st.session_state.selected_cid == cid:
            cls += " selected"
        if not info.get("alive", True):
            cls += " dead"
        toks = parse_brief(info.get("brief", ""))[:2]
        right = "".join(token_html(t) for t in toks)
        rows.append(f"""
<div class='{cls}'>
  <div class='role-left'>
    <div class='role-idx'>{i}.</div>
    <div class='role-name'>{info.get('name', str(cid))}</div>
  </div>
  <div class='role-right'>{right}</div>
</div>""")
    # no more hard padding to 13 lines; because we now support long lists (scroll).
    return "".join(rows)

left_rows = render_role_rows(left_part)
mid_rows  = render_role_rows(mid_part)

full_log = getattr(engine, "log", [])
if st.session_state.playing and st.session_state.turn_frames:
    shown = st.session_state.turn_start_log_len + st.session_state.frame_i + 1
    log_lines = full_log[:shown][-400:]
else:
    log_lines = full_log[-400:]
log_html = "".join(format_log_line(s) for s in log_lines)

PANEL_CSS = """<style>
  :root{--bg:#efefef;--panel:#f7f7f7;--line:#d7d7d7;--text:#111;--muted:#666;--select:#fff3b0;--kill:#d0021b;}
  html, body { height:100%; margin:0; background:var(--bg); overflow:hidden; }
  .nb-panel{ height:100%; background:var(--panel); border:1px solid var(--line); overflow:hidden; }
  .nb-panel-title{ font-weight:700; padding:8px 10px; border-bottom:1px solid var(--line); background:#f3f3f3; }
  .nb-scroll{ height: calc(100% - 41px); overflow-y:auto; }
  .role-row{ display:flex; align-items:center; justify-content:space-between; padding:6px 10px; border-bottom:1px solid var(--line); font-size:16px; color:var(--text); }
  .role-left{ display:flex; gap:8px; align-items:center; min-width:0; }
  .role-idx{ width:30px; font-weight:700; }
  .role-name{ white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .role-right{ display:flex; gap:10px; align-items:center; }
  .sttok{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:14px; font-weight:700; border:1px solid rgba(0,0,0,0.10); background:rgba(0,0,0,0.03); line-height:1.2; }
  .selected{ background:var(--select); }
  .dead{ opacity:0.45; text-decoration:line-through; }
  .log-line{ padding:3px 10px; font-size:16px; line-height:1.25; white-space:pre-wrap; color:var(--text); }
  .log-empty{ color:var(--muted); }
  .log-name{ font-weight:800; }
  .log-kill{ color:var(--kill); font-weight:900; }
  .log-bullet{ color:var(--muted); font-weight:700; }
  .log-section{ font-weight:900; }
</style>"""

def role_panel_html(title, rows):
    return f"<!doctype html><html><head>{PANEL_CSS}</head><body><div class='nb-panel'><div class='nb-panel-title'>{title}</div><div class='nb-scroll'>{rows}</div></div></body></html>"

def log_panel_html(title, lines):
    return f"""<!doctype html><html><head>{PANEL_CSS}</head><body>
<div class='nb-panel'><div class='nb-panel-title'>{title}</div><div class='nb-scroll' id='log-scroll'>{lines}<div id='end'></div></div></div>
<script>const sc=document.getElementById('log-scroll'); if(sc) sc.scrollTop=sc.scrollHeight;</script>
</body></html>"""

IFRAME_H = 860
colA, colB, colC = st.columns([1.0, 1.0, 1.15], gap="small")
with colA:
    components.html(role_panel_html("角色", left_rows), height=IFRAME_H, scrolling=False)
with colB:
    components.html(role_panel_html("角色", mid_rows), height=IFRAME_H, scrolling=False)
with colC:
    components.html(log_panel_html("日志", log_html), height=IFRAME_H, scrolling=False)
