import datetime
import json
import logging
import math
import os
from pathlib import Path

import dotenv
import pytz
import requests
from web3 import Web3
from web3.contract import Contract

from triton.constants import (
    LOCAL_TIMEZONE,
    OLAS_TOKEN_ADDRESS_GNOSIS,
    STAKING_CONTRACTS,
)
from triton.tools import wei_to_olas

logger = logging.getLogger("chain")

dotenv.load_dotenv(override=True)

GNOSIS_RPC = os.getenv("GNOSIS_RPC")
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")

# Instantiate the web3 provider and ethereum client
web3 = Web3(Web3.HTTPProvider(GNOSIS_RPC))


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


def get_olas_balance(address: str):
    """ "Get OLAS balance"""
    olas_token_contract = load_contract(OLAS_TOKEN_ADDRESS_GNOSIS, "olas", False)
    olas_balance = olas_token_contract.functions.balanceOf(address).call()
    return olas_balance


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
    service_info = (staking_token_contract.functions.getServiceInfo(service_id).call())[
        2
    ]
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
    epoch_end = datetime.datetime.fromtimestamp(
        checkpoint_ts + liveness_period,
        pytz.timezone(LOCAL_TIMEZONE),
    )

    return {
        "accrued_rewards": accrued_rewards,
        "mech_requests_this_epoch": mech_requests_this_epoch,
        "required_mech_requests": mech_requests_24h_threshold,
        "epoch_end": epoch_end.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def get_olas_price() -> float:
    """Get OLAS price"""
    url = f"https://api.coingecko.com/api/v3/simple/price?ids=autonolas&vs_currencies=usd&x_cg_demo_api_key={COINGECKO_API_KEY}"
    headers = {"accept": "application/json"}
    response = requests.get(url=url, headers=headers, timeout=30)
    if response.status_code != 200:
        logger.error(response)
        return None
    price = response.json()["autonolas"]["usd"]
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
