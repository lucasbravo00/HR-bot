"""People Ops Copilot — an AI assistant for hiring and people operations.

This module is the router: it resolves navigation, picks the AI engine, and hands
off to a module in `views/`.
"""

import streamlit as st

from core import db
from views import competency_matrices, job_descriptions, recruiting, ui
from views.common import render_engine_picker

st.set_page_config(page_title="People Ops Copilot", page_icon="🧭", layout="wide")
db.init_db()
ui.load_css()

# Streamlit forbids writing to a widget's session_state key once that widget has been
# instantiated in the same run. Anything that navigates or prefills on the user's
# behalf therefore parks its value under a `pending_*` key, resolved here — before a
# single widget exists.
PENDING_KEYS = {
    "pending_section": "section",
    "pending_job_choice": "job_choice",
    "pending_new_jd_text": "new_jd_text",
    "pending_jd_choice": "jd_choice",
    "pending_cm_choice": "cm_choice",
    "pending_cm_role": "cm_role",
}
for pending, target in PENDING_KEYS.items():
    if pending in st.session_state:
        st.session_state[target] = st.session_state.pop(pending)

SECTIONS = {
    "🎯 Recruiting": recruiting,
    "📝 Job descriptions": job_descriptions,
    "📊 Competency matrices": competency_matrices,
}

st.sidebar.title("🧭 People Ops Copilot")
st.sidebar.caption("Evidence-based hiring, human in the loop")

# Containers reserve sidebar order up front, so the engine picker can render last
# while still being resolved before the view that needs it.
section_box = st.sidebar.container()
view_box = st.sidebar.container()
engine_box = st.sidebar.container()

with section_box:
    section_label = st.radio("Module", list(SECTIONS), key="section")
    st.divider()

with engine_box:
    provider = render_engine_picker()

SECTIONS[section_label].render(provider, view_box)
