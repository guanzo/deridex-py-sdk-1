from deridex.perpetuals.v1.client import MainnetClient
from deridex.perpetuals.v1.account import Account
from dotenv import dotenv_values

# Create test account
user_mnemonic = dotenv_values(".env")["mnemonic"]
user_account = Account(user_mnemonic)

client = MainnetClient(account=user_account)
# Setup perpetual obj
perpetual = client.get_perpetual("ALGO/STBL2")

# Get add Txs
gtx = perpetual.add(1, 10_000, user_account)
# Submit Tx
gtx.submit(client.algod)