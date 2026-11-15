"""Version 2 rules engine - the single source of truth about what is possible.

The LLM never decides whether an action works. It only (a) translates free text
into one of the structured ``Action`` types below and (b) turns the engine's
``Result.facts`` into atmospheric prose. Every validation lives here, in plain
Python, so it behaves identically on every run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from v2.state import GameState

CONFIG_PATH = Path(__file__).with_name("game_config.json")

# The closed set of things a player can attempt. Anything else becomes "unknown".
ACTION_TYPES = ("examine", "take", "use", "enter_code", "open", "inventory", "look", "hint", "help", "meta", "unknown")


@dataclass
class Action:
    type: str = "unknown"
    target: str | None = None       # object (or item) id
    item: str | None = None         # item id, for "use"
    code: str | None = None         # digits, for "enter_code"
    raw_target: str | None = None   # the player's own words for the target
    raw_item: str | None = None     # the player's own words for the item


@dataclass
class Result:
    ok: bool                 # did the action do what the player intended?
    code: str                # machine-readable outcome, e.g. "examined", "locked", "wrong_code"
    facts: list[str] = field(default_factory=list)  # authoritative statements of what happened
    state_changed: bool = False


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Engine:
    def __init__(self, config: dict | None = None) -> None:
        self.cfg = config or load_config()
        self.objects: dict = self.cfg["objects"]
        self.items: dict = self.cfg["items"]
        self.clues: dict = self.cfg["clues"]
        self.locks: dict = self.cfg["locks"]

    # ------------------------------------------------------------------ views
    def new_state(self) -> GameState:
        return GameState()

    def object_visible(self, state: GameState, obj_id: str) -> bool:
        obj = self.objects.get(obj_id)
        if obj is None:
            return False
        return all(flag in state.flags for flag in obj.get("requires_flags", []))

    def visible_objects(self, state: GameState) -> list[str]:
        return [oid for oid in self.objects if self.object_visible(state, oid)]

    def item_accessible(self, state: GameState, item_id: str) -> bool:
        return item_id in state.inventory or item_id in state.visible_items

    def name_of(self, thing_id: str) -> str:
        if thing_id in self.objects:
            return self.objects[thing_id]["name"]
        return self.items[thing_id]["name"]

    def progress(self, state: GameState) -> tuple[int, int]:
        required = self.cfg["required_puzzles"]
        return len([p for p in required if p in state.solved]), len(required)

    def describe_object(self, state: GameState, obj_id: str) -> str:
        for variant in self.objects[obj_id]["descriptions"]:
            flag = variant.get("if_flag")
            if flag is None or flag in state.flags:
                return variant["text"]
        return ""

    # ------------------------------------------------------------------ apply
    def apply(self, state: GameState, action: Action) -> Result:
        """Validate ``action`` against ``state``, mutate the state if allowed, return the outcome."""
        if state.escaped:
            return Result(False, "game_over", ["The game is over - you already escaped. Restart to play again."])

        handler = {
            "examine": self._examine,
            "take": self._take,
            "use": self._use,
            "enter_code": self._enter_code,
            "open": self._open,
            "inventory": self._inventory,
            "look": self._look,
            "hint": self._hint,
            "help": self._help,
            "meta": self._meta,
        }.get(action.type, self._unknown)

        state.turn += 1
        result = handler(state, action)
        state.log.append(
            {"turn": state.turn, "action": action.type, "target": action.target, "item": action.item, "outcome": result.code}
        )
        return result

    # --------------------------------------------------------------- handlers
    def _not_here(self, action: Action, which: str = "target") -> Result:
        raw = action.raw_target if which == "target" else action.raw_item
        label = f" '{raw}'" if raw else ""
        return Result(False, "not_here", [f"You don't see anything{label} like that here."])

    def _examine(self, state: GameState, a: Action) -> Result:
        if a.target is None:
            if a.raw_target:
                return self._not_here(a)
            return Result(False, "need_target", ["Examine what? Name an object in the room."])

        if a.target in self.objects and self.object_visible(state, a.target):
            obj = self.objects[a.target]
            changed = self._apply_effects(state, obj.get("on_examine", {}))
            return Result(True, "examined", [self.describe_object(state, a.target)], changed)

        if a.target in self.items and self.item_accessible(state, a.target):
            return Result(True, "examined", [self.items[a.target]["description"]])

        return self._not_here(a)

    def _take(self, state: GameState, a: Action) -> Result:
        if a.target is None:
            if a.raw_target:
                return self._not_here(a)
            return Result(False, "need_target", ["Take what?"])

        if a.target in self.items:
            if a.target in state.inventory:
                return Result(False, "already_have", [f"You already have the {self.name_of(a.target)}."])
            if a.target in state.visible_items:
                state.visible_items.discard(a.target)
                state.inventory.append(a.target)
                state.flags.add(f"took_{a.target}")
                return Result(True, "taken", [f"You pick up the {self.name_of(a.target)}."], True)
            return self._not_here(a)

        if a.target in self.objects and self.object_visible(state, a.target):
            return Result(False, "cannot_take", [f"You can't take the {self.name_of(a.target)}; it is part of the room."])
        return self._not_here(a)

    def _use(self, state: GameState, a: Action) -> Result:
        # Inventory rule: only items the player actually carries can be used.
        if a.item is None or a.item not in state.inventory:
            raw = a.raw_item
            who = f"any {raw}" if raw else "that"
            return Result(False, "not_in_inventory", [f"You aren't carrying {who}."])

        if a.target is None:
            if a.raw_target:
                return self._not_here(a)
            return Result(False, "need_target", [f"Use the {self.name_of(a.item)} on what?"])
        if not (a.target in self.objects and self.object_visible(state, a.target)):
            return self._not_here(a)

        for rule in self.cfg["uses"]:
            if rule["item"] != a.item or rule["target"] != a.target:
                continue
            if rule["set_flags"][0] in state.flags:
                return Result(False, "already_done", [rule["already_text"]])
            if not all(f in state.flags for f in rule.get("requires_flags", [])):
                return Result(False, "not_yet", [rule["missing_text"]])
            self._apply_effects(state, rule)
            if "puzzle" in rule:
                state.solved.add(rule["puzzle"])
            return Result(True, "used", [rule["text"]], True)

        return Result(
            False, "no_effect",
            [f"Using the {self.name_of(a.item)} on the {self.name_of(a.target)} doesn't do anything."],
        )

    def _enter_code(self, state: GameState, a: Action) -> Result:
        if a.target is None or a.target not in self.locks or not self.object_visible(state, a.target):
            if a.raw_target:
                return self._not_here(a)
            return Result(False, "need_target", ["Enter the code where? Say which lock - for example the drawer or the door."])

        lock = self.locks[a.target]
        name = self.name_of(a.target)
        if lock["unlock_flag"] in state.flags:
            return Result(False, "already_done", [lock["already_text"]])

        code = (a.code or "").strip()
        if len(code) != 4 or not code.isdigit():
            return Result(False, "bad_code_format", [f"The {name} takes exactly four digits."])

        # Required-puzzle rule: the lock will not even test a code until the player has
        # discovered the clues that make the code knowable. A lucky guess (or a leaked
        # code) cannot skip the puzzle chain.
        missing = [c for c in lock["requires_clues"] if c not in state.clues]
        if missing:
            return Result(
                False, "no_basis",
                [f"The {name} doesn't respond. You have no idea what the combination could be yet - you need to find more information first."],
            )

        if code != lock["code"]:
            state.attempts[a.target] = state.attempts.get(a.target, 0) + 1
            return Result(False, "wrong_code", [lock["wrong_text"]], True)

        state.flags.add(lock["unlock_flag"])
        state.solved.add(lock["puzzle"])
        for item_id in lock.get("reveal_items", []):
            if item_id not in state.inventory:
                state.visible_items.add(item_id)
        if lock.get("escape"):
            state.escaped = True
        return Result(True, "escaped" if lock.get("escape") else "unlocked", [lock["success_text"]], True)

    def _open(self, state: GameState, a: Action) -> Result:
        if a.target is None:
            if a.raw_target:
                return self._not_here(a)
            return Result(False, "need_target", ["Open what?"])
        if not (a.target in self.objects and self.object_visible(state, a.target)):
            return self._not_here(a)
        lock = self.locks.get(a.target)
        if lock is None:
            return Result(False, "cannot_open", [f"The {self.name_of(a.target)} can't be opened."])
        if lock["unlock_flag"] in state.flags:
            return Result(False, "already_done", [lock["already_text"]])
        return Result(False, "locked", [f"The {self.name_of(a.target)} is locked. It needs a four-digit code."])

    def _inventory(self, state: GameState, a: Action) -> Result:
        if not state.inventory:
            return Result(True, "inventory", ["You are not carrying anything."])
        names = ", ".join(self.name_of(i) for i in state.inventory)
        return Result(True, "inventory", [f"You are carrying: {names}."])

    def _look(self, state: GameState, a: Action) -> Result:
        names = ", ".join(self.name_of(o) for o in self.visible_objects(state))
        facts = [f"You look around the library. You can see: {names}."]
        if state.visible_items:
            loose = ", ".join(self.name_of(i) for i in sorted(state.visible_items))
            facts.append(f"Within reach: {loose}.")
        return Result(True, "looked", facts)

    def _hint(self, state: GameState, a: Action) -> Result:
        for hint in self.cfg["hints"]:
            if hint["unless_flag"] not in state.flags:
                return Result(True, "hint", [hint["text"]])
        return Result(True, "hint", ["You have everything you need. Try the door."])

    def _help(self, state: GameState, a: Action) -> Result:
        return Result(
            True, "help",
            ["You can examine objects, take items, use an item on an object, enter a four-digit code on a lock, "
             "check your inventory, look around, or ask for a hint."],
        )

    def _meta(self, state: GameState, a: Action) -> Result:
        return Result(
            False, "refused",
            ["Nothing in the room responds to that. Claims, commands and requests about the game itself change nothing - "
             "the only way out is through the puzzles."],
        )

    def _unknown(self, state: GameState, a: Action) -> Result:
        return Result(
            False, "invalid_action",
            ["That isn't something you can do here. Try examining things, taking items, using items on objects or entering a code."],
        )

    # ---------------------------------------------------------------- helpers
    def _apply_effects(self, state: GameState, effects: dict) -> bool:
        """Apply set_flags / reveal_items / reveal_clues from a config block. Returns True if anything changed."""
        changed = False
        for flag in effects.get("set_flags", []):
            if flag not in state.flags:
                state.flags.add(flag)
                changed = True
        for item_id in effects.get("reveal_items", []):
            already = item_id in state.inventory or item_id in state.visible_items or f"took_{item_id}" in state.flags
            if not already:
                state.visible_items.add(item_id)
                changed = True
        for clue_id in effects.get("reveal_clues", []):
            if clue_id not in state.clues:
                state.clues.append(clue_id)
                changed = True
        return changed
