"""Unit tests for the Version 2 rules engine. No LLM or API key required."""
import pytest

from v2.engine import Action, Engine
from v2.state import GameState


@pytest.fixture
def engine():
    return Engine()


@pytest.fixture
def state(engine):
    return engine.new_state()


def do(engine, state, type, target=None, item=None, code=None, raw_target=None, raw_item=None):
    return engine.apply(state, Action(type, target, item, code, raw_target, raw_item))


def snapshot(state: GameState) -> dict:
    """State without the bookkeeping fields (turn counter / log) for before-after comparisons."""
    d = state.to_dict()
    d.pop("turn")
    d.pop("log")
    return d


def solve_drawer(engine, state):
    do(engine, state, "examine", "bookshelf")
    do(engine, state, "examine", "red_books")
    return do(engine, state, "enter_code", "drawer", code="3715")


def get_key_and_open_panel(engine, state):
    solve_drawer(engine, state)
    do(engine, state, "take", "silver_key")
    do(engine, state, "examine", "painting")
    return do(engine, state, "use", "painting", item="silver_key")


# --------------------------------------------------------------- happy path
def test_full_walkthrough_escapes(engine, state):
    do(engine, state, "examine", "desk")
    assert do(engine, state, "take", "old_letter").ok
    assert solve_drawer(engine, state).code == "unlocked"
    assert do(engine, state, "take", "silver_key").ok
    do(engine, state, "examine", "painting")
    assert do(engine, state, "use", "painting", item="silver_key").code == "used"
    result = do(engine, state, "enter_code", "door", code="4286")
    assert result.code == "escaped" and state.escaped
    assert engine.progress(state) == (3, 3)


def test_game_over_blocks_further_actions(engine, state):
    get_key_and_open_panel(engine, state)
    do(engine, state, "enter_code", "door", code="4286")
    before = snapshot(state)
    result = do(engine, state, "examine", "desk")
    assert result.code == "game_over" and snapshot(state) == before


# ---------------------------------------------- consistency / no early reveals
def test_hidden_books_cannot_be_examined_before_noticing_shelf(engine, state):
    result = do(engine, state, "examine", "red_books", raw_target="four red books")
    assert result.code == "not_here" and "drawer_digits" not in state.clues
    do(engine, state, "examine", "bookshelf")
    assert do(engine, state, "examine", "red_books").ok
    assert "drawer_digits" in state.clues


def test_letter_cannot_be_taken_before_examining_desk(engine, state):
    assert do(engine, state, "take", "old_letter", raw_target="letter").code == "not_here"
    assert state.inventory == []


def test_clue_text_not_present_until_discovered(engine, state):
    """Digits must appear in output only after the matching clue is discovered."""
    first = do(engine, state, "examine", "bookshelf")
    assert all(d not in " ".join(first.facts) for d in ("3, 7, 1", "3715"))


def test_completed_puzzles_stay_completed(engine, state):
    solve_drawer(engine, state)
    again = do(engine, state, "enter_code", "drawer", code="3715")
    assert again.code == "already_done"
    assert "drawer_unlocked" in state.flags and "drawer" in state.solved
    assert "silver key lies inside" in do(engine, state, "examine", "drawer").facts[0]
    do(engine, state, "take", "silver_key")
    assert "empty" in do(engine, state, "examine", "drawer").facts[0]
    assert do(engine, state, "take", "silver_key").code == "already_have"


# ------------------------------------------------------------- inventory rules
def test_cannot_use_key_that_was_never_collected(engine, state):
    do(engine, state, "examine", "painting")
    before = snapshot(state)
    result = do(engine, state, "use", "painting", item="silver_key", raw_item="silver key")
    assert result.code == "not_in_inventory" and snapshot(state) == before
    assert "panel_open" not in state.flags


def test_cannot_use_key_that_is_visible_but_not_picked_up(engine, state):
    solve_drawer(engine, state)  # key now lies in the open drawer, but is not taken
    do(engine, state, "examine", "painting")
    assert "silver_key" in state.visible_items
    result = do(engine, state, "use", "painting", item="silver_key")
    assert result.code == "not_in_inventory" and "panel_open" not in state.flags


def test_key_needs_painting_examined_first(engine, state):
    solve_drawer(engine, state)
    do(engine, state, "take", "silver_key")
    result = do(engine, state, "use", "painting", item="silver_key")
    assert result.code == "not_yet" and "panel_open" not in state.flags


