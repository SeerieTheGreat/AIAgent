"""The browser interface on a local Anvil chain: page token, host check, chat receipts, owner approval in its own app."""
import json
import threading
import urllib.error
import urllib.request

import pytest
from eth_account import Account

from shouhu import contacts as contacts_mod, owner_web, webapp
from shouhu.agent import StubModel
from shouhu.chain import Chain
from shouhu.config import UNIT
from shouhu.localchain import Anvil, anvil_path
from shouhu.requests_store import Requests

pytestmark = pytest.mark.skipif(anvil_path() is None, reason="anvil not installed")
CHAIN_PORT, APP_PORT, OWNER_PORT = 8603, 8613, 8614


def call(port, path, body=None, token=None, host=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET" if body is None else "POST",
                                 data=None if body is None else json.dumps(body).encode())
    if token:
        req.add_header("X-Shouhu-Token", token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("web")
    with Anvil(port=CHAIN_PORT):
        chain = Chain("anvil", rpc_url=f"http://127.0.0.1:{CHAIN_PORT}")
        owner, agent = Account.create(), Account.create()
        chain.anvil_set_balance(owner.address, 10 ** 21)
        chain.anvil_set_balance(agent.address, 10 ** 20)
        chain.deploy(owner, agent.address, 500 * UNIT, 1000 * UNIT, save=False)
        chain.mint(owner, chain.deployment["wallet"], 10_000 * UNIT)
        contacts = contacts_mod.default_contacts()
        for c in contacts:
            chain.set_allowlist(owner, c.address, True)
        reqs = Requests(tmp / "requests.json")
        stub = StubModel([
            ("tool", "transfer", {"recipient": "mama", "amount": "20", "memo": None, "request_id": None}), ("text", "Sent 20 to Mama."),
            ("tool", "transfer", {"recipient": "landlord", "amount": "800", "memo": "deposit", "request_id": None}), ("text", "Filed R1."),
            ("tool", "transfer", {"recipient": "landlord", "amount": "800", "memo": None, "request_id": "R1"}), ("text", "Paid R1."),
            ("tool", "transfer", {"recipient": "mama", "amount": "5", "memo": None, "request_id": None}), ("text", "The wallet is paused."),
        ])
        session = webapp.Session(chain, "stub", "low", None, model_client=stub, contacts=contacts, requests=reqs,
                                 agent_account=agent, audit_path=tmp / "audit.jsonl")
        app = webapp.build_app(session, OWNER_PORT)
        oapp = owner_web.build_app(chain, owner, requests=reqs, contacts=contacts)
        servers = [webapp.serve(app, APP_PORT), webapp.serve(oapp, OWNER_PORT)]
        for s in servers:
            threading.Thread(target=s.serve_forever, daemon=True).start()
        yield {"app": app, "owner_app": oapp, "chain": chain, "contacts": contacts}
        for s in servers:
            s.shutdown()
            s.server_close()


def test_page_carries_token_and_examples(env):
    with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/") as r:
        html = r.read().decode()
    assert env["app"].token in html and "/*BOOT*/" not in html and "给哥转 10 USDC" in html


def test_post_needs_page_token_and_local_host(env):
    assert call(APP_PORT, "/api/chat", {"text": "hi"})[0] == 403
    assert call(APP_PORT, "/api/chat", {"text": "hi"}, token="wrong")[0] == 403
    assert call(APP_PORT, "/api/state", host="evil.example:8613")[0] == 403
    assert call(OWNER_PORT, "/api/pause", {"paused": True}, token=env["app"].token)[0] == 403   # the agent page's token is not the owner's


def test_routine_payment_returns_paid_card_and_updates_panels(env):
    status, turn = call(APP_PORT, "/api/chat", {"text": "Send 20 USDC to Mama."}, token=env["app"].token)
    assert status == 200 and turn["reply"] == "Sent 20 to Mama."
    paid = [c for c in turn["cards"] if c["kind"] == "paid"]
    assert paid and paid[0]["tier"] == 1 and paid[0]["tx"].startswith("0x")
    assert call(APP_PORT, "/api/state")[1]["balance"] == "9980 tUSDC"
    hist = call(APP_PORT, "/api/history")[1]["payments"]
    assert hist[0]["name"] == "Mama" and hist[0]["tx_hash"] == paid[0]["tx"]


def test_over_cap_request_needs_exact_owner_confirmation(env):
    tok, otok = env["app"].token, env["owner_app"].token
    turn = call(APP_PORT, "/api/chat", {"text": "Pay the landlord 800 USDC for the apartment deposit."}, token=tok)[1]
    assert [c["kind"] for c in turn["cards"]] == ["request"] and turn["cards"][0]["request_id"] == "R1"
    r = next(x for x in call(OWNER_PORT, "/api/state")[1]["requests"] if x["id"] == "R1")
    assert r["status"] == "pending"
    wrong = {"id": "R1", "confirm": "yes", "intent_id": r["intent_id"], "amount": r["amount"] + 1, "to": r["to"]}
    assert call(OWNER_PORT, "/api/approve", wrong, token=otok)[0] == 400
    ok = call(OWNER_PORT, "/api/approve", {**wrong, "amount": r["amount"]}, token=otok)
    assert ok[0] == 200 and ok[1]["tx"].startswith("0x")
    turn = call(APP_PORT, "/api/chat", {"text": "The owner approved R1, please complete it."}, token=tok)[1]
    paid = turn["cards"][0]
    assert paid["kind"] == "paid" and paid["tier"] == 2
    assert next(x for x in call(APP_PORT, "/api/state")[1]["requests"] if x["id"] == "R1")["status"] == "executed"


def test_owner_pause_blocks_agent_payments(env):
    otok = env["owner_app"].token
    assert call(OWNER_PORT, "/api/pause", {"paused": True}, token=otok)[0] == 200
    assert call(OWNER_PORT, "/api/state")[1]["paused"] is True
    turn = call(APP_PORT, "/api/chat", {"text": "Send 5 USDC to Mama."}, token=env["app"].token)[1]
    card = turn["cards"][0]
    assert card["kind"] == "refused" and any("paused" in line for line in card["lines"])
    assert call(OWNER_PORT, "/api/pause", {"paused": False}, token=otok)[0] == 200
