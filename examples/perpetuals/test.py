from deridex.perpetuals.v1.client import MainnetClient
from algosdk import account
from algosdk.atomic_transaction_composer import AccountTransactionSigner

# Create test account
user_sk, user_addr = account.generate_account()
user_signer = AccountTransactionSigner(user_sk)


client = MainnetClient(address=user_addr, signer=user_signer)
client.get_perpetual("ALGO/STBL2")