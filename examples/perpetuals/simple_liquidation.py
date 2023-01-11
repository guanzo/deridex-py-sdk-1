from deridex.perpetuals.v1.client import MainnetClient
from deridex.perpetuals.v1.account import Account
from dotenv import dotenv_values

# Create test account
user_mnemonic = dotenv_values(".env")["mnemonic"]
user_account = Account(user_mnemonic)

client = MainnetClient(account=user_account)
# Setup perpetual obj
perpetual = client.get_perpetual("ALGO/STBL2")
# Get vault accounts opted into perpetual contract
accounts = perpetual.get_vault_accounts()

# Get all vault accounts with a position
account_positions = {}
for account in accounts:
    if accounts[account]["pa"] > 0:
        account_positions[account] = perpetual.get_position(account, accounts[account])

# Liquidate all vault accounts with a position if possible
for account in account_positions:
    if account_positions[account]["leverage"] >= 3000:
        gtx = perpetual.liquidate(user_account, account)
        gtx.submit(client.algod)
