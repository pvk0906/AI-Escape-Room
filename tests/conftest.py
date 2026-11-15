"""Shared test helpers: a scriptable fake LLM so the whole pipeline can be tested offline."""
import json

import pytest

from common.llm import LLMClient, LLMError
from v2.engine import load_config
from v2.intent import RuleIntentParser


def rules_as_llm_json(text: str) -> str:
    """Simulate a *well-behaved* LLM parser by serialising the rule parser's answer."""
    a = RuleIntentParser(load_config()).parse(text)
    return json.dumps(
        {"action": a.type, "target": a.target, "item": a.item, "code": a.code,
         "target_text": a.raw_target, "item_text": a.raw_item}
    )


class FakeLLM(LLMClient):
    """parser_reply / narrator_reply may be a string or a function(user_message) -> string."""

    def __init__(self, parser_reply=None, narrator_reply=None, fail=False):
        super().__init__("none")
        self.parser_reply = parser_reply or (lambda msg: rules_as_llm_json(msg.split('"""')[1]))
        self.narrator_reply = narrator_reply or (lambda msg: "Dust drifts through the lamplight as the room settles.")
        self.fail = fail
        self.calls = []  # (role, system, user_message)

    @property
    def is_configured(self):
        return True

    def generate(self, system, messages, **kwargs):
        role = "parser" if "intent classifier" in system else "narrator"
        self.calls.append((role, system, messages[-1].content))
        if self.fail:
            raise LLMError("simulated outage")
        reply = self.parser_reply if role == "parser" else self.narrator_reply
        return reply(messages[-1].content) if callable(reply) else reply


@pytest.fixture
def fake_llm():
    return FakeLLM()
