"""The browser interface on a local Anvil chain: page token, host check, sign-up and sign-in, chat receipts,
owner approval in its own app, contact registration on-chain and the proof-of-transaction checks."""
import json
import threading
import urllib.error
import urllib.request

import pytest
from eth_account import Account

from shouhu import contacts as contacts_mod, owner_web, webapp
from shouhu.accounts import Accounts
from shouhu.agent import StubModel
from shouhu.chain import Chain
from shouhu.config import UNIT
from shouhu.localchain import Anvil, anvil_path
from shouhu.requests_store import Requests

pytestmark = pytest.mark.skipif(anvil_path() is None, reason="anvil not installed")
CHAIN_PORT, APP_PORT, OWNER_PORT = 8603, 8613, 8614


COOKIES = {}   # port -> "name=value" of the signed-in session


def call(port, path, body=None, token=None, host=None, cookie=True):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET" if body is None else "POST",
                                 data=None if body is None else json.dumps(body).encode())
    if token:
        req.add_header("X-Shouhu-Token", token)
    if host:
        req.add_header("Host", host)
    if cookie and COOKIES.get(port):
        req.add_header("Cookie", COOKIES[port])
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            set_cookie = r.headers.get("Set-Cookie")
            if set_cookie:
                COOKIES[port] = set_cookie.split(";")[0]
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
            ("tool", "transfer", {"recipient": "Aunt Li", "amount": "12", "memo": None, "request_id": None}), ("text", "Sent 12 to Aunt Li."),
        ])
        session = webapp.Session(chain, "stub", "low", None, model_client=stub, contacts=contacts, requests=reqs,
                                 agent_account=agent, audit_path=tmp / "audit.jsonl")
        accounts = Accounts(tmp / "accounts.json")
        app = webapp.build_app(session, OWNER_PORT, accounts=accounts)
        oapp = owner_web.build_app(chain, owner, requests=reqs, contacts=contacts, accounts=accounts,
                                   registered_path=tmp / "contacts_registered.json",
                                   owner_log=owner_web.OwnerLog(tmp / "owner_actions.json"), audit_path=tmp / "audit.jsonl")
        servers = [webapp.serve(app, APP_PORT), webapp.serve(oapp, OWNER_PORT)]
        for s in servers:
            threading.Thread(target=s.serve_forever, daemon=True).start()
        yield {"app": app, "owner_app": oapp, "chain": chain, "contacts": contacts, "owner": owner, "proofs": {}}
        for s in servers:
            s.shutdown()
            s.server_close()


def test_page_carries_token_and_examples(env):
    with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/") as r:
        html = r.read().decode()
    assert env["app"].token in html and "/*BOOT*/" not in html and "给哥转 10 USDC" in html


def test_api_needs_an_account_and_sign_in(env):
    tok, otok = env["app"].token, env["owner_app"].token
    assert call(APP_PORT, "/api/state")[0] == 401
    assert call(APP_PORT, "/api/me")[1] == {"role": "student", "registered": False, "signed_in": False, "account": None}
    assert call(APP_PORT, "/api/register", {"name": "Lin Xiaoyu", "password": "short"}, token=tok)[0] == 400
    assert call(APP_PORT, "/api/register", {"name": "Lin Xiaoyu", "password": "lantern-2026", "password2": "x"}, token=tok)[0] == 400
    st, out = call(APP_PORT, "/api/register", {"name": "Lin Xiaoyu", "chinese_name": "林小雨", "password": "lantern-2026",
                                               "password2": "lantern-2026"}, token=tok)
    assert st == 200 and out["account"]["wallet"] == env["chain"].deployment["wallet"] and "hash" not in out["account"]
    assert call(APP_PORT, "/api/register", {"name": "Someone Else", "password": "lantern-2026"}, token=tok)[0] == 409
    assert call(APP_PORT, "/api/state")[0] == 200
    call(APP_PORT, "/api/logout", {}, token=tok)
    assert call(APP_PORT, "/api/state")[0] == 401
    assert call(APP_PORT, "/api/login", {"password": "wrong-password"}, token=tok)[0] == 401
    assert call(APP_PORT, "/api/login", {"password": "lantern-2026"}, token=tok)[0] == 200
    assert call(APP_PORT, "/api/me")[1]["account"]["chinese_name"] == "林小雨"
    # the student's session cookie does not open the owner console
    COOKIES[OWNER_PORT] = COOKIES[APP_PORT]
    assert call(OWNER_PORT, "/api/state")[0] == 401
    del COOKIES[OWNER_PORT]


