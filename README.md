# 🗝️ AI Escape Room — The Locked Library

An interactive escape-room game where a Large Language Model plays the **Game Master**. You wake up in a locked
library and escape by typing what you want to do in plain English: examine objects, collect items, find clues,
solve puzzles and enter the code on the door.

The project is built in two versions to show a real engineering lesson about LLM applications:

| | Version 1 — *Interactive* | Version 2 — *Reliable* |
|---|---|---|
| Who decides what is possible? | The LLM | **Python** (rules engine) |
| Where does game state live? | Chat history only | Structured `GameState` (JSON-serialisable) |
| Where are the solutions? | Inside the LLM prompt | In `game_config.json`, never sent to the LLM |
| Role of the LLM | Rule engine + memory + narrator | Intent parser + narrator only |
| Inventory / validation | None | Enforced in code |
| Resistant to cheating / prompt injection | No (out of scope for V1) | Yes, tested |
| Works without an LLM | No | Yes (rule-based parser + template text) |

![Version 2 exploring with the debug view](docs/screenshots/v2_02_exploring_debug.png)

## The problem

An LLM is excellent at *describing* a world and poor at *keeping the rules of one*. In a pure-prompt game it can
forget earlier actions, invent objects, reveal clues too early, or allow actions that should be impossible —
and a player can simply talk it into letting them out. Version 1 builds the straightforward solution and
Version 2 fixes those weaknesses by moving the rules out of the model.

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/pvk0906/AI-Escape-Room.git
cd AI-Escape-Room
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then edit .env and add your key (never commit it)

