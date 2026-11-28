from datetime import UTC, datetime, timedelta

from tronpy.keys import PrivateKey

from tronpay.book import Name, Signer, Wallet
from tronpay.journal import Event, Kind, Payment, PaymentId
from tronpay.network import NetworkName
from tronpay.pick import Funds, choose, paid_before
from tronpay.values import TokenAmount, TronAddress


def address(seed: int) -> TronAddress:
    return TronAddress(PrivateKey(seed.to_bytes(32, "big")).public_key.to_base58check_address())


MAIN = Wallet(Name("main"), address(1), Signer.KEYCHAIN)
SPARE = Wallet(Name("spare"), address(2), Signer.KEYCHAIN)
PHONE = Wallet(Name("phone"), address(3), Signer.EXTERNAL)
ALICE = address(10)
BOB = address(11)
T0 = datetime(2026, 11, 1, tzinfo=UTC)


def payment(
    sender: Wallet, recipient: TronAddress, day: int, last: Kind, network: NetworkName = NetworkName.MAINNET
) -> Payment:
    pid = PaymentId.new()
    at = T0 + timedelta(days=day)
    events = [Event(Kind.CONFIRMED, at, {}, pid)]
    if last is not Kind.CONFIRMED:
        events.append(Event(last, at, {}, pid))
    return Payment(pid, at, network, sender.name, sender.address, Name("alice"), recipient, TokenAmount(1), events)


def usdt(amount: int) -> Funds:
    return Funds(usdt=TokenAmount(amount), trx=TokenAmount(1))


def test_paid_before_is_most_recent_first_and_only_what_left_the_wallet() -> None:
    payments = [
        payment(MAIN, ALICE, 1, Kind.SENT),
        payment(PHONE, ALICE, 2, Kind.QR),
        payment(SPARE, ALICE, 3, Kind.CONFIRMED),  # cancelled half way: nothing left the wallet
        payment(SPARE, BOB, 4, Kind.SENT),  # another recipient
        payment(SPARE, ALICE, 5, Kind.SENT, NetworkName.NILE),  # another network
        payment(MAIN, ALICE, 6, Kind.BROADCAST),
    ]
    assert paid_before(payments, [MAIN, SPARE, PHONE], NetworkName.MAINNET, ALICE) == [MAIN, PHONE]


def test_paid_before_ignores_a_wallet_no_longer_in_the_book() -> None:
    assert paid_before([payment(SPARE, ALICE, 1, Kind.SENT)], [MAIN], NetworkName.MAINNET, ALICE) == []


def test_choose_takes_the_last_wallet_that_paid_and_holds_the_amount() -> None:
    funds = {MAIN: usdt(5), PHONE: usdt(100), SPARE: usdt(100)}
    choice = choose([MAIN, PHONE], [MAIN, SPARE, PHONE], ALICE, TokenAmount(50), funds.__getitem__)
    assert choice.chosen is not None and choice.chosen.wallet == PHONE
    assert [s.wallet for s in choice.skipped] == [MAIN]
    assert choice.options == []


def test_choose_offers_the_other_wallets_with_the_amount_when_the_history_has_none() -> None:
    funds = {
        MAIN: usdt(5),
        SPARE: usdt(100),
        PHONE: Funds(usdt=TokenAmount(100), trx=None),  # not activated
    }
    choice = choose([MAIN], [MAIN, SPARE, PHONE], ALICE, TokenAmount(50), funds.__getitem__)
    assert choice.chosen is None
    assert [s.wallet for s in choice.skipped] == [MAIN]
    assert [o.wallet for o in choice.options] == [SPARE]


def test_choose_never_offers_the_recipient_itself() -> None:
    funds = {MAIN: usdt(100), SPARE: usdt(100)}
    choice = choose([], [MAIN, SPARE], SPARE.address, TokenAmount(50), funds.__getitem__)
    assert [o.wallet for o in choice.options] == [MAIN]
