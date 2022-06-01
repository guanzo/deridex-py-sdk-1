import math
from algosdk.future.transaction import ApplicationNoOpTxn, AssetTransferTxn, ApplicationOptInTxn
from algosdk import encoding, logic

from .config import OptionType
from .contract_strings import OptionStrings, DataStrings
from ...utils import read_global_state, read_local_state, get_option_app_id, format_state


class Option:
    def __init__(self, algod_client, indexer_client, network, option_type, underlying_asset, collateral_asset):
        """Contructor class for option pools
        :param algod_client: a class:`AlgodClient` for interacting with the network
        :type algod_client: class:`AlgodClient`
        :param indexer_client: a class:`IndexerClient` for interacting with the network
        :type indexer_client: class:`IndexerClient`
        :param option_type: a class:`OptionType` object for the type of option (e.g. call or put)
        :type option_type: class:`OptionType`
        :param underlying_asset: asset that the option is tracked against
        :type underlying_asset: str
        :param collateral_asset: asset used as pool collateral for the option
        :type collateral_asset: str
        :param network: what network to connect to
        :type network: str
        """
        self.algod = algod_client
        self.indexer = indexer_client
        self.network = network
        self.option_type = option_type
        self.underlying_asset = underlying_asset
        self.underlying_asset_id = 0
        self.collateral_asset = collateral_asset

        if option_type == OptionType.CALL:
            ot = "c"
        elif option_type == OptionType.PUT:
            ot = "p"
        else:
            raise Exception("Malformed option_type")

        self.symbol = f"{ot}{underlying_asset}-{collateral_asset}-CASH"

        self.appId = get_option_app_id(self.network, self.symbol)
        self.appAddr = logic.get_application_address(self.appId)

        option_global_state = read_global_state(self.indexer, self.appId)
        data_global_state = read_global_state(self.indexer, option_global_state['data'])
        oracle_global_state = read_global_state(self.indexer, data_global_state['oracle'])

        self.global_states = {
            "option":option_global_state,
            "data": data_global_state,
            "oracle": oracle_global_state
        }
        self.local_state = {}

    def __repr__(self):
        return f"Option('{self.symbol}')"

    def __str__(self):
        return f"Option('{self.symbol}')"

    def update_global_state(self):
        option_global_state = read_global_state(self.indexer, self.appId)
        data_global_state = read_global_state(self.indexer, option_global_state['data'])
        oracle_global_state = read_global_state(self.indexer, data_global_state['oracle'])

        self.global_states = {
            "option": option_global_state,
            "data": data_global_state,
            "oracle": oracle_global_state
        }

    def update_local_state(self, address):
        self.local_state = read_local_state(self.indexer, address, self.appId)

    def get_open_contracts(self):
        results = {}
        accounts = self.indexer.accounts(application_id=self.appId)["accounts"]
        for account in accounts:
            address = account["address"]
            for app in account["apps-local-state"]:
                if app["id"] == self.appId:
                    state = format_state(app["key-value"])
                    if state["created"] > 0:
                        results[address] = state
                    break
        return results

    def get_default_params(self):
        """Initializes the transactions parameters for the client.
        """
        params = self.algod.suggested_params()
        params.flat_fee = True
        params.fee = 1000
        return params

    def opt_in(self, address):
        local_state = self.indexer.lookup_account_application_local_state(address, application_id=self.appId)["apps-local-states"]
        if local_state is None:
            return ApplicationOptInTxn(
                sender=address,
                sp=self.get_default_params(),
                index=self.appId,
            )
        else:
            return None

    # User Functions
    def quote(self, size, length):
        # Update global state
        self.update_global_state()

        # Calculate contract cost
        price = self.global_states["oracle"]["latest_price"] / 1_000_000
        adjusted_size = size / self.global_states["option"]["contract_scale"]
        if self.option_type == OptionType.CALL:
            std = self.global_states["data"]["pstd"] / 1_000_000
        else:
            std = self.global_states["data"]["nstd"] / 1_000_000
        premium = adjusted_size * price * math.sqrt(length) * std
        executor_reserve = adjusted_size * price * (self.global_states["option"]["executor_fee"] / 1_000_000)
        protocol_fee = adjusted_size * price * (self.global_states["option"]["protocol_fee"] / 1_000_000)
        return int((premium + executor_reserve + protocol_fee) * 1_000_000)

    def available_collateral(self):
        assets = self.indexer.account_info(self.appAddr)["account"]["assets"]
        for asset in assets:
            if asset["asset-id"] == self.global_states["option"]["cid"]:
                total = asset["amount"]
                break
        locked = self.global_states["option"]["locked"]
        return total - locked

    def create(self, address, size, length, payment, atomic_group=None):
        """Create new option contract
        :param address: user address
        :type address: str
        :param size: amount of underlying asset to write against
        :type size: int
        :param length: number of days before expiration
        :type length: int
        :param payment: max amount of collateral asset to pay
        :type payment: int
        :param atomic_group: list of previous transactions to group
        :type atomic_group: list
        :return:
        """
        # Update global state
        self.update_global_state()

        # Get network params
        suggested_params = self.get_default_params()
        suggested_params.flat_fee = True
        suggested_params.fee = 1000

        suggested_params_no_op = self.get_default_params()
        suggested_params_no_op.flat_fee = True
        suggested_params_no_op.fee = 8000

        # Get txn vars
        app_args = [OptionStrings.create.encode(), size, length]
        accounts = [self.global_states["option"]["treasury"]]
        foreign_assets = [self.global_states["option"]["cid"]]
        # Data, dummy, oracle
        foreign_apps = [
            int(self.global_states["option"]["data"]),
            int(self.global_states["data"]["dummy"]),
            int(self.global_states["data"]["oracle"])
        ]

        # Calculate contract cost
        price = self.global_states["oracle"]["latest_price"]/1_000_000
        adjusted_size = size/self.global_states["option"]["contract_scale"]
        if self.option_type == OptionType.CALL:
            std = self.global_states["data"]["pstd"]/1_000_000
        else:
            std = self.global_states["data"]["nstd"]/1_000_000
        premium = adjusted_size * price * math.sqrt(length) * std
        executor_reserve = adjusted_size * price * (self.global_states["option"]["executor_fee"]/1_000_000)
        protocol_fee = adjusted_size * price * (self.global_states["option"]["protocol_fee"] / 1_000_000)
        cost = int((premium + executor_reserve + protocol_fee) * 1_000_000)
        # Error out if not enough payment
        if payment < cost:
            raise Exception(f"Cost exceeds payment provided. Cost: {cost} | Payment: {payment}")

        txn0 = ApplicationNoOpTxn(
            sender=address,
            sp=suggested_params_no_op,
            index=self.appId,
            app_args=app_args,
            accounts=accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
        )

        txn1 = AssetTransferTxn(
            sender=address,
            sp=suggested_params,
            receiver=self.appAddr,
            amt=payment,
            index=int(self.global_states["option"]["cid"]),
        )
        optin_tx = self.opt_in(address)
        if atomic_group:
            # If opted in
            if optin_tx is None:
                return atomic_group + [txn0, txn1]
            else:
                return atomic_group + [optin_tx, txn0, txn1]
        else:
            if optin_tx is None:
                return [txn0, txn1]
            else:
                return [optin_tx, txn0, txn1]

    def execute(self, address, target, atomic_group=None):
        # Update global state
        self.update_global_state()

        # Get network params
        suggested_params_no_op = self.get_default_params()
        suggested_params_no_op.flat_fee = True
        suggested_params_no_op.fee = 5000

        # Get txn vars
        app_args = [OptionStrings.execute.encode()]
        foreign_assets = [int(self.global_states["option"]["cid"])]
        foreign_accounts = [target]
        # Data, dummy, oracle
        foreign_apps = [
            int(self.global_states["option"]["data"]),
            int(self.global_states["data"]["dummy"]),
            int(self.global_states["data"]["oracle"])
        ]

        txn0 = ApplicationNoOpTxn(
            sender=address,
            sp=suggested_params_no_op,
            index=self.appId,
            app_args=app_args,
            accounts=foreign_accounts,
            foreign_apps=foreign_apps,
            foreign_assets=foreign_assets,
        )

        if atomic_group:
            return atomic_group + [txn0]
        else:
            return [txn0]

    def mint(self, address, collateral_to, atomic_group=None):
        # Update global state
        self.update_global_state()

        # Get network params
        suggested_params = self.get_default_params()
        suggested_params.flat_fee = True
        suggested_params.fee = 1000

        suggested_params_no_op = self.get_default_params()
        suggested_params_no_op.flat_fee = True
        suggested_params_no_op.fee = 4000

        # Get txn vars
        app_args = [OptionStrings.mint.encode()]
        foreign_assets = [
            int(self.global_states["option"]["cid"]),
            int(self.global_states["option"]["token"]),
        ]
        # Data, dummy, oracle
        foreign_apps = [
            int(self.global_states["option"]["data"]),
            int(self.global_states["data"]["dummy"]),
            int(self.global_states["data"]["oracle"])
        ]

        txn0 = ApplicationNoOpTxn(
            sender=address,
            sp=suggested_params_no_op,
            index=self.appId,
            app_args=app_args,
            foreign_assets=foreign_assets,
            foreign_apps=foreign_apps,
        )

        txn1 = AssetTransferTxn(
            sender=address,
            sp=suggested_params,
            receiver=self.appAddr,
            amt=collateral_to,
            index=int(self.global_states["option"]["cid"]),
        )
        if atomic_group:
            return atomic_group + [txn0, txn1]
        else:
            return [txn0, txn1]

    def burn(self, address, pool_to, atomic_group=None):
        # Update global state
        self.update_global_state()

        # Get network params
        suggested_params = self.get_default_params()
        suggested_params.flat_fee = True
        suggested_params.fee = 1000

        suggested_params_no_op = self.get_default_params()
        suggested_params_no_op.flat_fee = True
        suggested_params_no_op.fee = 4000

        # Get txn vars
        app_args = [OptionStrings.burn.encode()]
        foreign_assets = [
            int(self.global_states["option"]["cid"]),
            int(self.global_states["option"]["token"]),
        ]
        # Data, dummy, oracle
        foreign_apps = [
            int(self.global_states["option"]["data"]),
            int(self.global_states["data"]["dummy"]),
            int(self.global_states["data"]["oracle"])
        ]

        txn0 = ApplicationNoOpTxn(
            sender=address,
            sp=suggested_params_no_op,
            index=self.appId,
            app_args=app_args,
            foreign_assets=foreign_assets,
            foreign_apps=foreign_apps,
        )

        txn1 = AssetTransferTxn(
            sender=address,
            sp=suggested_params,
            receiver=self.appAddr,
            amt=pool_to,
            index=int(self.global_states["option"]["token"]),
        )
        if atomic_group:
            return atomic_group + [txn0, txn1]
        else:
            return [txn0, txn1]

