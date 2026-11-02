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

Wallets and contacts live in `TRONPAY_HOME` (default `~/.config/tronpay`), outside the repository:

- `wallets.json` is written by `tronpay create` and `tronpay add`
- `contacts.toml` is edited by hand: `alice = "T..."`

## Commands

```bash
tronpay create main                  # new key in the macOS Keychain
tronpay export-key main              # copy the key to the clipboard for a backup
tronpay add phone T...               # a wallet whose key is on a phone: tronpay pays from it by QR
tronpay wallets
tronpay receive main                 # address and QR to receive TRX
tronpay balance [wallet|contact|address]
tronpay send main alice 100 --dry-run
tronpay send main alice 100          # add --burn to burn TRX instead of renting energy
tronpay --network nile ...           # the Nile testnet (no rental there, energy is burned)
```

## How `send` works

1. Checks that the sender has the USDT and is activated
2. Shows the recipient's TRX and USDT, the sender's last transfers to it (Tronscan), and warns when the recipient is unknown, not activated, marked risky, or looks like a known address with the same first and last four characters (address poisoning)
3. Dry-runs the transfer on the node for the exact energy: about 65,000 when the recipient holds USDT, about 130,000 when it holds none
4. Works out the bandwidth and whether it burns TRX
5. Prices the missing energy at ITRX, next to what burning it would cost
6. Asks for `yes`, rents the energy, waits until it arrives (180 s at most) and sends
7. A Keychain wallet signs and broadcasts here, with a fee limit that caps the TRX burned; an external wallet gets a Trust Wallet QR to scan

Python is pinned below 3.14: tronpy 0.6.2 requires coincurve<21 there, and coincurve 20 has no 3.14 wheels
