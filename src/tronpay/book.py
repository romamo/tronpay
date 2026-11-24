"""The address book: wallets and contacts, kept outside the repository in TRONPAY_HOME (default ~/.config/tronpay)

Both files are written by tronpay: wallets.json by `tronpay create` and `tronpay add`, contacts.json by
`tronpay contact add` and `tronpay contact remove`. A payment goes only to a name from this book.
"""

import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tronpay.values import TronAddress

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}")


@dataclass(frozen=True)
class Name:
    """A wallet or contact name: letters, digits, dots, dashes and underscores, never an address"""

    value: str

    def __post_init__(self) -> None:
        if not NAME.fullmatch(self.value):
            raise ValueError(
                f"a name is 1-32 letters, digits, '.', '-' or '_', starting with a letter or digit: {self.value!r}"
            )

    def __str__(self) -> str:
        return self.value


class Signer(StrEnum):
    KEYCHAIN = "keychain"  # the key is in the macOS Keychain, tronpay signs
    EXTERNAL = "external"  # the key is in another wallet (a phone), tronpay shows a QR


@dataclass(frozen=True)
class Wallet:
    name: Name
    address: TronAddress
    signer: Signer


@dataclass(frozen=True)
class Contact:
    name: Name
    address: TronAddress


def home() -> Path:
    path = Path(os.environ.get("TRONPAY_HOME", Path.home() / ".config" / "tronpay"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class Book:
    def __init__(self, root: Path) -> None:
        self._wallets_path = root / "wallets.json"
        self._contacts_path = root / "contacts.json"
        legacy = root / "contacts.toml"
        if legacy.exists():
            raise SystemExit(f"{legacy} is no longer read: add each contact with `tronpay contact add`, then delete it")

    def wallets(self) -> list[Wallet]:
        if not self._wallets_path.exists():
            return []
        data = json.loads(self._wallets_path.read_text(encoding="utf-8"))
        return [Wallet(Name(name), TronAddress(w["address"]), Signer(w["signer"])) for name, w in data.items()]

    def add_wallet(self, wallet: Wallet) -> None:
        self.check_new(wallet.name, wallet.address)
        wallets = [*self.wallets(), wallet]
        data = {str(w.name): {"address": str(w.address), "signer": str(w.signer)} for w in wallets}
        self._wallets_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def wallet(self, name: Name) -> Wallet:
        for w in self.wallets():
            if w.name == name:
                return w
        raise SystemExit(f"no wallet named {name}")

    def contacts(self) -> list[Contact]:
        if not self._contacts_path.exists():
            return []
        data = json.loads(self._contacts_path.read_text(encoding="utf-8"))
        return [Contact(Name(name), TronAddress(address)) for name, address in data.items()]

    def add_contact(self, contact: Contact) -> None:
        self.check_new(contact.name, contact.address)
        self._write_contacts([*self.contacts(), contact])

    def remove_contact(self, name: Name) -> Contact:
        contacts = self.contacts()
        for c in contacts:
            if c.name == name:
                self._write_contacts([other for other in contacts if other.name != name])
                return c
        raise SystemExit(f"no contact named {name}")

    def known(self) -> dict[Name, TronAddress]:
        """Every named address: wallets first, then contacts"""
        names = {w.name: w.address for w in self.wallets()}
        for c in self.contacts():
            if c.name in names:
                raise SystemExit(f"{c.name} is both a wallet and a contact")
            names[c.name] = c.address
        return names

    def address(self, name: Name) -> TronAddress:
        """The address of a wallet or contact; a payment never goes to an address outside the book"""
        known = self.known()
        if name not in known:
            raise SystemExit(f"{name} is not in the address book: tronpay contact add {name} <address>")
        return known[name]

    def resolve(self, name_or_address: str) -> TronAddress:
        """A name from the book or a bare address, for read-only commands"""
        for name, address in self.known().items():
            if str(name) == name_or_address:
                return address
        return TronAddress(name_or_address)

    def name_of(self, address: TronAddress) -> Name | None:
        for name, a in self.known().items():
            if a == address:
                return name
        return None

    def lookalikes(self, address: TronAddress) -> list[tuple[Name, TronAddress]]:
        """Known addresses with the same first and last four characters: the address poisoning pattern"""
        return [(name, known) for name, known in self.known().items() if address.looks_like(known)]

    def check_new(self, name: Name, address: TronAddress) -> None:
        for n, a in self.known().items():
            if n == name:
                raise SystemExit(f"{name} is already in the address book")
            if a == address:
                raise SystemExit(f"{address} is already in the address book as {n}")

    def _write_contacts(self, contacts: list[Contact]) -> None:
        data = {str(c.name): str(c.address) for c in contacts}
        self._contacts_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
