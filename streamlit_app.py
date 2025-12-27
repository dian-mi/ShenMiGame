# -*- coding: utf-8 -*-
import re
import importlib
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# IMPORTANT: set_page_config must be the first Streamlit command.
st.set_page_config(page_title="神秘游戏", layout="wide")

UI_VERSION = "v6-2025-12-27"

st.markdown("""
<style>
  :root{
    --bg: #efefef;
    --panel: #f7f7f7;
    --line: #d7d7d7;
    --text: #111;
    --muted: #666;
    --select: #fff3b0;
    --kill: #d0021b;
  }
  html, body, [data-testid="stAppViewContainer"] { height: 100%; overflow: hidden; background: var(--bg); }
  [data-testid="stAppViewContainer"] > .main { height: 100%; overflow: hidden; background: var(--bg); }
  .block-container { padding-top: 0.35rem; padding-bottom: 0.35rem; max-width: 100%; }
  header { visibility: hidden; height: 0px; }

  .nb-panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 0px;
    height: calc(100vh - 170px);
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
  .role-idx{ width: 30px; color: var(--text); font-weight: 700; }
  .role-name{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .role-right{ display:flex; gap: 10px; align-items:center; }
  .sttok{
    display:inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 14px;
    font-weight: 700;
    border: 1px solid rgba(0,0,0,0.10);
    background: rgba(0,0,0,0.03);
    color: var(--text);
    line-height: 1.2;
  }
  .selected{ background: var(--select); }
  .dead{ opacity: 0.45; text-decoration: line-through; }

  .log-line{
    padding: 3px 10px;
    font-size: 16px;
    line-height: 1.25;
    color: var(--text);
    white-space: pre-wrap;
  }
  .log-empty{ color: var(--muted); }
  .log-name{ font-weight: 800; }
  .log-kill{ color: var(--kill); font-weight: 900; }
  .log-bullet{ color: var(--muted); font-weight: 700; }
  .log-section{ font-weight: 900; }

  .stButton>button { height: 42px; border-radius: 6px; }
  #log-end { height: 1px; }
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

# Session state
if "speed" not in st.session_state:
    st.session_state.speed = 0.25
if "selected_cid" not in st.session_state:
    st.session_state.selected_cid = None
if "playing" not in st.session_state:
    st.session_state.playing = False
if "frame_i" not in st.session_state:
    st.session_state.frame_i = 0
if "turn_start_log_len" not in st.session_state:
    st.session_state.turn_start_log_len = 0
if "turn_frames" not in st.session_state:
    st.session_state.turn_frames = []

# Status colors aligned to a1.1.10 feel
STATUS_COLOR = {
    "护盾": "#f5a623",
    "净化": "#2ecc71",
    "雷霆": "#4a90e2",
    "封印": "#4a90e2",
    "遗忘": "#4a90e2",
    "感电": "#4a90e2",
    "氧化": "#2ecc71",
    "还原": "#2ecc71",
    "附生": "#2ecc71",
    "鱼": "#2ecc71",
    "乘胜追击": "#2ecc71",
    "集火": "#d0021b",
    "濒亡": "#d0021b",
    "炸弹": "#d0021b",
    "厄运": "#d0021b",
    "腐化": "#d0021b",
    "绝息": "#111111",
    "隐身": "#9b9b9b",
    "静默": "#9b9b9b",
    "迂回": "#9b9b9b",
    "目击": "#9b9b9b",
    "黄昏": "#9b9b9b",
    "留痕": "#9b9b9b",
    "辩护": "#f8d24a",
    "圣辉": "#f8d24a",
    "神威": "#f8d24a",
    "防线": "#f8d24a",
    "越挫越勇": "#f8d24a",
    "特异性免疫": "#f8d24a",
    "洪伟之赐": "#f8d24a",
}

def token_html(token: str):
    key = token
    for k in STATUS_COLOR.keys():
        if token.startswith(k):
            key = k
            break
    color = STATUS_COLOR.get(key, "#bfc5cc")
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

# Log formatting
NAME_IN_BRACKETS = re.compile(r"【([^】]+)】")
NAME_WITH_NUM = re.compile(r"^(.*?)(\(\d+\))$")

def strip_name_num(s: str) -> str:
    m = NAME_WITH_NUM.match(s.strip())
    if m:
        return m.group(1)
    return s

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

def render_log_html(lines):
    html = [format_log_line(s) for s in lines]
    html.append("<div id='log-end'></div>")
    html.append("""
<script>
  const el = window.parent.document.querySelector('#log-end');
  if (el) { el.scrollIntoView({behavior: 'instant', block: 'end'}); }
</script>
""")
    return "\n".join(html) if html else "<div class='log-line log-empty'>暂无日志</div>"

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

def get_selected_from_frame(fr, snap_roles):
    highlights = fr.get("highlights") if isinstance(fr, dict) else None
    if highlights:
        for h in highlights:
            if isinstance(h, dict) and h.get("cid") in snap_roles:
                return h["cid"]
    return st.session_state.selected_cid

def start_play_one_turn():
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
        st.session_state.playing = False
        return
    st.session_state.frame_i += 1

# Controls
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
        st.info("正在播放中…（逐行+自动滚动）")
    else:
        st.caption("目标：严格复刻 a1.1.10 的三栏 UI（角色/角色/日志）。")

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

if st.session_state.playing:
    interval_ms = int(max(80, float(st.session_state.speed) * 1000))
    st_autorefresh(interval=interval_ms, key="anim_tick")
    step_frame_if_playing()

# Main 3 panels
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

alive_rank = [cid for cid in rank if roles_map.get(cid, {}).get("alive", True)]
numbered = list(enumerate(alive_rank, start=1))
left_part = numbered[:13]
mid_part = numbered[13:26]

if st.session_state.playing and st.session_state.turn_frames:
    fi = min(st.session_state.frame_i, len(st.session_state.turn_frames)-1)
    fr = st.session_state.turn_frames[fi]
    st.session_state.selected_cid = get_selected_from_frame(fr, roles_map)

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
    while len(rows) < 13:
        rows.append("<div class='role-row'><div class='role-left'><div class='role-idx'>&nbsp;</div><div class='role-name'>&nbsp;</div></div><div class='role-right'></div></div>")
    return "\n".join(rows)

left_box.markdown(render_role_list(left_part, roles_map, selected_cid=st.session_state.selected_cid), unsafe_allow_html=True)
mid_box.markdown(render_role_list(mid_part, roles_map, selected_cid=st.session_state.selected_cid), unsafe_allow_html=True)

full_log = getattr(engine, "log", [])
if st.session_state.playing and st.session_state.turn_frames:
    shown = st.session_state.turn_start_log_len + st.session_state.frame_i + 1
    log_lines = full_log[:shown][-400:]
else:
    log_lines = full_log[-400:]

log_box.markdown(render_log_html(log_lines), unsafe_allow_html=True)
