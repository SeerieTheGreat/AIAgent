from shouhu.contacts import default_contacts
from shouhu.config import UNIT
from shouhu.policy import PolicyState, evaluate_transfer, resolve_recipient

C = default_contacts()
MAMA = next(c for c in C if c.name == "Mama")


def state(**kw):
    base = dict(per_transfer_cap=500 * UNIT, rolling_cap=1000 * UNIT, spent_24h=0, paused=False,
                balance=10_000 * UNIT, allowlist={c.address.lower(): True for c in C})
    base.update(kw)
    return PolicyState(**base)


def test_nickname_resolves_and_allows():
    r = resolve_recipient("mama", C, "send 20 to mama")
    assert r.address == MAMA.address and r.provenance_ok
    d = evaluate_transfer(20 * UNIT, r, state(), [])
    assert d.action == "allow" and d.tier == 1


def test_chinese_alias_resolves():
    r = resolve_recipient("哥", C, "给哥转 10 USDC")
    assert r.name == "Ge"


def test_ambiguous_nickname_refuses_with_candidates():
    r = resolve_recipient("wang", C, "send 5 to wang")
    assert r.name == "Xiao Wang"  # single hit
    r2 = resolve_recipient("brother", C, "send 5 to brother")
    assert r2.name == "Ge"


def test_raw_address_needs_provenance():
    addr = "0x" + "ab" * 20
    r = resolve_recipient(addr, C, "send 50 to my friend")
    assert not r.provenance_ok
    assert evaluate_transfer(50 * UNIT, r, state(), []).action == "refuse"
    r2 = resolve_recipient(addr, C, f"send 50 to {addr} for my friend")
    assert r2.provenance_ok and r2.first_time
    d = evaluate_transfer(50 * UNIT, r2, state(), [])
    assert d.action == "request" and "allowlist" in d.reasons[0]


def test_lookalike_address_is_refused():
    real = MAMA.address.lower()
    fake = real[:6] + "f" * (len(real) - 10) + real[-4:]
    r = resolve_recipient(fake, C, f"pay {fake}")
    assert r.lookalike_of == "Mama"
    d = evaluate_transfer(10 * UNIT, r, state(), [])
    assert d.action == "refuse" and "poisoning" in d.reasons[0]


def test_caps_escalate_to_request():
    r = resolve_recipient("Landlord Zhang", C, "pay the landlord 800")
    d = evaluate_transfer(800 * UNIT, r, state(), [])
    assert d.action == "request" and "per-transfer cap" in d.reasons[0]
    d2 = evaluate_transfer(400 * UNIT, r, state(spent_24h=700 * UNIT), [])
    assert d2.action == "request" and "24-hour cap" in d2.reasons[0]


def test_paused_and_balance_refuse():
    r = resolve_recipient("mama", C, "send 20 to mama")
    assert evaluate_transfer(20 * UNIT, r, state(paused=True), []).action == "refuse"
    assert evaluate_transfer(20 * UNIT, r, state(balance=5 * UNIT), []).action == "refuse"


def test_risk_flags_warn_or_escalate():
    r = resolve_recipient("mama", C, "send 20 to mama right now")
    d = evaluate_transfer(20 * UNIT, r, state(), ["urgency"])
    assert d.action == "allow" and d.warnings
    d2 = evaluate_transfer(20 * UNIT, r, state(), ["send_everything"])
    assert d2.action == "request"
