import math
import os
from algosdk import account, encoding, mnemonic
from algosdk.logic import get_application_address
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner, AccountTransactionSigner
from algosdk.abi import Contract
from algosdk.error import AlgodHTTPError
from algosdk.future.transaction import (StateSchema, ApplicationOptInTxn, ApplicationCallTxn, ApplicationCreateTxn, PaymentTxn,
                                        AssetCreateTxn, OnComplete)
from ...utils import read_global_state, read_local_state, get_option_app_id, format_state


class Perpetual:
    """
    :param algod_client: an algod client
    :type algod_client: class:`AlgodClient`
    :param indexer_client: an indexer client
    :type indexer_client: class:`IndexerClient`
    :param network: the network to use
    :type network: str
    :param app_id: the app id of the perpetual
    :type app_id: int
    """
    def __init__(self, algod_client, indexer_client, network, appId, symbol):
        self.algod_client = algod_client
        self.indexer_client = indexer_client
        self.network = network
        self.appId = appId
        self.symbol = symbol

        # Get state
        self.global_state = read_global_state(indexer_client, self.appId)
        self.local_state = {}

        # Get ABI
        path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(path, "abi/perpetual.json"), "r") as f:
            self.perpetual_contract = Contract.from_json(f.read())
        with open(os.path.join(path, "abi/manager.json"), "r") as f:
            self.manager_contract = Contract.from_json(f.read())

        # Get info from contract
        self.a1 = self.global_state["a1"]
        self.a1u = self.global_state["a1u"]
        self.a2 = self.global_state["a2"]
        self.a2u = self.global_state["a2u"]

        # Get addresses
        self.manager_addr = get_application_address(self.global_state["manager"])
        self.perpetual_addr = get_application_address(self.appId)


    def __repr__(self):
        return f"Perpetual('{self.symbol}')"

    def __str__(self):
        return f"Perpetual('{self.symbol}')"

    def update_global_state(self):
        self.global_state = read_global_state(self.algod_client, self.appId)

    def update_local_state(self, address):
        self.local_state = read_local_state(self.indexer_client, address, self.appId)

    def get_suggested_params(self, fee=1):
        """Initializes the transactions parameters for the client.
        """
        params = self.algod_client.suggested_params()
        params.flat_fee = True
        params.fee = 1000 * fee
        return params

    def opt_in(self, address, signer):
        local_state = self.indexer_client.lookup_account_application_local_state(address, application_id=self.appId)["apps-local-states"]
        if local_state is None:
            # Generate vault account
            vault_pk, vault_addr = account.generate_account()
            vault_signer = AccountTransactionSigner(vault_pk)

            gtx = AtomicTransactionComposer()
            gtx.add_transaction(
                TransactionWithSigner(
                    PaymentTxn(
                        sender=address,
                        sp=self.get_suggested_params(),
                        receiver=vault_addr,
                        amt=787_000
                    ),
                    signer
                )
            )
            gtx.add_method_call(
                app_id=self.global_state["manager"],
                on_complete=OnComplete.OptInOC,
                method=self.manager_contract.get_method_by_name("vault"),
                sender=vault_addr,
                sp=self.get_suggested_params(),
                signer=vault_signer,
                method_args=[
                    address
                ],
            )
            gtx.add_transaction(
                TransactionWithSigner(
                    PaymentTxn(
                        sender=vault_addr,
                        sp=self.get_suggested_params(),
                        receiver=vault_addr,
                        amt=0,
                        rekey_to=self.manager_addr
                    ),
                    vault_signer
                )
            )
            gtx.add_method_call(
                app_id=self.global_state["manager"],
                on_complete=OnComplete.OptInOC,
                method=self.manager_contract.get_method_by_name("user"),
                sender=address,
                sp=self.get_suggested_params(),
                signer=signer,
                method_args=[
                    vault_addr
                ],
            )
            return gtx