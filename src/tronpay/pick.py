"""Choosing the sender when `send` is given only the recipient

The wallets that already paid this recipient come first, the most recent first: the first of them that holds
the amount pays. When none of them does, every other wallet that holds the amount is offered to choose from.
"""

from collections.abc import Callable
from dataclasses import dataclass

from tronpay.book import Wallet
from tronpay.journal import Kind, Payment
from tronpay.network import NetworkName
from tronpay.values import TokenAmount, TronAddress

# a payment that reached one of these left the wallet: it was broadcast, or its QR was shown to sign on the phone
PAID = {Kind.BROADCAST, Kind.SENT, Kind.QR}


@dataclass(frozen=True)
class Funds:
    usdt: TokenAmount
    trx: TokenAmount | None  # None: the account is not activated on chain

    def cover(self, amount: TokenAmount) -> bool:
        return self.trx is not None and self.usdt >= amount

    def __str__(self) -> str:
        trx = "not activated" if self.trx is None else f"{self.trx} TRX"
        return f"{self.usdt} USDT, {trx}"


@dataclass(frozen=True)
class Candidate:
    wallet: Wallet
    funds: Funds


@dataclass(frozen=True)
class Choice:
    """The wallet chosen from the history, or the wallets to choose from when the history has none that covers"""

    chosen: Candidate | None
    skipped: list[Candidate]  # wallets from the history that do not hold the amount, in the order they were tried
    options: list[Candidate]  # other wallets that hold the amount, when nothing was chosen


def paid_before(
    payments: list[Payment], wallets: list[Wallet], network: NetworkName, recipient: TronAddress
) -> list[Wallet]:
    """Wallets that paid this recipient on this network, the most recent payment first, each once"""
    by_address = {w.address: w for w in wallets}
    seen: list[Wallet] = []
    for p in reversed(payments):
        if p.network is not network or p.recipient_address != recipient:
            continue
        if not any(e.kind in PAID for e in p.events):
            continue
        wallet = by_address.get(p.sender_address)
        if wallet is not None and wallet not in seen:
            seen.append(wallet)
    return seen


def choose(
    history: list[Wallet],
    wallets: list[Wallet],
    recipient: TronAddress,
    amount: TokenAmount,
    funds_of: Callable[[Wallet], Funds],
) -> Choice:
    skipped = []
    for wallet in history:
        candidate = Candidate(wallet, funds_of(wallet))
        if candidate.funds.cover(amount):
            return Choice(candidate, skipped, [])
        skipped.append(candidate)
    rest = [w for w in wallets if w not in history and w.address != recipient]
    options = [c for c in (Candidate(w, funds_of(w)) for w in rest) if c.funds.cover(amount)]
    return Choice(None, skipped, options)
