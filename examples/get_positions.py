import os
from dotenv import dotenv_values
from algosdk import mnemonic
from deridex.options.v1.client import TestnetClient, MainnetClient


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

print(client.get_positions())

