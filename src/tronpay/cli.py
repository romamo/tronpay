import argparse
import math
import os
import subprocess
import time
from datetime import UTC, datetime

import qrcode

from tronpay import keys
from tronpay.book import Book, Signer, Wallet, home
from tronpay.chain import Chain
from tronpay.itrx import Itrx
from tronpay.network import NETWORKS, Network, NetworkName
from tronpay.tronscan import Tronscan
from tronpay.values import Energy, Sun, TokenAmount, TronAddress

FEE_LIMIT_FACTOR = 1.2  # the most TRX a transfer may burn, relative to burning all the energy it needs
ENERGY_WAIT_SECONDS = 180


def main() -> None:
    parser = argparse.ArgumentParser(prog="tronpay", description="Send USDT on TRON with energy rented from ITRX")
    parser.add_argument("--network", type=NetworkName, choices=list(NetworkName), default=NetworkName.MAINNET)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="create a wallet; its key goes to the macOS Keychain")
    p.add_argument("name")

    p = sub.add_parser("add", help="add a wallet whose key lives elsewhere (a phone); tronpay pays from it by QR")
    p.add_argument("name")
    p.add_argument("address")

    sub.add_parser("wallets", help="list wallets")

    p = sub.add_parser("receive", help="show a wallet's address and its QR to receive TRX or USDT")
    p.add_argument("name")

    p = sub.add_parser("balance", help="TRX, USDT, energy and bandwidth of a wallet, contact or address")
    p.add_argument("target", nargs="?", help="default: every wallet")

    p = sub.add_parser("send", help="check the recipient, cover the energy, send USDT")
    p.add_argument("sender", help="wallet name")
    p.add_argument("recipient", help="wallet, contact or address")
    p.add_argument("amount", help="USDT, e.g. 100.50")
    p.add_argument("--dry-run", action="store_true", help="stop after the plan")
    p.add_argument("--burn", action="store_true", help="burn TRX for the missing energy instead of renting it")

    p = sub.add_parser("export-key", help="copy a Keychain wallet's private key to the clipboard, for a backup")
    p.add_argument("name")

    args = parser.parse_args()
    network = NETWORKS[args.network]
    book = Book(home())
    match args.command:
        case "create":
            create(book, args.name)
        case "add":
            book.add_wallet(Wallet(args.name, TronAddress(args.address), Signer.EXTERNAL))
            print(f"Added {args.name}: {args.address}")
        case "wallets":
            for w in book.wallets():
                print(f"{w.name:<16} {w.address}  {w.signer}")
        case "receive":
            receive(book.wallet(args.name))
        case "balance":
            balance(book, chain(network), args.target)
        case "send":
            send(book, network, args)
        case "export-key":
            export_key(book.wallet(args.name))


def chain(network: Network) -> Chain:
    return Chain(network, os.environ.get("TRONGRID_KEY") or None)


def create(book: Book, name: str) -> None:
    if name in book.known():
        raise SystemExit(f"{name!r} is already taken")
    address = keys.create()
    book.add_wallet(Wallet(name, address, Signer.KEYCHAIN))
    print(f"Created {name}: {address}")
    print("The key is only in the Keychain. Back it up now: tronpay export-key " + name)


def receive(wallet: Wallet) -> None:
    print(f"{wallet.name}: {wallet.address}")
    print_qr(str(wallet.address))
    print("An address activates with its first incoming TRX; USDT payments need TRX for fees or rented energy")


def balance(book: Book, c: Chain, target: str | None) -> None:
    rows = [(target, book.resolve(target))] if target else [(w.name, w.address) for w in book.wallets()]
    if not rows:
        raise SystemExit("no wallets yet: tronpay create <name>")
    for name, address in rows:
        trx = c.trx_balance(address)
        usdt = c.usdt_balance(address)
        if trx is None:
            print(f"{name:<16} {address}  not activated, {usdt} USDT")
            continue
        r = c.resources(address)
        print(
            f"{name:<16} {address}  {trx} TRX  {usdt} USDT  "
            f"energy {r.energy:,}  bandwidth {r.free_bandwidth:,} free + {r.staked_bandwidth:,} staked"
        )


