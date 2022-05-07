from deridex.options.v1.client import TestnetClient
from deridex.options.v1.config import OptionType


client = TestnetClient()
option = client.get_option(OptionType.CALL, underlying_asset="ALGO", collateral_asset="tUSD")
print(option.global_state)