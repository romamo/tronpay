from dataclasses import dataclass

from tronpy import Tron
from tronpy.abi import trx_abi
from tronpy.exceptions import AddressNotFound
from tronpy.keys import PrivateKey

# tronpy's own serializer for raw_data (it computes txids with it); the size of a transaction is its bandwidth
from tronpy.proto.transaction import _raw_data_to_protobuf
from tronpy.providers import HTTPProvider
from tronpy.tron import TransactionRet

from tronpay.network import Network
from tronpay.values import Bandwidth, Energy, Sun, TokenAmount, TronAddress

TRANSFER = "transfer(address,uint256)"
SIGNATURE_BYTES = 67  # protobuf tag, length and a 65-byte signature
RESULT_BYTES = 64  # java-tron reserves this per contract call (MAX_RESULT_SIZE_IN_TX)


@dataclass(frozen=True)
class Resources:
    energy: Energy
    free_bandwidth: Bandwidth
    staked_bandwidth: Bandwidth


@dataclass(frozen=True)
class Prices:
    energy: Sun  # burned per unit of energy the account lacks
    bandwidth: Sun  # burned per byte when the account lacks bandwidth


@dataclass(frozen=True)
class Broadcast:
    txid: str
    result: TransactionRet


@dataclass(frozen=True)
class Receipt:
    txid: str
    energy_used: Energy
    burned: Sun


class Chain:
    def __init__(self, network: Network, api_key: str | None) -> None:
        self._network = network
        self._client = Tron(HTTPProvider(network.trongrid_url, api_key=api_key))
        self._usdt = self._client.get_contract(str(network.usdt))

    def trx_balance(self, address: TronAddress) -> TokenAmount | None:
        """None when the account is not activated on chain"""
        try:
            account = self._client.get_account(str(address))
        except AddressNotFound:
            return None
        return TokenAmount(int(account.get("balance", 0)))

    def usdt_balance(self, address: TronAddress) -> TokenAmount:
        return TokenAmount(int(self._usdt.functions.balanceOf(str(address))))

    def resources(self, address: TronAddress) -> Resources:
        r = self._client.get_account_resource(str(address))
        return Resources(
            energy=Energy(r.get("EnergyLimit", 0) - r.get("EnergyUsed", 0)),
            free_bandwidth=Bandwidth(r.get("freeNetLimit", 0) - r.get("freeNetUsed", 0)),
            staked_bandwidth=Bandwidth(r.get("NetLimit", 0) - r.get("NetUsed", 0)),
        )

    def prices(self) -> Prices:
        params = {p["key"]: p.get("value", 0) for p in self._client.get_chain_parameters()}
        return Prices(energy=Sun(int(params["getEnergyFee"])), bandwidth=Sun(int(params["getTransactionFee"])))

    def transfer_energy(self, sender: TronAddress, recipient: TronAddress, amount: TokenAmount) -> Energy:
        """Energy a USDT transfer takes, from a dry run on the node; about twice as much when the recipient holds no USDT"""
        parameter = trx_abi.encode_abi(["address", "uint256"], [str(recipient), amount.units]).hex()
        ret = self._client.trigger_constant_contract(str(sender), str(self._network.usdt), TRANSFER, parameter)
        if not ret.get("result", {}).get("result"):
            raise RuntimeError(f"the dry run of the transfer failed: {ret}")
        return Energy(int(ret["energy_used"]))

    def transfer_bandwidth(self, sender: TronAddress, recipient: TronAddress, amount: TokenAmount) -> Bandwidth:
        tx = self._usdt.functions.transfer(str(recipient), amount.units).with_owner(str(sender)).fee_limit(1).build()
        raw = len(_raw_data_to_protobuf(tx.to_json()["raw_data"]).SerializeToString())
        length_bytes = len(_varint(raw))
        return Bandwidth(1 + length_bytes + raw + SIGNATURE_BYTES + RESULT_BYTES)

    def broadcast(self, key: PrivateKey, recipient: TronAddress, amount: TokenAmount, fee_limit: Sun) -> Broadcast:
        """Sign and broadcast a USDT transfer; its txid is known from here on, whatever happens next"""
        sender = key.public_key.to_base58check_address()
        tx = (
            self._usdt.functions.transfer(str(recipient), amount.units)
            .with_owner(sender)
            .fee_limit(fee_limit)
            .build()
            .sign(key)
        )
        return Broadcast(txid=tx.txid, result=tx.broadcast())

    def confirm(self, broadcast: Broadcast) -> Receipt:
        info = broadcast.result.wait(timeout=90)
        receipt = info.get("receipt", {})
        if receipt.get("result") != "SUCCESS":
            raise RuntimeError(f"transaction {broadcast.txid} failed: {info}")
        return Receipt(
            txid=broadcast.txid,
            energy_used=Energy(int(receipt.get("energy_usage_total", 0))),
            burned=Sun(int(info.get("fee", 0))),
        )


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)