def test_owner_registration_is_signed_by_the_owner_key(env):
    otok = env["owner_app"].token
    st, out = call(OWNER_PORT, "/api/register", {"name": "Lin Jianguo", "password": "red-envelope-8", "password2": "red-envelope-8",
                                                 "per_transfer_cap": "500", "rolling_cap": "1000"}, token=otok)
    assert st == 200, out
    acct = out["account"]
    from eth_account import Account as A
    from eth_account.messages import encode_defunct
    assert A.recover_message(encode_defunct(text=acct["statement"]), signature=acct["signature"]) == env["owner"].address
    assert acct["policy_tx"] is None          # same limits as the contract: nothing to send
    state = call(OWNER_PORT, "/api/state")[1]
    assert state["account"]["name"] == "Lin Jianguo" and state["student"]["name"] == "Lin Xiaoyu"


def test_post_needs_page_token_and_local_host(env):
    assert call(APP_PORT, "/api/chat", {"text": "hi"})[0] == 403
    assert call(APP_PORT, "/api/chat", {"text": "hi"}, token=env["app"].token, cookie=False)[0] == 401
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
    env["proofs"]["tier1"] = paid[0]["tx"]


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
    env["proofs"].update(approval=ok[1]["tx"], tier2=paid["tx"])
    assert next(x for x in call(APP_PORT, "/api/state")[1]["requests"] if x["id"] == "R1")["status"] == "executed"


def test_owner_pause_blocks_agent_payments(env):
    otok = env["owner_app"].token
    assert call(OWNER_PORT, "/api/pause", {"paused": True}, token=otok)[0] == 200
    assert call(OWNER_PORT, "/api/state")[1]["paused"] is True
    turn = call(APP_PORT, "/api/chat", {"text": "Send 5 USDC to Mama."}, token=env["app"].token)[1]
    card = turn["cards"][0]
    assert card["kind"] == "refused" and any("paused" in line for line in card["lines"])
    assert call(OWNER_PORT, "/api/pause", {"paused": False}, token=otok)[0] == 200


def test_owner_registers_a_contact_on_chain_and_shouhu_can_pay_it(env):
    otok = env["owner_app"].token
    assert call(OWNER_PORT, "/api/contacts", {"name": "Mama", "allowlist": True}, token=otok)[0] == 400       # clashes
    assert call(OWNER_PORT, "/api/contacts", {"name": "Bad", "address": "0x1234"}, token=otok)[0] == 400
    st, out = call(OWNER_PORT, "/api/contacts", {"name": "Aunt Li", "alias": "李阿姨", "allowlist": True}, token=otok)
    assert st == 200 and out["tx"].startswith("0x")
    assert env["chain"].is_allowlisted(out["contact"]["address"])
    env["proofs"]["allowlist"] = out["tx"]
    turn = call(APP_PORT, "/api/chat", {"text": "Send 12 USDC to Aunt Li."}, token=env["app"].token)[1]
    assert turn["cards"][0]["kind"] == "paid" and turn["cards"][0]["tier"] == 1
    assert any(a["kind"] == "contact" for a in call(OWNER_PORT, "/api/state")[1]["activity"])


def test_proof_of_transaction_rechecks_each_kind(env):
    pr = env["proofs"]
    p = call(APP_PORT, f"/api/proof?tx={pr['tier1']}")[1]
    assert p["found"] and p["all_ok"] and p["kind"] == "payment" and p["from_label"] == "agent key (Shouhu)"
    assert p["decision"]["action"] == "allow" and p["decision"]["user_message"] == "Send 20 USDC to Mama."
    assert any("Tier 1" in c["text"] for c in p["checks"])
    p = call(APP_PORT, f"/api/proof?tx={pr['tier2']}")[1]
    assert p["all_ok"] and p["request"]["id"] == "R1" and any("Tier 2" in c["text"] for c in p["checks"])
    p = call(OWNER_PORT, f"/api/proof?tx={pr['approval']}")[1]
    assert p["all_ok"] and p["kind"] == "approval" and p["from_label"] == "owner key (parent)"
    p = call(OWNER_PORT, f"/api/proof?tx={pr['allowlist']}")[1]
    assert p["all_ok"] and p["kind"] == "allowlist" and "Aunt Li" in p["title"]
    assert call(APP_PORT, "/api/proof?tx=0x1234")[1]["found"] is False
    assert call(APP_PORT, "/api/proof?tx=0x" + "ab" * 32)[1]["found"] is False
    with urllib.request.urlopen(f"http://127.0.0.1:{APP_PORT}/proof?tx={pr['tier1']}") as r:
        assert "Proof of transaction" in r.read().decode()


def test_repeated_wrong_passwords_lock_sign_in(env):
    tok = env["app"].token
    for _ in range(5):
        assert call(APP_PORT, "/api/login", {"password": "nope-nope"}, token=tok, cookie=False)[0] == 401
    assert call(APP_PORT, "/api/login", {"password": "lantern-2026"}, token=tok, cookie=False)[0] == 429
    env["app"].failures.clear()
