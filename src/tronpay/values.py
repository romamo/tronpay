from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import NewType

from tronpy.keys import is_base58check_address

Sun = NewType("Sun", int)
Energy = NewType("Energy", int)
Bandwidth = NewType("Bandwidth", int)

DECIMALS = 6
SUN_PER_TRX = 10**DECIMALS


@dataclass(frozen=True)
class TronAddress:
    value: str

    def __post_init__(self) -> None:
        if not is_base58check_address(self.value):
            raise ValueError(f"not a TRON address: {self.value!r}")

    def __str__(self) -> str:
        return self.value

    def looks_like(self, other: "TronAddress") -> bool:
        """Same first and last 4 characters but a different address: the address poisoning pattern"""
        a, b = self.value, other.value
        return a != b and a[:4] == b[:4] and a[-4:] == b[-4:]


@dataclass(frozen=True, order=True)
class TokenAmount:
    """An amount of a 6-decimal token (TRX or USDT), kept as integer base units"""

    units: int

    def __post_init__(self) -> None:
        if self.units < 0:
            raise ValueError(f"negative amount: {self.units}")

    @classmethod
    def parse(cls, text: str) -> "TokenAmount":
        try:
            value = Decimal(text)
        except InvalidOperation as e:
            raise ValueError(f"not a number: {text!r}") from e
        if not value.is_finite() or value <= 0:
            raise ValueError(f"amount must be positive: {text!r}")
        if value.as_tuple().exponent < -DECIMALS:
            raise ValueError(f"more than {DECIMALS} decimals: {text!r}")
        return cls(int(value * SUN_PER_TRX))

    @property
    def decimal(self) -> Decimal:
        return Decimal(self.units) / SUN_PER_TRX

    def __str__(self) -> str:
        return f"{self.decimal:,.6f}".rstrip("0").rstrip(".")
