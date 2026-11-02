import pytest

from tronpay.values import TokenAmount, TronAddress

USDT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"


@pytest.mark.parametrize(
    ("text", "units"),
    [("100.20", 100_200_000), ("4.35", 4_350_000), ("0.000001", 1), ("1234.56", 1_234_560_000)],
)
def test_amount_is_exact(text: str, units: int) -> None:
    assert TokenAmount.parse(text).units == units


@pytest.mark.parametrize("text", ["0", "-1", "1.0000001", "abc", "nan", "inf"])
def test_amount_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        TokenAmount.parse(text)


def test_address_rejects_bad_checksum() -> None:
    with pytest.raises(ValueError):
        TronAddress(USDT[:-1] + "u")


def test_looks_like_flags_same_ends_only() -> None:
    a = TronAddress(USDT)
    assert not a.looks_like(a)
    assert not a.looks_like(TronAddress("TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"))
