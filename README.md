# Bitcoin Selfish Mining Simulator

> **Course:** CS 521 — Graduate Seminar in Distributed Systems  
> **Based on:** *"Majority is not Enough: Bitcoin Mining is Vulnerable"* — Eyal & Sirer (CCS 2014)

---

## Core Theory

### What is Selfish Mining?

In Bitcoin, miners compete to extend the blockchain by solving a computationally expensive puzzle. The longest chain wins, and the miner who found the winning block receives the block reward. The "honest" strategy is to immediately broadcast every block you find.

**Selfish mining** is a deviation: instead of broadcasting immediately, a mining pool *withholds* newly found blocks, secretly building a private chain. It then strategically publishes blocks to force honest miners to waste work on blocks that will be orphaned (discarded).

### The State Machine (Eyal & Sirer)

The attack is modeled as a Markov chain parameterized by:

| Symbol | Meaning |
|--------|---------|
| **α** | Fraction of total hash rate controlled by the selfish pool |
| **γ** | Fraction of honest miners who adopt the selfish block during a race (propagation advantage, 0 ≤ γ ≤ 1) |
| **δ** | Selfish pool's current private lead (number of hidden blocks ahead of public chain) |

The key transitions are:

| State (δ) | Honest finds block | Selfish finds block |
|-----------|--------------------|---------------------|
| 0 (tied) | Honest gets block, δ stays 0 | SM hides block, δ → 1 |
| 1 (SM leads by 1) | **RACE**: SM publishes its block; γ fraction of honest mines on SM → honest block orphaned with prob γ | δ → 2 |
| 2 (SM leads by 2) | SM publishes both; honest block orphaned ☠️; δ → 0 | δ → 3 |
| ≥ 3 (large lead) | SM releases 1 block; honest block orphaned ☠️; δ decreases by 1 | δ increases by 1 |

### The Profitability Threshold

The paper proves that selfish mining is profitable (earns more than fair share α) when:

```
α  >  α* = (1 − γ) / (3 − 2γ)
```

Key thresholds:

| γ (propagation) | α* (threshold) | Meaning |
|-----------------|----------------|---------|
| 0.0 (no advantage) | 33.3% | Classic "33% attack" threshold |
| 0.5 (half reach) | **25.0%** | The "25% threshold" often cited |
| 1.0 (full reach) | 0% | Any selfish pool is profitable |

This overturns the naive belief that Bitcoin is safe as long as no single party controls >50% of hash power.

### Revenue Formula

The closed-form relative revenue of the selfish pool is:

```
R(α, γ) = [α(1−α)²(4α + γ(1−2α)) − α³] / [1 − α(1 + (2−α)α)]
```

When R(α, γ) > α, the selfish pool earns a *disproportionate* share — the core result of the paper.

---

## Application Guide

### Installation

```bash
# 1. Clone the repo, then go to the folder that contains app.py
cd cs521   # or: cd Final_Project — use whatever directory name you cloned into

# 2. (Recommended) Python 3.11 virtual environment
python -m venv .venv311
.\.venv311\Scripts\activate          # Windows PowerShell
# source .venv311/bin/activate       # macOS / Linux

# 3. Install dependencies
pip install streamlit plotly pandas numpy

# 4. Launch the app (must be run from this directory so assets/ loads correctly)
streamlit run app.py
```

The app opens at `http://localhost:8501` in your browser.

---

### The Three Modes

#### 1. Theory & Analysis (default)

A full analytical dashboard showing:
- **Profitability heat-map**: every (α, γ) pair colored by excess revenue — instantly shows the dangerous region
- **Revenue curve**: plots R(α, γ) vs. α for the current γ, with the threshold marked
- **State machine diagram**: visual summary of all transitions
- **Key metrics**: live calculation of selfish revenue, excess vs. fair share, and threshold

**Best for:** Opening your presentation. Set α = 0.33 and γ = 0.5, point to the star on the heat-map, and explain why the orange region is dangerous.

---

