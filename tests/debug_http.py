import os
import sys

sys.path.insert(0, "D:/JARVES/orbit")

# Test 1: Direct function call
from orbit.core.chat_api import _try_tool_execution

msg2 = "Create orbit_data/test_nl2.txt containing test content"
result, tool = _try_tool_execution(msg2)
print(f"Direct: result={str(result)[:100]}, tool={tool}")

# Test 2: Via AGENT_REGISTRY
from orbit.agents.base import BaseAgent

from orbit.agents import AGENT_REGISTRY

agent_cls = AGENT_REGISTRY.get("TAS")
if agent_cls and issubclass(agent_cls, BaseAgent):
    agent = agent_cls()
    result2 = agent.execute(msg2)
    print(f"Agent: {str(result2)[:100]}")

# Test 3: SmartRouter step by step
from orbit.core.smart_router import auto_route

route = auto_route(msg2)
print(
    f"Router: is_tool={route.is_tool_command}, agent={route.best_agent()}, intent={route.intent}"
)

# Test 4: TaskAgent._run directly
from orbit.agents.task_agents import TaskAgent

ta = TaskAgent()
result3 = ta._run(msg2)
print(f"TaskAgent._run: {str(result3)[:100]}")

# Check file
print(f"File exists: {os.path.exists('D:/JARVES/orbit_data/test_nl2.txt')}")
