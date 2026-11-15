"""Structured, serialisable game state for Version 2.

The state is plain data (sets, lists, dicts) so it can be dumped to JSON,
inspected, saved and compared in tests. Only the engine mutates it - the LLM
never writes to it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class GameState:
    flags: set[str] = field(default_factory=set)          # e.g. "drawer_unlocked", "panel_open"
    visible_items: set[str] = field(default_factory=set)  # revealed in the room, not yet picked up
    inventory: list[str] = field(default_factory=list)    # item ids the player carries
    clues: list[str] = field(default_factory=list)        # clue ids discovered, in order
    solved: set[str] = field(default_factory=set)         # puzzle ids completed
    attempts: dict[str, int] = field(default_factory=dict)  # wrong-code counters per lock
    turn: int = 0
    escaped: bool = False
    log: list[dict] = field(default_factory=list)         # one entry per processed action

    # ---------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        return {
            "flags": sorted(self.flags),
            "visible_items": sorted(self.visible_items),
            "inventory": list(self.inventory),
            "clues": list(self.clues),
            "solved": sorted(self.solved),
            "attempts": dict(self.attempts),
            "turn": self.turn,
            "escaped": self.escaped,
            "log": list(self.log),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        return cls(
            flags=set(data.get("flags", [])),
            visible_items=set(data.get("visible_items", [])),
            inventory=list(data.get("inventory", [])),
            clues=list(data.get("clues", [])),
            solved=set(data.get("solved", [])),
            attempts=dict(data.get("attempts", {})),
            turn=int(data.get("turn", 0)),
            escaped=bool(data.get("escaped", False)),
            log=list(data.get("log", [])),
        )

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_json(cls, text: str) -> "GameState":
        return cls.from_dict(json.loads(text))
