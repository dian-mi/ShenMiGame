
# -*- coding: utf-8 -*-
import streamlit as st
from pathlib import Path
import importlib

st.set_page_config(page_title="神秘游戏 a1.1.10", layout="wide")
st.caption("UI VERSION: v9-role43-fix")

@st.cache_resource(show_spinner=False)
def load_engine():
    try:
        core = importlib.import_module("engine_core")
    except Exception:
        here = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location("engine_core", here / "engine_core.py")
        core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(core)
    return core.GameEngine()

engine = load_engine()

# ---- roles: support ANY count (43+) ----
roles = list(engine.roles.values())
roles.sort(key=lambda r: r.cid)

half = (len(roles) + 1) // 2
left_roles = roles[:half]
right_roles = roles[half:]

col1, col2, col3 = st.columns([1,1,1.4])

def render_roles(rs):
    for r in rs:
        name = r.name
        if not r.alive:
            name = f"💀 {name}"
        st.markdown(f"- **{name}**")

with col1:
    st.markdown("### 角色")
    render_roles(left_roles)

with col2:
    st.markdown("### 角色")
    render_roles(right_roles)

with col3:
    st.markdown("### 日志")
    for line in engine.logs[-200:]:
        st.markdown(line)
