"""Version 2 turn pipeline:  text -> Action -> validated Result -> narration.

    player text --(IntentParser: LLM or rules)--> Action
                --(Engine.apply: Python rules)--> Result + updated GameState
                --(Narrator: LLM or template)---> text shown to the player
"""
from __future__ import annotations

from dataclasses import dataclass

from common.llm import LLMClient
from v2.engine import Action, Engine, Result, load_config
from v2.intent import IntentParser
from v2.narrator import Narrator


@dataclass
class TurnOutput:
    narration: str
    action: Action
    result: Result
    parser_source: str            # "llm" | "rules"
    narration_source: str         # "llm" | "template" | "template (guard)"
    guard_reason: str | None = None


class EscapeRoomGame:
    def __init__(self, llm: LLMClient | None = None, config: dict | None = None) -> None:
        self.config = config or load_config()
        self.llm = llm
        self.engine = Engine(self.config)
        self.parser = IntentParser(llm, self.config)
        self.narrator = Narrator(llm)
        self.state = self.engine.new_state()

    @property
    def intro(self) -> str:
        return self.config["intro"]

    @property
    def escaped(self) -> bool:
        return self.state.escaped

    def reset(self) -> None:
        self.state = self.engine.new_state()

    def turn(self, player_text: str) -> TurnOutput:
        action, parser_source = self.parser.parse(player_text)
        result = self.engine.apply(self.state, action)
        objects = [self.engine.name_of(o) for o in self.engine.visible_objects(self.state)]
        inventory = [self.engine.name_of(i) for i in self.state.inventory]
        narration, narration_source, reason = self.narrator.narrate(action, result, objects, inventory)
        return TurnOutput(narration, action, result, parser_source, narration_source, reason)
