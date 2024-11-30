import getpass
import json
import os
import tempfile
from pathlib import Path
from typing import Tuple

import click
import yaml
from aea_ledger_ethereum.ethereum import EthereumCrypto


class KeyManager:
    """KeyManager"""

    def __init__(self, path: Path):
        """Constructor"""
        self.path = path
        self.json_keys = {
            "agent": path / "keys.json",
            "operator": path / "operator_keys.json",
        }

        with open(path / "keys.json", "r", encoding="utf-8") as file:
            keys = json.load(file)
            agent_pkey = keys[0]["private_key"]
            self.encrypted = agent_pkey.startswith("{")

    def get_keys(self, tag: str, password: str = None) -> Tuple[str, str]:
        """Get the keys"""

        if not password:
            password = os.getenv("KEY_PASSWORD")

        if self.encrypted:
            with tempfile.TemporaryDirectory() as temp_dir:

                # Load the encrypted keys
                keys = json.load(self.json_keys[tag].open("r"))

                # Write the encrypted private key to a temp file
                temp_file = Path(temp_dir, "0")
                temp_file.open("w+", encoding="utf-8").write(
                    str(keys[0]["private_key"])
                )

                # Decrypt the private key
                crypto = EthereumCrypto.load_private_key_from_path(temp_file, password)
                address = crypto.address
                pkey = crypto.key.hex()[2:]
                return address, pkey

        keys = json.load(self.json_keys[tag].open("r"))[0]
        address = keys["address"]
        pkey = keys["private_key"]
        return address, pkey

    def decrypt(self, password: str = None) -> str:
        """Decrypt the private keys"""

        if not self.encrypted:
            return

        if not password:
            password = os.getenv("KEY_PASSWORD")

        for key_name, key_path in self.json_keys.items():

            # Load the encrypted data
            json_data = json.load(key_path.open("r"))

            # Get the ecnrypted private key
            encrypted_pkey = json.loads(json_data[0]["private_key"])

            # Decrypt the private key
            decrypted_pkey = EthereumCrypto.decrypt(encrypted_pkey, password=password)

            # Build the decrypted json
            decrypted_json_keys = [
                {
                    "address": json_data[0]["address"],
                    "private_key": "0x" + decrypted_pkey,
                    "ledger": "ethereum",
                }
            ]

            # Write the decrypted json to file
            self.write_key_to_file(decrypted_json_keys, key_path)

            # Also update txts
            if key_name == "agent":
                self.write_key_to_file(decrypted_pkey, self.path / "agent_pkey.txt")

            if key_name == "operator":
                self.write_key_to_file(decrypted_pkey, self.path / "operator_pkey.txt")
                self.write_key_to_file(
                    decrypted_pkey, self.path / "current_owner_pkey.txt"
                )

        self.encrypted = False

    def encrypt(self, new_password: str):
        """Encrypt the private keys"""

        if self.encrypted:
            return

        for key_name, key_path in self.json_keys.items():
            with tempfile.TemporaryDirectory() as temp_dir:

                # Load the encrypted keys
                keys = json.load(key_path.open("r"))

                # Write the encrypted private key to a temp file
                temp_file = Path(temp_dir, "0")
                temp_file.open("w+", encoding="utf-8").write(
                    str(keys[0]["private_key"])
                )

                # Encrypt the private key
                crypto = EthereumCrypto.load_private_key_from_path(temp_file, None)
                encrypted_pkey = crypto.encrypt(new_password)
                encrypted_json_keys = [
                    {
                        "address": crypto.address,
                        "private_key": json.dumps(encrypted_pkey),
                        "ledger": "ethereum",
                    }
                ]

                # Write the encrypted key
                self.write_key_to_file(encrypted_json_keys, key_path)

                # Also update txts
                if key_name == "agent":
                    self.write_key_to_file(encrypted_pkey, self.path / "agent_pkey.txt")

                if key_name == "operator":
                    self.write_key_to_file(
                        encrypted_pkey, self.path / "operator_pkey.txt"
                    )
                    self.write_key_to_file(
                        encrypted_pkey, self.path / "current_owner_pkey.txt"
                    )

        os.environ["KEY_PASSWORD"] = new_password
        self.encrypted = True

    def write_key_to_file(self, data, path):
        """Write keys to file"""
        with open(path, "w", encoding="utf-8") as file:
            if path.suffix == ".txt":
                text = data if isinstance(data, str) else json.dumps(data)
                file.write(text)
            else:
                json.dump(data, file, indent=2)

    def interactive_encrypt(self):
        """Interactive encrypt"""
        if self.encrypted:
            print("The keys are already encrypted")
            return
        password = getpass.getpass("Input the new password (hidden input): ")
        self.encrypt(password)
        print("OK")

    def interactive_decrypt(self):
        """Interactive decrypt"""
        if not self.encrypted:
            print("The keys are not encrypted")
            return
        password = getpass.getpass("Input the current password (hidden input): ")
        self.decrypt(password)
        print("OK")


@click.command()
@click.option("-e", "--encrypt", "mode", flag_value="encrypt", help="Encrypt the keys.")
@click.option("-d", "--decrypt", "mode", flag_value="decrypt", help="Decrypt the keys.")
def process(mode):
    """Process encryption"""

    # Load configuration
    with open("config.yaml", "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    if mode == "encrypt":
        for trader_name, trader_path in config["traders"].items():
            print(f"Encrypting {trader_name}")
            km = KeyManager(Path(trader_path) / ".trader_runner")
            km.interactive_encrypt()

    elif mode == "decrypt":
        for trader_name, trader_path in config["traders"].items():
            print(f"Decrypting {trader_name}")
            km = KeyManager(Path(trader_path) / ".trader_runner")
            km.interactive_decrypt()

    else:
        click.echo("Please pass -e for encryption and -d for decryption")


if __name__ == "__main__":
    process()
