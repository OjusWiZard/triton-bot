import json
import logging
import os
import time
from pathlib import Path
from threading import Thread
from typing import Tuple

import dotenv

from triton.chain import (claim_rewards, get_native_balance, get_olas_balance,
                          get_staking_status, transfer_olas)
from triton.key_manager import KeyManager
from triton.tools import load_env_to_dict

dotenv.load_dotenv(override=True)


class Trader:
    """Trader"""

    def __init__(self, name: str, repo_path: Path) -> None:
        """Constructor"""

        self.name = name
        self.stop_flag = False
        self.staking_thread = None
        self.logger = logging.getLogger(name)

        trader_folder = repo_path / ".trader_runner"
        self.key_manager = KeyManager(trader_folder)
        self.agent_address, self.agent_pkey = self.key_manager.get_keys("agent")
        self.operator_address, self.operator_pkey = self.key_manager.get_keys(
            "operator"
        )

        with open(trader_folder / "service_id.txt", "r", encoding="utf-8") as file:
            self.service_id = int(file.readline().strip())

        with open(
            trader_folder / "service_safe_address.txt", "r", encoding="utf-8"
        ) as file:
            self.service_safe_address = file.readline().strip()

        env_vars = load_env_to_dict(trader_folder / ".env")
        self.staking_program = env_vars["STAKING_PROGRAM"]
        self.agent_id = int(env_vars["AGENT_ID"])
        self.staking_contract_address = env_vars["CUSTOM_STAKING_ADDRESS"]
        self.mech_contract_address = env_vars["MECH_CONTRACT_ADDRESS"]
        self.mech_activity_checker_contract_address = env_vars[
            "MECH_ACTIVITY_CHECKER_CONTRACT"
        ]
        self.withdrawal_address = os.getenv("WITHDRAWAL_ADDRESS", None)

    def get_staking_status(self) -> dict:
        """Get the staking status"""
        self.logger.info("Checking staking status")
        return get_staking_status(
            mech_contract_address=self.mech_contract_address,
            staking_token_address=self.staking_contract_address,
            activity_checker_address=self.mech_activity_checker_contract_address,
            service_id=self.service_id,
            safe_address=self.service_safe_address,
        )

    def check_balance(self) -> dict:
        """Check the native balance"""
        agent_native_balance = get_native_balance(self.agent_address)
        safe_native_balance = get_native_balance(self.service_safe_address)
        operator_native_balance = get_native_balance(self.operator_address)
        safe_olas_balance = get_olas_balance(self.service_safe_address) / 1e18

        self.logger.info(
            "Agent balance = %.2f xDAI | Safe balance: %.2f xDAI  %.2f OLAS | Operator balance: %.2f xDAI",
            agent_native_balance,
            safe_native_balance,
            safe_olas_balance,
            operator_native_balance,
        )

        return {
            "agent_native_balance": agent_native_balance,
            "safe_native_balance": safe_native_balance,
            "safe_olas_balance": safe_olas_balance,
            "operator_native_balance": operator_native_balance,
        }

    def claim_rewards(self) -> None:
        """Claim staking rewards"""

        self.logger.info("Claiming rewards")
        claim_rewards(
            self.staking_contract_address,
            self.operator_address,
            self.operator_pkey,
            self.service_id,
        )

    def withdraw_rewards(self) -> Tuple[bool, float]:
        """Withdraw staking rewards"""

        if not self.withdrawal_address:
            return False, 0

        self.logger.info("Withdrawing rewards")
        olas_value = transfer_olas(
            self.service_safe_address, self.agent_pkey, self.withdrawal_address
        )

        if not olas_value:
            return False, 0

        return True, olas_value