def send(book: Book, network: Network, args: argparse.Namespace) -> None:
    sender = book.wallet(args.sender)
    recipient = book.resolve(args.recipient)
    amount = TokenAmount.parse(args.amount)
    if recipient == sender.address:
        raise SystemExit("the recipient is the sender")
    recipient_name = book.name_of(recipient)
    c = chain(network)

    print(f"Send {amount} USDT on {network.name}")
    print(f"  from {sender.name} {sender.address}")
    print(f"  to   {recipient_name or 'unknown'} {recipient}")
    print()

    sender_trx = c.trx_balance(sender.address)
    if sender_trx is None:
        raise SystemExit(f"{sender.name} is not activated: send it some TRX first")
    sender_usdt = c.usdt_balance(sender.address)
    if sender_usdt < amount:
        raise SystemExit(f"{sender.name} has {sender_usdt} USDT, less than {amount}")
    print(f"Sender:    {sender_usdt} USDT, {sender_trx} TRX")

    warnings = []
    recipient_trx = c.trx_balance(recipient)
    recipient_usdt = c.usdt_balance(recipient)
    if recipient_trx is None:
        print(f"Recipient: {recipient_usdt} USDT, not activated")
        warnings.append("the recipient account is not activated on chain")
    else:
        print(f"Recipient: {recipient_usdt} USDT, {recipient_trx} TRX")
    for name, known in book.known().items():
        if recipient.looks_like(known):
            warnings.append(f"ADDRESS POISONING? the recipient looks like {name} {known} but is a different address")

    history = Tronscan(network).history(sender.address, recipient)
    if history.risky:
        warnings.append("Tronscan marks the recipient as risky")
    if history.transfers:
        print("History:")
        now = datetime.now(UTC)
        for t in history.transfers[:3]:
            print(f"  {(now - t.at).days} days ago sent {t.amount} USDT  {network.tx_link(t.txid)}")
    else:
        warnings.append(f"{sender.name} never sent USDT to this address")
    print()

    energy_needed = c.transfer_energy(sender.address, recipient, amount)
    bandwidth_needed = c.transfer_bandwidth(sender.address, recipient, amount)
    resources = c.resources(sender.address)
    prices = c.prices()
    energy_lack = Energy(max(0, energy_needed - resources.energy))
    # a transaction is paid by staked or by free bandwidth as a whole, never by the two together
    bandwidth_covered = max(resources.staked_bandwidth, resources.free_bandwidth) >= bandwidth_needed
    bandwidth_burn = Sun(0 if bandwidth_covered else bandwidth_needed * prices.bandwidth)
    print(f"Energy:    needs {energy_needed:,}, has {resources.energy:,}, lacks {energy_lack:,}")
    print(
        f"Bandwidth: needs {bandwidth_needed}, has {resources.free_bandwidth} free + {resources.staked_bandwidth} "
        f"staked; burns {TokenAmount(bandwidth_burn)} TRX"
    )

    rent = energy_lack > 0 and network.rental and not args.burn
    energy_burn = Sun(0 if rent else energy_lack * prices.energy)
    if rent:
        itrx = Itrx()
        rent_price = itrx.price(energy_lack)
        print(
            f"Rent:      {energy_lack:,} energy from ITRX for {TokenAmount(rent_price)} TRX from the ITRX balance "
            f"(burning it would cost {TokenAmount(Sun(energy_lack * prices.energy))} TRX)"
        )
    elif energy_lack:
        print(f"Burn:      {TokenAmount(energy_burn)} TRX for the missing energy")
    wallet_cost = TokenAmount(bandwidth_burn + energy_burn)
    if sender_trx < wallet_cost:
        raise SystemExit(f"{sender.name} has {sender_trx} TRX, but the transfer burns {wallet_cost} TRX")
    fee_limit = Sun(math.ceil(energy_needed * prices.energy * FEE_LIMIT_FACTOR))

    for w in warnings:
        print(f"WARNING: {w}")
    print()
    if args.dry_run:
        print("Dry run: nothing rented or sent")
        return
    if input(f"Send {amount} USDT to {recipient}? Type yes: ") != "yes":
        raise SystemExit("cancelled")

    if rent:
        serial = itrx.rent(sender.address, energy_lack)
        print(f"Rented, ITRX order {serial}; waiting for the energy...")
        wait_for_energy(c, sender.address, energy_needed, serial)

    if sender.signer is Signer.KEYCHAIN:
        receipt = c.transfer(keys.load(sender.address), recipient, amount, fee_limit)
        print(f"Sent: {network.tx_link(receipt.txid)}")
        print(f"Energy used {receipt.energy_used:,}, TRX burned {TokenAmount(receipt.burned)}")
    else:
        link = (
            f"https://link.trustwallet.com/send?asset=c195_t{network.usdt}"
            f"&address={recipient}&amount={amount.decimal}"
        )
        print(f"Scan with Trust Wallet on the phone that holds {sender.name}:")
        print_qr(link)
        print(link)


def wait_for_energy(c: Chain, address: TronAddress, needed: Energy, serial: str) -> None:
    deadline = time.monotonic() + ENERGY_WAIT_SECONDS
    while time.monotonic() < deadline:
        energy = c.resources(address).energy
        if energy >= needed:
            print(f"Energy {energy:,} is there")
            return
        time.sleep(5)
    raise SystemExit(f"the energy did not arrive in {ENERGY_WAIT_SECONDS}s; check ITRX order {serial}, nothing was sent")


def export_key(wallet: Wallet) -> None:
    if wallet.signer is not Signer.KEYCHAIN:
        raise SystemExit(f"{wallet.name} has no key in the Keychain")
    if input(f"Copy the private key of {wallet.name} to the clipboard? Type the wallet name: ") != wallet.name:
        raise SystemExit("cancelled")
    subprocess.run(["pbcopy"], input=keys.load(wallet.address).hex().encode(), check=True)
    print("Copied. Store it offline, then clear the clipboard")


def print_qr(data: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.print_ascii(invert=True)
