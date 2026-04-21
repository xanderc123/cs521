"""Eyal–Sirer selfish mining formulas and step simulation."""

from __future__ import annotations

import random
from typing import Tuple

import pandas as pd

from .models import Block, BlockType, MiningEvent, Miner, SimState


def selfish_mining_revenue(alpha: float, gamma: float) -> float:
    """
    Closed-form relative revenue for a selfish pool (Eyal & Sirer, 2014).

    alpha : fraction of total hash rate controlled by selfish pool
    gamma : fraction of honest miners that mine on selfish chain during a race
    """
    if alpha <= 0:
        return 0.0
    if alpha >= 1:
        return 1.0
    denom = 1 - alpha * (1 + (2 - alpha) * alpha)
    if abs(denom) < 1e-12:
        return max(0.0, min(1.0, alpha))
    simple = (
        alpha * (1 - alpha) ** 2 * (4 * alpha + gamma * (1 - 2 * alpha)) - alpha**3
    ) / denom
    return max(0.0, min(1.0, float(simple)))


def profitability_threshold(gamma: float) -> float:
    """Minimum alpha for selfish mining to be profitable (rev > alpha)."""
    if gamma >= 1:
        return 0.0
    return (1 - gamma) / (3 - 2 * gamma)


def _handle_selfish_finds(state: SimState) -> None:
    pid = state.total_blocks_mined
    state.total_blocks_mined += 1
    blk = Block(
        id=pid,
        block_type=BlockType.SELFISH,
        height=len(state.public_chain) + len(state.private_chain),
        miner=Miner.SELFISH.value,
    )
    state.private_chain.append(blk)
    state.selfish_lead += 1
    delta = state.selfish_lead
    if delta == 1:
        state.events.append(
            "Selfish mined block #1 privately. Keeping secret (lead=1)."
        )
    else:
        state.events.append(f"Selfish extends private chain. Lead now = {delta}.")


def _honest_lead_zero(state: SimState, blk: Block) -> None:
    state.public_chain.append(blk)
    state.honest_blocks_in_main += 1
    state.events.append("Honest block added to public chain. Selfish lead stays 0.")


def _honest_lead_one_race(state: SimState, blk: Block, pid: int, gamma: float) -> None:
    race_blk = state.private_chain.pop()
    race_blk.height = len(state.public_chain)
    state.public_chain.append(race_blk)
    state.selfish_lead = 0

    if random.random() < gamma:
        blk.is_orphan = True
        state.orphaned_blocks.append(blk)
        state.honest_orphan_count += 1
        state.selfish_blocks_in_main += 1
        state.events.append(
            f"RACE: Selfish published. γ={gamma:.2f} → Selfish wins. "
            f"Honest block #{pid} orphaned."
        )
    else:
        state.public_chain.pop()
        race_blk.is_orphan = True
        state.orphaned_blocks.append(race_blk)
        state.selfish_orphan_count += 1
        state.public_chain.append(blk)
        state.honest_blocks_in_main += 1
        state.events.append(
            f"RACE: Selfish published. γ={gamma:.2f} → Honest wins. "
            f"Selfish block orphaned."
        )


def _honest_lead_two(state: SimState, blk: Block, pid: int) -> None:
    while state.private_chain:
        pb = state.private_chain.pop(0)
        pb.height = len(state.public_chain)
        state.public_chain.append(pb)
        state.selfish_blocks_in_main += 1
    state.selfish_lead = 0
    blk.is_orphan = True
    state.orphaned_blocks.append(blk)
    state.honest_orphan_count += 1
    state.events.append(
        f"Selfish publishes 2 blocks. Honest block #{pid} orphaned. Lead reset to 0."
    )


def _honest_lead_gt_two(state: SimState, blk: Block, pid: int) -> None:
    pub_blk = state.private_chain.pop(0)
    pub_blk.height = len(state.public_chain)
    state.public_chain.append(pub_blk)
    state.selfish_blocks_in_main += 1
    state.selfish_lead -= 1
    blk.is_orphan = True
    state.orphaned_blocks.append(blk)
    state.honest_orphan_count += 1
    state.events.append(
        f"Selfish releases 1 block. Honest block #{pid} orphaned. "
        f"Lead now = {state.selfish_lead}."
    )


def _honest_lead_negative(state: SimState, blk: Block) -> None:
    state.public_chain.append(blk)
    state.honest_blocks_in_main += 1
    state.selfish_lead = 0
    state.events.append("Honest block added (selfish reset).")


def _handle_honest_finds(state: SimState, gamma: float) -> None:
    pid = state.total_blocks_mined
    delta = state.selfish_lead
    state.total_blocks_mined += 1
    blk = Block(
        id=pid,
        block_type=BlockType.HONEST,
        height=len(state.public_chain),
        miner=Miner.HONEST.value,
    )

    if delta == 0:
        _honest_lead_zero(state, blk)
    elif delta == 1:
        _honest_lead_one_race(state, blk, pid, gamma)
    elif delta == 2:
        _honest_lead_two(state, blk, pid)
    elif delta > 2:
        _honest_lead_gt_two(state, blk, pid)
    else:
        _honest_lead_negative(state, blk)


def handle_event(state: SimState, event: MiningEvent, gamma: float) -> SimState:
    """
    Apply one step of the Eyal–Sirer state machine.

    Mutates ``state`` in place and returns the same object for convenient chaining.

    States are represented implicitly by ``state.selfish_lead`` (δ):
      δ = 0  → both chains equal length
      δ > 0  → selfish pool has a private lead of δ blocks
      δ < 0  → honest chain is ahead (selfish pool lost a race)
    """
    if event == MiningEvent.SELFISH_FINDS:
        _handle_selfish_finds(state)
    elif event == MiningEvent.HONEST_FINDS:
        _handle_honest_finds(state, gamma)
    state.round_num += 1
    return state


def run_simulation(
    alpha: float, gamma: float, n_rounds: int = 500
) -> Tuple[pd.DataFrame, SimState]:
    """Run full automated simulation; returns per-round statistics and final state."""
    state = SimState()
    records = []

    for _ in range(n_rounds):
        event = (
            MiningEvent.SELFISH_FINDS
            if random.random() < alpha
            else MiningEvent.HONEST_FINDS
        )
        state = handle_event(state, event, gamma)
        records.append(
            {
                "round": state.round_num,
                "selfish_lead": state.selfish_lead,
                "selfish_revenue": state.revenue_selfish(),
                "honest_revenue": state.revenue_honest(),
                "honest_orphans": state.honest_orphan_count,
                "selfish_orphans": state.selfish_orphan_count,
                "public_chain_len": len(state.public_chain),
            }
        )

    return pd.DataFrame(records), state
