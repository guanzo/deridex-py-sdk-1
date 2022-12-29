from algosdk.atomic_transaction_composer import AccountTransactionSigner
from algosdk import encoding, mnemonic


class Account:
    """
    Class that contains users address and signer object
    """
    def __init__(self, secret_phrase):
        self.mnemonic = secret_phrase
        self.address = mnemonic.to_public_key(self.mnemonic)
        self.signer = AccountTransactionSigner(mnemonic.to_private_key(secret_phrase))
