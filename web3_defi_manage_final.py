from web3 import Web3
from eth_account import Account
import requests
import json
import time
import decimal
import numpy as np
import math
from web3 import exceptions
from eth_abi import encode
import web3
from web3.exceptions import ContractLogicError, TimeExhausted
import logging
from calculation import *
import pickle
import os
logger = logging.getLogger(__name__)

class Web3_Network(Web3):

    #router_address = '0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48E'
    #factory_address='0x0227628f3F023bb0B980b67D528571c95c6DaC1c'

    def __init__(self, rpc_url: str, private_key: str | None = None, explorer_api_key: str | None = None):
        
        super().__init__(Web3.HTTPProvider(rpc_url))

        if not self.is_connected():
            raise ConnectionError("RPC connection failed")

        self.rpc_url = rpc_url
        self.private_key = private_key
        if explorer_api_key is not None:
            self.explorer_api_key = explorer_api_key

        if private_key:
            self.account = Account.from_key(private_key)
            self.address = self.account.address
        else:
            self.account = None
            self.address = None
        self.chain_id = self.eth.chain_id
        #
        # ---- gas mode detection (ONCE) ----
        latest_block = self.eth.get_block('latest')
        self.network_gas_mode = (
            'EIP-1559'
            if 'baseFeePerGas' in latest_block
            else 'LEGACY'
        )
    #
    #
    def get_network_name_from_api(self) -> str:
        try:
            response = requests.get(f"https://chainid.network/chains.json")
            chains = response.json()
            for chain in chains:
                if chain["chainId"] == self.chain_id:
                    self.network_name=chain['name']
                    return chain["name"]
        except:
            pass
        return f"Unknown (ID: {self.chain_id})"
    #
    #
    def get_router_address(self,inp_router_address: str):
        self.router_address=self.to_checksum_address(inp_router_address)
    #
    #
    def get_factory_address(self,inp_factory_address: str):
        self.factory_address=self.to_checksum_address(inp_factory_address)
    #
    #
    def get_position_manager_address(self,inp_position_manager_address: str):
        self.position_manager_address=self.to_checksum_address(inp_position_manager_address)
    #
    #
    def get_jitzap_address(self,inp_jitzap_address: str):
        self.jitzap_address=self.to_checksum_address(inp_jitzap_address)
    #
    #
    def get_explorer_api_key(self,inp_explorer_api_key: str):
        self.explorer_api_key=inp_explorer_api_key
    #
    #
    def fetch_implementation_address(self, contract_address: str, api_key: str=None, inp_chain_id: int=None):
        if api_key is None:
            api_key = self.explorer_api_key
        if inp_chain_id is None:
            inp_chain_id = self.chain_id
        try:
            contract_address = self.to_checksum_address(contract_address)
        except ValueError:
            return None

        url = "https://api.etherscan.io/v2/api"
        params = {
            "module": "contract",
            "action": "getsourcecode", #
            "address": contract_address,
            "apikey": api_key,
            "chainid": inp_chain_id
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") == "1" and data["result"]:
                result = data["result"][0]
                implementation_address = result.get('Implementation')
                if implementation_address and implementation_address != '0x000000000000000000000000000000000000000':
                    return self.to_checksum_address(implementation_address)
        except Exception as e:
            print(f"Error checking implementation for {contract_address}: {e}")

        return None
    #
    #
    def fetch_abi_retry(self, contract_address: str, retries: int = 3, api_key: str = None, inp_chain_id: int = None):
        """
        Correctly fetches the ABI by checking the implementation address first,
        then the proxy address, with retry logic for each.
        """
        if api_key is None:
            api_key = self.explorer_api_key
        if inp_chain_id is None:
            inp_chain_id = self.chain_id
            
        try:
            initial_address = self.to_checksum_address(contract_address)
        except ValueError:
            return None

        # 1. Identify implementation address if it exists (for Proxies)
        implementation_address = self.fetch_implementation_address(initial_address, api_key, inp_chain_id)

        # 2. Prioritize: Implementation first, then Proxy
        addresses_to_check = []
        if implementation_address:
            addresses_to_check.append(implementation_address)
        addresses_to_check.append(initial_address)

        url = "https://api.etherscan.io/v2/api"

        # 3. Iterate through addresses and attempt to fetch
        for current_addr in addresses_to_check:
            time.sleep(0.2)  # Small delay before each new address attempt
            params = {
                "module": "contract",
                "action": "getabi",
                "address": current_addr,
                "apikey": api_key,
                "chainid": inp_chain_id
            }

            for attempt in range(retries):
                try:
                    # Small delay to respect rate limits
                    time.sleep(0.5) 
                    resp = requests.get(url, params=params, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()

                    # If status is "1", we found a valid ABI
                    if data.get("status") == "1":
                        print(f"Successfully fetched ABI from: {current_addr}")
                        return json.loads(data["result"])
                    
                    # If it's a known error like "Contract source code not verified", 
                    # we might want to break retries and try the next address
                    if "not verified" in data.get("result", "").lower():
                        print(f"Contract {current_addr} not verified on explorer.")
                        break

                except requests.exceptions.RequestException as e:
                    print(f"Request error for {current_addr} (attempt {attempt+1}): {e}")
                    time.sleep(1)

        # 4. If all attempts fail, return False to trigger fallback ABI
        print(f"Failed to fetch ABI for {contract_address} after checking all addresses.")
        return False
    #
    #
    def GET_FACTORY_ABI(self, factory_address: str=None)-> list:
        if factory_address is None:
            factory_address = self.factory_address
        self.UNISWAP_V3_FACTORY_ABI=self.fetch_abi_retry(factory_address)
        if self.UNISWAP_V3_FACTORY_ABI is False:
            self.UNISWAP_V3_FACTORY_ABI=self.FACTORY_ABI_FALLBACK
    #
    #
    def factory_contract(self, factory_address: str):
        self.GET_FACTORY_ABI(factory_address)
        self.factory_contract = self.eth.contract(address=factory_address, abi=self.UNISWAP_V3_FACTORY_ABI)
    #
    #
    def get_pool_address(self, tokenA: str, tokenB: str, fee: int) -> str | None:
        if not hasattr(self, "factory_contract"):
            #raise RuntimeError("Factory contract not initialized")
            if not hasattr(self, "factory_address"):
                raise RuntimeError("Factory address not set")
            self.factory_contract(self.factory_address)

        try:
            pool_address = self.factory_contract.functions.getPool(
                self.to_checksum_address(tokenA),
                self.to_checksum_address(tokenB),
                fee
            ).call()

            if int(pool_address, 16) == 0:
                return None

            return self.to_checksum_address(pool_address)

        except Exception as e:
            print(f"Error fetching pool address: {e}")
            return None
    #
    #
    def get_pool_id(self, token0, token1, fee, tick_spacing, hook_address: str="0x0000000000000000000000000000000000000000") -> str:
        "work for to get v4 then v3 pool id"
        token0 = self.to_checksum_address(token0)
        token1 = self.to_checksum_address(token1)
        hook_address = self.to_checksum_address(hook_address)

        encoded = encode(
            ['address', 'address', 'uint24', 'int24', 'address'],
            [token0, token1, fee, tick_spacing, hook_address]
        )

        pool_id = Web3.keccak(encoded).hex()
        return pool_id
    #
    #
    def get_pool_address_from_pool_id(self, pool_id) -> str:
        encoded = encode(
            ['address', 'bytes32'],
            [self.factory_address, bytes.fromhex(pool_id[2:])]
        )
        pool_address = Web3.to_checksum_address(Web3.keccak(encoded)[12:].hex())
        return pool_address
    #
    #
    def simulate_tx(self, tx_func, sender: str | None = None, value: int = 0) -> bool:
        try:
            if sender is None:
                sender = self.account.address

            tx_func.call({
                "from": sender,
                "value": value
            })
            return True

        except Exception as e:
            self.last_simulation_error = str(e)
            return False
    #
    #
    def estimate_gas_safe(
        self,
        tx_func,
        sender: str | None = None,
        value: int = 0,
        multiplier: float = 1.2
    ) -> int | None:

        try:
            if sender is None:
                sender = self.account.address

            gas = tx_func.estimate_gas({
                "from": sender,
                "value": value
            })

            return int(gas * multiplier)

        except Exception as e:
            self.last_gas_error = str(e)
            return None
    #
    #
    def build_and_send_transaction(
        self,
        tx_func,
        sender: str | None = None,
        value: int = 0,
        gas_multiplier: float = 1.2,
        wait_for_confirmation: bool = True
    ) -> str | bool:
        """
        Network-level transaction executor.
        tx_func must be a web3 ContractFunction.
        """

        try:
            if sender is None:
                sender = self.address
            if sender is None:
                raise ValueError("Sender address is not set")

            # ---- base tx params (network responsibility) ----
            tx_params = {
                'from': sender,
                'value': value,
                'nonce': self.eth.get_transaction_count(sender),
                'chainId': self.chain_id
            }

            # ---- gas estimation ----
            estimated_gas = tx_func.estimate_gas({
                'from': sender,
                'value': value
            })
            tx_params['gas'] = int(estimated_gas * gas_multiplier)

            # ---- gas pricing (based on init-detected mode) ----
            if self.network_gas_mode == 'EIP-1559':
                base_fee = self.eth.get_block('latest')['baseFeePerGas']
                priority_fee = self.eth.max_priority_fee


                tx_params['maxPriorityFeePerGas'] = priority_fee
                tx_params['maxFeePerGas'] = int(base_fee * 2 + priority_fee)
            else:
                tx_params['gasPrice'] = self.eth.gas_price

            # ---- build tx via function (tx-specific logic) ----
            tx = tx_func.build_transaction(tx_params)
            
        except Exception as e:
            print(tx_params)
            self.last_send_error = f"Build Error: {e}"
            print(self.last_send_error)
            return False

        # ---- sign & send ----
        try:
            signed = self.account.sign_transaction(tx)
            tx_hash = self.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            print(f"Transaction sent: {tx_hash_hex}")

            if not wait_for_confirmation:
                return tx_hash_hex

            receipt = self.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt.status == 1:
                print(f"Confirmed in block {receipt.blockNumber}")
                return tx_hash_hex
            else:
                self.last_send_error = "Transaction reverted on-chain"
                return False

        except Exception as e:
            self.last_send_error = f"Send Error: {e}"
            print(self.last_send_error)
            return False
    #
    #
    def build_and_send_transaction_advanced(
        self,
        tx_func,
        sender: str | None = None,
        value: int = 0,
        gas_multiplier: float = 1.2,
        wait_for_confirmation: bool = True,
        manual_gas_limit: int = 1000000
    ) -> str | bool:
        """
        Builds, signs, and broadcasts a transaction with fallback gas handling.
        """
        
        if sender is None:
            sender = self.address

        # ---- 1) Initialize base transaction parameters ----
        tx_params = {
            'from': sender,
            'value': value,
            'nonce': self.eth.get_transaction_count(sender),
            'chainId': self.chain_id
        }

        # ---- 2) Gas Management (Estimate with Fallback) ----
        try:
            # Attempt to estimate gas from the node
            estimated_gas = tx_func.estimate_gas({'from': sender, 'value': value})
            tx_params['gas'] = int(estimated_gas * gas_multiplier)
        except Exception as e:
            # If estimation fails (common in Multicall), use the manual safety limit
            print(f"⚠️ Gas estimation failed: {e}. Using manual gas limit: {manual_gas_limit}")
            tx_params['gas'] = manual_gas_limit

        # ---- 3) Gas Pricing (EIP-1559 vs Legacy) ----
        if self.network_gas_mode == 'EIP-1559':
            # Priority fee handling for modern networks (Sepolia, Mainnet, etc.)
            base_fee = self.eth.get_block('latest')['baseFeePerGas']
            priority_fee = self.eth.max_priority_fee
            
            tx_params['maxPriorityFeePerGas'] = priority_fee
            # Set maxFee at 2x base_fee + priority to ensure inclusion
            tx_params['maxFeePerGas'] = int(base_fee * 2 + priority_fee)
        else:
            # Legacy gas pricing
            tx_params['gasPrice'] = self.eth.gas_price

        # ---- 4) Build Contract Transaction ----
        try:
            # Final data encoding and transaction object creation
            tx = tx_func.build_transaction(tx_params)
        except Exception as e:
            self.last_send_error = f"❌ Build Error (Data Mismatch): {e}"
            print(self.last_send_error)
            print(f"Debug params: {tx_params}")
            return False

        # ---- 5) Signing and Broadcasting ----
        try:
            signed = self.account.sign_transaction(tx)
            tx_hash = self.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            print(f"🚀 Transaction broadcasted! Hash: {tx_hash_hex}")

            if not wait_for_confirmation:
                return tx_hash_hex

            # ---- 6) Confirmation Handling ----
            receipt = self.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            if receipt.status == 1:
                print(f"✅ Confirmed in block {receipt.blockNumber}")
                return tx_hash_hex
            else:
                self.last_send_error = "🔴 Transaction reverted on-chain"
                print(f"{self.last_send_error} | Check hash for details: {tx_hash_hex}")
                return False

        except Exception as e:
            self.last_send_error = f"❌ Send/Sign Error: {e}"
            print(self.last_send_error)
            return False
    #
    #
#
#
class BaseEntity:
    def __init__(self, net: Web3_Network):
        self.net = net
#
#
class ABIRegistry(BaseEntity):
    def __init__(self, net: Web3_Network):
        super().__init__(net)
        self.abi_cache = {}  # In-memory cache for ABIs
        self.ERC20_ABI_FALLBACK = [
            {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
            ],
            "name": "allowance",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
            {"name": "_from", "type": "address"},
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
            ],
            "name": "transferFrom",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        },
        {
            "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"}
            ],
            "name": "permit",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "nonces",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "anonymous": False,
            "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
            ],
            "name": "Transfer",
            "type": "event"
        },
        {
            "anonymous": False,
            "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
            ],
            "name": "Approval",
            "type": "event"
        }
        ]
            #
            #
            #
        self.NFPM_ABI_FALLBACK = [
        {
            "inputs": [
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "int24", "name": "tickLower", "type": "int24"},
            {"internalType": "int24", "name": "tickUpper", "type": "int24"},
            {"internalType": "uint256", "name": "amount0Desired", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1Desired", "type": "uint256"},
            {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
            ],
            "name": "mint",
            "outputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "amount0Min", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1Min", "type": "uint256"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"}
            ],
            "name": "decreaseLiquidity",
            "outputs": [
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint128", "name": "amount0Max", "type": "uint128"},
            {"internalType": "uint128", "name": "amount1Max", "type": "uint128"}
            ],
            "name": "collect",
            "outputs": [
            {"internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"internalType": "uint256", "name": "amount1", "type": "uint256"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
            "name": "positions",
            "outputs": [
            {"internalType": "uint96", "name": "nonce", "type": "uint96"},
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "int24", "name": "tickLower", "type": "int24"},
            {"internalType": "int24", "name": "tickUpper", "type": "int24"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "anonymous": False,
            "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "address", "name": "liquidity", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"}
            ],
            "name": "IncreaseLiquidity",
            "type": "event"
        },
        {
            "anonymous": False,
            "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"}
            ],
            "name": "DecreaseLiquidity",
            "type": "event"
        },
        {
            "anonymous": False,
            "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"}
            ],
            "name": "Collect",
            "type": "event"
        }
        ]
            #
            #
            #
        self.V3_POOL_ABI_FALLBACK = [
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "internalType": "address", "name": "owner", "type": "address"},
                    {"indexed": True, "internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"indexed": True, "internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"indexed": False, "internalType": "uint128", "name": "amount", "type": "uint128"},
                    {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                    {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"}
                ],
                "name": "Mint",
                "type": "event"
            },
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
                    {"indexed": True, "internalType": "address", "name": "recipient", "type": "address"},
                    {"indexed": False, "internalType": "uint256", "name": "amount0", "type": "uint256"},
                    {"indexed": False, "internalType": "uint256", "name": "amount1", "type": "uint256"},
                    {"indexed": False, "internalType": "uint256", "name": "sqrtPriceX96", "type": "uint256"},
                    {"indexed": False, "internalType": "uint128", "name": "liquidity", "type": "uint128"},
                    {"indexed": False, "internalType": "int24", "name": "tick", "type": "int24"}
                ],
                "name": "Swap",
                "type": "event"
            },
            {
                "inputs": [
                    {"internalType": "int24", "name": "tickLower", "type": "int24"},
                    {"internalType": "int24", "name": "tickUpper", "type": "int24"},
                    {"internalType": "uint128", "name": "amount", "type": "uint128"}
                ],
                "name": "mint",
                "outputs": [
                    {"internalType": "uint256", "name": "amount0", "type": "uint256"},
                    {"internalType": "uint256", "name": "amount1", "type": "uint256"}
                ],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "int256", "name": "amount0Delta", "type": "int256"},
                    {"internalType": "int256", "name": "amount1Delta", "type": "int256"},
                    {"internalType": "bytes", "name": "data", "type": "bytes"}
                ],
                "name": "swap",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "slot0",
                "outputs": [
                    {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                    {"internalType": "int24", "name": "tick", "type": "int24"},
                    {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                    {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                    {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                    {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                    {"internalType": "bool", "name": "unlocked", "type": "bool"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "int24", "name": "tick", "type": "int24"}],
                "name": "ticks",
                "outputs": [
                    {"internalType": "uint128", "name": "liquidityGross", "type": "uint128"},
                    {"internalType": "int128", "name": "liquidityNet", "type": "int128"},
                    {"internalType": "uint256", "name": "feeGrowthOutside0X128", "type": "uint256"},
                    {"internalType": "uint256", "name": "feeGrowthOutside1X128", "type": "uint256"},
                    {"internalType": "int56", "name": "tickCumulativeOutside", "type": "int56"},
                    {"internalType": "uint160", "name": "secondsPerLiquidityOutsideX128", "type": "uint160"},
                    {"internalType": "uint32", "name": "secondsOutside", "type": "uint32"},
                    {"internalType": "bool", "name": "initialized", "type": "bool"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "liquidity",
                "outputs": [{"internalType": "uint128", "name": "", "type": "uint128"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "fee",
                "outputs": [{"internalType": "uint24", "name": "", "type": "uint24"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token0",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token1",
                "outputs": [{"internalType": "address", "name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
            #
            #
            #
        self.V4_POOL_ABI_FALLBACK = [
        {
            "inputs": [
            { "internalType": "bytes32", "name": "poolId", "type": "bytes32" }
            ],
            "name": "getSlot0",
            "outputs": [
            { "internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160" },
            { "internalType": "int24", "name": "tick", "type": "int24" },
            { "internalType": "uint16", "name": "observationIndex", "type": "uint16" },
            { "internalType": "uint16", "name": "observationCardinality", "type": "uint16" },
            { "internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16" },
            { "internalType": "bool", "name": "unlocked", "type": "bool" }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            { "internalType": "bytes32", "name": "poolId", "type": "bytes32" }
            ],
            "name": "getLiquidity",
            "outputs": [
            { "internalType": "uint128", "name": "liquidity", "type": "uint128" }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            { "internalType": "bytes32", "name": "poolId", "type": "bytes32" },
            { "internalType": "int24", "name": "tick", "type": "int24" }
            ],
            "name": "getTickLiquidity",
            "outputs": [
            { "internalType": "int128", "name": "liquidityNet", "type": "int128" },
            { "internalType": "uint128", "name": "liquidityGross", "type": "uint128" }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            { "internalType": "bytes32", "name": "poolId", "type": "bytes32" },
            { "internalType": "address", "name": "owner", "type": "address" },
            { "internalType": "int24", "name": "tickLower", "type": "int24" },
            { "internalType": "int24", "name": "tickUpper", "type": "int24" }
            ],
            "name": "getPosition",
            "outputs": [
            { "internalType": "uint128", "name": "liquidity", "type": "uint128" },
            { "internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256" },
            { "internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256" }
            ],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [
            { "internalType": "bytes[]", "name": "paths", "type": "bytes[]" },
            { "internalType": "uint128[]", "name": "amounts", "type": "uint128[]" },
            { "internalType": "uint24", "name": "maximumTickDivergence", "type": "uint24" },
            { "internalType": "uint32", "name": "secondsAgo", "type": "uint32" }
            ],
            "name": "checkOracleSlippage",
            "outputs": [],
            "stateMutability": "view",
            "type": "function"
        }
        ]
            #
            #
            #
        self.V3_ROUTER_ABI_FALLBACK = [
        {
            "inputs": [
            {
                "components": [
                {"internalType": "bytes", "name": "path", "type": "bytes"},
                {"internalType": "address", "name": "recipient", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"}
                ],
                "internalType": "struct ISwapRouter.ExactInputParams",
                "name": "params",
                "type": "tuple"
            }
            ],
            "name": "exactInput",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "components": [
                {"internalType": "address", "name": "tokenIn", "type": "address"},
                {"internalType": "address", "name": "tokenOut", "type": "address"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"},
                {"internalType": "address", "name": "recipient", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactInputSingleParams",
                "name": "params",
                "type": "tuple"
            }
            ],
            "name": "exactInputSingle",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "components": [
                {"internalType": "bytes", "name": "path", "type": "bytes"},
                {"internalType": "address", "name": "recipient", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "uint256", "name": "amountInMaximum", "type": "uint256"}
                ],
                "internalType": "struct ISwapRouter.ExactOutputParams",
                "name": "params",
                "type": "tuple"
            }
            ],
            "name": "exactOutput",
            "outputs": [{"internalType": "uint256", "name": "amountIn", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
            {
                "components": [
                {"internalType": "address", "name": "tokenIn", "type": "address"},
                {"internalType": "address", "name": "tokenOut", "type": "address"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"},
                {"internalType": "address", "name": "recipient", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "uint256", "name": "amountInMaximum", "type": "uint256"},
                {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}
                ],
                "internalType": "struct ISwapRouter.ExactOutputSingleParams",
                "name": "params",
                "type": "tuple"
            }
            ],
            "name": "exactOutputSingle",
            "outputs": [{"internalType": "uint256", "name": "amountIn", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "bytes[]", "name": "data", "type": "bytes[]"}],
            "name": "multicall",
            "outputs": [{"internalType": "bytes[]", "name": "results", "type": "bytes[]"}],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "refundETH",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "uint256", "name": "amountMinimum", "type": "uint256"},
            {"internalType": "address", "name": "recipient", "type": "address"}
            ],
            "name": "sweepToken",
            "outputs": [],
            "stateMutability": "payable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "WETH9",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "factory",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        }
        ]
            #
            #
            #
        self.FACTORY_ABI_FALLBACK = [
                {
                "constant": True,
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"},
                    {"name": "fee", "type": "uint24"}
                ],
                "name": "getPool",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"}]
        self.JIT_ZAP_ABI_FALLBACK = [
            {"inputs":[{"internalType":"address","name":"_router","type":"address"},
                                                {"internalType":"address","name":"_nfpm","type":"address"}],
                                                "stateMutability":"nonpayable","type":"constructor"},
                                                {"inputs":[{"internalType":"address","name":"token0","type":"address"},
                                                           {"internalType":"address","name":"token1","type":"address"},
                                                           {"internalType":"uint24","name":"fee","type":"uint24"},
                                                           {"internalType":"int24","name":"tickLower","type":"int24"},
                                                           {"internalType":"int24","name":"tickUpper","type":"int24"},
                                                           {"internalType":"uint256","name":"amount0Total","type":"uint256"},
                                                           {"internalType":"uint256","name":"amount1Total","type":"uint256"},
                                                           {"internalType":"bool","name":"performSwap","type":"bool"},
                                                           {"internalType":"bool","name":"zeroForOne","type":"bool"},
                                                           {"internalType":"uint256","name":"swapAmountIn","type":"uint256"},
                                                           {"internalType":"uint256","name":"amountOutMinSwap","type":"uint256"},
                                                           {"internalType":"uint256","name":"amount0MinMint","type":"uint256"},
                                                           {"internalType":"uint256","name":"amount1MinMint","type":"uint256"}],"name":"executeJIT","outputs":[],"stateMutability":"nonpayable","type":"function"},
                                                           {"inputs":[],"name":"nfpm","outputs":[{"internalType":"contract INonfungiblePositionManager","name":"","type":"address"}],"stateMutability":"view","type":"function"},
                                                           {"inputs":[],"name":"router","outputs":[{"internalType":"contract ISwapRouter","name":"","type":"address"}],"stateMutability":"view","type":"function"}]
    #
    #
    def GET_ERC20_ABI(self, token_address: str) -> list:
        token_address=self.net.to_checksum_address(token_address)
        if token_address in self.abi_cache.keys():
            return self.abi_cache[token_address]
        ERC20_ABI=self.net.fetch_abi_retry(token_address)
        if ERC20_ABI:
            self.abi_cache[token_address]=ERC20_ABI
            return ERC20_ABI
        else:
            return self.ERC20_ABI_FALLBACK
    #
    #
    def GET_NFPM_ABI(self, nfpm_address: str=None) -> list:
        if nfpm_address is None:
            nfpm_address=self.net.position_manager_address
        nfpm_address=self.net.to_checksum_address(nfpm_address)
        if nfpm_address in self.abi_cache.keys():
            return self.abi_cache[nfpm_address]
        NFPM_ABI=self.net.fetch_abi_retry(nfpm_address)
        if NFPM_ABI:
            self.abi_cache[nfpm_address]=NFPM_ABI
            return NFPM_ABI
        else:
            return self.NFPM_ABI_FALLBACK
    #
    #
    def GET_V3_POOL_ABI(self, pool_address: str) -> list:
        pool_address=self.net.to_checksum_address(pool_address)
        if pool_address in self.abi_cache.keys():
            return self.abi_cache[pool_address]
        V3_POOL_ABI=self.net.fetch_abi_retry(pool_address)
        if V3_POOL_ABI:
            self.abi_cache[pool_address]=V3_POOL_ABI
            return V3_POOL_ABI
        else:
            return self.V3_POOL_ABI_FALLBACK
    #
    #
    def GET_ROUTER_ABI(self, router_address: str=None) -> list:
        if router_address is None:
            router_address=self.net.router_address
        router_address=self.net.to_checksum_address(router_address)
        if router_address in self.abi_cache.keys():
            return self.abi_cache[router_address]
        ROUTER_ABI=self.net.fetch_abi_retry(router_address)
        if ROUTER_ABI:
            self.abi_cache[router_address]=ROUTER_ABI
            return ROUTER_ABI
        else:
            return self.V3_ROUTER_ABI_FALLBACK
    #
    #
    def GET_FACTORY_ABI(self, factory_address: str=None) -> list:
        if factory_address is None:
            factory_address=self.net.factory_address
        factory_address=self.net.to_checksum_address(factory_address)
        if factory_address in self.abi_cache.keys():
            return self.abi_cache[factory_address]
        FACTORY_ABI=self.net.fetch_abi_retry(factory_address)
        if FACTORY_ABI:
            self.abi_cache[factory_address]=FACTORY_ABI
            return FACTORY_ABI
        else:
            return self.FACTORY_ABI_FALLBACK
    #
    #
    def GET_JITZAP_ABI(self,JITZAP_ADDRESS:str=None) -> list:
        if JITZAP_ADDRESS is None:
            JITZAP_ADDRESS=self.net.jitzap_address
        JITZAP_ADDRESS=self.net.to_checksum_address(JITZAP_ADDRESS)
        if JITZAP_ADDRESS in self.abi_cache.keys():
            return self.abi_cache[JITZAP_ADDRESS]
        JITZAP_ABI=self.net.fetch_abi_retry(JITZAP_ADDRESS)
        if JITZAP_ABI:
            self.abi_cache[JITZAP_ADDRESS]=JITZAP_ABI
            return JITZAP_ABI
        else:
            self.abi_cache[self.net.jitzap_address]=self.JIT_ZAP_ABI_FALLBACK
            return self.JIT_ZAP_ABI_FALLBACK
    #
    #
    def GET_ANY_CONTRACT_ABI(self, contract_address: str) -> list:
        contract_address=self.net.to_checksum_address(contract_address)
        if contract_address in self.abi_cache.keys():
            return self.abi_cache[contract_address]
        ABI=self.net.fetch_abi_retry(contract_address)
        if ABI:
            self.abi_cache[contract_address]=ABI
            return ABI
        else:
            return []
    #
    #
    def clear_abi_cache(self):
        self.abi_cache = {}
    #
    #
    def dump_abi_cache(self):
        os.makedirs('abi_cache', exist_ok=True)
        #os.chdir('abi_cache')
        for address, abi in self.abi_cache.items():
            with open(f'abi_cache\\abi_{address}.json', 'w') as f:
                json.dump(abi, f, indent=4)
    #
    #
    def load_abi_cache(self):
        if not os.path.exists('abi_cache'):
            return False
        for filename in os.listdir('abi_cache'):
            if filename.startswith('abi_') and filename.endswith('.json'):
                address = filename[4:-5]
                with open(f'abi_cache\\{filename}', 'r') as f:
                    abi = json.load(f)
                    self.abi_cache[address] = abi
#
#
#
class Token(BaseEntity):
    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,address: str):
        super().__init__(net)
        self.abi_reg = abi_reg

        self.address = net.to_checksum_address(address)
        self.contract = None

        self.name: str | None = None
        self.symbol: str | None = None
        self.decimals: int | None = None
        self.load()
    def load(self):
        erc20abi=self.abi_reg.GET_ERC20_ABI(self.address)

        self.contract = self.net.eth.contract(
            address=self.address,
            abi=erc20abi
        )

        #self.name = self.contract.functions.name().call()
        self.symbol = self.contract.functions.symbol().call()
        self.decimals = self.contract.functions.decimals().call()
        self.balance_of()

    def balance_of(self, address: str=None) -> int:
        if address is None:
            address = self.net.account.address
            self.token_balance = self.contract.functions.balanceOf(
                self.net.to_checksum_address(address)
                ).call()

    def allowance(self, owner: str, spender: str) -> int:
        return self.contract.functions.allowance(
            self.net.to_checksum_address(owner),
            self.net.to_checksum_address(spender)
        ).call()

    def ensure_allowance(self, spender: str, amount: int, infinite: bool = True) -> bool:
        self.load()
        spender = self.net.to_checksum_address(spender)

        current = self.allowance(self.net.account.address, spender)
        if current >= amount:
            return True

        # USDT-style reset
        if current > 0:
            self.net.build_and_send_transaction(
                self.contract.functions.approve(spender, 0),
                wait_for_confirmation=True
            )
        

        approve_amount = (2**256 - 1) if infinite else amount


        tx_hash = self.net.build_and_send_transaction(
            self.contract.functions.approve(spender, approve_amount),
            wait_for_confirmation=True
        )

        if not tx_hash:
            raise RuntimeError(f"Approve failed for {self.symbol}")

        return True
    #
    #
    def transfer(self, to_address: str, amount: int, wait_for_confirmation: bool = True) -> str | bool:
        self.load()
        try:
            tx_hash = self.net.build_and_send_transaction(
                self.contract.functions.transfer(
                    self.net.to_checksum_address(to_address),
                    amount
                ),
                wait_for_confirmation=wait_for_confirmation
            )

            if not tx_hash:
                self.last_send_error = "🔴 Transfer transaction failed to send"
                print(self.last_send_error)
                return False

            if wait_for_confirmation:
                receipt = self.net.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
                tx_hash_hex = tx_hash.hex()
                if receipt.status == 1:
                    print(f"✅ Transfer of {amount / (10 ** self.decimals)} {self.symbol} to {to_address} confirmed in tx {tx_hash_hex}")
        except Exception as e:
            self.last_send_error = f"🔴 Transfer failed: {str(e)}"
            print(self.last_send_error)
            return False

        return tx_hash
#
#
#
class V3Pool(BaseEntity):
    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,address: str | None = None):
        super().__init__(net)
        self.abi_reg = abi_reg
        self.address: str | None = (
            net.to_checksum_address(address)
            if address is not None
            else None
        )

        self.contract = None

        self.token0: str | None = None
        self.token1: str | None = None
        self.fee: int | None = None

        self.sqrtPriceX96: int | None = None
        self.tick: int | None = None
        self.liquidity: int | None = None
        self.load()

    # ---------- factory constructor ----------
    @classmethod
    def from_factory(
        cls,
        net: Web3_Network,
        tokenA: str,
        tokenB: str,
        fee: int,
        abi_reg:ABIRegistry,
        factory_address: str = None
    ) -> "V3Pool":

        '''if not hasattr(net, "UNISWAP_V3_FACTORY_ABI"):
            raise RuntimeError("UNISWAP_V3_FACTORY_ABI not loaded in network")'''
        
        if factory_address is None:
            factory_address = net.factory_address

        pool_abi=abi_reg.GET_FACTORY_ABI(factory_address)
        factory = net.eth.contract(
            address=net.to_checksum_address(factory_address),
            abi=pool_abi
        )

        pool_address = factory.functions.getPool(
            net.to_checksum_address(tokenA),
            net.to_checksum_address(tokenB),
            fee
        ).call()

        if int(pool_address, 16) == 0:
            raise ValueError("Pool does not exist for given tokens and fee")

        return cls(net,abi_reg ,pool_address)

    # ---------- load static data ----------
    def load(self):
        if self.address is None:
            raise RuntimeError("Pool address is not set")
        pool_abi=self.abi_reg.GET_V3_POOL_ABI(self.address)

        self.contract = self.net.eth.contract(
            address=self.address,
            abi=pool_abi
        )

        self.token0 = self.contract.functions.token0().call()
        self.token1 = self.contract.functions.token1().call()
        self.fee = self.contract.functions.fee().call()

    # ---------- load dynamic state ----------
    def update_state(self):
        if self.contract is None:
            raise RuntimeError("Pool contract not loaded")

        slot0 = self.contract.functions.slot0().call()
        self.sqrtPriceX96 = slot0[0]
        self.current_tick = slot0[1]
        self.liquidity = self.contract.functions.liquidity().call()
        self.tickspacing = self.contract.functions.tickSpacing().call()
    #
    #
    def get_nearest_valid_tick(self, tick: int) -> int:
        if self.contract is None:
            raise RuntimeError("Pool contract not loaded")

        tickspacing = self.contract.functions.tickSpacing().call()
        return tick - (tick % tickspacing)
    #
    #ُ
    def get_current_match_tick_range(self, inp_divid: int,step: int=None) -> tuple[int,int]:
        inp_current_tick=self.current_tick
        inp_tickspacing=self.tickspacing
        a=self.get_nearest_valid_tick(inp_current_tick)
        b=a+(1*inp_tickspacing)
        lowertick=0
        uppertick=0
        st=(b-a)/inp_divid
        if inp_current_tick>a+st*(inp_divid-1):
            lowertick=a
            uppertick=b+(1*inp_tickspacing)
        elif inp_current_tick<(a+1*st):
            lowertick=a-(1*inp_tickspacing)
            uppertick=b
        else:
            lowertick=a
            uppertick=b
        if step is not None:
            lowertick=lowertick-step*inp_tickspacing
            uppertick=uppertick+step*inp_tickspacing
        return lowertick,uppertick
    #
    #---------------------------------------------------------
    def get_token(self)->tuple[Token,Token]:
        return [Token(self.net,self.abi_reg ,self.token0),Token(self.net,self.abi_reg ,self.token1)]
    #---------------------------------------------------------
    def info(self) -> dict:
        if self.contract is None:
            raise RuntimeError("Pool contract not loaded")

        slot0 = self.contract.functions.slot0().call()
        liquidity = self.contract.functions.liquidity().call()

        return {
            "sqrtPriceX96": slot0[0],
            "current_tick": slot0[1],
            "liquidity": liquidity,
            "token0": self.token0,
            "token1": self.token1,
            "fee": self.fee,
            "tickspacing": self.tickspacing

        }
#
#
#
class SwapRouter(BaseEntity):
    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,router_address: str=None):
        super().__init__(net)
        self.abi_reg = abi_reg
        if router_address is None:
            router_address = self.net.router_address
        self.address = net.to_checksum_address(router_address)
        self.contract = None

        self._load_contract()

    def _load_contract(self):
        '''if not hasattr(self.net, "ROUTER_ABI"):
            raise RuntimeError("ROUTER_ABI not loaded in network")'''
        
        router_abi=self.abi_reg.GET_ROUTER_ABI(self.address)

        self.contract = self.net.eth.contract(
            address=self.address,
            abi=router_abi
        )

    # --------------------------------------------------
    # internal helpers
    # --------------------------------------------------
    def build_swap_params(
        self,
        token_in: Token,
        token_out: Token,
        fee: int,
        amount_in: int,
        amount_out_min: int=0,
        deadline: int=None
    ) -> dict:
        if deadline is None:
            p= {
                "tokenIn": token_in.address,
                "tokenOut": token_out.address,
                "fee": fee,
                "recipient": self.net.account.address,
                #"deadline": deadline,
                "amountIn": amount_in,
                "amountOutMinimum": amount_out_min,
                "sqrtPriceLimitX96": 0,
            }
            self.swap_param=p
            return p
        else:
            p={
                "tokenIn": token_in.address,
                "tokenOut": token_out.address,
                "fee": fee,
                "recipient": self.net.account.address,
                "deadline": deadline,
                "amountIn": amount_in,
                "amountOutMinimum": amount_out_min,
                "sqrtPriceLimitX96": 0,
            }
            self.swap_param=p
            return p
    # --------------------------------------------------
    # simulation (call)
    # --------------------------------------------------
    def simulate_exact_input_single(
        self,
        token_in: Token,
        token_out: Token,
        fee: int,
        amount_in: int,
        deadline: int=None
    ) -> int:
        if deadline is None:
            deadline = int(time.time()) + 300
        token_in.load()
        token_in.ensure_allowance(self.address, amount_in)
        params = self.build_swap_params(token_in, token_out, fee, amount_in, deadline=deadline)


        amount_out = self.contract.functions.exactInputSingle(
            params
        ).call({
            "from": self.net.account.address
        })

        return amount_out

    # --------------------------------------------------
    # real swap (transaction)
    # --------------------------------------------------
    def swap_exact_input_single(
        self,
        token_in: Token,
        token_out: Token,
        fee: int,
        amount_in: int,
        amount_out_min: int = None,
        slippage: float = 0.05,
        deadline_seconds: int = 180
    ):
        """
        Executes a single swap on Uniswap V3.
        Calculates amount_out_min automatically if not provided based on simulation.
        """
        #amount_in = int(amount_in)
        # 1. Check and set allowance (waits for confirmation if needed)
        token_in.load()
        token_in.ensure_allowance(self.address, amount_in)


        # 2. Quoting: Simulate the swap to get predicted output amount
        predicted_amount_out = self.simulate_exact_input_single(token_in, token_out, fee, amount_in)
        
        if predicted_amount_out <= 0:
            raise ValueError("Simulation returned an invalid predicted amount.")

        # 3. Apply slippage to the predicted amount if amount_out_min is not specified
        if amount_out_min is None:
            amount_out_min = int(predicted_amount_out * (1 - slippage))

        # 4. Price Impact/Safety Check: Comparing current pool price vs simulation
        pool = V3Pool.from_factory(self.net, token_in.address, token_out.address ,fee,self.abi_reg,self.net.factory_address)
        time.sleep(0.5)  # Small delay to avoid rate limits
        pool.load()
        time.sleep(0.5)  # Small delay to avoid rate limits
        pool.update_state()
        cp = calculate_raw_price_from_sqrt_price(pool.sqrtPriceX96)
        
        # Determine raw amount based on pool state (token0 vs token1)
        raw_amount_out = int(amount_in * cp) if token_in.address == pool.token0 else int(amount_in / cp)
        
        # Warning if simulation deviates significantly from spot price (high impact)
        if abs(raw_amount_out - predicted_amount_out) > raw_amount_out * slippage:
             print(f"Warning: High price impact or slippage detected. Raw: {raw_amount_out}, Predicted: {predicted_amount_out}")

        # 5. Prepare transaction parameters for SwapRouter
        params = self.build_swap_params(token_in, token_out, fee, amount_in, amount_out_min, deadline=(int(time.time()) + deadline_seconds))

        # 6. Prepare the contract function call
        swap_func = self.contract.functions.exactInputSingle(params)

        print(f"Action: Swapping {amount_in} {token_in.symbol} for at least {amount_out_min} {token_out.symbol}")

        # 7. Execute via the unified network layer (Build -> Sign -> Send -> Wait)
        # Returns the transaction hash as hex string or False on failure
        return self.net.build_and_send_transaction(swap_func)
    #
    #
    def build_swap_exact_input_single_call(
        self,
        token_in,
        token_out,
        fee,
        amount_in,
        deadline,
        slippage=0.01
    ):
        pool = V3Pool.from_factory(
            self.net,
            token_in.address,
            token_out.address,
            fee,
            self.net.factory_address,
        )
        pool.load()
        pool.update_state()

        cp = calculate_raw_price_from_sqrt_price(pool.sqrtPriceX96)

        raw_out = (
            int(amount_in * cp)
            if token_in.address == pool.token0
            else int(amount_in / cp)
        )

        amount_out_min = int(raw_out * (1 - slippage))

        logger.info(
            f"[SWAP] {token_in.symbol}->{token_out.symbol} | "
            f"in={amount_in} | min_out={amount_out_min}"
        )

        params = (
            token_in.address,           # tokenIn
            token_out.address,          # tokenOut
            fee,                        # fee
            self.net.address,    # recipient
            #deadline,                   # deadline
            int(amount_in),              # amountIn
            0,
            #int(amount_out_min),        # amountOutMinimum
            0                           # sqrtPriceLimitX96
        )

        hex_data = self.contract.functions.exactInputSingle(params)._encode_transaction_data()
        return self.net.to_bytes(hexstr=hex_data)
    #
    #
    def build_mint_call(
        self,
        token0: Token,
        token1: Token,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        #amount0_desired: int,
        #amount1_desired: int,
        amount0_min: int = 0,
        amount1_min: int = 0,
        deadline: int = None
    ):


        if deadline is None:
            deadline = int(time.time()) + 600  # default 10 minutes from now

        params = (
            token0.address,         # token0
            token1.address,         # token1
            fee,                    # fee
            tick_lower,             # tickLower
            tick_upper,             # tickUpper
            amount0_min,           # amount0Min
            amount1_min,           # amount1Min
            self.net.address,  # recipient
            deadline                # deadline
        )

        hex_data = self.contract.functions.mint(params)._encode_transaction_data()
        return self.net.to_bytes(hexstr=hex_data)
#
#
#
class LPPosition(BaseEntity):
    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,token_id: int):
        super().__init__(net)
        self.abi_reg = abi_reg
        self.token_id = token_id

        self.token0: str | None = None
        self.token1: str | None = None
        self.fee: int | None = None

        self.tick_lower: int | None = None
        self.tick_upper: int | None = None
        self.liquidity: int | None = None

        self.tokens_fee0: int | None = None
        self.tokens_fee1: int | None = None
        self.load()

    def load(self, pm_address: str=None):
        if pm_address is None:
            pm_address = self.net.position_manager_address

        nfpm_abi=self.abi_reg.GET_NFPM_ABI(pm_address)
        
        nfpm_contract = self.net.eth.contract(
            address=self.net.to_checksum_address(pm_address), 
            abi=nfpm_abi
        )
        self.nfpm_contract=nfpm_contract


        pos = nfpm_contract.functions.positions(
            self.token_id
        ).call()

        self.token0 = pos[2]
        self.token1 = pos[3]
        self.fee = pos[4]
        self.tick_lower = pos[5]
        self.tick_upper = pos[6]
        self.liquidity = pos[7]
        self.tokens_fee0 = pos[10]
        self.tokens_fee1 = pos[11]

    def is_in_range(self, current_tick: int) -> bool:
        return self.tick_lower <= current_tick <= self.tick_upper
    #-----------------------------------------------------------------
    def is_in_range_extended(self) -> bool:
        pool=V3Pool.from_factory(self.net,self.token0,self.token1,self.fee,self.abi_reg,self.net.factory_address)
        pool.load()
        pool.update_state()
        current_tick=pool.current_tick
        return self.is_in_range(current_tick)
    #-----------------------------------------------------------------
    def is_in_range_pro(self,pool: V3Pool) -> bool:
        pool.update_state()
        current_tick=pool.current_tick
        return self.is_in_range(current_tick)
    #
    def get_onchain_balances(self) -> tuple[int, int]:
        if self.liquidity is None:
            raise RuntimeError("Position not loaded")

        if self.liquidity == 0:
            return 0, 0

        params = {
            "tokenId": self.token_id,
            "liquidity": self.liquidity,
            "amount0Min": 0,
            "amount1Min": 0,
            "deadline": int(time.time()) + 60,
        }

        try:
            amount0, amount1 = self.nfpm_contract.functions.decreaseLiquidity(
                params
            ).call({"from": self.net.account.address})

            return amount0, amount1

        except Exception as e:
            raise RuntimeError(
                f"Failed to simulate decreaseLiquidity: {e}"
            )
    #
    # 
    def get_nft_pool(self) -> V3Pool:
        pool=V3Pool.from_factory(self.net,self.token0,self.token1,self.fee,self.abi_reg,self.net.factory_address)  
        pool.update_state()
        return pool
    def get_tokens(self) -> tuple[Token, Token]:
        return Token(self.net,self.abi_reg ,self.token0), Token(self.net,self.abi_reg ,self.token1)  # self.token0, self.token1
    #
    #     
    def info(self, pm_address: str=None) -> dict:
        if pm_address is None:
            pm_address = self.net.position_manager_address

        pos = self.nfpm_contract.functions.positions(
            self.token_id
        ).call()

        return {
            "token0": pos[2],
            "token1": pos[3],
            "fee": pos[4],
            "tick_lower": pos[5],
            "tick_upper": pos[6],
            "liquidity": pos[7],
            "tokens_fee0": pos[10],
            "tokens_fee1": pos[11]
        }

#
#
#
class PositionManager(BaseEntity):
    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,pm_address: str=None):
        super().__init__(net)
        self.abi_reg = abi_reg
        if pm_address is None:
            pm_address = self.net.position_manager_address
        
        self.address = self.net.to_checksum_address(pm_address)
        # Initialize ABI and contract instance
        
        nfpm_abi=self.abi_reg.GET_NFPM_ABI(pm_address)
        self.contract = self.net.eth.contract(
            address=self.address,
            abi=nfpm_abi
        )
    #
    #
    def get_all_positions(self, owner_address: str = None):
        """
        Fetches all Uniswap V3 LP NFTs owned by an address and returns a list of LPPosition objects.
        """
        if owner_address is None:
            owner_address = self.net.address
            
        owner_address = self.net.to_checksum_address(owner_address)
        positions_list = []
        
        try:
            # Get the total number of NFTs owned by the address
            balance = self.contract.functions.balanceOf(owner_address).call()
            print(f"Found {balance} Uniswap V3 LP NFTs for address: {owner_address}")

            if balance > 0:
                for i in range(balance):
                    # Get the token ID by index
                    token_id = self.contract.functions.tokenOfOwnerByIndex(owner_address, i).call()
                    
                    # Create and load an LPPosition object
                    # This object already contains the logic to fetch position details from the blockchain
                    pos = LPPosition(self.net,self.abi_reg ,token_id)
                    pos.load(self.address) # self.address here is the Position Manager contract address
                    
                    positions_list.append(pos)
                
                return positions_list
            else:
                print("No LP NFTs found for this address.")
                return []

        except Exception as e:
            print(f"Error fetching liquidity positions: {e}")
            return []
    #
    #
    def collect_fees(self, position: LPPosition, recipient: str = None):
        time.sleep(10)
        """
        Collects accumulated fees using an LPPosition object.
        """
        if not isinstance(position, LPPosition):
            raise ValueError("The 'position' argument must be an instance of LPPosition")
        # Safety check: Ensure there are fees to collect

        position.load()

        if position.tokens_fee0 == 0 and position.tokens_fee1 == 0:
            print(f"Action: Position NFT #{position.token_id} has no fees to collect. Skipping...")
            return False
        
        # Determine recipient: prioritize passed argument, then the position owner, then the network address
        if recipient is None:
            recipient = self.net.address

        # Use max uint128 to ensure all pending fees are collected
        # This is a standard practice in Uniswap V3 interaction
        max_uint128 = 2**128 - 1
        
        params = {
            "tokenId": position.token_id,
            "recipient": self.net.to_checksum_address(recipient),
            "amount0Max": max_uint128,
            "amount1Max": max_uint128
        }
        
        # Build the function call using the initialized contract
        func = self.contract.functions.collect(params)
        
        print(f"Action: Preparing to collect fees for NFT #{position.token_id}")
        
        # Send transaction using Web3_Network's built-in transaction builder
        # This handles gas estimation, nonce management, and signing
        return self.net.build_and_send_transaction(func)
    #
    #
    def decrease_liquidity(self, position: LPPosition, percentage: float = 1.0, slippage: float = 0.02, deadline: int = None):
        time.sleep(10)
        """
        Decreases liquidity based on a percentage (0.0 to 1.0) of the position.
        Automatically calculates amount0Min and amount1Min using on-chain balances and slippage.
        """

        if not isinstance(position, LPPosition):
            raise ValueError("The 'position' argument must be an instance of LPPosition")

        position.load()

        if position.liquidity == 0:
            print(f"Action: Position NFT #{position.token_id} has zero liquidity. Skipping decrease...")
            return False
        
        if not (0 < percentage <= 1.0):
            raise ValueError("Percentage must be between 0 and 1.0 (e.g., 0.5 for 50%)")

        if deadline is None:
            deadline = int(time.time()) + 300

        # Calculate the amount of liquidity to remove
        liquidity_to_remove = int(position.liquidity * percentage)
        
        if liquidity_to_remove == 0:
            print("Action: Liquidity to remove is zero. Skipping...")
            return False

        # Get current on-chain balances for the position to estimate min amounts
        # amount0 and amount1 are the principal amounts for the total liquidity
        am0_total, am1_total = position.get_onchain_balances()
        
        # Scale the amounts based on the percentage being removed and apply slippage
        amount0_min = int((am0_total * percentage) * (1 - slippage))
        amount1_min = int((am1_total * percentage) * (1 - slippage))

        params = {
            "tokenId": position.token_id,
            "liquidity": liquidity_to_remove,
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "deadline": deadline
        }
        
        print(f"Action: Preparing to remove {percentage*100}% of liquidity for NFT #{position.token_id}")
        print(f"Details: Liquidity: {liquidity_to_remove}, Min0: {amount0_min}, Min1: {amount1_min}")

        func = self.contract.functions.decreaseLiquidity(params)
        return self.net.build_and_send_transaction(func)
    #
    #
    def burn_position(self, position: LPPosition):
        time.sleep(10)
        """
        Removes the NFT from the blockchain.
        This is only possible when both liquidity and fees have been fully collected (set to zero).
        """
        if not isinstance(position, LPPosition):
            raise ValueError("The 'position' argument must be an instance of LPPosition")

        position.load()

        # Safety check: Uniswap V3 NFPM will revert if liquidity is not zero
        if position.liquidity > 0:
            
            self.decrease_liquidity(position, percentage=1.0, slippage=0.05)

        # Safety check: Uniswap V3 NFPM will revert if fees are not collected
        if position.tokens_fee0 > 0 or position.tokens_fee1 > 0:
    
            self.collect_fees(position)


        print(f"Action: Preparing to burn NFT #{position.token_id}")

        # Build the burn function call
        func = self.contract.functions.burn(position.token_id)
        
        # Build and return the transaction through Web3_Network
        return self.net.build_and_send_transaction(func)
    #
    #
    def full_exit(self, position: LPPosition, slippage: float = 0.02):
        """
        Executes a complete exit from a position:
        1. Removes 100% of liquidity with slippage protection.
        2. Collects all principal tokens and accumulated fees.
        3. Burns the NFT to clear it from the wallet.
        """
        if not isinstance(position, LPPosition):
            raise ValueError("The 'position' argument must be an instance of LPPosition")

        position.load()

        # 1. Decrease Liquidity (100%)
        # Our updated decrease_liquidity already handles get_onchain_balances and slippage internally
        if position.liquidity > 0:
            print(f"Action: Initiating full liquidity removal for NFT #{position.token_id}...")
            self.decrease_liquidity(position, percentage=1.0, slippage=slippage)
            
            # IMPORTANT: In a real environment, you must wait for the transaction receipt 
            # here before proceeding to collect/burn, as the blockchain state needs to update.
            # Example: self.net.w3.eth.wait_for_transaction_receipt(tx_hash)

        # 2. Collect Tokens and Fees
        # This will sweep all tokens (principal + fees) to the recipient's wallet
        print(f"Action: Collecting all tokens and fees for NFT #{position.token_id}...")
        self.collect_fees(position)

        # 3. Burn the NFT
        # Now that liquidity is 0, we can safely remove the NFT from the wallet
        print(f"Action: Burning NFT #{position.token_id} to finalize exit.")
        return self.burn_position(position)
    #
    #   
    def build_mint_params(
        self,
        token0: Token,
        token1: Token,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_desired: int,
        amount1_desired: int,
        slippage: float = 0.01,
        deadline: int = None
    ):
        if deadline is None:
            deadline = int(time.time()) + 300

        self.mint_params = {
            "token0": token0.address,
            "token1": token1.address,
            "fee": fee,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired": amount0_desired,
            "amount1Desired": amount1_desired,
            "amount0Min": 0,
            "amount1Min": 0,
            "recipient": self.net.address,
            "deadline": deadline
        }

        return self.mint_params

    #
    #
    def simulate_mint(self, token0: Token, token1: Token, fee: int, tick_lower: int, tick_upper: int, amount0_desired: int, amount1_desired: int):
        self.build_mint_params(token0, token1, fee, tick_lower, tick_upper, amount0_desired, amount1_desired)
        try:
            _, liquidity, amount0, amount1 = self.contract.functions.mint(
                self.mint_params
            ).call({"from": self.net.address})

            self.mint_simulation = {
                "liquidity": liquidity,
                "amount0_used": amount0,
                "amount1_used": amount1
            }

            return self.mint_simulation

        except Exception as e:
            self.mint_simulation = {
                "error": str(e)
            }
            return self.mint_simulation
    #
    #
    def apply_mint_slippage(self, slippage: float):
        if not hasattr(self, "mint_simulation"):
            raise RuntimeError("Mint simulation not run")

        self.mint_params["amount0Min"] = int(
            self.mint_simulation["amount0_used"] * (1 - slippage)
        )
        self.mint_params["amount1Min"] = int(
            self.mint_simulation["amount1_used"] * (1 - slippage)
        )

        return self.mint_params
    #
    #
    def build_mint_call(self):
        return (
            self.contract.functions
            .mint(tuple(self.mint_params.values()))
            ._encode_transaction_data()
        )

    #
    def mint_liquidity(
        self,
        token0: Token,
        token1: Token,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_desired: int,
        amount1_desired: int,
        amount0_min: int = 0,
        amount1_min: int = 0,
        slippage: float = 0.01,
        deadline: int = None
    ):
        """
        Mints a new Uniswap V3 LP position NFT.
        Automatically calculates amount0Min and amount1Min using slippage.
        """

        if deadline is None:
            deadline = int(time.time()) + 300

        # Ensure allowances for both tokens
        #self.net.router_contract(self.net.router_address)
        #router = SwapRouter(self.net, self.net.router_address)
        #router._ensure_allowance(token0, amount0_desired)
        #router._ensure_allowance(token1, amount1_desired)
        token0.load()
        token1.load()
        token0.ensure_allowance(self.address, amount0_desired)
        token1.ensure_allowance(self.address, amount1_desired)

        # Calculate minimum amounts based on slippage
        #amount0_min = int(amount0_desired * (1 - slippage))
        #amount1_min = int(amount1_desired * (1 - slippage))

        params = {
            "token0": token0.address,
            "token1": token1.address,
            "fee": fee,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired": amount0_desired,
            "amount1Desired": amount1_desired,
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "recipient": self.net.account.address,
            "deadline": deadline
        }

        print(f"Action: Preparing to mint new LP position NFT...")
        print(f"Details: Token0: {token0.symbol}, Token1: {token1.symbol}, Fee: {fee}, "
              f"Amounts Desired: {amount0_desired}/{amount1_desired}, "
              f"Min Amounts: {amount0_min}/{amount1_min}, "
              f"Ticks: [{tick_lower}, {tick_upper}]")

        func = self.contract.functions.mint(params)
        return self.net.build_and_send_transaction(func)
    #
    #
    #
    #
    def jit_mint(self, token0: Token, token1: Token, fee: int, slippage: float = 0.01, deadline: int = None,step: int=None):
        pool=V3Pool.from_factory(self.net, token0.address, token1.address, fee,self.abi_reg ,self.net.factory_address)
        pool.load()
        pool.update_state()
        cp=calculate_raw_price_from_sqrt_price(pool.sqrtPriceX96)
        tick_lower, tick_upper = pool.get_current_match_tick_range(10,step=step)
        lp=calculate_raw_price_by_tick(tick_lower)
        up=calculate_raw_price_by_tick(tick_upper)
        token0.load()
        token1.load()
        token0.balance_of()
        token1.balance_of()
        bal0=token0.token_balance
        bal1=token1.token_balance
        res=calculate_required_amount_and_swap(cp,lp,up,bal0,bal1)

        router = SwapRouter(self.net,self.abi_reg ,self.net.router_address)

        if res['swap_details']=='token0 -> token1':
            swap_amount=int(res['swap_amount'])
            if swap_amount/10**token0.decimals<0.0001:
                pass
            else:
                print(f"Info: Swapping {res['amount0_target']} {token0.symbol} for {res['amount1_target']} {token1.symbol} to balance amounts.")
                router.swap_exact_input_single(token_in=token0, token_out=token1, fee=fee, amount_in=swap_amount, slippage=slippage)

        elif res['swap_details']=='token1 -> token0':
            swap_amount=int(res['swap_amount'])
            if swap_amount/10**token1.decimals<0.0001:
                pass
            else:
                print(f"Info: Swapping {res['amount1_target']} {token1.symbol} for {res['amount0_target']} {token0.symbol} to balance amounts.")
                router.swap_exact_input_single(token_in=token1, token_out=token0, fee=fee, amount_in=swap_amount, slippage=slippage)  


        #time.sleep(5)  # Small delay to let balances update
        token0.balance_of()
        token1.balance_of()

        sim_mint_res=self.simulate_mint(token0, token1, fee, tick_lower, tick_upper, token0.token_balance, token1.token_balance)
        amount0min=int(sim_mint_res['amount0_used']*(1-slippage))
        amount1min=int(sim_mint_res['amount1_used']*(1-slippage))

        return self.mint_liquidity(token0, token1, fee, tick_lower,
                                    tick_upper, token0.token_balance, token1.token_balance,amount0min,amount1min ,slippage, deadline)
    #
    #
#
#
#
class JITZAP(BaseEntity):

    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,jit_zap_address: str=None):
        super().__init__(net)
        self.abi_reg = abi_reg
        if jit_zap_address is None:
            jit_zap_address = self.net.jitzap_address
        self.address = self.net.to_checksum_address(jit_zap_address)

        JITZAP_ABI=self.abi_reg.GET_JITZAP_ABI(jit_zap_address)
        # register ABI directly (NO fetch)

        self.contract = self.net.eth.contract(
            address=self.address,
            abi=JITZAP_ABI
        )
    #
    #
    def execute_jit(
        self,
        token0: Token,
        token1: Token,
        fee: int,
        tick_lower: int,
        tick_upper: int,
        amount0_total: int,
        amount1_total: int,
        perform_swap: bool,
        zero_for_one: bool,
        swap_amount_in: int,
        amount_out_min_swap: int,
        amount0_min_mint: int,
        amount1_min_mint: int,
        gas_limit: int | None = None
    ):
        
        token0.load()
        token1.load()
        token0.ensure_allowance(self.address, amount0_total)
        token1.ensure_allowance(self.address, amount1_total)

        tx = self.contract.functions.executeJIT(
            token0.address,
            token1.address,
            fee,
            tick_lower,
            tick_upper,
            amount0_total,
            amount1_total,
            perform_swap,
            zero_for_one,
            swap_amount_in,
            amount_out_min_swap,
            amount0_min_mint,
            amount1_min_mint
        )
        hash=self.net.build_and_send_transaction_advanced(tx)
        return hash
    #
    #
    def execute_jit_zap_mint(
        self,
        token0: Token,
        token1: Token,
        fee: int,
        slippage: float = 0.02,
        deadline: int = None,
        step: int = None
    ):
        """
        Executes a JIT Zap to mint a new Uniswap V3 LP position NFT.
        """
        pool=V3Pool.from_factory(self.net, token0.address, token1.address, fee,self.abi_reg ,self.net.factory_address)
        #pool.load()
        pool.update_state()
        cp=calculate_raw_price_from_sqrt_price(pool.sqrtPriceX96)
        tick_lower, tick_upper = pool.get_current_match_tick_range(10,step=step)
        lp=calculate_raw_price_by_tick(tick_lower)
        up=calculate_raw_price_by_tick(tick_upper)
        bal0=token0.token_balance
        bal1=token1.token_balance
        res=calculate_required_amount_and_swap(cp,lp,up,bal0,bal1)
        
        #amount0_total=max(bal0,res['amount0_target'])
        #amount1_total=max(bal1,res['amount1_target'])
        amount0_total=bal0
        amount1_total=bal1

        if res['amount0_target']<1 or res['amount1_target']<1:
            raise RuntimeError("Insufficient balance for JIT Zap minting.")
        
        zeroforone=False
        perform_swap=False
        swap_amount=0
        amount_out_min_swap=0
        amount0mint=0
        amount1mint=0

        if res['amount0_target']!=bal0 and res['amount1_target']!=bal1:
            perform_swap=True
            if res['swap_details']=='token1 -> token0':
                zeroforone=False
                amount_out_min_swap=int(res['amount0_target']* (1 - slippage))
            elif res['swap_details']=='token0 -> token1':
                zeroforone=True
                amount_out_min_swap=int(res['amount1_target']* (1 - slippage))
            
            swap_amount=int(res['swap_amount'])
            #
            #

            return self.execute_jit(
                token0,
                token1,
                fee,
                tick_lower,
                tick_upper,
                amount0_total,
                amount1_total,
                perform_swap,
                zeroforone,
                swap_amount,
                amount_out_min_swap,
                amount0mint,
                amount1mint
            )
        else:
            return self.execute_jit(
                token0,
                token1,
                fee,
                tick_lower,
                tick_upper,
                amount0_total,
                amount1_total,
                False,
                0,
                0,
                0,
                int(amount0_total* (1 - slippage)),
                int(amount1_total* (1 - slippage))
            )