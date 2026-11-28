# tronpay

A CLI to send USDT on TRON. Before each payment it checks the recipient, works out the energy the transfer needs, rents what is missing from ITRX and sends, only after you type `yes`

## Setup

```bash
uv sync
```

Environment, for example from a `.env` file passed with `uv run --env-file`:

- `TRONGRID_KEY`: TronGrid API key (optional; tronpy's shared keys are used without it)
- `TRONSCAN_API_KEY`: Tronscan API key, for the recipient's history and risk flag
- `ITRX_KEY`, `ITRX_SECRET`: ITRX.io API key and secret, for renting energy; rentals are paid from the ITRX account balance

Everything tronpay keeps lives in `TRONPAY_HOME` (default `~/.config/tronpay`), outside the repository:

- `wallets.json`: your wallets, written by `tronpay create` and `tronpay add`
- `contacts.json`: the recipients, written by `tronpay contact add` and `tronpay contact remove`
- `history.jsonl`: the payment history, one event per line, only ever appended to

## Address book

A payment goes only to a name from the address book (a wallet or a contact), never to an address typed on the command line. Add each recipient once, before the first payment: `tronpay contact add` prints the address in groups of four to check against the source, warns when it looks like a known address (the same first and last four characters), and asks for `yes`

## History

`tronpay history` lists every payment from `history.jsonl`: when, how much, from and to whom, the energy rental and the TRX burned, and the transaction link. A payment writes its events as it goes: `confirmed` when you type `yes`, `rented` with the ITRX order, `broadcast` with the txid as soon as the transaction is on the network, then `sent` with the receipt, or `qr` for a wallet that signs on a phone. A payment that stopped half way shows the last step it reached. Address book changes are written too; `tronpay history --all` prints every event

## Commands

```bash
tronpay create main                  # new key in the macOS Keychain
tronpay export-key main              # copy the key to the clipboard for a backup
tronpay add phone T...               # a wallet whose key is on a phone: tronpay pays from it by QR
tronpay wallets
tronpay contact add alice T...       # a recipient, checked and confirmed once
tronpay contact remove alice
tronpay contacts
tronpay receive main                 # address and QR to receive TRX
tronpay balance [wallet|contact|address]
tronpay send main alice 100 --dry-run
tronpay send main alice 100          # add --burn to burn TRX instead of renting energy
tronpay send alice 100               # the sender is chosen from the history, see below
tronpay history                      # payments made with tronpay
tronpay --network nile ...           # the Nile testnet (no rental there, energy is burned)
```

## Choosing the sender

Without a sender, `send` takes the wallet that last paid the recipient (from `history.jsonl`, on the same network, a payment that was broadcast or shown as a QR) and holds the amount with an activated account. When it does not, it tries the wallet that paid before that, and so on, printing each one it skips. When no wallet that paid before holds the amount, it lists every other wallet that does, with its USDT and TRX, and asks for the number

## How `send` works

1. Checks that the sender has the USDT and is activated
2. Shows the recipient's TRX and USDT, the sender's last transfers to it (Tronscan), and warns when the recipient is unknown, not activated, marked risky, or looks like a known address with the same first and last four characters (address poisoning)
3. Dry-runs the transfer on the node for the exact energy: about 65,000 when the recipient holds USDT, about 130,000 when it holds none
4. Works out the bandwidth and whether it burns TRX
5. Prices the missing energy at ITRX, next to what burning it would cost
6. Asks for `yes`, writes the payment to the history, rents the energy, waits until it arrives (180 s at most) and sends
7. A Keychain wallet signs and broadcasts here, with a fee limit that caps the TRX burned; an external wallet gets a Trust Wallet QR to scan

Python is pinned below 3.14: tronpy 0.6.2 requires coincurve<21 there, and coincurve 20 has no 3.14 wheels