#### 2. Interactive Step-by-Step (recommended for live demos)

A click-driven simulator where you manually fire each event:

| Button | What Happens |
|--------|-------------|
| ⛏️ Honest Miner Finds Block | An honest miner extends the public chain (or triggers a race/orphan) |
| 🔒 Selfish Miner Finds Block | Selfish pool adds a block to their private chain |
| 🔄 Reset | Clear everything and start fresh |

**What to watch:**
- The **🔒 Private Chain** grows silently while honest miners are unaware
- When δ = 1 and an honest block appears → a **RACE** resolves in real time
- The **☠️ Orphaned Blocks** graveyard fills up, representing wasted honest work
- The **Event Log** narrates every state machine transition
- The **Revenue History** chart shows selfish revenue climbing above the fair line

**Recommended demo script:**

1. Reset. Set α = 0.33, γ = 0.5.
2. Click **Selfish** 2 times → show private chain growing (δ = 2).
3. Click **Honest** → watch the SM immediately publish 2 blocks and orphan the honest block. Point to the ☠️.
4. Repeat. After ~20 rounds the revenue chart will show selfish pool above the dotted fair line.
5. Highlight the excess revenue metric.

---

#### 3. Auto Simulation

Runs a full statistical simulation (up to 5,000 rounds) and displays:
- **Revenue over time** (converges toward theoretical value)
- **Selfish lead δ over time** (shows the pool accumulating and burning its lead)
- **Cumulative orphan count** (honest waste grows monotonically)
- **Revenue distribution** in the final 20% of rounds (compare to theoretical)
- **Alpha sweep** — runs micro-simulations across all α values to empirically verify the profitability curve

**Best for:** Showing statistical robustness and the match between simulation and theory.

---

### Parameter Cheat Sheet

| Scenario | α | γ | Expected outcome |
|----------|---|---|-----------------|
| Safe zone (honest wins) | 0.20 | 0.5 | Revenue < 20%, not profitable |
| Classic "33% threat" | 0.33 | 0.0 | Barely profitable (α ≈ α*) |
| "25% threat" (γ=0.5) | 0.30 | 0.5 | Clearly profitable, good demo |
| Strong attacker | 0.40 | 0.5 | ~50% revenue with only 40% hash |
| Full propagation | 0.10 | 1.0 | Even 10% hash is profitable |

---

## Project Structure

Repository layout (all paths relative to the directory that contains `app.py`):

```
.
├── app.py                    # Streamlit entry: page config, sidebar, three modes, Plotly charts
├── README.md
├── .gitignore                # Ignores e.g. .venv311/
├── assets/
│   ├── theme.css             # Injected global styles (dark theme, metric cards, blocks, …)
│   └── plotly_hooks.js       # Injected script: Plotly legend opacity + interactive button paint
└── selfish_mining_sim/       # Importable package (simulation + UI helpers)
    ├── __init__.py           # Re-exports models + engine API
    ├── models.py             # Block, SimState, BlockType, MiningEvent, Miner
    ├── engine.py             # R(α,γ), profitability threshold, handle_event, run_simulation
    └── theme.py              # Reads assets/, inject_theme_css, plotly_hooks_component, plotly_dark, metric_card_html
```

`app.py` imports `selfish_mining_sim` for domain logic and theme helpers; CSS/JS are loaded from `assets/` at runtime, so keep the working directory at the project root when you run Streamlit.

---

## References

1. **Eyal, I., & Sirer, E. G. (2014).** Majority is not enough: Bitcoin mining is vulnerable. *Proceedings of the 18th International Conference on Financial Cryptography and Data Security (FC 2014).*  
   [https://arxiv.org/abs/1311.0243](https://arxiv.org/abs/1311.0243)

2. Nakamoto, S. (2008). Bitcoin: A peer-to-peer electronic cash system.

3. Sapirshtein, A., Sompolinsky, Y., & Zohar, A. (2016). Optimal selfish mining strategies in bitcoin. *FC 2016.*
