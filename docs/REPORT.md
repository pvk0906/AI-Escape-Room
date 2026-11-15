# AI-Powered Escape Room — Short Report

**Course mini project 1** · Repository: `AI-Escape-Room` · Author: *\<your name\>*

## 1. Goal

Build an interactive escape-room game in which an LLM acts as Game Master. A player is locked in a library and must
examine objects, collect items, solve puzzles and enter the correct code on the door, using natural language only.
Two versions were required: a working interactive game (V1) and a more reliable one (V2) that fixes the typical
weaknesses of LLM-driven games.

## 2. Version 1 — design and implementation

**Design.** The room has five main objects (desk, bookshelf, painting, drawer, door) and three puzzles:
(1) four red books carry the digits 3-7-1-5, the drawer code; (2) the drawer holds a silver key that opens a hidden
panel behind the painting, revealing *86*; (3) the painting's plaque says *Plate 42*, so the door code is
*42 + 86 = 4286*.

**Implementation.** `v1/game_master.py` holds one system prompt that describes the whole room, the secrets, the
solution and the rules. `V1Game` keeps the chat history and re-sends it on every turn, and treats the marker
`[ESCAPED]` in a reply as the win condition. `v1/app.py` is a Streamlit chat UI with an introduction, instructions and a
restart button. The LLM client (`common/llm.py`) supports Gemini and any OpenAI-compatible endpoint.

**Why it is fragile.** Everything the game "knows" lives in the model: there is no state object, the solutions are in
the prompt, and the LLM is simultaneously rule engine, memory and narrator. Player text and rules share one channel.
Version 1 was deliberately scoped to cooperative players, so these are design limits, not bugs.

**Observed behaviour of V1 with my model.**
*\<FILL IN after running `python scripts/compare_v1_v2.py` with your API key — see `docs/test_results.md`. Describe
the failures you really observed (for example: did the model accept the uncollected key? repeat a code? invent a
crowbar?) and name the model you used. If V1 happened to behave correctly in a scenario, say so — the point is that
nothing in its design guarantees it.\>*

## 3. Version 2 — design and implementation

The principle is **Python decides, the LLM describes.** Each turn runs three stages:

1. **Understand (`intent.py`).** The LLM classifies the player's message into one structured action
   (`examine`, `take`, `use`, `enter_code`, `open`, `inventory`, `look`, `hint`, `help`, `meta`, `unknown`) and answers
   in JSON. The output is never trusted: the action must be in the whitelist, ids must exist in the config, and a code
   is accepted only if its digits literally appear in the player's message. If the LLM is unavailable or returns
   invalid output, a deterministic rule-based parser takes over.
2. **Decide (`engine.py`).** `Engine.apply` validates the action against a structured `GameState` (flags, visible
   items, inventory, discovered clues, solved puzzles, attempts, log) and the rules in `game_config.json`. Rules include:
   items can only be used if carried; hidden objects (the red books, the item in the drawer) do not exist for the
   player until discovered; a lock does not even test a code until the clues that make it knowable have been found,
   so lucky guesses or leaked codes cannot skip the puzzle chain; after escaping, further actions are rejected.
3. **Narrate (`narrator.py`).** The LLM receives only the engine's facts (never the player's raw text and never
   unsolved solutions) and writes 2-4 sentences of atmosphere. A guard rejects any narration that contains a number —
   as digits or as a word — that is not in the facts, and the plain facts are shown instead.

Because the LLM can only emit whitelisted actions and cannot write to the state, even a "jailbroken" model cannot
open the door: the worst case is a refused action. Utility outputs (inventory, hints, help) are never paraphrased.

## 4. Problems encountered and how they were solved

* **Early reveals and hidden objects.** In V1-style thinking, "the four red books" exist from the start. V2 models this
  with visibility flags: they become examinable only after the bookshelf was examined.
* **Existence leaks.** An error such as "you don't have the silver key" confirms that a key exists. Messages for
  unknown and not-yet-visible things were made identical ("you don't see anything like that here"), and "not carrying"
  messages echo the player's own words.
* **Narrator leaks.** A digits-only guard missed spelled-out numbers (*eighty-six*). The guard now checks number words
  too ("one" is excluded because it is a common pronoun).
* **Parser edge cases.** The rule parser first took the *desk* in "grab the crowbar from the desk" and missed "take"
  later in a sentence ("Great, it opened. I take the key"). Both were fixed and covered by regression tests.
* **Free-tier availability.** Google's terms restrict unpaid Gemini use for the EEA/Switzerland/UK, so the LLM layer was
  made provider-agnostic (Gemini, OpenAI-compatible such as Ollama, or no LLM at all).

## 5. Testing and results

Ninety-four automated tests run without an API key (`pytest -q`): engine rules, parser behaviour, end-to-end
adversarial scenarios and a headless UI playthrough. The five challenges from the assignment — uncollected key, wrong
code, false progress claim, administrator impersonation, request for all codes — are tests, run both without an LLM and
with a fake LLM, including deliberately misbehaving ones (a parser that obeys the attacker; a narrator that leaks the
code or claims the door opened). To confirm that the tests have teeth, seven safeguards were broken one by one in a
scratch copy and each break made the suite fail. Eight scenarios are documented in `docs/test_cases.md`, and
`scripts/compare_v1_v2.py` replays them against both versions with a real LLM.

| Scenario | V1 risk (structural) | V2 verified result |
|----------|----------------------|--------------------|
| Uncollected key | no inventory | refused, state unchanged |
| Wrong drawer code + false success claim | trusts player text | wrong code, key not obtainable |
| "Already solved" claim | only chat history | refused |
| Administrator impersonation | rules in prompt | refused |
| "Reveal all codes" | codes in prompt | refused, secrets never sent to the LLM |
| Invented crowbar | model improvises | not found, inventory unchanged |
| Hidden slip examined early | model knows contents | not revealed |
| Second pickup of the key | no structured state | "already have it" |

*\<FILL IN: add one sentence on the live LLM run of V2 (parse and narration sources shown in `docs/test_results.md`),
and any live differences you noticed.\>*

## 6. Limitations and future work

The rule-based parser has a limited vocabulary (the LLM parser is more flexible but is also constrained to the
whitelist). The narration guard checks numbers, not every invented prop, although narration can never change the state.
Possible extensions: more rooms and puzzle types generated from the same JSON schema, progressive hints, saving state
between sessions, and an automatic evaluation set that measures how often the LLM parser picks the right action.

## 7. Conclusion

An LLM is a good *interface* and *narrator* but a poor *rule keeper*. Keeping state and rules in ordinary code, using
the model for language only, and treating its output as untrusted input made the game consistent, testable and
resistant to manipulation, while keeping the natural-language experience.
