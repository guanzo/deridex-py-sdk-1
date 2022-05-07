from .config import OptionType
from ...utils import read_global_state, get_option_app_id


class Option:
    def __init__(self, algod_client, indexer_client, network, option_type, underlying_asset, collateral_asset):
        """ Contructor class for option pools
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
        self.option_type = option_type
        self.underlying = underlying_asset
        self.collateral = collateral_asset

        if option_type == OptionType.CALL:
            ot = "c"
        elif option_type == OptionType.PUT:
            ot = "p"
        else:
            raise Exception("Malformed option_type")

        self.symbol = f"{ot}{underlying_asset}-{collateral_asset}"

        self.global_state = read_global_state(
            self.indexer,
            get_option_app_id(network, self.symbol)
        )
        self.local_state = {}

    def get_local_state(self, ):
        pass

    # User Functions
    def create(self, address):
        pass

    def execute(self, address):
        pass

    def mint(self, address, collateral_to):
        pass

    def burn(self, address, pool_to):
        pass

