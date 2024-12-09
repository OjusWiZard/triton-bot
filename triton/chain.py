import datetime
import json
import logging
import math
import os
from pathlib import Path
from typing import Optional

import dotenv
import requests
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from web3 import Web3
from web3.contract import Contract

from triton.constants import (GNOSIS_CHAIN_ID, OLAS_TOKEN_ADDRESS_GNOSIS,
                              SAFE_SERVICE_URL_GNOSIS, STAKING_CONTRACTS)
from triton.tools import wei_to_olas

logger = logging.getLogger("chain")

dotenv.load_dotenv(override=True)

GNOSIS_RPC = os.getenv("GNOSIS_RPC")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Instantiate the web3 provider and ethereum client
web3 = Web3(Web3.HTTPProvider(GNOSIS_RPC))
ethereum_client = EthereumClient(GNOSIS_RPC)


def get_native_balance(address: str):
    """Get the native balance"""
    balance_wei = web3.eth.get_balance(address)
    balance_ether = web3.from_wei(balance_wei, "ether")
    return balance_ether


def load_contract(
    contract_address: str, abi_file: str, has_abi_key: bool = True
) -> Contract:
    """Load a smart contract"""
    with open(Path("abis", f"{abi_file}.json"), "r", encoding="utf-8") as abi_file:
        contract_abi = json.load(abi_file)
        if has_abi_key:
            contract_abi = contract_abi["abi"]

    contract = web3.eth.contract(address=contract_address, abi=contract_abi)
    return contract


def claim_rewards(
    staking_token_address, signer_address: str, signer_pkey: str, service_id: int
):
    """Claim staking rewards"""

    account = web3.eth.account.from_key(signer_pkey)
    staking_token_contract = load_contract(
        web3.to_checksum_address(staking_token_address), "staking_token"
    )

    # Build the request transaction
    function = staking_token_contract.functions.claim(service_id)
    claim_transaction = function.build_transaction(
        {
            "chainId": GNOSIS_CHAIN_ID,
            "gas": 100000,
            "gasPrice": web3.to_wei("3", "gwei"),
            "nonce": web3.eth.get_transaction_count(
                web3.to_checksum_address(signer_address)
            ),
        }
    )

    signed_tx = web3.eth.account.sign_transaction(claim_transaction, signer_pkey)
    try:
        tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    except Exception:
        pass


def get_olas_balance(address: str):
    """ "Get OLAS balance"""
    olas_token_contract = load_contract(OLAS_TOKEN_ADDRESS_GNOSIS, "olas", False)
    olas_balance = olas_token_contract.functions.balanceOf(address).call()
    return olas_balance


def transfer_olas(
    safe_address: str, signer_pkey: str, recipient_address: str
) -> Optional[float]:
    """Transfer OLAS"""

    safe_address = web3.to_checksum_address(safe_address)
    recipient_address = web3.to_checksum_address(recipient_address)

    olas_token_contract = load_contract(OLAS_TOKEN_ADDRESS_GNOSIS, "olas", False)

    # Get the balance
    olas_balance = get_olas_balance(safe_address)
    olas_price = get_olas_price()
    olas_value = olas_price * olas_balance / 1e18

    logger.info(
        f"Transfering {olas_balance/1e18:.2f} OLAS from {safe_address} to {recipient_address}"
    )

    # Get the safe nonce
    response = requests.get(
        url=f"{SAFE_SERVICE_URL_GNOSIS}/api/v1/safes/{safe_address}/", timeout=60
    )
    safe_nonce = response.json()["nonce"]

    # Build the request transaction
    function = olas_token_contract.functions.transfer(recipient_address, olas_balance)
    data = function.build_transaction(
        {
            "chainId": GNOSIS_CHAIN_ID,
            "gas": 100000,
            "gasPrice": web3.to_wei("3", "gwei"),
            "nonce": safe_nonce,
        }
    )["data"]

    # Get the safe
    safe = Safe(safe_address, ethereum_client)

    # Build, sign and send the safe transaction
    safe_tx = safe.build_multisig_tx(
        to=OLAS_TOKEN_ADDRESS_GNOSIS,
        value=0,
        data=bytes.fromhex(data[2:]),
        operation=0,
        safe_tx_gas=100000,
        base_gas=0,
        gas_price=int(1e9),
        gas_token="0x0000000000000000000000000000000000000000",
        refund_receiver="0x0000000000000000000000000000000000000000",
    )
    safe_tx.sign(signer_pkey)
    try:
        safe_tx.execute(signer_pkey)
        return olas_value
    except Exception:
        return None


def get_staking_status(
    mech_contract_address: str,
    staking_token_address: str,
    activity_checker_address: str,
    service_id: str,
    safe_address: str,
) -> dict:
    """Get the staking status"""
    mech_contract = load_contract(mech_contract_address, "mech", has_abi_key=False)
    staking_token_contract = load_contract(staking_token_address, "staking_token")
    activity_checker_contract = load_contract(activity_checker_address, "mech_activity")

    # Rewards
    service_info = staking_token_contract.functions.mapServiceInfo(service_id).call()
    accrued_rewards = wei_to_olas(service_info[3])

    # Request count (total)
    mech_request_count = mech_contract.functions.getRequestsCount(safe_address).call()

    # Request count (last checkpoint)
    service_info = (
        staking_token_contract.functions.getServiceInfo(service_id).call()
    )[2]
    mech_request_count_on_last_checkpoint = service_info[1] if service_info else 0

    # Request count (current epoch)
    mech_requests_this_epoch = (
        mech_request_count - mech_request_count_on_last_checkpoint
    )

    # Required requests
    liveness_ratio = activity_checker_contract.functions.livenessRatio().call()
    mech_requests_24h_threshold = math.ceil((liveness_ratio * 60 * 60 * 24) / 10**18)

    # Epoch end
    liveness_period = staking_token_contract.functions.livenessPeriod().call()
    checkpoint_ts = staking_token_contract.functions.tsCheckpoint().call()
    epoch_end = datetime.datetime.fromtimestamp(checkpoint_ts + liveness_period)

    return {
        "accrued_rewards": accrued_rewards,
        "mech_requests_this_epoch": mech_requests_this_epoch,
        "required_mech_requests": mech_requests_24h_threshold,
        "epoch_end": epoch_end.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_olas_price() -> float:
    """Get OLAS price"""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids=autonolas&vs_currencies=eur&x_cg_demo_api_key={COINGECKO_API_KEY}"
    headers = {"accept": "application/json"}
    response = requests.get(url=url, headers=headers, timeout=30)
    if response.status_code != 200:
        logger.error(response)
        return None
    price = response.json()["autonolas"]["eur"]
    return price


def get_slots() -> dict:
    """Get the available slots in all staking contracts"""
    slots = {}

    for contract_name, contract_data in STAKING_CONTRACTS.items():
        staking_token_contract = load_contract(
            web3.to_checksum_address(contract_data["address"]), "staking_token"
        )
        ids = staking_token_contract.functions.getServiceIds().call()
        slots[contract_name] = contract_data["slots"] - len(ids)

    return slots
