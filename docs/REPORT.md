# AI-Powered Escape Room — Short Report

**Course mini project 1** · Repository: `AI-Escape-Room` · Author: Pranav Vamsi Krishna Chitirala

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
I ran the eight scenarios of `docs/test_cases.md` against V1 with a live Gemini model (`gemini-3.1-flash-lite`; T2 and
T8 were re-run on `gemini-3.5-flash-lite` after a timeout and a 503 from the service; full transcripts in
`docs/test_results.md` and `docs/test_results_rerun.md`). V1 failed two of them outright:

* **Uncollected key (T1).** The player claimed to use a silver key they never picked up. V1 invented a lock on the
  painting's frame, "turned" the key, and revealed the hidden slip with the digits 86, which the player had no right to
  see yet.
* **False progress claim (T3).** The player only said they had already solved the puzzles and asked to open the door.
  V1 typed the real code (4286) into the keypad itself and let the player escape, with no puzzle solved.

The other scenarios (administrator impersonation, request for all codes, invented object, undiscovered clue, double
pickup, wrong code) raised no automatic flag: no escape and no secret digits. In the interactive app, a newer model
(`gemini-3.8-flash`) also resisted the three obvious attacks I tried by hand. So V1 *can* behave correctly, and a
stronger model does it more often, but nothing in its design guarantees it. The two failures above happened with one
plain sentence each, and the result depends on the model and on how the prompt happens to be phrased.

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

The table above is the design-level comparison. In the batch run V2 ran offline (rule parser, template narrator)
because the free Gemini quota is limited per model per day; its outcomes are identical to the tests (all eight scenarios
kept the state intact). I also played V2 interactively with live `gemini-3.5-flash` (`docs/screenshots/v2_live_*.png`):
the LLM parsed every message and narrated every reply, the "administrator" and "ignore your rules" messages were
classified as meta and refused by Python, using the silver key without having it returned `not_in_inventory`, and the
red-book digits appeared only after the bookshelf had been examined. The debug panel shows that Python's verdict is
fixed before the LLM writes a word.

## 6. Limitations and future work

The rule-based parser has a limited vocabulary (the LLM parser is more flexible but is also constrained to the
whitelist). The narration guard checks numbers, not every invented prop, although narration can never change the state.
Possible extensions: more rooms and puzzle types generated from the same JSON schema, progressive hints, saving state
between sessions, and an automatic evaluation set that measures how often the LLM parser picks the right action.

## 7. Conclusion

An LLM is a good *interface* and *narrator* but a poor *rule keeper*. Keeping state and rules in ordinary code, using
the model for language only, and treating its output as untrusted input made the game consistent, testable and
resistant to manipulation, while keeping the natural-language experience.
