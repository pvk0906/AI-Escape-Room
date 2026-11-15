"""Version 1 - the LLM *is* the game.

Everything the game knows (room layout, secrets, solution, rules) lives in one
system prompt. The only "state" is the chat history that is re-sent on every
turn. This is deliberately simple: it is the baseline that Version 2 improves.
"""
from __future__ import annotations

from common.llm import LLMClient, Message

ESCAPE_MARKER = "[ESCAPED]"

INTRO = (
    "You wake up on a cold stone floor, head pounding. You are locked inside an old library. "
    "Dust hangs in the lamplight. You can make out a **desk**, a **bookshelf**, a **painting**, "
    "a small **locked drawer** and a heavy **door** with a four-digit keypad.\n\n"
    "**How to play:** type what you want to do in plain English, e.g. *\"examine the bookshelf\"*, "
    "*\"pick up the letter\"* or *\"try 1234 on the drawer\"*. Look closely at everything, collect "
    "useful items, solve the puzzles and find the code that opens the door."
)

SYSTEM_PROMPT = f"""You are the Game Master of a text-based escape room called "The Locked Library".
The player is locked in a library and must escape. Stay in character, be atmospheric, and keep every
reply to 2-4 sentences. Address the player as "you".

=== THE ROOM (secret - reveal details ONLY when the player investigates them) ===
- DESK: dusty oak desk. Under the inkwell lies an old LETTER. The letter says: "The books remember what
  I forgot. When you find the key, remember the painting watches over what is hidden. The way out is the
  plate first, then what the frame hides."
- BOOKSHELF: rows of dusty books, but FOUR RED BOOKS on the middle shelf stick out at different depths.
  Inside the front cover of each red book is a handwritten digit. Left to right the digits are 3, 7, 1, 5.
- DRAWER: small drawer with a four-digit dial lock. The correct code is 3715. Inside is a SILVER KEY.
- PAINTING: a storm-tossed lighthouse. A brass plaque reads "Plate 42". There is a tiny keyhole in the
  lower edge of the frame. Turning the SILVER KEY in it opens a hidden panel containing a slip of paper
  with the digits 86.
- DOOR: heavy oak door with a four-digit keypad. The correct code is 4286 (the plaque number 42 followed
  by the hidden panel's 86).

=== RULES ===
1. Only describe what the player examines. Never reveal the codes, the solution or later puzzle steps early.
2. The player can only use items they have actually picked up. The silver key is in the locked drawer.
3. Remember everything the player has done so far in this conversation and stay consistent.
4. If the player enters a wrong code, say it does not work. Do not hint at which digits are right.
5. When (and only when) the player enters 4286 on the door, describe their escape and end that reply
   with the exact marker {ESCAPE_MARKER}
"""


class V1Game:
    """Holds the chat history and talks to the LLM. No other state is tracked."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.history: list[Message] = []
        self.escaped = False
        self.reset()

    def reset(self) -> None:
        self.escaped = False
        # Gemini expects the conversation to start with a user turn.
        self.history = [
            Message("user", "I am ready to begin."),
            Message("assistant", INTRO),
        ]

    def play(self, player_text: str) -> str:
        """Send the player's message and return the Game Master's reply."""
        if self.escaped:
            return "You have already escaped! Press **Restart** to play again."
        self.history.append(Message("user", player_text))
        reply = self.llm.generate(SYSTEM_PROMPT, self.history, temperature=0.8)
        if ESCAPE_MARKER in reply:
            self.escaped = True
            reply = reply.replace(ESCAPE_MARKER, "").strip()
        self.history.append(Message("assistant", reply))
        return reply
