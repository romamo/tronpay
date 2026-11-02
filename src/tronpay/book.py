"""Wallets and contacts, kept outside the repository in TRONPAY_HOME (default ~/.config/tronpay)

wallets.json is written by tronpay; contacts.toml is edited by hand:

    alice = "T..."
"""

import json
import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from tronpay.values import TronAddress


class Signer(StrEnum):
    KEYCHAIN = "keychain"  # the key is in the macOS Keychain, tronpay signs
    EXTERNAL = "external"  # the key is in another wallet (a phone), tronpay shows a QR


@dataclass(frozen=True)
class Wallet:
    name: str
    address: TronAddress
    signer: Signer


def home() -> Path:
    path = Path(os.environ.get("TRONPAY_HOME", Path.home() / ".config" / "tronpay"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class Book:
    def __init__(self, root: Path) -> None:
        self._wallets_path = root / "wallets.json"
        self._contacts_path = root / "contacts.toml"

    def wallets(self) -> list[Wallet]:
        if not self._wallets_path.exists():
            return []
        data = json.loads(self._wallets_path.read_text())
        return [Wallet(name, TronAddress(w["address"]), Signer(w["signer"])) for name, w in data.items()]

    def add_wallet(self, wallet: Wallet) -> None:
        wallets = self.wallets()
        for w in wallets:
            if w.name == wallet.name:
                raise SystemExit(f"wallet {wallet.name!r} already exists")
            if w.address == wallet.address:
                raise SystemExit(f"address {wallet.address} is already wallet {w.name!r}")
        wallets.append(wallet)
        data = {w.name: {"address": str(w.address), "signer": str(w.signer)} for w in wallets}
        self._wallets_path.write_text(json.dumps(data, indent=2) + "\n")

    def wallet(self, name: str) -> Wallet:
        for w in self.wallets():
            if w.name == name:
                return w
        raise SystemExit(f"no wallet named {name!r}")

    def contacts(self) -> dict[str, TronAddress]:
        if not self._contacts_path.exists():
            return {}
        data = tomllib.loads(self._contacts_path.read_text())
        return {name: TronAddress(address) for name, address in data.items()}

    def known(self) -> dict[str, TronAddress]:
        """Every named address: wallets first, then contacts"""
        names = {w.name: w.address for w in self.wallets()}
        for name, address in self.contacts().items():
            if name in names:
                raise SystemExit(f"{name!r} is both a wallet and a contact")
            names[name] = address
        return names

    def resolve(self, name_or_address: str) -> TronAddress:
        known = self.known()
        if name_or_address in known:
            return known[name_or_address]
        return TronAddress(name_or_address)

    def name_of(self, address: TronAddress) -> str | None:
        for name, a in self.known().items():
            if a == address:
                return name
        return None
