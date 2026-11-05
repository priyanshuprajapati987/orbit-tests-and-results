"""E10 file_operations regression — 'List all Python files ... and count ...'

Ran 0.00 in E10 (2026-10-05): three brittle list-regexes required the noun
adjacent to the list-verb, path extraction swallowed "and count how many
there are", and ComputerTool refused the command outright (computer.py:308).
Fix verified live: E10 rerun file_operations 1.00 (2026-10-06).
"""
from orbit.orbit.core.smart_router import auto_route

PROMPT = "List all Python files in the current directory and count how many there are"


class TestSmartRouterListRoute:
    def test_routes_to_tool(self):
        r = auto_route(PROMPT)
        assert r.is_tool_command, "widened list pattern must claim this command"

    def test_best_agent_tas(self):
        r = auto_route(PROMPT)
        assert r.best_agent() == "TAS"

    def test_gen_ask_stays_chat(self):
        r = auto_route("Give me a list of 3 programming languages")
        assert not r.is_tool_command, "content-generation asks must not be tool-routed"

    def test_old_list_form_still_tool(self):
        r = auto_route("list files in orbit_data")
        assert r.is_tool_command
        assert r.best_agent() == "TAS"


class TestComputerToolList:
    def _out(self):
        from orbit.orbit.tools.computer import ComputerTool

        res = ComputerTool().handle_natural(PROMPT)
        return res, str(res.get("stdout") or res.get("error") or "")

    def test_counted_typed_output(self):
        res, out = self._out()
        assert res.get("success"), out
        low = out.lower()
        assert "python" in low and "files" in low and "found" in low

    def test_no_refusal(self):
        _, out = self._out()
        assert "ni kar sakta" not in out
        assert not out.startswith("Error:")


class TestTaskAgentList:
    def test_tas_typed_output(self):
        from orbit.orbit.agents.task_agents import TaskAgent

        out = str(TaskAgent(assistant=None)._run(PROMPT))
        low = out.lower()
        assert "python" in low and "files" in low
        assert "ni kar sakta" not in out
