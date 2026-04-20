"""Shared Streamlit styling, Plotly dark theme helpers, and static assets."""

from __future__ import annotations

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

COL_PAPER = "#0d1117"
COL_PLOT = "#0d1117"
COL_PANEL = "#161b22"
COL_FONT = "#e8eaed"
COL_LEGEND_BG = "#161b22"
COL_BORDER = "#374151"


def _read_asset(filename: str) -> str:
    path = _ASSETS_DIR / filename
    return path.read_text(encoding="utf-8")


def inject_theme_css() -> None:
    import streamlit as st

    css = _read_asset("theme.css")
    st.markdown(f"<style>\n{css}\n</style>", unsafe_allow_html=True)


def plotly_hooks_component() -> None:
    import streamlit.components.v1 as components

    js = _read_asset("plotly_hooks.js")
    html = (
        '<div style="height:0;width:0;overflow:hidden;">plotly-legend-opacity</div>\n'
        f"<script>\n{js}\n</script>"
    )
    components.html(html, height=1)


def metric_card_html(value: str, label: str, *, value_color: str | None = None) -> str:
    style = f' style="color:{value_color}"' if value_color else ""
    return (
        f'<div class="metric-card">'
        f'<div class="value"{style}>{value}</div>'
        f'<div class="label">{label}</div>'
        f"</div>"
    )


def _legend_base(**overrides: object) -> dict:
    leg = dict(
        bgcolor=COL_LEGEND_BG,
        bordercolor=COL_BORDER,
        borderwidth=1,
        font=dict(color=COL_FONT, size=12),
    )
    leg.update(overrides)
    return leg


def legend_top_right() -> dict:
    return _legend_base(
        x=0.99, y=0.99, xanchor="right", yanchor="top", valign="top"
    )


def legend_top_left() -> dict:
    return _legend_base(x=0.01, y=0.99)


def legend_panel() -> dict:
    """Default legend box for subplot-style charts."""
    return _legend_base()


def plotly_dark(
    *,
    height: int | None = None,
    paper_bgcolor: str = COL_PAPER,
    plot_bgcolor: str | None = None,
    margin: dict | None = None,
    legend: dict | None = None,
    showlegend: bool | None = None,
    font: dict | None = None,
    **extra: object,
) -> dict:
    layout: dict = {
        "paper_bgcolor": paper_bgcolor,
        "plot_bgcolor": plot_bgcolor if plot_bgcolor is not None else paper_bgcolor,
        "font": font or dict(color=COL_FONT),
    }
    if height is not None:
        layout["height"] = height
    if margin is not None:
        layout["margin"] = margin
    if legend is not None:
        layout["legend"] = legend
    if showlegend is not None:
        layout["showlegend"] = showlegend
    layout.update(extra)
    return layout
