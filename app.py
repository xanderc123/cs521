"""
Bitcoin Selfish Mining Simulator
Based on: "Majority is not Enough: Bitcoin Mining is Vulnerable" (Eyal & Sirer, 2014)

Graduate-level course presentation tool.
"""

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import time
import random
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

# ─────────────────────────────────────────────────────────────────────────────
# Data Structures
# ─────────────────────────────────────────────────────────────────────────────

class BlockType(Enum):
    HONEST = "honest"
    SELFISH = "selfish"
    ORPHAN = "orphan"

@dataclass
class Block:
    id: int
    block_type: BlockType
    height: int
    miner: str
    is_orphan: bool = False
    parent_id: Optional[int] = None

@dataclass
class SimState:
    public_chain: List[Block] = field(default_factory=list)
    private_chain: List[Block] = field(default_factory=list)
    orphaned_blocks: List[Block] = field(default_factory=list)
    selfish_lead: int = 0          # δ in the paper
    total_blocks_mined: int = 0
    selfish_blocks_in_main: int = 0
    honest_blocks_in_main: int = 0
    honest_orphan_count: int = 0
    selfish_orphan_count: int = 0
    events: List[str] = field(default_factory=list)
    round_num: int = 0

    def revenue_selfish(self) -> float:
        total = self.selfish_blocks_in_main + self.honest_blocks_in_main
        if total == 0:
            return 0.0
        return self.selfish_blocks_in_main / total

    def revenue_honest(self) -> float:
        total = self.selfish_blocks_in_main + self.honest_blocks_in_main
        if total == 0:
            return 0.0
        return self.honest_blocks_in_main / total


# ─────────────────────────────────────────────────────────────────────────────
# Core Selfish Mining Logic  (Eyal & Sirer state machine)
# ─────────────────────────────────────────────────────────────────────────────

def selfish_mining_revenue(alpha: float, gamma: float) -> float:
    """
    Closed-form relative revenue for a selfish pool (Eyal & Sirer, 2014).

    alpha : fraction of total hash rate controlled by selfish pool
    gamma : fraction of honest miners that mine on selfish chain during a race
            (network propagation advantage, 0 ≤ γ ≤ 1)

    Returns: relative revenue of the selfish pool
    """
    if alpha <= 0:
        return 0.0
    if alpha >= 1:
        return 1.0
    beta = 1 - alpha
    numerator   = alpha * (beta**2 + beta * alpha * gamma * (4*alpha + gamma*(1 - 2*alpha)) - alpha**3)
    denominator = 1 - alpha * (1 + alpha * (2 - alpha))
    # Protect against degenerate denominator
    if abs(denominator) < 1e-12:
        return alpha
    rev = numerator / denominator
    # Fallback to simpler formula if complex case returns garbage
    # Simple version from original paper
    simple = (alpha * (1-alpha)**2 * (4*alpha + gamma*(1-2*alpha)) - alpha**3) / \
             (1 - alpha*(1 + (2-alpha)*alpha))
    try:
        result = simple
    except Exception:
        result = alpha
    return max(0.0, min(1.0, result))


def profitability_threshold(gamma: float) -> float:
    """
    Minimum alpha for selfish mining to be profitable (rev > alpha).
    From the paper: alpha > (1 - gamma) / (3 - 2*gamma)
    """
    if gamma >= 1:
        return 0.0
    return (1 - gamma) / (3 - 2 * gamma)


