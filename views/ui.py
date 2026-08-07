"""Presentation components for the copilot's design system.

Streamlit's built-in widgets carry the theme from `.streamlit/config.toml`; these
helpers cover the custom surfaces — candidate rows, evidence cards, interview
questions — that the design calls for and Streamlit has no primitive for.

Everything user- or model-supplied is HTML-escaped: résumé quotes and model output
land inside markup here, and a stray `<` should never reach the DOM as a tag.
"""

from html import escape
from pathlib import Path

import streamlit as st

CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "styles.css"

# Evidence status drives color throughout the app: green found, amber partial,
# neutral absent. Absent is deliberately NOT red — a gap is a question, not a fault.
STATUS_STYLES = {
    "evidence_found": {"accent": "#12A06A", "fg": "#0E6B4A", "bg": "#E6F4EE", "label": "evidence found"},
    "partial_evidence": {"accent": "#D89A2B", "fg": "#8A6212", "bg": "#FCF3E2", "label": "partial evidence"},
    "no_evidence": {"accent": "#C6C8D2", "fg": "#5A5F6B", "bg": "#EFEFF3", "label": "no evidence"},
}

BADGE_STYLES = {
    "neutral": {"fg": "#5A5F6B", "bg": "#EFEFF3"},
    "brand": {"fg": "#4B44E0", "bg": "#EFEEFD"},
    "warn": {"fg": "#8A6212", "bg": "#FCF3E2"},
    "danger": {"fg": "#8F2C26", "bg": "#FDF3F2"},
    "success": {"fg": "#0E6B4A", "bg": "#E6F4EE"},
}


def load_css() -> None:
    if CSS_PATH.exists():
        st.markdown(f"<style>{CSS_PATH.read_text()}</style>", unsafe_allow_html=True)


def _html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def badge(text: str, kind: str = "neutral") -> str:
    style = BADGE_STYLES.get(kind, BADGE_STYLES["neutral"])
    return (
        f'<span class="pc-badge" style="color:{style["fg"]};background:{style["bg"]}">'
        f"{escape(text)}</span>"
    )


def section_label(text: str, meta: str = "") -> None:
    meta_html = f'<span class="pc-label-meta">{escape(meta)}</span>' if meta else ""
    _html(f'<div class="pc-label-row"><span class="pc-label">{escape(text)}</span>{meta_html}</div>')


def chips(items: list[str]) -> None:
    if items:
        _html("".join(f'<span class="pc-chip">{escape(i)}</span>' for i in items))


def summary_card(label: str, body: str, tally: list[tuple[str, int, str]] | None = None) -> None:
    """A prose card with an optional dot-and-count footer."""
    tally_html = ""
    if tally:
        items = "".join(
            f'<div class="pc-tally-item"><span class="pc-dot" style="background:{color}"></span>'
            f"<span><strong>{count}</strong> {escape(name)}</span></div>"
            for name, count, color in tally
        )
        tally_html = f'<div class="pc-tally">{items}</div>'
    _html(
        f'<div class="pc-card"><div class="pc-label">{escape(label)}</div>'
        f"<p>{escape(body)}</p>{tally_html}</div>"
    )


def alert(title: str, body: str) -> None:
    _html(
        f'<div class="pc-alert"><div class="pc-alert-title">⚠️ {escape(title)}</div>'
        f'<div class="pc-alert-body">{escape(body)}</div></div>'
    )


def candidate_row(rank: int, name: str, score: float, badges: list[tuple[str, str]]) -> None:
    """One line of the ranking: position, name, score and an evidence bar.

    The bar is brand-colored at every score — grading candidates green-to-red would
    read as a verdict, and the number only measures evidence present in a résumé.
    """
    badge_html = " ".join(badge(text, kind) for text, kind in badges)
    _html(
        f'<div class="pc-card" style="padding:13px 16px">'
        f'<div class="pc-cand">'
        f'<span class="pc-rank">{rank}</span>'
        f'<span class="pc-cand-name">{escape(name)}</span>'
        f'<span class="pc-score">{score:.1f}%</span>'
        f"</div>"
        f'<div class="pc-bar"><div style="width:{max(0.0, min(score, 100.0)):.1f}%;background:#4B44E0"></div></div>'
        f'<div style="margin-top:9px">{badge_html}</div>'
        f"</div>"
    )


def evidence_card(name: str, status: str, quotes: list[str], reasoning: str, meta: str = "") -> None:
    style = STATUS_STYLES.get(status, STATUS_STYLES["no_evidence"])
    quote_html = "".join(f'<div class="pc-quote">“{escape(q)}”</div>' for q in quotes)
    meta_html = f'<span class="pc-ev-meta">{escape(meta)}</span>' if meta else ""
    _html(
        f'<div class="pc-ev" style="border-left-color:{style["accent"]}">'
        f'<div class="pc-ev-head">'
        f'<span class="pc-ev-name">{escape(name)}</span>'
        f'<span class="pc-badge" style="color:{style["fg"]};background:{style["bg"]}">{style["label"]}</span>'
        f"{meta_html}</div>"
        f"{quote_html}"
        f'<div class="pc-reason">{escape(reasoning)}</div>'
        f"</div>"
    )


def question_card(n: int, question: str, competency: str, rationale: str, listen_for: str) -> None:
    _html(
        f'<div class="pc-card" style="padding:16px 18px">'
        f'<div class="pc-q"><span class="pc-q-n">{n}</span><div style="flex:1">'
        f'<div class="pc-q-text">{escape(question)}</div>'
        f'<div style="margin-top:8px">{badge(competency, "brand")}</div>'
        f'<div class="pc-q-cols">'
        f'<div class="pc-q-col"><div class="pc-q-h">Why it matters</div>'
        f'<div class="pc-q-b">{escape(rationale)}</div></div>'
        f'<div class="pc-q-col"><div class="pc-q-h">Listen for</div>'
        f'<div class="pc-q-b">{escape(listen_for)}</div></div>'
        f"</div></div></div></div>"
    )


def milestone_card(title: str, description: str, success_signal: str) -> None:
    _html(
        f'<div class="pc-ms"><div class="pc-ms-title">{escape(title)}</div>'
        f'<div class="pc-ms-desc">{escape(description)}</div>'
        f'<div class="pc-ms-signal">✅ {escape(success_signal)}</div></div>'
    )
