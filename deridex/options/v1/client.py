import os
import json
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from .config import OptionType
from .option import Option

# contracts abspath
my_path = os.path.abspath(os.path.dirname(__file__))
OPTIONS_CONTRACTS_FPATH = os.path.join(my_path, "contracts.json")


class Client:
    def __init__(self, algod_client: AlgodClient, indexer_client: IndexerClient, address: str, network: str):
        """Constructor method for generic client

        :param algod_client: a class:`AlgodClient` for interacting with the network
        :type algod_client: class:`AlgodClient`
        :param indexer_client: a class:`IndexerClient` for interacting with the network
        :type indexer_client: class:`IndexerClient`
        :param address: user address
        :type address: str
        :param network: what network to connect to
        :type network: str
        """
        self.address = address
        self.algod = algod_client
        self.indexer = indexer_client
        self.network = network

    def get_default_params(self):
        """Initializes the transactions parameters for the client.
        """
        params = self.algod.suggested_params()
        params.flat_fee = True
        params.fee = 1000
        return params

    def get_option(self, option_type, underlying_asset, collateral_asset):
        """ Returns option object for the underlying_asset and collateral_asset pair
        :param option_type: a class:`OptionType` object for the type of option (e.g. call or put)
        :type option_type: class:`OptionType`
        :param underlying_asset: asset that the option is tracked against
        :type underlying_asset: str
        :param collateral_asset: asset used as pool collateral for the option
        :type collateral_asset: str
        :return: a class:`Option` object for the option_type, underlying_asset and collateral_asset
        :rtype: class:`Option`
        """
        return Option(self.algod, self.indexer, self.network, option_type, underlying_asset, collateral_asset)

    def get_positions(self):
        # Pull contract info
        with open(OPTIONS_CONTRACTS_FPATH, 'r') as contracts_file:
            json_file = json.load(contracts_file)[self.network]['contracts']

        # Iterate through known contracts and initialize option objects
        options = []
        for key, value in json_file.items():
            option_type = OptionType.CALL if key[0] == 'c' else OptionType.PUT

            if value['assetId'] == 0:
                underlying_asset = 'ALGO'
            else:
                underlying_asset = self.indexer.asset_info(value['assetId'])['asset']['params']['unit-name']

            if value['collateralAssetId'] == 0:
                collateralAsset = 'ALGO'
            else:
                collateralAsset = self.indexer.asset_info(value['collateralAssetId'])['asset']['params']['unit-name']

            option = self.get_option(option_type, underlying_asset, collateralAsset)
            try:
                option.update_local_state(self.address)
            except KeyError:
                pass

            # Add option object to return param if local state
            if len(option.local_state) != 0:  # If has local state
                if option.local_state['created'] != 0:  # If in current position
                    options.append(option)

        return options


class TestnetClient(Client):
    def __init__(self, algod_client=None, indexer_client=None, address=None):
        if algod_client is None:
            algod_client = AlgodClient("", "https://node.testnet.algoexplorerapi.io", headers={"User-Agent": "algosdk"})
        if indexer_client is None:
            indexer_client = IndexerClient("", "https://algoindexer.testnet.algoexplorerapi.io",
                                           headers={"User-Agent": "algosdk"})
        super().__init__(algod_client, indexer_client, address, network="testnet")


class MainnetClient(Client):
    def __init__(self, algod_client=None, indexer_client=None, address=None):
        if algod_client is None:
            algod_client = AlgodClient("", "https://node.algoexplorerapi.io", headers={"User-Agent": "algosdk"})
        if indexer_client is None:
            indexer_client = IndexerClient("", "https://algoindexer.algoexplorerapi.io",
                                           headers={"User-Agent": "algosdk"})
        super().__init__(algod_client, indexer_client, address, network="mainnet")

