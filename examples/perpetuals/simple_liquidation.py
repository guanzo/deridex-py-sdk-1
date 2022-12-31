from deridex.perpetuals.v1.client import MainnetClient
from deridex.perpetuals.v1.account import Account
from dotenv import dotenv_values

# Create test account
user_mnemonic = dotenv_values(".env")["mnemonic"]
user_account = Account(user_mnemonic)

client = MainnetClient(account=user_account)
perpetual = client.get_perpetual("ALGO/STBL2")
accounts = perpetual.get_accounts()

for account in accounts:
    if account["leverage"] >= 30:
        gtx = perpetual.liquidate(user_account, account)
        gtx.submit(client.algod)