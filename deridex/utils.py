import os
import json
from algosdk.future.transaction import assign_group_id, ApplicationNoOpTxn
from algosdk.error import AlgodHTTPError
from algosdk.encoding import encode_address
from base64 import b64decode, b64encode


# contracts abspath
my_path = os.path.abspath(os.path.dirname(__file__))
OPTIONS_CONTRACTS_FPATH = os.path.join(my_path, "options/v1/contracts.json")


def get_option_app_id(network, symbol):
    """Returns option app id of symbol for the specified network. Pulled from hardcoded values in contracts.json.
    :param network: network to query data for
    :type network: string e.g. 'testnet'
    :param symbol: symbol to get option data for
    :type symbol: string e.g. 'cALGO-STBL'
    :return: option app id
    :rtype: int
    """
    with open(OPTIONS_CONTRACTS_FPATH, 'r') as contracts_file:
        json_file = json.load(contracts_file)[network]
        return json_file['contracts'][symbol]["appId"]


def format_state(state):
    """Returns state dict formatted to human-readable strings
    :param state: dict of state returned by read_local_state or read_global_state
    :type state: dict
    :return: dict of state with keys + values formatted from bytes to utf-8 strings
    :rtype: dict
    """
    formatted_state = {}
    for item in state:
        key = item["key"]
        value = item["value"]
        try:
            formatted_key = b64decode(key).decode("utf-8")
        except:
            formatted_key = b64decode(key)
        if value["type"] == 1:
            # byte string
            try:
                formatted_state[formatted_key] = b64decode(value["bytes"]).decode("utf-8")
            except:
                formatted_state[formatted_key] = value["bytes"]
        else:
            # integer
            formatted_state[formatted_key] = value["uint"]
    return formatted_state


def read_global_state(indexer_client, app_id, block=None):
    """Returns dict of global state for application with the given app_id
    :param indexer_client: indexer client
    :type indexer_client: :class:`IndexerClient`
    :param app_id: id of the application
    :type app_id: int
    :param block: block at which to query historical data
    :type block: int, optional
    :return: dict of global state for application with id app_id
    :rtype: dict
    """

    try:
        application_info = indexer_client.applications(app_id, round_num=block).get("application", {})
    except:
        raise Exception("Application does not exist.")
    return format_state(application_info["params"]["global-state"])


def read_local_state(indexer_client, address, app_id, block=None):
    """Returns dict of local state for address for application with id app_id
    :param indexer_client: indexer client
    :type indexer_client: :class:`IndexerClient`
    :param address: address of account for which to get state
    :type address: string
    :param app_id: id of the application
    :type app_id: int
    :param block: block at which to get the historical local state
    :type block: int, optional
    :return: dict of local state of address for application with id app_id
    :rtype: dict
    """

    try:
        results = indexer_client.account_info(address, round_num=block).get("account", {})
    except:
        raise Exception("Account does not exist.")

    for local_state in results['apps-local-state']:
        if local_state['id'] == app_id:
            if 'key-value' not in local_state:
                return {}
            return format_state(local_state['key-value'])
    return {}


def wait_for_confirmation(client, txid):
    """Waits for a transaction with id txid to complete. Returns dict with transaction information
    after completion.
    :param client: algod client
    :type client: :class:`AlgodClient`
    :param txid: id of the sent transaction
    :type txid: string
    :return: dict of transaction information
    :rtype: dict
    """
    last_round = client.status().get('last-round')
    txinfo = client.pending_transaction_info(txid)
    while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
        print("Waiting for confirmation")
        last_round += 1
        client.status_after_block(last_round)
        txinfo = client.pending_transaction_info(txid)
    txinfo['txid'] = txid
    print("Transaction {} confirmed in round {}.".format(txid, txinfo.get('confirmed-round')))
    return txinfo


class TransactionGroup:

    def __init__(self, transactions):
        """Constructor method for :class:`TransactionGroup` class
        :param transactions: list of unsigned transactions
        :type transactions: list
        """
        transactions = assign_group_id(transactions)
        self.transactions = transactions
        self.signed_transactions = [None for _ in self.transactions]

    def sign_with_private_key(self, private_key):
        """Signs the transactions with specified private key and saves to class state
        :param private_key: private key of user
        :type private_key: string
        """
        for i, txn in enumerate(self.transactions):
            self.signed_transactions[i] = txn.sign(private_key)

    def sign_with_private_keys(self, private_keys):
        """Signs the transactions with specified list of private keys and saves to class state
        :param private_key: private key of user
        :type private_key: string
        """
        assert (len(private_keys) == len(self.transactions))
        for i, txn in enumerate(self.transactions):
            self.signed_transactions[i] = txn.sign(private_keys[i])

    def submit(self, algod, wait=False):
        """Submits the signed transactions to network using the algod client
        :param algod: algod client
        :type algod: :class:`AlgodClient`
        :param wait: wait for txn to complete, defaults to False
        :type wait: boolean, optional
        :return: dict of transaction id
        :rtype: dict
        """
        try:
            txid = algod.send_transactions(self.signed_transactions)
        except AlgodHTTPError as e:
            raise Exception(str(e))
        if wait:
            return wait_for_confirmation(algod, txid)
        return {'txid': txid}