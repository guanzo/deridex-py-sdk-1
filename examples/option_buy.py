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
    client = MainnetClient()
else:
    client = TestnetClient()

option = client.get_option(OptionType.CALL, underlying_asset="ALGO", collateral_asset="TNR")
size = 1000
length = 3
# Get quoted price of the option
quote = option.quote(size, length)
# Create transactions for options contract
txs = option.create(sender, size, length, quote)
# Assemble group transaction
gtx = TransactionGroup(txs)
gtx.sign_with_private_key(key)
gtx.submit(client.algod, wait=True)
