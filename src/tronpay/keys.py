import keyring
from tronpy.keys import PrivateKey

from tronpay.values import TronAddress

SERVICE = "tronpay"


def create() -> TronAddress:
    key = PrivateKey.random()
    address = TronAddress(key.public_key.to_base58check_address())
    keyring.set_password(SERVICE, str(address), key.hex())
    if load(address).hex() != key.hex():
        raise RuntimeError("the key read back from the Keychain does not match")
    return address


def load(address: TronAddress) -> PrivateKey:
    secret = keyring.get_password(SERVICE, str(address))
    if secret is None:
        raise SystemExit(f"no key for {address} in the Keychain")
    key = PrivateKey(bytes.fromhex(secret))
    if key.public_key.to_base58check_address() != str(address):
        raise RuntimeError(f"the Keychain key for {address} belongs to another address")
    return key
