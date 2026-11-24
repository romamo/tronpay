"""The payment history: an append-only JSON Lines file in TRONPAY_HOME, one event per line

A payment writes `confirmed` when you type yes, then `rented` (an ITRX order), `broadcast` (the txid, as soon as
the transaction is on the network) and `sent` (its receipt), or `qr` for a wallet whose key is on a phone.
A payment with no `sent` or `qr` stopped half way: its last event says how far it got.
Address book changes are written too, as `contact_added` and `contact_removed`.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from tronpay.book import Name
from tronpay.network import NetworkName
from tronpay.values import Energy, Sun, TokenAmount, TronAddress


class Kind(StrEnum):
    CONFIRMED = "confirmed"
    RENTED = "rented"
    BROADCAST = "broadcast"
    SENT = "sent"
    QR = "qr"
    CONTACT_ADDED = "contact_added"
    CONTACT_REMOVED = "contact_removed"


PAYMENT_KINDS = {Kind.CONFIRMED, Kind.RENTED, Kind.BROADCAST, Kind.SENT, Kind.QR}


@dataclass(frozen=True)
class PaymentId:
    value: str

    def __post_init__(self) -> None:
        if len(self.value) != 32 or any(c not in "0123456789abcdef" for c in self.value):
            raise ValueError(f"not a payment id: {self.value!r}")

    @classmethod
    def new(cls) -> "PaymentId":
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Event:
    kind: Kind
    at: datetime
    data: dict[str, Any]
    payment: PaymentId | None = None

    def __post_init__(self) -> None:
        if (self.payment is not None) != (self.kind in PAYMENT_KINDS):
            raise ValueError(f"a {self.kind} event {'needs' if self.kind in PAYMENT_KINDS else 'has no'} payment id")
        if self.at.tzinfo is None:
            raise ValueError("an event time needs a time zone")

    def to_json(self) -> str:
        record: dict[str, Any] = {"at": self.at.isoformat(), "kind": str(self.kind)}
        if self.payment is not None:
            record["payment"] = str(self.payment)
        record.update(self.data)
        return json.dumps(record, sort_keys=True)

    @classmethod
    def from_json(cls, line: str) -> "Event":
        record = json.loads(line)
        if not isinstance(record, dict):
            raise TypeError(f"not a history event: {line!r}")
        at = datetime.fromisoformat(record.pop("at"))
        kind = Kind(record.pop("kind"))
        payment = record.pop("payment", None)
        return cls(
            kind=kind,
            at=at,
            data=record,
            payment=None if payment is None else PaymentId(payment),
        )


@dataclass
class Payment:
    """A payment put together from its events"""

    id: PaymentId
    at: datetime
    network: NetworkName
    sender: Name
    sender_address: TronAddress
    recipient: Name
    recipient_address: TronAddress
    amount: TokenAmount
    events: list[Event] = field(default_factory=list)

    @property
    def last(self) -> Kind:
        return self.events[-1].kind

    @property
    def status(self) -> str:
        match self.last:
            case Kind.SENT:
                return "sent"
            case Kind.QR:
                return "QR shown, signed on the phone"
            case Kind.BROADCAST:
                return "broadcast, not confirmed"
            case kind:
                return f"stopped after {kind}"

    def value(self, kind: Kind, key: str) -> Any:
        for e in self.events:
            if e.kind is kind:
                return e.data[key]
        return None


class Journal:
    def __init__(self, root: Path) -> None:
        self.path = root / "history.jsonl"

    def write(self, event: Event) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(event.to_json() + "\n")
            f.flush()

    def events(self) -> list[Event]:
        if not self.path.exists():
            return []
        events = []
        for number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                events.append(Event.from_json(line))
            except (ValueError, KeyError, TypeError) as e:
                raise SystemExit(f"{self.path}:{number}: malformed history line: {e}") from e
        return events

    def payments(self) -> list[Payment]:
        """Payments in the order they were confirmed"""
        payments: dict[PaymentId, Payment] = {}
        for e in self.events():
            if e.payment is None:
                continue
            if e.kind is Kind.CONFIRMED:
                if e.payment in payments:
                    raise SystemExit(f"{self.path}: payment {e.payment} is confirmed twice")
                payments[e.payment] = Payment(
                    id=e.payment,
                    at=e.at,
                    network=NetworkName(e.data["network"]),
                    sender=Name(e.data["sender"]),
                    sender_address=TronAddress(e.data["sender_address"]),
                    recipient=Name(e.data["recipient"]),
                    recipient_address=TronAddress(e.data["recipient_address"]),
                    amount=TokenAmount(e.data["amount_units"]),
                    events=[e],
                )
            elif e.payment in payments:
                payments[e.payment].events.append(e)
            else:
                raise SystemExit(f"{self.path}: a {e.kind} event of payment {e.payment} before it was confirmed")
        return list(payments.values())


def now() -> datetime:
    return datetime.now(UTC)


def confirmed(
    payment: PaymentId,
    network: NetworkName,
    sender: Name,
    sender_address: TronAddress,
    recipient: Name,
    recipient_address: TronAddress,
    amount: TokenAmount,
    energy_needed: Energy,
    energy_lack: Energy,
    rent_price: Sun | None,
    burn_estimate: Sun,
) -> Event:
    return Event(
        Kind.CONFIRMED,
        now(),
        {
            "network": str(network),
            "sender": str(sender),
            "sender_address": str(sender_address),
            "recipient": str(recipient),
            "recipient_address": str(recipient_address),
            "amount_units": amount.units,
            "energy_needed": energy_needed,
            "energy_lack": energy_lack,
            "rent_price_sun": rent_price,
            "burn_estimate_sun": burn_estimate,
        },
        payment,
    )


def contact_event(kind: Kind, name: Name, address: TronAddress) -> Event:
    return Event(kind, now(), {"name": str(name), "address": str(address)})
