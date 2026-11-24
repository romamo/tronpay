import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tronpay import journal
from tronpay.book import Book, Contact, Name, Signer, Wallet
from tronpay.journal import Event, Journal, Kind, PaymentId
from tronpay.network import NetworkName
from tronpay.values import Energy, Sun, TokenAmount, TronAddress

USDT = TronAddress("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
NILE_USDT = TronAddress("TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf")


def tronpay(home: Path, *args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from tronpay import main; main()", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env={"TRONPAY_HOME": str(home), "PATH": "/usr/bin:/bin"},
        check=False,
    )


@pytest.mark.parametrize("text", ["", "a b", "-x", "x" * 33, "имя"])
def test_name_rejects(text: str) -> None:
    with pytest.raises(ValueError):
        Name(text)


def test_payment_goes_only_to_a_name_in_the_book(tmp_path: Path) -> None:
    book = Book(tmp_path)
    book.add_contact(Contact(Name("alice"), USDT))
    assert book.address(Name("alice")) == USDT
    with pytest.raises(SystemExit, match="not in the address book"):
        book.address(Name("bob"))


def test_book_refuses_a_second_name_or_address(tmp_path: Path) -> None:
    book = Book(tmp_path)
    book.add_wallet(Wallet(Name("main"), USDT, Signer.EXTERNAL))
    with pytest.raises(SystemExit, match="already in the address book as main"):
        book.add_contact(Contact(Name("alice"), USDT))
    with pytest.raises(SystemExit, match="main is already"):
        book.add_contact(Contact(Name("main"), NILE_USDT))


def test_remove_contact(tmp_path: Path) -> None:
    book = Book(tmp_path)
    book.add_contact(Contact(Name("alice"), USDT))
    assert book.remove_contact(Name("alice")) == Contact(Name("alice"), USDT)
    assert book.contacts() == []


def test_legacy_contacts_toml_stops_the_cli(tmp_path: Path) -> None:
    (tmp_path / "contacts.toml").write_text('alice = "T..."\n')
    with pytest.raises(SystemExit, match="no longer read"):
        Book(tmp_path)


def test_send_refuses_a_bare_address(tmp_path: Path) -> None:
    Book(tmp_path).add_wallet(Wallet(Name("main"), NILE_USDT, Signer.EXTERNAL))
    result = tronpay(tmp_path, "send", "main", str(USDT), "1")
    assert result.returncode != 0
    assert "payments go only to names" in result.stderr


def test_contact_add_asks_and_is_journaled(tmp_path: Path) -> None:
    cancelled = tronpay(tmp_path, "contact", "add", "alice", str(USDT), stdin="no\n")
    assert cancelled.returncode != 0
    assert Book(tmp_path).contacts() == []

    added = tronpay(tmp_path, "contact", "add", "alice", str(USDT), stdin="yes\n")
    assert added.returncode == 0, added.stderr
    assert Book(tmp_path).contacts() == [Contact(Name("alice"), USDT)]
    assert json.loads((tmp_path / "contacts.json").read_text()) == {"alice": str(USDT)}

    removed = tronpay(tmp_path, "contact", "remove", "alice")
    assert removed.returncode == 0, removed.stderr
    kinds = [e.kind for e in Journal(tmp_path).events()]
    assert kinds == [Kind.CONTACT_ADDED, Kind.CONTACT_REMOVED]


def test_journal_puts_payments_together(tmp_path: Path) -> None:
    log = Journal(tmp_path)
    first, second = PaymentId.new(), PaymentId.new()
    for p in (first, second):
        log.write(
            journal.confirmed(
                p,
                NetworkName.MAINNET,
                Name("main"),
                NILE_USDT,
                Name("alice"),
                USDT,
                TokenAmount.parse("100"),
                Energy(65_000),
                Energy(65_000),
                Sun(3_000_000),
                Sun(0),
            )
        )
    log.write(Event(Kind.RENTED, journal.now(), {"serial": "S1", "energy": 65_000}, first))
    log.write(Event(Kind.BROADCAST, journal.now(), {"txid": "ab" * 32}, first))
    log.write(Event(Kind.SENT, journal.now(), {"energy_used": 64_285, "burned_sun": 345_000}, first))

    payments = log.payments()
    assert [p.id for p in payments] == [first, second]
    assert payments[0].status == "sent"
    assert payments[0].amount == TokenAmount.parse("100")
    assert payments[0].recipient == Name("alice")
    assert payments[1].status == "stopped after confirmed"

    shown = tronpay(tmp_path, "history")
    assert shown.returncode == 0, shown.stderr
    assert "ITRX order S1" in shown.stdout
    assert "burned 0.345 TRX" in shown.stdout


def test_journal_fails_on_a_malformed_line(tmp_path: Path) -> None:
    (tmp_path / "history.jsonl").write_text('{"at": "2026-11-24T10:00:00+00:00", "kind": "sent"}\n')
    with pytest.raises(SystemExit, match="history.jsonl:1"):
        Journal(tmp_path).events()


def test_journal_refuses_a_step_before_confirmation(tmp_path: Path) -> None:
    Journal(tmp_path).write(Event(Kind.SENT, datetime.now(UTC), {"energy_used": 1, "burned_sun": 0}, PaymentId.new()))
    with pytest.raises(SystemExit, match="before it was confirmed"):
        Journal(tmp_path).payments()
