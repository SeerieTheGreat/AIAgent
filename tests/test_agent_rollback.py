"""A turn that fails mid-tool-call must leave the conversation valid for the next turn."""
from types import SimpleNamespace

import pytest

from shouhu.agent import ShouhuAgent, StubModel


class FlakyChain:
    name = "anvil"

    def wallet_state(self):
        raise RuntimeError("rate limited")      # an endpoint error that is not a ChainError


class NullAudit:
    def log(self, event, **data):
        return {}


def test_failed_turn_is_rolled_back():
    ctx = SimpleNamespace(chain=FlakyChain(), contacts=[], audit=NullAudit(), requests=None, agent_account=None,
                          user_message="", risk=[])
    agent = ShouhuAgent(StubModel([("tool", "get_portfolio", {}), ("text", "Hello again.")]), ctx)
    with pytest.raises(RuntimeError):
        agent.chat("What's in my wallet?")
    assert agent.messages == []
    assert agent.chat("hi") == "Hello again."
    assert [m["role"] for m in agent.messages] == ["user", "assistant"]
