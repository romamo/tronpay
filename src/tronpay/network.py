import os
from dataclasses import dataclass
from enum import StrEnum

from tronpay.values import TronAddress


class NetworkName(StrEnum):
    MAINNET = "mainnet"
    NILE = "nile"


@dataclass(frozen=True)
class Network:
    name: NetworkName
    trongrid_url: str
    tronscan_api_url: str
    explorer_tx_url: str
    usdt: TronAddress
    rental: bool

    def tx_link(self, txid: str) -> str:
        return f"{self.explorer_tx_url}{txid}"


NETWORKS = {
    NetworkName.MAINNET: Network(
        name=NetworkName.MAINNET,
        trongrid_url="https://api.trongrid.io",
        tronscan_api_url="https://apilist.tronscanapi.com/",
        explorer_tx_url="https://tronscan.org/#/transaction/",
        usdt=TronAddress("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"),
        rental=True,
    ),
    NetworkName.NILE: Network(
        name=NetworkName.NILE,
        trongrid_url="https://nile.trongrid.io",
        tronscan_api_url="https://nileapi.tronscan.org/",
        explorer_tx_url="https://nile.tronscan.org/#/transaction/",
        usdt=TronAddress("TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"),
        rental=False,
    ),
}


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"environment variable {name} is not set")
    return value
