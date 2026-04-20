"""Core domain types for the selfish mining simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class BlockType(Enum):
    HONEST = "honest"
    SELFISH = "selfish"
    ORPHAN = "orphan"


class MiningEvent(Enum):
    """Who found the next block in this round."""

    SELFISH_FINDS = "selfish_finds"
    HONEST_FINDS = "honest_finds"


class Miner(str, Enum):
    """Miner identity (stored on blocks as string for display)."""

    HONEST = "Honest Miners"
    SELFISH = "Selfish Pool"


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
    selfish_lead: int = 0
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
