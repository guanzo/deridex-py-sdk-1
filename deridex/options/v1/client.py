from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient

from .config import OptionType
from .option import Option


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

