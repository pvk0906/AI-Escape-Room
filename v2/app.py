"""Version 2 UI.  Run from the repository root:  streamlit run v2/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from common.llm import LLMClient
from v2.pipeline import EscapeRoomGame

st.set_page_config(page_title="AI Escape Room - V2", page_icon="🗝️", layout="wide")
st.title("🗝️ The Locked Library — Version 2")
st.caption("Reliable edition: Python owns the rules and game state; the LLM only interprets your words and narrates the outcome.")


def new_session() -> None:
    st.session_state.game = EscapeRoomGame(LLMClient.from_env())
    st.session_state.messages = [{"role": "assistant", "text": st.session_state.game.intro, "debug": None}]


if "game" not in st.session_state:
    new_session()

game: EscapeRoomGame = st.session_state.game
engine, state = game.engine, game.state

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.subheader("Game")
    solved, total = engine.progress(state)
    st.progress(solved / total, text=f"Puzzles solved: {solved}/{total}")
    st.caption(f"Turn {state.turn}")

    st.markdown("**🎒 Inventory**")
    if state.inventory:
        for item_id in state.inventory:
            st.write(f"- {engine.name_of(item_id)}")
    else:
        st.write("_empty_")

    st.markdown("**🔎 Clues found**")
    if state.clues:
        for clue_id in state.clues:
            st.write(f"- {engine.clues[clue_id]['text']}")
    else:
        st.write("_none yet_")

    if st.button("🔄 Restart game", use_container_width=True):
        new_session()
        st.rerun()

    st.divider()
    show_debug = st.toggle("Show how my messages are processed", value=False)
    if game.llm is not None and game.llm.is_configured:
        st.caption(f"LLM: `{game.llm.description}`")
    else:
        st.info("No LLM configured - running in offline mode (rule-based parsing, template text). Set up `.env` to enable the AI Game Master.")
    st.markdown(
        "**How to play**\n- Examine objects\n- Pick things up\n- Use items on objects\n- Enter 4-digit codes\n- Ask for a *hint* if stuck"
    )

# --------------------------------------------------------------------- chat
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if show_debug and msg["debug"]:
            with st.expander("What happened behind the scenes"):
                st.json(msg["debug"])

if show_debug:
    with st.sidebar.expander("Full game state (JSON)"):
        st.json(state.to_dict())

if game.escaped:
    st.success("🎉 You escaped the library! Press Restart in the sidebar to play again.")

if prompt := st.chat_input("What do you do?", disabled=game.escaped):
    st.session_state.messages.append({"role": "user", "text": prompt, "debug": None})
    out = game.turn(prompt)
    debug = {
        "parsed_action": {k: v for k, v in vars(out.action).items() if v is not None},
        "parsed_by": out.parser_source,
        "engine_outcome": out.result.code,
        "action_succeeded": out.result.ok,
        "engine_facts": out.result.facts,
        "narrated_by": out.narration_source,
        "guard_reason": out.guard_reason,
    }
    st.session_state.messages.append({"role": "assistant", "text": out.narration, "debug": debug})
    st.rerun()
