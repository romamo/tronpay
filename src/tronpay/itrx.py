"""Energy rental through ITRX.io: https://develop.itrx.io/api/ (paid from the ITRX account balance)"""

import hashlib
import hmac
import json
import time

import httpx

from tronpay.network import require_env
from tronpay.values import Energy, Sun, TronAddress

PERIOD = "1H"


class Itrx:
    def __init__(self) -> None:
        self._secret = require_env("ITRX_SECRET")
        self._http = httpx.Client(
            base_url="https://itrx.io/api/v1/",
            headers={"API-KEY": require_env("ITRX_KEY")},
            timeout=15,
        )

    def price(self, energy: Energy) -> Sun:
        response = self._http.get("frontend/order/price", params={"energy_amount": energy, "period": PERIOD})
        response.raise_for_status()
        data = response.json()
        return Sun(int(data["total_price"]) + int(data["addition"]))

    def rent(self, receiver: TronAddress, energy: Energy) -> str:
        body = json.dumps(
            {"energy_amount": energy, "period": PERIOD, "receive_address": str(receiver)},
            sort_keys=True,
            separators=(",", ":"),
        )
        timestamp = str(int(time.time()))
        signature = hmac.new(self._secret.encode(), f"{timestamp}&{body}".encode(), hashlib.sha256).hexdigest()
        response = self._http.post(
            "frontend/order",
            content=body,
            headers={"Content-Type": "application/json", "TIMESTAMP": timestamp, "SIGNATURE": signature},
        )
        response.raise_for_status()
        data = response.json()
        if "serial" not in data:
            raise RuntimeError(f"ITRX did not create the order: {data}")
        return str(data["serial"])
