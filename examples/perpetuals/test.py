from deridex.perpetuals.v1.client import MainnetClient
from deridex.perpetuals.v1.config import SIDE
from deridex.perpetuals.v1.account import Account
from algosdk import account, mnemonic
from algosdk.atomic_transaction_composer import AccountTransactionSigner
from dotenv import dotenv_values

# Create test account
user_mnemonic = dotenv_values(".env")["mnemonic"]

user_account = Account(user_mnemonic)

client = MainnetClient(account=user_account)
perpetual = client.get_perpetual("ALGO/STBL2")
print(perpetual.get_vault_accounts())
