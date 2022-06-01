import os
from dotenv import dotenv_values
from algosdk import mnemonic
from deridex.options.v1.client import TestnetClient, MainnetClient
from deridex.options.v1.config import OptionType
from deridex.utils import TransactionGroup


my_path = os.path.abspath(os.path.dirname(__file__))
ENV_PATH = os.path.join(my_path, ".env")
user = dotenv_values(ENV_PATH)
sender = mnemonic.to_public_key(user['mnemonic'])
key = mnemonic.to_private_key(user['mnemonic'])

IS_MAINNET = False
if IS_MAINNET:
    client = MainnetClient(address=sender)
else:
    client = TestnetClient(address=sender)

options = [
    client.get_option(OptionType.CALL, underlying_asset="ALGO", collateral_asset="TNR"),
    client.get_option(OptionType.PUT, underlying_asset="ALGO", collateral_asset="TNR")
    ]

for option in options:
    print(f'Checking {option} accounts')
    latest_block_time = client.algod.block_info(block=client.algod.status()["last-round"])["block"]["ts"]

    addresses = option.get_open_contracts()

    # Execute all valid addresses
    for address, state in addresses.items():
        if latest_block_time > state["expiry"]:
            print(f"Executing: {address}")
            # Create transactions for options contract
            txs = option.execute(sender, address)
            # Assemble group transaction
            gtx = TransactionGroup(txs)
            gtx.sign_with_private_key(key)
            gtx.submit(client.algod, wait=True)

