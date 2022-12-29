import os
import json
from algosdk.v2client.algod import AlgodClient
from algosdk.v2client.indexer import IndexerClient
from algosdk.atomic_transaction_composer import AccountTransactionSigner
from .perpetual import Perpetual


class Client:
    def __init__(self, algod_client: AlgodClient, indexer_client: IndexerClient, address: str,
                 signer: AccountTransactionSigner, network: str):
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
        self.signer = signer

    def get_perpetual(self, symbol):
        """ Returns Perpetual object for the symbol
        :param symbol: a string for the symbol of the perpetual
        :type symbol: str
        :return: a class:`Perpetual` object for the symbol
        :rtype: class:`Perpetual`
        """
        # Get info from json file
        path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(path, "contracts.json"), 'r') as contracts_file:
            json_file = json.load(contracts_file)[self.network]
            contract_info = json_file[symbol]

        appID = contract_info["appID"]
        return Perpetual(self.algod, self.indexer, self.network, appID, symbol)


class TestnetClient(Client):
    def __init__(self, algod_client=None, indexer_client=None, address=None, signer=None):
        if algod_client is None:
            algod_client = AlgodClient("", "https://node.testnet.algoexplorerapi.io", headers={"User-Agent": "algosdk"})
        if indexer_client is None:
            indexer_client = IndexerClient("", "https://algoindexer.testnet.algoexplorerapi.io",
                                           headers={"User-Agent": "algosdk"})
        super().__init__(algod_client, indexer_client, address, signer, network="testnet")


class MainnetClient(Client):
    def __init__(self, algod_client=None, indexer_client=None, address=None, signer=None):
        if algod_client is None:
            algod_client = AlgodClient("", "https://node.algoexplorerapi.io", headers={"User-Agent": "algosdk"})
        if indexer_client is None:
            indexer_client = IndexerClient("", "https://algoindexer.algoexplorerapi.io",
                                           headers={"User-Agent": "algosdk"})
        super().__init__(algod_client, indexer_client, address, signer, network="mainnet")