def handle_event(state: SimState, event: str, alpha: float, gamma: float) -> SimState:
    """
    Apply one step of the Eyal-Sirer state machine.

    States are represented implicitly by `state.selfish_lead` (δ):
      δ = 0  → both chains equal length
      δ > 0  → selfish pool has a private lead of δ blocks
      δ < 0  → honest chain is ahead (selfish pool lost a race)
    """
    pid = state.total_blocks_mined  # block id counter
    delta = state.selfish_lead

    if event == "selfish_finds":
        # Selfish pool mines a block on their private chain
        state.total_blocks_mined += 1
        blk = Block(id=pid, block_type=BlockType.SELFISH,
                    height=len(state.public_chain) + len(state.private_chain),
                    miner="Selfish Pool")
        state.private_chain.append(blk)
        state.selfish_lead += 1
        delta = state.selfish_lead

        if delta == 1:
            state.events.append("🔒 Selfish mined block #1 privately. Keeping secret (lead=1).")
        else:
            state.events.append(f"🔒 Selfish extends private chain. Lead now = {delta}.")

    elif event == "honest_finds":
        # Honest miner mines a block on the public chain
        state.total_blocks_mined += 1
        blk = Block(id=pid, block_type=BlockType.HONEST,
                    height=len(state.public_chain),
                    miner="Honest Miners")

        if delta == 0:
            # Both equal: honest block extends public chain, selfish pool starts fresh
            state.public_chain.append(blk)
            state.honest_blocks_in_main += 1
            state.events.append("✅ Honest block added to public chain. Selfish lead stays 0.")

        elif delta == 1:
            # Tie! Selfish immediately publishes their one private block → race
            # Fraction γ of honest miners adopt selfish block
            race_blk = state.private_chain.pop()
            race_blk.height = len(state.public_chain)
            state.public_chain.append(race_blk)  # tentatively on public
            state.selfish_lead = 0

            # Honest block is the competing tip
            # With probability γ, selfish wins the race (γ fraction of honest mines on it)
            # We model it deterministically: selfish gets γ share, honest gets (1-γ)
            # For the interactive sim we'll do a probabilistic draw
            if random.random() < gamma:
                # Selfish wins race: honest block becomes orphan
                blk.is_orphan = True
                state.orphaned_blocks.append(blk)
                state.honest_orphan_count += 1
                state.selfish_blocks_in_main += 1
                state.events.append(
                    f"⚔️ RACE! Selfish published. γ={gamma:.2f} → Selfish wins! "
                    f"Honest block #{pid} ORPHANED. ☠️"
                )
            else:
                # Honest wins race: selfish block becomes orphan
                state.public_chain.pop()  # remove selfish block from public
                race_blk.is_orphan = True
                state.orphaned_blocks.append(race_blk)
                state.selfish_orphan_count += 1
                state.public_chain.append(blk)
                state.honest_blocks_in_main += 1
                state.events.append(
                    f"⚔️ RACE! Selfish published. γ={gamma:.2f} → Honest wins. "
                    f"Selfish block ORPHANED. ☠️"
                )

        elif delta == 2:
            # Selfish publishes both private blocks — both are accepted
            while state.private_chain:
                pb = state.private_chain.pop(0)
                pb.height = len(state.public_chain)
                state.public_chain.append(pb)
                state.selfish_blocks_in_main += 1
            state.selfish_lead = 0
            # Honest block is now stale (public chain just jumped ahead)
            blk.is_orphan = True
            state.orphaned_blocks.append(blk)
            state.honest_orphan_count += 1
            state.events.append(
                f"🚀 SELFISH PUBLISHES 2 blocks! Honest block #{pid} ORPHANED. ☠️ Lead reset to 0."
            )

        elif delta > 2:
            # Selfish publishes one block to match honest, maintains lead
            pub_blk = state.private_chain.pop(0)
            pub_blk.height = len(state.public_chain)
            state.public_chain.append(pub_blk)
            state.selfish_blocks_in_main += 1
            state.selfish_lead -= 1
            # Honest block still orphaned since public chain advances
            blk.is_orphan = True
            state.orphaned_blocks.append(blk)
            state.honest_orphan_count += 1
            state.events.append(
                f"📤 Selfish releases 1 block. Honest block #{pid} ORPHANED. "
                f"Lead now = {state.selfish_lead}."
            )

        else:
            # delta < 0: shouldn't happen in normal SM, treat as honest wins
            state.public_chain.append(blk)
            state.honest_blocks_in_main += 1
            state.selfish_lead = 0
            state.events.append("✅ Honest block added (selfish reset).")

    state.round_num += 1
    return state


# ─────────────────────────────────────────────────────────────────────────────
# Automated Simulation
# ─────────────────────────────────────────────────────────────────────────────

