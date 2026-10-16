import pytest
from shouhu.config import UNIT
from shouhu.money import AmountError, fmt, to_units


def test_parse_and_format():
    assert to_units("20") == 20 * UNIT
    assert to_units(19.5) == 19_500_000
    assert to_units("1,000 USDC") == 1000 * UNIT
    assert fmt(20 * UNIT) == "20 tUSDC"
    assert fmt(19_500_000) == "19.50 tUSDC"


def test_rejects_bad_amounts():
    for bad in ("0", "-5", "abc", "", True, "0.0000001"):
        with pytest.raises(AmountError):
            to_units(bad)
