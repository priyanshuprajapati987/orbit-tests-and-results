"""Regression tests: content-generation 'list' asks must reach the LLM.

E4 instruction_following root cause (fixed 2026-10-06): any message containing
"list" used to be swallowed by the shopping-list handler, so
"Give me a list of 3 programming languages" never reached the model.
Contract: generation asks -> None (fall through to LLM), list-management
ops -> dispatch a string. List state is mocked so tests never mutate the
real data/lists.json.
"""
from unittest.mock import patch

from orbit.orbit import assistant_handlers as ah
from orbit.orbit import lists as lists_mod


class TestListGenGate:
    def test_gen_ask_returns_none_e4_full(self):
        assert ah._handle_list(None, "Give me a list of 3 programming languages") is None

    def test_gen_ask_returns_none_variants(self):
        for msg in (
            "list of 5 European capitals",
            "Give me a list of examples of renewable energy",
            "tell me list of fruits",
            "what are list of design patterns",
            "Give me a list of top 3 sorting algorithms",
        ):
            assert ah._handle_list(None, msg) is None, msg

    def test_gen_ask_with_op_word_still_dispatches(self):
        with patch.object(lists_mod, "format_list", return_value="(mocked)"):
            out = ah._handle_list(None, "show list of items in shopping")
            assert isinstance(out, str) and out

    def test_tool_ask_add_dispatches(self):
        with patch.object(lists_mod, "add_items_from_text",
                          return_value=[{"text": "milk"}]) as m:
            out = ah._handle_list(None, "add milk to shopping list")
        assert isinstance(out, str) and "1 item" in out
        m.assert_called_once()

    def test_tool_ask_show_dispatches(self):
        with patch.object(lists_mod, "format_list", return_value="(mocked)"):
            out = ah._handle_list(None, "show my shopping list")
        assert isinstance(out, str) and "(mocked)" in out

    def test_tool_ask_delete_dispatches(self):
        with patch.object(lists_mod, "delete_list") as m:
            out = ah._handle_list(None, "delete shopping list")
        assert isinstance(out, str) and "delete" in out.lower()
        m.assert_called_once_with("shopping")

    def test_bare_list_falls_to_display_not_add(self):
        """Bare 'list' must not add anything — display fallback only."""
        with patch.object(lists_mod, "add_items_from_text") as add, \
                patch.object(lists_mod, "format_list", return_value="(mocked)"):
            out = ah._handle_list(None, "list")
        add.assert_not_called()
        assert isinstance(out, str)
