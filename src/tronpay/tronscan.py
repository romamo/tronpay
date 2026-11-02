from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from tronpay.network import Network, require_env
from tronpay.values import TokenAmount, TronAddress


@dataclass(frozen=True)
class Transfer:
    at: datetime
    amount: TokenAmount
    txid: str


@dataclass(frozen=True)
class History:
    transfers: list[Transfer]
    risky: bool


class Tronscan:
    def __init__(self, network: Network) -> None:
        self._network = network
        self._http = httpx.Client(
            base_url=network.tronscan_api_url,
            headers={"TRON-PRO-API-KEY": require_env("TRONSCAN_API_KEY")},
            timeout=20,
        )

    def history(self, sender: TronAddress, recipient: TronAddress) -> History:
        """USDT transfers from sender to recipient, newest first, and Tronscan's risk flag on the recipient"""
        response = self._http.get(
            "api/new/token_trc20/transfers",
            params={
                "start": 0,
                "limit": 10,
                "contract_address": str(self._network.usdt),
                "fromAddress": str(sender),
                "toAddress": str(recipient),
                "confirm": "true",
            },
        )
        response.raise_for_status()
        data = response.json()
        transfers = [
            Transfer(
                at=datetime.fromtimestamp(t["block_ts"] / 1000, UTC),
                amount=TokenAmount(int(t["quant"])),
                txid=t["transaction_id"],
            )
            for t in data["token_transfers"]
            if t["to_address"] == str(recipient)
        ]
        info = data.get("normalAddressInfo", {}).get(str(recipient), {})
        return History(transfers=transfers, risky=bool(info.get("risk")))