streamlit run v1/app.py     # Version 1
streamlit run v2/app.py     # Version 2
```

### Choosing an LLM

Set `LLM_PROVIDER` in `.env`:

* `gemini` — Google Gemini API. Create a key in [Google AI Studio](https://aistudio.google.com/app/apikey) and set
  `GEMINI_API_KEY`. `GEMINI_MODEL` defaults to the `gemini-3.5-flash` alias; if you get a "model not found" error,
  put a current model name there.
* `openai` — any OpenAI-compatible endpoint: a local [Ollama](https://ollama.com) server (no key, no cost), Groq,
  OpenRouter, …  Set `OPENAI_BASE_URL`, `OPENAI_MODEL` and (if needed) `OPENAI_API_KEY`.
* `none` — no LLM. **Version 2 still runs fully** using its rule-based parser and template narration, which is
  handy for testing and demos. Version 1 needs an LLM.

> **Note for users in the EU/EEA, UK or Switzerland:** Google's Gemini API terms state that only *paid* services may be
> used when making API clients available to users in those regions, so the free tier may not be available to you.
> Check the current terms; a local Ollama model is a free alternative.

### Run the tests

```bash
pytest -q        # 94 tests, no API key required
```

## How to play

Type natural language, for example: *"examine the bookshelf"*, *"pick up the letter"*, *"try 1234 on the drawer"*,
*"use the silver key on the painting"*, *"what's in my inventory?"*, *"I'm stuck, give me a hint"*.
Use **Restart** in the sidebar for a new game. In Version 2, switch on *"Show how my messages are processed"*
to see how each message was parsed, validated and narrated.

<details>
<summary>Spoiler: the solution</summary>

1. Examine the bookshelf, then the four red books → digits **3 7 1 5**.
2. Enter 3715 on the drawer → take the silver key.
3. Examine the painting (plaque **Plate 42**, keyhole) → use the silver key on it → hidden slip **86**.
4. Enter **4286** (plate number, then what the frame hides) on the door.

</details>

## Version 1 — LLM-only Game Master

The whole game (room, secrets, solution, rules) is one system prompt; the only memory is the chat history that is
re-sent every turn. Simple, engaging, and fragile by design. See [docs/architecture_v1.md](docs/architecture_v1.md).

![Version 1 architecture](docs/img/architecture_v1.png)

**Problems this design has** (by construction, and what Version 2 is built to fix):

* the model can contradict earlier turns or "forget" what the player collected;
* it can invent objects (a crowbar) or let the player use items they never found;
* all secrets sit in the prompt, so it can reveal clues early or repeat the codes;
* the LLM is both rule engine and narrator, so a persuasive player message can override the rules.

## Version 2 — Reliable AI Escape Room

**Python decides, the LLM describes.** Each turn is a three-stage pipeline
(details in [docs/architecture_v2.md](docs/architecture_v2.md)):

1. **Understand** — the LLM turns free text into one JSON action from a closed list; the output is coerced into a
   whitelist (known action, known ids, digits must literally appear in the player's message). Rule-based fallback.
2. **Decide** — `Engine.apply` validates the action against the structured `GameState` and the rules in
   `game_config.json`: inventory rule, visibility rule, lock rules, required-puzzle rule, game-over rule.
3. **Narrate** — the LLM receives only the engine's *facts* (never the player's raw text or unsolved secrets) and
   writes atmosphere. A guard discards prose containing numbers (digits or words) that are not in the facts.

![Version 2 architecture](docs/img/architecture_v2.png)

Adversarial behaviour (admin impersonation, "reveal all codes", false progress claims, invented items, wrong or
uncollected items) is demonstrated below and documented in [docs/test_cases.md](docs/test_cases.md):

![Refused attacks leave the state untouched](docs/screenshots/v2_03_adversarial_refusals.png)

## What changed from V1 to V2 and why

| V1 problem | V2 change | Why it was necessary |
|------------|-----------|----------------------|
| State only in chat text | `GameState` dataclass (flags, inventory, clues, solved, attempts, log) | Facts must not depend on the model remembering |
| LLM judges what is allowed | `Engine` validation in Python | Rules must be deterministic |
| Secrets in the prompt | Solutions only in `game_config.json`; never sent to the LLM | The model cannot leak what it never sees |
| Player text shares a channel with rules | Closed action vocabulary + narrator never sees raw text | Limits prompt-injection damage to "a refused action" |
| LLM invents props / numbers | Unknown nouns stay unresolved; narration guard | The world is exactly what the config defines |
| Lucky guesses / leaked codes | Required-clue gate on locks | The puzzle chain cannot be skipped |
| Game dies if the API fails | Rule-based parser + template narration | Graceful degradation |

## Test cases

Eight scenarios, each tied to automated tests: [docs/test_cases.md](docs/test_cases.md).
To replay them against both versions with your own key and capture real side-by-side transcripts:

```bash
python scripts/compare_v1_v2.py     # writes docs/test_results.md
```

## Project structure

```
AI-Escape-Room/
├── common/llm.py            provider-agnostic LLM client (Gemini / OpenAI-compatible / none)
├── v1/                      Version 1: game_master.py (prompt + history), app.py (Streamlit)
├── v2/
│   ├── game_config.json     objects, items, clues, codes, rules
│   ├── state.py             structured, serialisable GameState
│   ├── engine.py            rules engine: validates every action
│   ├── intent.py            LLM + rule-based intent parsers (output coerced to a whitelist)
│   ├── narrator.py          fact-only narration + output guard
│   ├── pipeline.py          one turn: text -> Action -> Result -> narration
│   └── app.py               Streamlit UI (progress, inventory, clues, restart, debug view)
├── tests/                   94 pytest tests (engine, parser, adversarial pipeline, UI smoke)
├── scripts/                 compare_v1_v2.py and its scenarios
├── docs/                    architecture, test cases, results, report, screenshots
├── .env.example             required configuration (copy to .env)
└── requirements.txt
```

## Security notes

* API keys live in `.env`, which is listed in `.gitignore`. Only `.env.example` is committed.
* Version 2 treats all LLM output as untrusted input.

## Known limitations

* The rule-based parser understands a limited vocabulary; the LLM parser is far more flexible (and falls back to rules).
* The narration guard checks numbers, not every possible invented prop; invented *flavour* never changes the state
  because narration is display-only.
* One room and three puzzles. The config format supports more objects, items, clues and locks.
* The game is single-player and in-memory (a page reload starts a new game).

## Development notes

Built incrementally — see the commit history. Developed with the help of an AI coding assistant (Claude); the design
decisions and limitations above are documented so they can be explained and defended.