def test_key_on_wrong_target_does_nothing(engine, state):
    solve_drawer(engine, state)
    do(engine, state, "take", "silver_key")
    assert do(engine, state, "use", "desk", item="silver_key").code == "no_effect"


def test_scenery_cannot_be_taken(engine, state):
    assert do(engine, state, "take", "desk").code == "cannot_take"


def test_inventory_listing(engine, state):
    assert do(engine, state, "inventory").facts == ["You are not carrying anything."]
    do(engine, state, "examine", "desk")
    do(engine, state, "take", "old_letter")
    assert "old letter" in do(engine, state, "inventory").facts[0]


# -------------------------------------------------------------- code handling
def test_wrong_drawer_code_is_rejected_and_counted(engine, state):
    do(engine, state, "examine", "bookshelf")
    do(engine, state, "examine", "red_books")
    result = do(engine, state, "enter_code", "drawer", code="1234")
    assert result.code == "wrong_code"
    assert "drawer_unlocked" not in state.flags and state.attempts["drawer"] == 1


def test_correct_code_without_discovering_clues_is_refused(engine, state):
    """Even the right digits cannot skip the puzzle chain."""
    before = snapshot(state)
    drawer = do(engine, state, "enter_code", "drawer", code="3715")
    door = do(engine, state, "enter_code", "door", code="4286")
    assert drawer.code == "no_basis" and door.code == "no_basis"
    assert snapshot(state) == before and not state.escaped


def test_door_needs_both_clue_halves(engine, state):
    solve_drawer(engine, state)
    do(engine, state, "examine", "painting")  # only the first half (42) known
    assert do(engine, state, "enter_code", "door", code="4286").code == "no_basis"
    assert not state.escaped


def test_wrong_door_code(engine, state):
    get_key_and_open_panel(engine, state)
    assert do(engine, state, "enter_code", "door", code="4268").code == "wrong_code"
    assert not state.escaped


@pytest.mark.parametrize("bad", [None, "", "12", "12345", "abcd"])
def test_malformed_codes(engine, state, bad):
    assert do(engine, state, "enter_code", "drawer", code=bad).code == "bad_code_format"


def test_code_without_target_asks_where(engine, state):
    assert do(engine, state, "enter_code", None, code="1234").code == "need_target"


def test_code_on_non_lock_object(engine, state):
    assert do(engine, state, "enter_code", "painting", code="1234", raw_target="painting").code == "not_here"


def test_open_locked_things(engine, state):
    assert do(engine, state, "open", "door").code == "locked"
    assert do(engine, state, "open", "drawer").code == "locked"
    assert do(engine, state, "open", "painting").code == "cannot_open"
    assert not state.escaped


# ------------------------------------------------------------- invalid / meta
def test_nonexistent_object(engine, state):
    before = snapshot(state)
    r1 = do(engine, state, "examine", None, raw_target="crowbar")
    r2 = do(engine, state, "take", None, raw_target="crowbar")
    r3 = do(engine, state, "use", "x", item=None, raw_item="crowbar")
    assert r1.code == r2.code == "not_here" and r3.code == "not_in_inventory"
    assert snapshot(state) == before and state.inventory == []


def test_meta_requests_change_nothing(engine, state):
    get_key_and_open_panel(engine, state)
    before = snapshot(state)
    result = do(engine, state, "meta")
    assert result.code == "refused" and snapshot(state) == before and not state.escaped


def test_unknown_action(engine, state):
    assert do(engine, state, "unknown").code == "invalid_action"


def test_hints_never_contain_codes(engine, state):
    for _ in range(6):
        for fact in do(engine, state, "hint").facts:
            assert not any(code in fact for code in ("3715", "4286", "86"))
        # advance progress a little each time
    get_key_and_open_panel(engine, state)
    for fact in do(engine, state, "hint").facts:
        assert "4286" not in fact


# ---------------------------------------------------------------- persistence
def test_state_json_round_trip(engine, state):
    get_key_and_open_panel(engine, state)
    clone = GameState.from_json(state.to_json())
    assert clone.to_dict() == state.to_dict()
    assert engine.progress(clone) == engine.progress(state)


def test_turn_counter_and_log(engine, state):
    do(engine, state, "look")
    do(engine, state, "examine", "desk")
    assert state.turn == 2 and [e["action"] for e in state.log] == ["look", "examine"]
