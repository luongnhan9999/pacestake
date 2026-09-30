import os
import sys
import json
import time
from genlayer_py import create_client, create_account, studionet

PK = os.getenv("PRIVATE_KEY", "0x1b807b1df022a40f872596b11565e6b6856547dc66996bd3d5a85b376ea3a0ef")
CONTRACT_PATH = os.path.join(os.path.dirname(__file__), "..", "contracts", "contract.py")

def main():
    print("=" * 70, flush=True)
    print("  DEPLOYING PACESTAKE INTELLIGENT CONTRACT TO GENLAYER STUDIONET  ", flush=True)
    print("=" * 70, flush=True)

    with open(CONTRACT_PATH, "r", encoding="utf-8") as f:
        code = f.read()

    acct = create_account(PK)
    client = create_client(chain=studionet, account=acct)

    print(f"[+] Deployer Address : {acct.address}", flush=True)
    bal = client.get_balance(acct.address)
    print(f"[+] Current Balance  : {bal / 1e18} GEN", flush=True)

    print("[*] Submitting deployment transaction...", flush=True)
    tx_hash = client.deploy_contract(code=code, args=[])
    print(f"[+] Deploy Tx Hash   : {tx_hash}", flush=True)

    print("[*] Waiting for transaction receipt...", flush=True)
    receipt = client.wait_for_transaction_receipt(tx_hash)
    print(f"[+] Receipt status   : {receipt.get('status')}", flush=True)
    contract_address = receipt.get("contract_address")
    print(f"[+] DEPLOYED ADDRESS : {contract_address}", flush=True)

    if contract_address:
        print("[*] Testing on-chain read call get_stats()...", flush=True)
        stats = client.read_contract(address=contract_address, function_name="get_stats", args=[])
        print(f"[+] On-Chain Stats   : {stats}", flush=True)

        output_file = os.path.join(os.path.dirname(__file__), "deployed_address.json")
        with open(output_file, "w") as out:
            json.dump({
                "contract_address": contract_address,
                "tx_hash": str(tx_hash),
                "network": "studionet",
                "explorer_url": f"http://explorer-studio.genlayer.com/address/{contract_address}"
            }, out, indent=2)
        print(f"[+] Deployment metadata saved to {output_file}", flush=True)

if __name__ == "__main__":
    main()
