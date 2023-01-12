import math
import os
from base64 import b64decode, b64encode
from algosdk import account, encoding, mnemonic
from algosdk.logic import get_application_address
from algosdk.atomic_transaction_composer import AtomicTransactionComposer, TransactionWithSigner, AccountTransactionSigner
from algosdk.abi import Contract
from algosdk.error import AlgodHTTPError
from algosdk.future.transaction import (StateSchema, ApplicationOptInTxn, ApplicationCallTxn, ApplicationCreateTxn, PaymentTxn,
                                        AssetCreateTxn, AssetTransferTxn, OnComplete)
from .config import SIDE
from .account import Account
from ...utils import read_global_state, read_local_state, get_option_app_id, format_state


class Quote:
    """Quote object returned by get_quote"""
    def __init__(self, swap_in, swap_out, borrow_amt, liq_price, price_impact, leverage, in_asset, in_basset, out_asset,
                 out_basset, in_mkt, out_mkt):
        self.swap_in = int(swap_in * 1e6)
        self.swap_out = swap_out
        self.borrow_amt = borrow_amt
        self.liq_price = liq_price
        self.price_impact = price_impact
        self.leverage = int(leverage * 1e2)
        self.in_asset = in_asset
        self.in_basset = in_basset
        self.out_asset = out_asset
        self.out_basset = out_basset
        self.in_mkt = in_mkt
        self.out_mkt = out_mkt


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
        self.global_state = {
            "self": read_global_state(indexer_client, self.appId),
        }
        self.global_state["a1mk"] = read_global_state(indexer_client, self.global_state["self"]["a1mk"])
        self.global_state["a2mk"] = read_global_state(indexer_client, self.global_state["self"]["a2mk"])
        self.global_state["amm"] = read_global_state(indexer_client, self.global_state["self"]["amm"])
        self.global_state["oracle"] = read_global_state(indexer_client, self.global_state["self"]["oracle"])
        self.local_state = {}
        self.vault_addr = None

        # Get ABI
        path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(path, "abi/perpetual.json"), "r") as f:
            self.perpetual_contract = Contract.from_json(f.read())
        with open(os.path.join(path, "abi/manager.json"), "r") as f:
            self.manager_contract = Contract.from_json(f.read())

        # Get info from contract
        self.a1 = self.global_state["self"]["a1"]
        self.a1u = self.global_state["self"]["a1u"]
        self.a2 = self.global_state["self"]["a2"]
        self.a2u = self.global_state["self"]["a2u"]

        # Get addresses
        self.manager_addr = get_application_address(self.global_state["self"]["manager"])
        self.perpetual_addr = get_application_address(self.appId)

    def __repr__(self):
        return f"Perpetual('{self.symbol}')"

    def __str__(self):
        return f"Perpetual('{self.symbol}')"

    def update_global_state(self):
        self.global_state["self"] = read_global_state(self.indexer_client, self.appId)
        self.global_state["a1mk"] = read_global_state(self.indexer_client, self.global_state["self"]["a1mk"])
        self.global_state["a2mk"] = read_global_state(self.indexer_client, self.global_state["self"]["a2mk"])
        self.global_state["amm"] = read_global_state(self.indexer_client, self.global_state["self"]["amm"])
        self.global_state["oracle"] = read_global_state(self.indexer_client, self.global_state["self"]["oracle"])

    def update_local_state(self, account_obj):
        manager_local_state = read_local_state(self.indexer_client, account_obj.address, self.global_state["self"]["manager"])
        self.vault_addr = encoding.encode_address(b64decode(manager_local_state["v"]))
        self.local_state = read_local_state(self.indexer_client, self.vault_addr, self.appId)

    def get_suggested_params(self, fee=1):
        """Initializes the transactions parameters for the client.
        """
        params = self.algod_client.suggested_params()
        params.flat_fee = True
        params.fee = 1000 * fee
        return params

    def get_vault_accounts(self):
        """
        Get vault accounts with their state
        """
        results = {}
        token = None
        while True:
            resp = self.indexer_client.accounts(application_id=self.appId, next_page=token)
            accounts = resp["accounts"]
            for account in accounts:
                address = account["address"]
                for app in account["apps-local-state"]:
                    if app["id"] == self.appId:
                        state = format_state(app["key-value"])
                        results[address] = state
                        break
            if "next-token" in resp:
                token = resp["next-token"]
            else:
                break

        return results

    def get_position(self, address: str, local_state: dict = None):
        """
        Get the position of a user
        :param address: the address of the user
        :type address: str
        :param local_state: the local state of the user
        :type local_state: dict
        :return: the position of the user
        :rtype: dict
        """
        self.update_global_state()
        if local_state is None:
            local_state = read_local_state(self.indexer_client, address, self.appId)
        # Check if in any position
        if local_state["pa"] != 0:
            # If long
            if local_state["pa"] == self.global_state["self"]["a1"]:
                borrow_amt_bAsset = int(local_state["a2bs"] / self.global_state["self"]["ta2bs"] * self.global_state["self"]["ta2b"])
                borrow_amt_uAsset = int(borrow_amt_bAsset * (self.global_state["a2mk"]["baer"] / 1e9))
                position_amt_uAsset = int(local_state["ps"] * (self.global_state["a1mk"]["baer"] / 1e9))
                oracle_price = self.global_state["oracle"]["latest_price"] / 1e6
                current_leverage = round(position_amt_uAsset * oracle_price / (position_amt_uAsset * oracle_price - borrow_amt_uAsset), 2) * 1e2
                return {
                    "side": "long",
                    "position_amt_bAsset": local_state["ps"],
                    "position_amt_uAsset": position_amt_uAsset,
                    "borrow_amt_bAsset": borrow_amt_bAsset,
                    "borrow_amt_uAsset": borrow_amt_uAsset,
                    "position_asset": self.global_state["self"]["a1"],
                    "position_uAsset": self.global_state["self"]["a1u"],
                    "borrow_asset": self.global_state["self"]["a2"],
                    "borrow_uAsset": self.global_state["self"]["a2u"],
                    "position_mkt": self.global_state["self"]["a1mk"],
                    "borrow_mkt": self.global_state["self"]["a2mk"],
                    "leverage": int(current_leverage)
                }
            # If short
            elif local_state["pa"] == self.global_state["self"]["a2"]:
                borrow_amt_bAsset = int(local_state["a1bs"] / self.global_state["self"]["ta1bs"] * self.global_state["self"]["ta1b"])
                borrow_amt_uAsset = int(borrow_amt_bAsset * (self.global_state["a1mk"]["baer"] / 1e9))
                position_amt_uAsset = int(local_state["ps"] * (self.global_state["a2mk"]["baer"] / 1e9))
                oracle_price = 1 / (self.global_state["oracle"]["latest_price"] / 1e6)
                current_leverage = round(position_amt_uAsset * oracle_price / (position_amt_uAsset * oracle_price - borrow_amt_uAsset), 2) * 1e2
                return {
                    "side": "short",
                    "position_amt_bAsset": local_state["ps"],
                    "position_amt_uAsset": position_amt_uAsset,
                    "borrow_amt_bAsset": borrow_amt_bAsset,
                    "borrow_amt_uAsset": borrow_amt_uAsset,
                    "position_asset": self.global_state["self"]["a2"],
                    "position_uAsset": self.global_state["self"]["a2u"],
                    "borrow_asset": self.global_state["self"]["a1"],
                    "position_mkt": self.global_state["self"]["a2mk"],
                    "borrow_mkt": self.global_state["self"]["a1mk"],
                    "leverage": int(current_leverage)
                }
            elif local_state["pa"] == 1:
                borrow_amt_bAsset = int(local_state["a2bs"] / self.global_state["self"]["ta2bs"] * self.global_state["self"]["ta2b"])
                borrow_amt_uAsset = int(borrow_amt_bAsset * (self.global_state["a2mk"]["baer"] / 1e9))
                position_amt_uAsset = int(local_state["ps"] * (self.global_state["a1mk"]["baer"] / 1e9))
                oracle_price = self.global_state["oracle"]["latest_price"] / 1e6
                current_leverage = round(position_amt_uAsset * oracle_price / (position_amt_uAsset * oracle_price - borrow_amt_uAsset),2) * 1e2
                return {
                    "side": "gov",
                    "position_amt_bAsset": local_state["ps"],
                    "position_amt_uAsset": position_amt_uAsset,
                    "borrow_amt_bAsset": borrow_amt_bAsset,
                    "borrow_amt_uAsset": borrow_amt_uAsset,
                    "position_asset": self.global_state["self"]["a1u"],
                    "position_uAsset": self.global_state["self"]["a1u"],
                    "borrow_asset": self.global_state["self"]["a2"],
                    "borrow_uAsset": self.global_state["self"]["a2u"],
                    "position_mkt": self.global_state["self"]["a1mk"],
                    "borrow_mkt": self.global_state["self"]["a2mk"],
                    "leverage": int(current_leverage)
                }

    def opt_in(self, account_obj: Account):
        local_state = self.indexer_client.lookup_account_application_local_state(account_obj.address, application_id=self.appId)["apps-local-states"]
        if local_state is None:
            # Generate vault account
            vault_pk, vault_addr = account.generate_account()
            vault_signer = AccountTransactionSigner(vault_pk)

            gtx = AtomicTransactionComposer()
            gtx.add_transaction(
                TransactionWithSigner(
                    PaymentTxn(
                        sender=account_obj.address,
                        sp=self.get_suggested_params(),
                        receiver=vault_addr,
                        amt=787_000
                    ),
                    account_obj.signer
                )
            )
            gtx.add_method_call(
                app_id=self.global_state["self"]["manager"],
                on_complete=OnComplete.OptInOC,
                method=self.manager_contract.get_method_by_name("vault"),
                sender=vault_addr,
                sp=self.get_suggested_params(),
                signer=vault_signer,
                method_args=[
                    account_obj.address
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
                app_id=self.global_state["self"]["manager"],
                on_complete=OnComplete.OptInOC,
                method=self.manager_contract.get_method_by_name("user"),
                sender=account_obj.address,
                sp=self.get_suggested_params(),
                signer=account_obj.signer,
                method_args=[
                    vault_addr
                ],
            )
            return gtx

    def quote(self, side: SIDE, amount: float, leverage: float):
        """
        Get the quote for a trade.
        :param side: the side of the trade
        :type side: SIDE
        :param amount: the amount of the trade
        :type amount: float
        :param leverage: the leverage of the trade
        :type leverage: float
        :return: the quote for the trade
        :rtype: dict
        """
        # Update state
        self.update_global_state()

        # Get quote
        if side == SIDE.LONG:
            in_bAsset = amount / (self.global_state["a2mk"]["baer"] / 1e9) * leverage
            swap_in_lf = in_bAsset * (1 - self.global_state["amm"]["sfp"]/1e6)
            swap_out_bamt = self.global_state["amm"]["b1"] * swap_in_lf / (self.global_state["amm"]["b2"] + swap_in_lf)
            swap_out_amt = swap_out_bamt * (self.global_state["a1mk"]["baer"] / 1e9)
            borrow_amt = amount * (leverage - 1)
            liq_price = borrow_amt * self.global_state["self"]["ml"] / (swap_out_amt * (self.global_state["self"]["ml"] - 100))
            price_impact = (((swap_in_lf / swap_out_bamt)/(self.global_state["amm"]["b2"] / self.global_state["amm"]["b1"])) - 1.0) / -1.0

            return Quote(
                amount, swap_out_amt, borrow_amt, liq_price, price_impact, leverage, self.global_state["self"]["a1u"],
                self.global_state["self"]["a1"], self.global_state["self"]["a2u"], self.global_state["self"]["a2"],
                self.global_state["self"]["a2mk"], self.global_state["self"]["a1mk"]
            )

        elif side == SIDE.SHORT:
            in_bAsset = amount / (self.global_state["a1mk"]["baer"] / 1e9) * leverage
            swap_in_lf = in_bAsset * (1 - self.global_state["amm"]["sfp"]/1e6)
            swap_out_bamt = self.global_state["amm"]["b2"] * swap_in_lf / (self.global_state["amm"]["b1"] + swap_in_lf)
            swap_out_amt = swap_out_bamt * (self.global_state["a2mk"]["baer"] / 1e9)
            borrow_amt = amount * (leverage - 1)
            liq_price = 1 / (borrow_amt * self.global_state["self"]["ml"] / (swap_out_amt * (self.global_state["self"]["ml"] - 100)))
            price_impact = (((swap_in_lf / swap_out_bamt)/(self.global_state["amm"]["b1"] / self.global_state["amm"]["b2"])) - 1.0) / -1.0

            return Quote(
                amount, swap_out_amt, borrow_amt, liq_price, price_impact, leverage, self.global_state["self"]["a2u"],
                self.global_state["self"]["a2"], self.global_state["self"]["a1u"], self.global_state["self"]["a1"],
                self.global_state["self"]["a1mk"], self.global_state["self"]["a2mk"]
            )

    def buy(self, quote: Quote, account_obj: Account, gtx: AtomicTransactionComposer = None):
        """
        Buy a perpetual contract.
        :param quote:
        :type quote: Quote
        :param account_obj:
        :type account_obj: Account
        :param gtx:
        :type gtx: AtomicTransactionComposer
        :return:
        :rtype: AtomicTransactionComposer
        """
        # If not currently building a ATC, create one
        if gtx is None:
            gtx = AtomicTransactionComposer()

        gtx.add_transaction(
            TransactionWithSigner(
                AssetTransferTxn(
                    index=quote.in_asset,
                    sender=account_obj.address,
                    sp=self.get_suggested_params(),
                    receiver=self.perpetual_addr,
                    amt=quote.swap_in,
                ),
                account_obj.signer
            )
        )
        # Step 1
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(8),
            method=self.perpetual_contract.get_method_by_name("entry_step_1"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                quote.in_asset,
                quote.in_basset,
                quote.in_mkt,
                self.global_state["self"]["af_manager"],
                self.global_state["self"]["manager"],
                self.global_state["self"]["interface"],
                self.vault_addr,
                quote.leverage
            ]
        )
        # Step 2
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(5),
            method=self.perpetual_contract.get_method_by_name("entry_step_2"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                quote.in_basset,
                quote.out_basset,
                self.global_state["self"]["amm"],
                self.global_state["self"]["lp_manager"],
                self.global_state["self"]["interface"],
                self.global_state["self"]["oracle"],
                quote.out_mkt,
                quote.in_mkt,
                0
            ]
        )
        # Step 3
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(4),
            method=self.perpetual_contract.get_method_by_name("entry_step_3"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                quote.out_basset,
                quote.out_basset,
                quote.out_mkt,
                self.global_state["self"]["af_manager"],
                self.global_state["self"]["manager"],
                self.global_state["self"]["interface"],
                self.vault_addr,
            ]
        )

        return gtx

    def close(self, account_obj: Account, gtx: AtomicTransactionComposer = None):
        """
        Close a position
        :param account_obj:
        :type account_obj: Account
        :param gtx:
        :type gtx: AtomicTransactionComposer
        :return:
        :rtype: AtomicTransactionComposer
        """
        position = self.get_position(account_obj.address)

        # If not currently building a ATC, create one
        if gtx is None:
            gtx = AtomicTransactionComposer()

        # Step 1
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(3),
            method=self.perpetual_contract.get_method_by_name("exit_step_1"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                position["position_asset"],
                position["position_asset"],
                position["position_mkt"],
                self.global_state["self"]["af_manager"],
                self.global_state["self"]["manager"],
                self.global_state["self"]["interface"],
                self.vault_addr,
            ]
        )
        # Step 2
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(5),
            method=self.perpetual_contract.get_method_by_name("exit_step_2"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                position["position_asset"],
                position["borrow_asset"],
                self.global_state["self"]["amm"],
                self.global_state["self"]["lp_manager"],
                self.global_state["self"]["interface"],
                0
            ]
        )
        # Step 3
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(12),
            method=self.perpetual_contract.get_method_by_name("exit_step_3"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                position["borrow_asset"],
                position["borrow_uAsset"],
                position["borrow_mkt"],
                self.global_state["self"]["af_manager"],
                self.global_state["self"]["manager"],
                self.global_state["self"]["interface"],
                self.vault_addr,
            ]
        )

        return gtx

    def liquidate(self, account_obj: Account, target: str, slippage: float = 0.01, gtx: AtomicTransactionComposer = None):

        # Get the target's position
        position = self.get_position(target)
        if position["leverage"] < self.global_state["self"]["ml"]:
            raise Exception("Target position is not liquidatable")

        slippage_adjusted_borrow = int(position["borrow_amt_bAsset"] * (1 + slippage))

        # If not currently building a ATC, create one
        if gtx is None:
            gtx = AtomicTransactionComposer()

        # Pay the borrow
        gtx.add_transaction(
            TransactionWithSigner(
                AssetTransferTxn(
                    sender=account_obj.address,
                    sp=self.get_suggested_params(),
                    receiver=self.perpetual_addr,
                    amt=slippage_adjusted_borrow,
                    index=position["borrow_asset"]
                ),
                account_obj.signer
            )
        )
        # Call the app
        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(5),
            sender=account_obj.address,
            signer=account_obj.signer,
            method=self.perpetual_contract.get_method_by_name("liquidate"),
            method_args=[
                position["position_asset"],
                position["position_asset"],
                position["borrow_asset"],
                position["position_mkt"],
                position["borrow_mkt"],
                self.global_state["self"]["manager"],
                self.global_state["self"]["oracle"],
                target
            ]
        )

        return gtx

    def add(self, uAsset: int, uAsset_amount: int, account_obj: Account, gtx: AtomicTransactionComposer = None):
        """
        Add liquidity.
        :param uAsset:
        :type uAsset: int
        :param amount:
        :type amount: int
        :param account_obj:
        :type account_obj: Account
        :param gtx:
        :type gtx: AtomicTransactionComposer
        :return:
        :rtype: AtomicTransactionComposer
        """
        self.update_local_state(account_obj)

        # If not currently building a ATC, create one
        if gtx is None:
            gtx = AtomicTransactionComposer()

        if uAsset == self.a1u:
            bAsset = self.a1
            market = self.global_state["self"]["a1mk"]
            gtx.add_transaction(
                TransactionWithSigner(
                    PaymentTxn(
                        sender=account_obj.address,
                        sp=self.get_suggested_params(),
                        receiver=self.perpetual_addr,
                        amt=uAsset_amount,
                    ),
                    account_obj.signer
                )
            )
        else:
            bAsset = self.a2
            market = self.global_state["self"]["a2mk"]
            gtx.add_transaction(
                TransactionWithSigner(
                    AssetTransferTxn(
                        index=uAsset,
                        sender=account_obj.address,
                        sp=self.get_suggested_params(),
                        receiver=self.perpetual_addr,
                        amt=uAsset_amount,
                    ),
                    account_obj.signer
                )
            )

        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(9),
            method=self.perpetual_contract.get_method_by_name("add"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                uAsset,
                bAsset,
                market,
                self.global_state["self"]["manager"],
                self.global_state["self"]["af_manager"],
                self.global_state["self"]["interface"],
                self.vault_addr,
            ]
        )

        return gtx

    def remove(self, uAsset: int, uAsset_amount: int, account_obj: Account, gtx: AtomicTransactionComposer = None):
        """
        Remove liquidity.
        :param uAsset:
        :type uAsset: int
        :param amount:
        :type amount: int
        :param account_obj:
        :type account_obj: Account
        :param gtx:
        :type gtx: AtomicTransactionComposer
        :return:
        :rtype: AtomicTransactionComposer
        """
        self.update_local_state(account_obj)

        # If not currently building a ATC, create one
        if gtx is None:
            gtx = AtomicTransactionComposer()

        global_state = self.global_state["self"]
        if uAsset == self.a1u:
            bAsset = self.a1
            market_app_id = global_state["a1mk"]
            bAsset_amount = uAsset_amount / (self.global_state["a1mk"]["baer"] / 1e9)
            supply_share = bAsset_amount * global_state['ta1ss'] / global_state['ta1s']
        else:
            bAsset = self.a2
            market_app_id = global_state["a2mk"]
            bAsset_amount = uAsset_amount / (self.global_state["a2mk"]["baer"] / 1e9)
            supply_share = bAsset_amount * global_state['ta2ss'] / global_state['ta2s']

        gtx.add_method_call(
            app_id=self.appId,
            on_complete=OnComplete.NoOpOC,
            sp=self.get_suggested_params(10),
            method=self.perpetual_contract.get_method_by_name("remove"),
            sender=account_obj.address,
            signer=account_obj.signer,
            method_args=[
                uAsset,
                bAsset,
                market_app_id,
                global_state["manager"],
                global_state["af_manager"],
                global_state["interface"],
                self.vault_addr,
                int(supply_share),
            ]
        )

        return gtx