def run_simulation(alpha: float, gamma: float, n_rounds: int = 500) -> pd.DataFrame:
    """Run full automated simulation, return per-round statistics."""
    state = SimState()
    records = []

    for _ in range(n_rounds):
        event = "selfish_finds" if random.random() < alpha else "honest_finds"
        state = handle_event(state, event, alpha, gamma)
        records.append({
            "round": state.round_num,
            "selfish_lead": state.selfish_lead,
            "selfish_revenue": state.revenue_selfish(),
            "honest_revenue": state.revenue_honest(),
            "honest_orphans": state.honest_orphan_count,
            "selfish_orphans": state.selfish_orphan_count,
            "public_chain_len": len(state.public_chain),
        })

    return pd.DataFrame(records), state


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit UI
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Bitcoin Selfish Mining Simulator",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Dark theme tweaks */
[data-testid="stAppViewContainer"] { background: #0d1117; }
[data-testid="stSidebar"] { background: #161b22; }

.metric-card {
    background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
    border: 1px solid #374151;
    border-radius: 12px;
    padding: 16px 20px;
    text-align: center;
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.metric-card .value {
    font-size: 2rem;
    font-weight: 700;
    color: #f59e0b;
}
.metric-card .label {
    font-size: 0.8rem;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 4px;
}

.block-public {
    display: inline-block;
    background: linear-gradient(135deg,#1d4ed8,#2563eb);
    border: 2px solid #3b82f6;
    border-radius: 8px;
    padding: 6px 12px;
    margin: 3px;
    font-size: 0.75rem;
    color: #e0f2fe;
    font-family: monospace;
}
.block-selfish-private {
    display: inline-block;
    background: linear-gradient(135deg,#7c2d12,#991b1b);
    border: 2px solid #ef4444;
    border-radius: 8px;
    padding: 6px 12px;
    margin: 3px;
    font-size: 0.75rem;
    color: #fee2e2;
    font-family: monospace;
}
.block-orphan {
    display: inline-block;
    background: #1f2937;
    border: 2px dashed #6b7280;
    border-radius: 8px;
    padding: 6px 12px;
    margin: 3px;
    font-size: 0.75rem;
    color: #6b7280;
    font-family: monospace;
    text-decoration: line-through;
}

.event-log {
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 12px;
    height: 200px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 0.82rem;
}

.lead-badge {
    display: inline-block;
    background: #78350f;
    border: 2px solid #f59e0b;
    border-radius: 20px;
    padding: 4px 16px;
    font-size: 1.1rem;
    font-weight: 700;
    color: #fde68a;
}
.lead-zero {
    background: #064e3b;
    border-color: #10b981;
    color: #a7f3d0;
}

.section-header {
    font-size: 1.1rem;
    font-weight: 600;
    color: #f3f4f6;
    border-left: 4px solid #f59e0b;
    padding-left: 10px;
    margin: 12px 0 8px 0;
}

.info-box {
    background: #161b22;
    border: 1px solid #30363d;
    border-left: 4px solid #3b82f6;
    border-radius: 6px;
    padding: 12px 16px;
    font-size: 0.85rem;
    color: #c9d1d9;
    margin: 8px 0;
}
</style>
""", unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⛏️ Selfish Mining Sim")
    st.markdown("*Eyal & Sirer, 2014*")
    st.divider()

    mode = st.radio(
        "Mode",
        ["📊 Theory & Analysis", "🎮 Interactive Step-by-Step", "🤖 Auto Simulation"],
        index=0,
    )
    st.divider()

    st.markdown("### Parameters")
    alpha = st.slider(
        "α — Selfish Pool Hash Rate",
        min_value=0.01, max_value=0.49, value=0.33, step=0.01,
        help="Fraction of total network hash power controlled by the selfish pool."
    )
    gamma = st.slider(
        "γ — Network Propagation Advantage",
        min_value=0.0, max_value=1.0, value=0.5, step=0.05,
        help="Fraction of honest miners who receive the selfish block first during a race (0=none, 1=all)."
    )

    threshold = profitability_threshold(gamma)
    is_profitable = alpha > threshold

    st.divider()
    st.markdown("### Profitability Check")
    if is_profitable:
        st.success(f"✅ Profitable! α={alpha:.2f} > threshold {threshold:.3f}")
    else:
        st.error(f"❌ Not Profitable. α={alpha:.2f} ≤ threshold {threshold:.3f}")

    st.markdown(f"""
<div class="info-box">
Threshold formula (Eyal & Sirer):<br>
<code>α* = (1−γ) / (3−2γ)</code><br><br>
At γ={gamma:.2f} → α* ≈ <strong>{threshold:.3f}</strong> ({threshold*100:.1f}%)
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MODE 1: Theory & Analysis
# ─────────────────────────────────────────────────────────────────────────────

if "Theory" in mode:
    st.title("⛏️ Bitcoin Selfish Mining — Theory & Analysis")
    st.markdown("> *\"Majority is not Enough: Bitcoin Mining is Vulnerable\"* — Eyal & Sirer (2014)")

    # ── Profitability Heat-Map ─────────────────────────────────────────────
    col1, col2 = st.columns([1.6, 1])

    with col1:
        st.markdown('<div class="section-header">Relative Revenue vs. α and γ</div>', unsafe_allow_html=True)

        alphas = np.linspace(0.01, 0.49, 80)
        gammas = np.linspace(0.0, 1.0, 60)
        Z = np.zeros((len(gammas), len(alphas)))

        for i, g in enumerate(gammas):
            for j, a in enumerate(alphas):
                rev = selfish_mining_revenue(a, g)
                Z[i, j] = rev - a  # excess revenue over honest mining

        fig_heat = go.Figure(data=go.Heatmap(
            z=Z,
            x=alphas,
            y=gammas,
            colorscale=[
                [0.0, "#1d4ed8"],   # bright blue  (most negative)
                [0.4, "#1e3a5f"],   # dark blue     (slightly negative)
                [0.5, "#111827"],   # near-black    (zero)
                [0.6, "#78350f"],   # dark amber    (slightly positive)
                [1.0, "#f59e0b"],   # bright amber  (most positive)
            ],
            zmid=0,
            colorbar=dict(
                title=dict(
                    text="Excess Revenue<br>(vs. honest mining)",
                    font=dict(color="#9ca3af"),
                ),
                tickfont=dict(color="#9ca3af"),
            ),
            hovertemplate="α=%{x:.2f}  γ=%{y:.2f}<br>Excess Rev=%{z:.3f}<extra></extra>",
        ))

        # Add profitability boundary line
        threshold_line = [(1-g)/(3-2*g) for g in gammas]
        fig_heat.add_trace(go.Scatter(
            x=threshold_line, y=gammas,
            mode="lines",
            line=dict(color="#f87171", width=2.5, dash="dash"),
            name="Profitability Threshold α*",
        ))

        # Mark current alpha/gamma
        fig_heat.add_trace(go.Scatter(
            x=[alpha], y=[gamma],
            mode="markers",
            marker=dict(size=14, color="#facc15", symbol="star",
                        line=dict(color="white", width=2)),
            name=f"Current (α={alpha:.2f}, γ={gamma:.2f})",
        ))

        fig_heat.update_layout(
            height=400,
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            font=dict(color="#c9d1d9"),
            xaxis=dict(title="α (Selfish Hash Rate)", gridcolor="#21262d", tickformat=".0%"),
            yaxis=dict(title="γ (Propagation Advantage)", gridcolor="#21262d", tickformat=".0%"),
            legend=dict(bgcolor="#161b22", bordercolor="#374151", borderwidth=1),
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(fig_heat, width="stretch")

    with col2:
        st.markdown('<div class="section-header">Relative Revenue at γ={:.2f}</div>'.format(gamma),
                    unsafe_allow_html=True)

        rev_curve = [selfish_mining_revenue(a, gamma) for a in alphas]
        fair_line = list(alphas)

        fig_rev = go.Figure()
        fig_rev.add_trace(go.Scatter(
            x=alphas, y=fair_line,
            mode="lines",
            line=dict(color="#6b7280", width=1.5, dash="dot"),
            name="Fair (honest mining)",
        ))
        fig_rev.add_trace(go.Scatter(
            x=alphas, y=rev_curve,
            mode="lines",
            line=dict(color="#f59e0b", width=2.5),
            name="Selfish Mining Revenue",
            fill="tonexty",
            fillcolor="rgba(245,158,11,0.1)",
        ))
        # Threshold vertical
        fig_rev.add_vline(x=threshold, line_color="#ef4444", line_dash="dash", line_width=1.5)
        fig_rev.add_annotation(x=threshold, y=0.7,
                               text=f"α*={threshold:.3f}", showarrow=True,
                               arrowhead=2, arrowcolor="#ef4444",
                               font=dict(color="#ef4444", size=11))
        # Mark current
        cur_rev = selfish_mining_revenue(alpha, gamma)
        fig_rev.add_trace(go.Scatter(
            x=[alpha], y=[cur_rev],
            mode="markers",
            marker=dict(size=12, color="#facc15", symbol="star",
                        line=dict(color="white", width=2)),
            name=f"Current α={alpha:.2f}",
        ))

        fig_rev.update_layout(
            height=400,
            paper_bgcolor="#0d1117",
            plot_bgcolor="#0d1117",
            font=dict(color="#c9d1d9"),
            xaxis=dict(title="α", gridcolor="#21262d", tickformat=".0%"),
            yaxis=dict(title="Relative Revenue", gridcolor="#21262d", tickformat=".0%"),
            legend=dict(bgcolor="#161b22", bordercolor="#374151", borderwidth=1, x=0.01, y=0.99),
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(fig_rev, width="stretch")

    # ── Key Metrics ────────────────────────────────────────────────────────
    cur_rev = selfish_mining_revenue(alpha, gamma)
    excess  = cur_rev - alpha

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="value">{alpha*100:.1f}%</div>
            <div class="label">Hash Rate α</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        color = "#10b981" if excess > 0 else "#ef4444"
        st.markdown(f"""
        <div class="metric-card">
            <div class="value" style="color:{color}">{cur_rev*100:.1f}%</div>
            <div class="label">Selfish Revenue</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="value" style="color:{'#10b981' if excess > 0 else '#ef4444'}">
                {'+' if excess >= 0 else ''}{excess*100:.1f}%
            </div>
            <div class="label">Excess vs Fair</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="value">{threshold*100:.1f}%</div>
            <div class="label">Threshold α*</div>
        </div>""", unsafe_allow_html=True)

    # ── State Machine Diagram ──────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-header">Eyal-Sirer State Machine</div>', unsafe_allow_html=True)

    col_sm1, col_sm2 = st.columns([1.2, 1])
    with col_sm1:
        fig_sm = go.Figure()

        # States as nodes
        states = {
            "δ=0\n(Tied)": (0.5, 0.5),
            "δ=1\n(Lead 1)": (2.0, 0.5),
            "δ=2\n(Lead 2)": (3.5, 0.5),
            "δ≥3\n(Large Lead)": (5.0, 0.5),
        }
        colors = ["#1d4ed8", "#b45309", "#92400e", "#7c2d12"]

        for (label, pos), color in zip(states.items(), colors):
            fig_sm.add_shape(type="rect",
                x0=pos[0]-0.4, y0=pos[1]-0.25, x1=pos[0]+0.4, y1=pos[1]+0.25,
                fillcolor=color, line=dict(color="white", width=1.5))
            fig_sm.add_annotation(x=pos[0], y=pos[1], text=label,
                font=dict(color="white", size=11), showarrow=False)

        # Transitions (arrows with labels)
        transitions = [
            # (from_x, from_y, to_x, to_y, label, color)
            (0.9, 0.5, 1.6, 0.5, "SM finds\nblock", "#ef4444"),
            (0.5, 0.25, 0.5, -0.1, "Honest finds\n(publish 0, earn 0)", "#6b7280"),
            (2.0, 0.25, 1.0, 0.0, "Honest finds\n(RACE, γ wins)", "#f59e0b"),
            (2.4, 0.5, 3.1, 0.5, "SM finds\nblock", "#ef4444"),
            (3.5, 0.25, 2.0, -0.15, "Honest finds\n(publish 2, orphan honest)", "#10b981"),
            (3.9, 0.5, 4.6, 0.5, "SM finds", "#ef4444"),
            (5.0, 0.25, 3.9, -0.1, "Honest finds\n(release 1)", "#3b82f6"),
        ]

        for (x0, y0, x1, y1, label, color) in transitions:
            fig_sm.add_annotation(
                ax=x0, ay=y0, x=x1, y=y1,
                xref="x", yref="y", axref="x", ayref="y",
                showarrow=True, arrowhead=2, arrowsize=1.2,
                arrowwidth=2, arrowcolor=color,
                font=dict(color=color, size=9),
                text=label,
            )

        fig_sm.update_layout(
            height=320,
            paper_bgcolor="#0d1117",
            plot_bgcolor="#161b22",
            xaxis=dict(visible=False, range=[-0.5, 6]),
            yaxis=dict(visible=False, range=[-0.6, 1.2]),
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig_sm, width="stretch")

    with col_sm2:
        st.markdown("""
<div class="info-box">
<strong>State Machine Rules (Eyal & Sirer)</strong><br><br>

<strong>δ = 0 (Tied):</strong><br>
• Honest mines → Honest gets the block, SM starts fresh.<br>
• SM mines → SM hides block, δ becomes 1.<br><br>

<strong>δ = 1 (SM leads by 1):</strong><br>
• Honest mines → RACE! SM publishes secret block.<br>
  &nbsp;&nbsp;- γ fraction of honest mines on SM block.<br>
  &nbsp;&nbsp;- If SM wins: honest block orphaned. ☠️<br>
• SM mines → δ becomes 2.<br><br>

<strong>δ = 2 (SM leads by 2):</strong><br>
• Honest mines → SM publishes both blocks immediately.<br>
  Honest block is orphaned. ☠️ δ resets to 0.<br>
• SM mines → δ becomes 3.<br><br>

<strong>δ ≥ 3 (Large lead):</strong><br>
• Honest mines → SM releases 1 block. Honest orphaned. ☠️<br>
  δ decreases by 1 (SM stays ahead).<br>
• SM mines → δ increases by 1.
</div>
""", unsafe_allow_html=True)

    # ── Paper Excerpt ──────────────────────────────────────────────────────
    st.divider()
    st.markdown('<div class="section-header">Key Insight from the Paper</div>', unsafe_allow_html=True)
    st.markdown("""
<div class="info-box">
<strong>Theorem (Eyal & Sirer, 2014):</strong> A selfish pool with hash rate α > α* = (1−γ)/(3−2γ)
earns a <em>disproportionately high</em> fraction of the mining reward, and the Bitcoin protocol
is therefore not incentive-compatible.<br><br>

At γ = 0 (no propagation advantage): α* ≈ 33.3% &nbsp;|&nbsp;
At γ = 0.5 (50% reach): α* ≈ 25% &nbsp;|&nbsp;
At γ = 1.0 (full propagation): α* → 0%<br><br>

<strong>Mechanism:</strong> By selectively withholding and then releasing mined blocks, the selfish pool
forces honest miners to waste work on blocks that will be orphaned, while the selfish pool's
own blocks are always on the winning chain.
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MODE 2: Interactive Step-by-Step
# ─────────────────────────────────────────────────────────────────────────────

elif "Interactive" in mode:
    st.title("🎮 Interactive Selfish Mining — Step-by-Step")
    st.markdown("*Click the buttons below to manually advance the mining process and observe the attack in real time.*")

    # Initialize session state
    if "sim_state" not in st.session_state:
        st.session_state.sim_state = SimState()
    if "history" not in st.session_state:
        st.session_state.history = []

    state: SimState = st.session_state.sim_state

    # ── Action Buttons ─────────────────────────────────────────────────────
    st.markdown("### Choose Next Event")
    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])

    with btn_col1:
        if st.button("⛏️ Honest Miner Finds Block", width="stretch", type="secondary"):
            st.session_state.sim_state = handle_event(
                st.session_state.sim_state, "honest_finds", alpha, gamma)
            st.session_state.history.append(("honest", st.session_state.sim_state.revenue_selfish()))
            st.rerun()

    with btn_col2:
        if st.button("🔒 Selfish Miner Finds Block", width="stretch", type="primary"):
            st.session_state.sim_state = handle_event(
                st.session_state.sim_state, "selfish_finds", alpha, gamma)
            st.session_state.history.append(("selfish", st.session_state.sim_state.revenue_selfish()))
            st.rerun()

    with btn_col3:
        if st.button("🔄 Reset Simulation", width="stretch"):
            st.session_state.sim_state = SimState()
            st.session_state.history = []
            st.rerun()

    state = st.session_state.sim_state

    # ── Chain Visualization ────────────────────────────────────────────────
    st.divider()

    lead_class = "lead-zero" if state.selfish_lead == 0 else ""
    lead_emoji = "🟢" if state.selfish_lead == 0 else ("🔴" if state.selfish_lead > 0 else "⚪")
    st.markdown(
        f'### Chain Status &nbsp;&nbsp; {lead_emoji} '
        f'<span class="lead-badge {lead_class}">Selfish Lead δ = {state.selfish_lead}</span>',
        unsafe_allow_html=True
    )

    chain_col1, chain_col2 = st.columns(2)

    with chain_col1:
        st.markdown("#### 🌐 Public Chain")
        if not state.public_chain:
            st.markdown("*[Genesis Block]*")
        else:
            chain_html = ""
            for blk in state.public_chain[-15:]:  # show last 15
                badge = "block-public" if blk.block_type == BlockType.HONEST else "block-selfish-private"
                miner_icon = "👤" if blk.miner == "Honest Miners" else "🔴"
                chain_html += f'<span class="{badge}">{miner_icon} #{blk.id}</span> → '
            chain_html = chain_html.rstrip(" → ")
            st.markdown(chain_html + " 🏁", unsafe_allow_html=True)
        st.caption(f"Length: {len(state.public_chain)} blocks  |  "
                   f"🔵 Honest: {state.honest_blocks_in_main}  |  "
                   f"🔴 Selfish: {state.selfish_blocks_in_main}")

    with chain_col2:
        st.markdown("#### 🔒 Selfish Private Chain (Hidden!)")
        if not state.private_chain:
            st.markdown("*[Empty — no secret blocks]*")
        else:
            priv_html = ""
            for blk in state.private_chain:
                priv_html += f'<span class="block-selfish-private">🔴 #{blk.id}</span> → '
            priv_html = priv_html.rstrip(" → ")
            st.markdown(priv_html + " 🔒", unsafe_allow_html=True)
        st.caption(f"Private blocks held: {len(state.private_chain)}")

    # Orphan graveyard
    if state.orphaned_blocks:
        st.markdown("#### ☠️ Orphaned Blocks")
        orphan_html = ""
        for blk in state.orphaned_blocks[-20:]:
            orphan_html += (f'<span class="block-orphan">'
                            f'{"👤" if blk.miner == "Honest Miners" else "🔴"} #{blk.id}</span> ')
        st.markdown(orphan_html, unsafe_allow_html=True)

    # ── Live Metrics ───────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Live Statistics")
    m1, m2, m3, m4, m5 = st.columns(5)

    with m1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="value">{state.round_num}</div>
            <div class="label">Rounds Played</div>
        </div>""", unsafe_allow_html=True)
    with m2:
        rev_s = state.revenue_selfish()
        color = "#10b981" if rev_s > alpha else "#ef4444"
        st.markdown(f"""
        <div class="metric-card">
            <div class="value" style="color:{color}">{rev_s*100:.1f}%</div>
            <div class="label">Selfish Revenue</div>
        </div>""", unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="value">{state.revenue_honest()*100:.1f}%</div>
            <div class="label">Honest Revenue</div>
        </div>""", unsafe_allow_html=True)
    with m4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="value" style="color:#ef4444">{state.honest_orphan_count}</div>
            <div class="label">Honest Orphans ☠️</div>
        </div>""", unsafe_allow_html=True)
    with m5:
        excess = rev_s - alpha
        color2 = "#10b981" if excess > 0 else "#ef4444"
        st.markdown(f"""
        <div class="metric-card">
            <div class="value" style="color:{color2}">
                {'+' if excess >= 0 else ''}{excess*100:.1f}%
            </div>
            <div class="label">Excess vs Fair</div>
        </div>""", unsafe_allow_html=True)

    # ── Revenue History Chart ──────────────────────────────────────────────
    if len(st.session_state.history) >= 2:
        st.divider()
        st.markdown("### Revenue History")
        hist_df = pd.DataFrame(st.session_state.history, columns=["event", "selfish_revenue"])
        hist_df["round"] = range(1, len(hist_df)+1)
        hist_df["fair_revenue"] = alpha

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Scatter(
            x=hist_df["round"], y=hist_df["fair_revenue"],
            mode="lines", line=dict(color="#6b7280", dash="dot", width=1.5),
            name=f"Fair Share (α={alpha:.2f})",
        ))
        fig_hist.add_trace(go.Scatter(
            x=hist_df["round"], y=hist_df["selfish_revenue"],
            mode="lines+markers",
            line=dict(color="#f59e0b", width=2),
            marker=dict(
                color=["#ef4444" if e=="selfish" else "#3b82f6"
                       for e in hist_df["event"]],
                size=7,
            ),
            name="Selfish Revenue",
        ))
        fig_hist.update_layout(
            height=260,
            paper_bgcolor="#0d1117", plot_bgcolor="#161b22",
            font=dict(color="#c9d1d9"),
            xaxis=dict(title="Round", gridcolor="#21262d"),
            yaxis=dict(title="Revenue Share", gridcolor="#21262d", tickformat=".0%"),
            legend=dict(bgcolor="#161b22", bordercolor="#374151", borderwidth=1),
            margin=dict(l=60, r=20, t=20, b=50),
        )
        st.plotly_chart(fig_hist, width="stretch")

    # ── Event Log ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Event Log")
    if state.events:
        log_html = "<br>".join(reversed(state.events[-20:]))
        st.markdown(f'<div class="event-log">{log_html}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="event-log"><em>No events yet — click a button above.</em></div>',
                    unsafe_allow_html=True)

    # ── Tip Box ───────────────────────────────────────────────────────────
    st.markdown("""
<div class="info-box" style="margin-top:16px">
<strong>Presentation Tips:</strong><br>
• Start with a few <em>Honest</em> blocks to show normal mining, then switch to <em>Selfish</em>.<br>
• Watch the 🔒 private chain grow. When an honest block appears at δ=1 or δ=2, notice what happens.<br>
• The ☠️ <em>orphan count</em> is the key metric — honest miners waste their work.<br>
• Try setting α=0.33, γ=0.5 (the classic "25% threshold" scenario).
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# MODE 3: Auto Simulation
# ─────────────────────────────────────────────────────────────────────────────

elif "Auto" in mode:
    st.title("🤖 Automated Selfish Mining Simulation")
    st.markdown("*Run thousands of rounds and analyze the statistical outcome.*")

    n_rounds = st.slider("Number of Rounds", 100, 5000, 1000, 100)

    if st.button("▶️ Run Simulation", type="primary", width="stretch"):
        with st.spinner("Simulating..."):
            df, final_state = run_simulation(alpha, gamma, n_rounds)

        st.success(f"Simulation complete! {n_rounds} rounds.")

        # ── Summary Metrics ────────────────────────────────────────────
        final_rev = final_state.revenue_selfish()
        theoretical_rev = selfish_mining_revenue(alpha, gamma)
        excess = final_rev - alpha

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="value">{alpha*100:.1f}%</div>
                <div class="label">Hash Rate α</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            color = "#10b981" if excess > 0 else "#ef4444"
            st.markdown(f"""
            <div class="metric-card">
                <div class="value" style="color:{color}">{final_rev*100:.1f}%</div>
                <div class="label">Simulated Revenue</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="value">{theoretical_rev*100:.1f}%</div>
                <div class="label">Theoretical Revenue</div>
            </div>""", unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div class="metric-card">
                <div class="value" style="color:#ef4444">{final_state.honest_orphan_count}</div>
                <div class="label">Honest Orphans ☠️</div>
            </div>""", unsafe_allow_html=True)
        with c5:
            orphan_rate = final_state.honest_orphan_count / max(1,
                final_state.honest_orphan_count + final_state.honest_blocks_in_main)
            st.markdown(f"""
            <div class="metric-card">
                <div class="value" style="color:#f59e0b">{orphan_rate*100:.1f}%</div>
                <div class="label">Honest Orphan Rate</div>
            </div>""", unsafe_allow_html=True)

        # ── Revenue Over Time ──────────────────────────────────────────
        st.divider()
        fig_sim = make_subplots(rows=2, cols=2,
            subplot_titles=[
                "Revenue Share Over Time",
                "Selfish Lead (δ) Over Time",
                "Cumulative Orphaned Blocks",
                "Revenue Distribution (Last 20%)",
            ],
            vertical_spacing=0.15,
        )

        # Panel 1: Revenue
        fig_sim.add_trace(go.Scatter(
            x=df["round"], y=[alpha]*len(df),
            mode="lines", line=dict(color="#6b7280", dash="dot", width=1.5),
            name="Fair Share", showlegend=True,
        ), row=1, col=1)
        fig_sim.add_trace(go.Scatter(
            x=df["round"], y=df["selfish_revenue"],
            mode="lines", line=dict(color="#f59e0b", width=2),
            name="Selfish Revenue", showlegend=True,
        ), row=1, col=1)

        # Panel 2: Lead
        fig_sim.add_trace(go.Scatter(
            x=df["round"], y=df["selfish_lead"],
            mode="lines", line=dict(color="#ef4444", width=1.5),
            fill="tozeroy", fillcolor="rgba(239,68,68,0.15)",
            name="Selfish Lead δ", showlegend=False,
        ), row=1, col=2)

        # Panel 3: Orphans
        fig_sim.add_trace(go.Scatter(
            x=df["round"], y=df["honest_orphans"],
            mode="lines", line=dict(color="#ef4444", width=2),
            name="Honest Orphans", showlegend=False,
        ), row=2, col=1)
        fig_sim.add_trace(go.Scatter(
            x=df["round"], y=df["selfish_orphans"],
            mode="lines", line=dict(color="#f59e0b", width=1.5, dash="dash"),
            name="Selfish Orphans", showlegend=False,
        ), row=2, col=1)

        # Panel 4: Final revenue distribution (last 20%)
        tail = df.tail(n_rounds // 5)
        fig_sim.add_trace(go.Histogram(
            x=tail["selfish_revenue"],
            nbinsx=30,
            marker_color="#f59e0b",
            name="Revenue dist",
            showlegend=False,
        ), row=2, col=2)
        fig_sim.add_vline(x=alpha, line_color="#6b7280", line_dash="dot", row=2, col=2)
        fig_sim.add_vline(x=theoretical_rev, line_color="#10b981", line_dash="dash", row=2, col=2)

        fig_sim.update_layout(
            height=600,
            paper_bgcolor="#0d1117",
            plot_bgcolor="#161b22",
            font=dict(color="#c9d1d9"),
            showlegend=True,
            legend=dict(bgcolor="#161b22", bordercolor="#374151", borderwidth=1),
        )
        for ann in fig_sim.layout.annotations:
            ann.font.color = "#9ca3af"

        for axis_key in ["xaxis", "yaxis", "xaxis2", "yaxis2",
                         "xaxis3", "yaxis3", "xaxis4", "yaxis4"]:
            if hasattr(fig_sim.layout, axis_key):
                getattr(fig_sim.layout, axis_key).update(
                    gridcolor="#21262d", zerolinecolor="#374151"
                )

        st.plotly_chart(fig_sim, width="stretch")

        # ── Alpha Sweep ────────────────────────────────────────────────
        st.divider()
        st.markdown('<div class="section-header">Alpha Sweep — Revenue vs. Hash Rate</div>',
                    unsafe_allow_html=True)
        st.markdown("*Running 300-round micro-simulations at each α value...*")

        sweep_alphas = np.linspace(0.05, 0.49, 25)
        sim_revs, theo_revs = [], []
        prog = st.progress(0)
        for idx, a in enumerate(sweep_alphas):
            _, s = run_simulation(a, gamma, 300)
            sim_revs.append(s.revenue_selfish())
            theo_revs.append(selfish_mining_revenue(a, gamma))
            prog.progress((idx+1)/len(sweep_alphas))
        prog.empty()

        fig_sweep = go.Figure()
        fig_sweep.add_trace(go.Scatter(
            x=sweep_alphas, y=list(sweep_alphas),
            mode="lines", line=dict(color="#6b7280", dash="dot", width=1.5),
            name="Fair Share (y=x)",
        ))
        fig_sweep.add_trace(go.Scatter(
            x=sweep_alphas, y=theo_revs,
            mode="lines", line=dict(color="#10b981", width=2.5),
            name="Theoretical Revenue",
        ))
        fig_sweep.add_trace(go.Scatter(
            x=sweep_alphas, y=sim_revs,
            mode="markers+lines", line=dict(color="#f59e0b", width=1.5),
            marker=dict(size=7, color="#f59e0b"),
            name="Simulated Revenue",
        ))
        fig_sweep.add_vline(x=threshold, line_color="#ef4444", line_dash="dash", line_width=2)
        fig_sweep.add_annotation(x=threshold, y=0.85,
            text=f"Threshold α*={threshold:.3f}",
            font=dict(color="#ef4444", size=12), showarrow=True,
            arrowcolor="#ef4444", arrowhead=2)

        fig_sweep.update_layout(
            height=360,
            paper_bgcolor="#0d1117", plot_bgcolor="#161b22",
            font=dict(color="#c9d1d9"),
            xaxis=dict(title="α (Hash Rate)", gridcolor="#21262d", tickformat=".0%"),
            yaxis=dict(title="Revenue Share", gridcolor="#21262d", tickformat=".0%"),
            legend=dict(bgcolor="#161b22", bordercolor="#374151", borderwidth=1),
            margin=dict(l=60, r=20, t=20, b=60),
        )
        st.plotly_chart(fig_sweep, width="stretch")

        # ── Raw Stats ─────────────────────────────────────────────────
        with st.expander("📋 Raw Statistics"):
            st.dataframe(df.describe().T.style.format("{:.4f}"), width="stretch")
