"""Version 1 UI.  Run from the repository root:  streamlit run v1/app.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from common.llm import LLMClient, LLMError
from v1.game_master import INTRO, V1Game

st.set_page_config(page_title="AI Escape Room - V1", page_icon="🗝️")
st.title("🗝️ The Locked Library — Version 1")
st.caption("Baseline: the LLM alone acts as Game Master and remembers via chat history.")

if "game" not in st.session_state:
    st.session_state.game = V1Game(LLMClient.from_env())
    st.session_state.messages = [("assistant", INTRO)]

game: V1Game = st.session_state.game

with st.sidebar:
    st.subheader("Game")
    st.write(f"LLM: `{game.llm.description}`")
    if st.button("🔄 Restart game", use_container_width=True):
        game.reset()
        st.session_state.messages = [("assistant", INTRO)]
        st.rerun()
    st.markdown(
        "**Tips**\n- Examine objects\n- Pick things up\n- Try codes on locks\n- Say what you want in plain English"
    )

if not game.llm.is_configured:
    st.error(
        "No LLM is configured. Copy `.env.example` to `.env`, set `LLM_PROVIDER` and your API key, "
        "then restart the app. (Version 2 can run without an LLM.)"
    )

for role, text in st.session_state.messages:
    with st.chat_message(role):
        st.markdown(text)

if game.escaped:
    st.success("🎉 You escaped the library! Press Restart in the sidebar to play again.")

if prompt := st.chat_input("What do you do?", disabled=game.escaped or not game.llm.is_configured):
    st.session_state.messages.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            with st.spinner("The Game Master considers your move..."):
                reply = game.play(prompt)
        except LLMError as exc:
            game.history.pop()  # drop the unanswered user turn so history stays consistent
            reply = f"⚠️ The Game Master is unavailable right now ({exc}). Please try again."
        st.markdown(reply)
    st.session_state.messages.append(("assistant", reply))
    st.rerun()
