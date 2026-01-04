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
from eth_utils import keccak
import web3
from web3.exceptions import ContractLogicError, TimeExhausted
import logging
from calculation import *
import pickle
import os
import hashlib
import base64
import re
from typing import Dict
from eth_account.messages import encode_typed_data
from tqdm import tqdm
import secrets
from eth_abi.packed import encode_packed
from requests.exceptions import RequestException
from urllib3.exceptions import ProtocolError, MaxRetryError, NewConnectionError, SSLError, ReadTimeoutError
from http.client import RemoteDisconnected
import socket
from uniswap_universal_router_decoder import FunctionRecipient, RouterCodec
from eth_abi import encode as abi_encode

#from uniswap_v4_position_manager_decoder import PositionManagerCodec






logger = logging.getLogger(__name__)

class Web3_Network(Web3):

    #router_address = '0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48E'
    #factory_address='0x0227628f3F023bb0B980b67D528571c95c6DaC1c'

    def __init__(self, rpc_url: str, private_key: str | None = None, explorer_api_key: str | None = None):
        
        super().__init__(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 60}))

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
        self.get_explorer_api_url()
    #
    #
    def safe_retry_call(self,fn, retries: int = 5, delay: float = 1.0, backoff: float = 2.0):
        """
        Executes a Web3 call function safely with retries and backoff on network/temporary RPC errors.
        
        Args:
            fn: Lambda function to execute the Web3 call, e.g. `lambda: contract.functions.name().call()`
            retries: Maximum number of attempts
            delay: Initial delay between attempts (seconds)
            backoff: Multiplier for exponential backoff

        Returns:
            Result of fn() if successful

        Raises:
            RuntimeError if all retries fail
            ContractLogicError immediately if a contract logic error occurs
        """
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                return fn()
            except ContractLogicError as e:
                #
                raise
            except (
                RequestException,
                OSError,
                ValueError,
                RemoteDisconnected,
                ProtocolError,
                MaxRetryError,
                NewConnectionError,
                SSLError,
                ReadTimeoutError,
                socket.timeout
            ) as e:
                last_exc = e
                if attempt < retries:
                    print(f"[Retry {attempt}/{retries}] Network error: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= backoff
                else:
                    break
        raise RuntimeError(f"Web3 call failed after {retries} attempts") from last_exc
    #
    #
    def get_explorer_api_url(self,inp_api_url: str=None):
        if inp_api_url is not None:
            self.api_url = inp_api_url
        else:
            self.api_url = "https://api.etherscan.io/v2/api"

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
    def get_universalrouter_address(self,inp_universalrouter_address: str):
        self.universalrouter_address=self.to_checksum_address(inp_universalrouter_address)
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
    def get_v4_position_manager_address(self,inp_v4_position_manager_address: str):
        self.v4_position_manager_address=self.to_checksum_address(inp_v4_position_manager_address)
    #
    #
    def get_pool_manager_address(self,pool_manager_address):
        self.pool_manager_address=self.to_checksum_address(pool_manager_address)
    #
    #
    def get_permit2_address(self,permit2_address:str):
        self.permit2_address=self.to_checksum_address(permit2_address)
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
    def build_factory_contract(self, factory_address: str=None):
        if factory_address is None:
            factory_address = self.factory_address
        self.GET_FACTORY_ABI(factory_address)
        self.factory_contract = self.eth.contract(address=factory_address, abi=self.UNISWAP_V3_FACTORY_ABI)
    #
    #
    def get_pool_address(self, tokenA: str, tokenB: str, fee: int) -> str | None:
        if not hasattr(self, "factory_contract"):
            #raise RuntimeError("Factory contract not initialized")
            if not hasattr(self, "factory_address"):
                raise RuntimeError("Factory address not set")
            self.build_factory_contract(self.factory_address)

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
    def send_transaction_flexible(
        self,
        tx_func=None,
        to_address: str | None = None,
        raw_data: str | None = None,
        value: int = 0,
        gas_multiplier: float = 1.2,
        wait_for_confirmation: bool = True,
        manual_gas_limit: int = 1000000
    ) -> str | bool:
        """
        Broadcasts a transaction in two modes:
        1. Using a contract function object (tx_func)
        2. Using raw calldata (raw_data) and a destination address (to_address)
        """
        sender = self.address
        
        # ---- 1) Initialize base transaction parameters ----
        tx_params = {
            'from': sender,
            'value': value,
            'nonce': self.eth.get_transaction_count(sender),
            'chainId': self.chain_id
        }

        # Determine target address and calldata
        if raw_data:
            if not to_address:
                raise ValueError("to_address is required when providing raw_data.")
            tx_params['to'] = Web3.to_checksum_address(to_address)
            tx_params['data'] = raw_data
        elif tx_func:
            # If tx_func is provided, 'to' and 'data' will be populated by build_transaction later
            pass
        else:
            raise ValueError("Either tx_func or raw_data/to_address must be provided.")

        # ---- 2) Gas Management (Estimate or Fallback) ----
        try:
            if tx_func:
                estimated_gas = tx_func.estimate_gas({'from': sender, 'value': value})
            else:
                # Estimate gas for raw calldata
                estimated_gas = self.eth.estimate_gas(tx_params)
            
            tx_params['gas'] = int(estimated_gas * gas_multiplier)
        except Exception as e:
            print(f"⚠️ Gas estimation failed: {e}. Using manual gas limit: {manual_gas_limit}")
            tx_params['gas'] = manual_gas_limit

        # ---- 3) Gas Pricing (EIP-1559 Support) ----
        if self.network_gas_mode == 'EIP-1559':
            latest_block = self.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            priority_fee = self.eth.max_priority_fee
            
            tx_params['maxPriorityFeePerGas'] = priority_fee
            tx_params['maxFeePerGas'] = int(base_fee * 2 + priority_fee)
            tx_params['type'] = 2 # EIP-1559 Transaction
        else:
            tx_params['gasPrice'] = self.eth.gas_price

        # ---- 4) Finalize Transaction Structure ----
        try:
            if tx_func:
                # Convert function object to a complete transaction dictionary
                final_tx = tx_func.build_transaction(tx_params)
            else:
                # Use the existing params dictionary for raw data execution
                final_tx = tx_params
        except Exception as e:
            self.last_send_error = f"❌ Build Error: {e}"
            print(self.last_send_error)
            return False

        # ---- 5) Signing and Broadcasting ----
        try:
            signed = self.account.sign_transaction(final_tx)
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
                print(f"{self.last_send_error} | Hash: {tx_hash_hex}")
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
        self.load_abi_cache()
        if not os.path.exists('abi_cache'):
            os.makedirs('abi_cache', exist_ok=True)
   
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
        self.V4_CONTRACT_ABI_FALLBACK=[
    # =========================
    # Constructor
    # =========================
    {
        "type": "constructor",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "_poolManager", "type": "address"},
            {"name": "_permit2", "type": "address"},
            {"name": "_unsubscribeGasLimit", "type": "uint256"},
            {"name": "_tokenDescriptor", "type": "address"},
            {"name": "_weth9", "type": "address"},
        ],
    },

    # =========================
    # Errors
    # =========================
    {"type": "error", "name": "AlreadySubscribed", "inputs": [
        {"name": "tokenId", "type": "uint256"},
        {"name": "subscriber", "type": "address"},
    ]},
    {"type": "error", "name": "Unauthorized", "inputs": []},
    {"type": "error", "name": "NotApproved", "inputs": [
        {"name": "caller", "type": "address"},
    ]},
    {"type": "error", "name": "DeadlinePassed", "inputs": [
        {"name": "deadline", "type": "uint256"},
    ]},
    {"type": "error", "name": "NotPoolManager", "inputs": []},
    {"type": "error", "name": "UnsupportedAction", "inputs": [
        {"name": "action", "type": "uint256"},
    ]},

    # =========================
    # Events
    # =========================
    {
        "type": "event",
        "name": "Transfer",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": True, "name": "id", "type": "uint256"},
        ],
    },
    {
        "type": "event",
        "name": "Approval",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "owner", "type": "address"},
            {"indexed": True, "name": "spender", "type": "address"},
            {"indexed": True, "name": "id", "type": "uint256"},
        ],
    },
    {
        "type": "event",
        "name": "Subscription",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "tokenId", "type": "uint256"},
            {"indexed": True, "name": "subscriber", "type": "address"},
        ],
    },
    {
        "type": "event",
        "name": "Unsubscription",
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "tokenId", "type": "uint256"},
            {"indexed": True, "name": "subscriber", "type": "address"},
        ],
    },

    # =========================
    # ERC721 View
    # =========================
    {
        "type": "function",
        "name": "ownerOf",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"type": "address"}],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"type": "uint256"}],
    },

    # =========================
    # Pool / Position
    # =========================
    {
        "type": "function",
        "name": "getPositionLiquidity",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [{"name": "liquidity", "type": "uint128"}],
    },
    {
        "type": "function",
        "name": "getPoolAndPositionInfo",
        "stateMutability": "view",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [
            {
                "name": "poolKey",
                "type": "tuple",
                "components": [
                    {"name": "currency0", "type": "address"},
                    {"name": "currency1", "type": "address"},
                    {"name": "fee", "type": "uint24"},
                    {"name": "tickSpacing", "type": "int24"},
                    {"name": "hooks", "type": "address"},
                ],
            },
            {"name": "info", "type": "uint256"},
        ],
    },

    # =========================
    # Liquidity Management
    # =========================
    {
        "type": "function",
        "name": "modifyLiquidities",
        "stateMutability": "payable",
        "inputs": [
            {"name": "unlockData", "type": "bytes"},
            {"name": "deadline", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "modifyLiquiditiesWithoutUnlock",
        "stateMutability": "payable",
        "inputs": [
            {"name": "actions", "type": "bytes"},
            {"name": "params", "type": "bytes[]"},
        ],
        "outputs": [],
    },

    # =========================
    # Subscription
    # =========================
    {
        "type": "function",
        "name": "subscribe",
        "stateMutability": "payable",
        "inputs": [
            {"name": "tokenId", "type": "uint256"},
            {"name": "newSubscriber", "type": "address"},
            {"name": "data", "type": "bytes"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "unsubscribe",
        "stateMutability": "payable",
        "inputs": [{"name": "tokenId", "type": "uint256"}],
        "outputs": [],
    },

    # =========================
    # Multicall
    # =========================
    {
        "type": "function",
        "name": "multicall",
        "stateMutability": "payable",
        "inputs": [{"name": "data", "type": "bytes[]"}],
        "outputs": [{"type": "bytes[]"}],
    },
]
        self.V4_POOL_MANAGER_ABI_FALLBACK = [
    {
        "inputs": [{"internalType": "address", "name": "initialOwner", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "constructor",
    },

    # ───────────── Errors ─────────────
    {"inputs": [], "name": "AlreadyUnlocked", "type": "error"},
    {"inputs": [
        {"internalType": "address", "name": "currency0", "type": "address"},
        {"internalType": "address", "name": "currency1", "type": "address"},
    ], "name": "CurrenciesOutOfOrderOrEqual", "type": "error"},
    {"inputs": [], "name": "CurrencyNotSettled", "type": "error"},
    {"inputs": [], "name": "DelegateCallNotAllowed", "type": "error"},
    {"inputs": [], "name": "InvalidCaller", "type": "error"},
    {"inputs": [], "name": "ManagerLocked", "type": "error"},
    {"inputs": [], "name": "MustClearExactPositiveDelta", "type": "error"},
    {"inputs": [], "name": "NonzeroNativeValue", "type": "error"},
    {"inputs": [], "name": "PoolNotInitialized", "type": "error"},
    {"inputs": [], "name": "ProtocolFeeCurrencySynced", "type": "error"},
    {"inputs": [{"internalType": "uint24", "name": "fee", "type": "uint24"}], "name": "ProtocolFeeTooLarge", "type": "error"},
    {"inputs": [], "name": "SwapAmountCannotBeZero", "type": "error"},
    {"inputs": [{"internalType": "int24", "name": "tickSpacing", "type": "int24"}], "name": "TickSpacingTooLarge", "type": "error"},
    {"inputs": [{"internalType": "int24", "name": "tickSpacing", "type": "int24"}], "name": "TickSpacingTooSmall", "type": "error"},
    {"inputs": [], "name": "UnauthorizedDynamicLPFeeUpdate", "type": "error"},

    # ───────────── Events ─────────────
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "PoolId", "name": "id", "type": "bytes32"},
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": False, "internalType": "int128", "name": "amount0", "type": "int128"},
            {"indexed": False, "internalType": "int128", "name": "amount1", "type": "int128"},
            {"indexed": False, "internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"indexed": False, "internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"indexed": False, "internalType": "int24", "name": "tick", "type": "int24"},
            {"indexed": False, "internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "Swap",
        "type": "event",
    },

    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "PoolId", "name": "id", "type": "bytes32"},
            {"indexed": True, "internalType": "address", "name": "sender", "type": "address"},
            {"indexed": False, "internalType": "int24", "name": "tickLower", "type": "int24"},
            {"indexed": False, "internalType": "int24", "name": "tickUpper", "type": "int24"},
            {"indexed": False, "internalType": "int256", "name": "liquidityDelta", "type": "int256"},
            {"indexed": False, "internalType": "bytes32", "name": "salt", "type": "bytes32"},
        ],
        "name": "ModifyLiquidity",
        "type": "event",
    },

    # ───────────── View Functions ─────────────
    {
        "inputs": [{"internalType": "Currency", "name": "currency", "type": "address"}],
        "name": "protocolFeesAccrued",
        "outputs": [{"internalType": "uint256", "name": "amount", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },

    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },

    # ───────────── Core Functions ─────────────
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "Currency", "name": "currency0", "type": "address"},
                    {"internalType": "Currency", "name": "currency1", "type": "address"},
                    {"internalType": "uint24", "name": "fee", "type": "uint24"},
                    {"internalType": "int24", "name": "tickSpacing", "type": "int24"},
                    {"internalType": "contract IHooks", "name": "hooks", "type": "address"},
                ],
                "internalType": "struct PoolKey",
                "name": "key",
                "type": "tuple",
            },
            {
                "components": [
                    {"internalType": "bool", "name": "zeroForOne", "type": "bool"},
                    {"internalType": "int256", "name": "amountSpecified", "type": "int256"},
                    {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                ],
                "internalType": "struct IPoolManager.SwapParams",
                "name": "params",
                "type": "tuple",
            },
            {"internalType": "bytes", "name": "hookData", "type": "bytes"},
        ],
        "name": "swap",
        "outputs": [{"internalType": "BalanceDelta", "name": "swapDelta", "type": "int256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },

    {
        "inputs": [{"internalType": "bytes", "name": "data", "type": "bytes"}],
        "name": "unlock",
        "outputs": [{"internalType": "bytes", "name": "result", "type": "bytes"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
        self.UNIVERSAL_ROUTER_ABI_FALLBACK= [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "permit2", "type": "address"},
                    {"internalType": "address", "name": "weth9", "type": "address"},
                    {"internalType": "address", "name": "v2Factory", "type": "address"},
                    {"internalType": "address", "name": "v3Factory", "type": "address"},
                    {"internalType": "bytes32", "name": "pairInitCodeHash", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "poolInitCodeHash", "type": "bytes32"},
                    {"internalType": "address", "name": "v4PoolManager", "type": "address"},
                    {"internalType": "address", "name": "v3NFTPositionManager", "type": "address"},
                    {"internalType": "address", "name": "v4PositionManager", "type": "address"},
                ],
                "internalType": "struct RouterParameters",
                "name": "params",
                "type": "tuple",
            }
        ],
        "stateMutability": "nonpayable",
        "type": "constructor",
    },
    {"inputs": [], "name": "BalanceTooLow", "type": "error"},
    {"inputs": [], "name": "ContractLocked", "type": "error"},
    {"inputs": [{"internalType": "Currency", "name": "currency", "type": "address"}], "name": "DeltaNotNegative", "type": "error"},
    {"inputs": [{"internalType": "Currency", "name": "currency", "type": "address"}], "name": "DeltaNotPositive", "type": "error"},
    {"inputs": [], "name": "ETHNotAccepted", "type": "error"},
    {
        "inputs": [
            {"internalType": "uint256", "name": "commandIndex", "type": "uint256"},
            {"internalType": "bytes", "name": "message", "type": "bytes"},
        ],
        "name": "ExecutionFailed",
        "type": "error",
    },
    {"inputs": [], "name": "FromAddressIsNotOwner", "type": "error"},
    {"inputs": [], "name": "InputLengthMismatch", "type": "error"},
    {"inputs": [], "name": "InsufficientBalance", "type": "error"},
    {"inputs": [], "name": "InsufficientETH", "type": "error"},
    {"inputs": [], "name": "InsufficientToken", "type": "error"},
    {
        "inputs": [{"internalType": "bytes4", "name": "action", "type": "bytes4"}],
        "name": "InvalidAction",
        "type": "error",
    },
    {"inputs": [], "name": "InvalidBips", "type": "error"},
    {
        "inputs": [{"internalType": "uint256", "name": "commandType", "type": "uint256"}],
        "name": "InvalidCommandType",
        "type": "error",
    },
    {"inputs": [], "name": "InvalidEthSender", "type": "error"},
    {"inputs": [], "name": "InvalidPath", "type": "error"},
    {"inputs": [], "name": "InvalidReserves", "type": "error"},
    {"inputs": [], "name": "LengthMismatch", "type": "error"},
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "NotAuthorizedForToken",
        "type": "error",
    },
    {"inputs": [], "name": "NotPoolManager", "type": "error"},
    {"inputs": [], "name": "OnlyMintAllowed", "type": "error"},
    {"inputs": [], "name": "SliceOutOfBounds", "type": "error"},
    {"inputs": [], "name": "TransactionDeadlinePassed", "type": "error"},
    {"inputs": [], "name": "UnsafeCast", "type": "error"},
    {
        "inputs": [{"internalType": "uint256", "name": "action", "type": "uint256"}],
        "name": "UnsupportedAction",
        "type": "error",
    },
    {"inputs": [], "name": "V2InvalidPath", "type": "error"},
    {"inputs": [], "name": "V2TooLittleReceived", "type": "error"},
    {"inputs": [], "name": "V2TooMuchRequested", "type": "error"},
    {"inputs": [], "name": "V3InvalidAmountOut", "type": "error"},
    {"inputs": [], "name": "V3InvalidCaller", "type": "error"},
    {"inputs": [], "name": "V3InvalidSwap", "type": "error"},
    {"inputs": [], "name": "V3TooLittleReceived", "type": "error"},
    {"inputs": [], "name": "V3TooMuchRequested", "type": "error"},
    {
        "inputs": [
            {"internalType": "uint256", "name": "minAmountOutReceived", "type": "uint256"},
            {"internalType": "uint256", "name": "amountReceived", "type": "uint256"},
        ],
        "name": "V4TooLittleReceived",
        "type": "error",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "maxAmountInRequested", "type": "uint256"},
            {"internalType": "uint256", "name": "amountRequested", "type": "uint256"},
        ],
        "name": "V4TooMuchRequested",
        "type": "error",
    },
    {
        "inputs": [],
        "name": "V3_POSITION_MANAGER",
        "outputs": [{"internalType": "contract INonfungiblePositionManager", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "V4_POSITION_MANAGER",
        "outputs": [{"internalType": "contract IPositionManager", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes", "name": "commands", "type": "bytes"},
            {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes", "name": "commands", "type": "bytes"},
            {"internalType": "bytes[]", "name": "inputs", "type": "bytes[]"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "execute",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "msgSender",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "poolManager",
        "outputs": [{"internalType": "contract IPoolManager", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "int256", "name": "amount0Delta", "type": "int256"},
            {"internalType": "int256", "name": "amount1Delta", "type": "int256"},
            {"internalType": "bytes", "name": "data", "type": "bytes"},
        ],
        "name": "uniswapV3SwapCallback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes", "name": "data", "type": "bytes"}],
        "name": "unlockCallback",
        "outputs": [{"internalType": "bytes", "name": "", "type": "bytes"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {"stateMutability": "payable", "type": "receive"},
]
    #
    #
    def GET_ERC20_ABI(self, token_address: str) -> list:
        token_address=self.net.to_checksum_address(token_address)
        if token_address in self.abi_cache.keys():
            return self.abi_cache[token_address]
        ERC20_ABI=self.net.fetch_abi_retry(token_address)
        if ERC20_ABI:
            self.abi_cache[token_address]=ERC20_ABI
            with open(f'abi_cache\\abi_{token_address}.json', 'w') as f:
                json.dump(ERC20_ABI, f, indent=4)
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
            with open(f'abi_cache\\abi_{nfpm_address}.json', 'w') as f:
                json.dump(NFPM_ABI, f, indent=4)
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
            with open(f'abi_cache\\abi_{pool_address}.json', 'w') as f:
                json.dump(V3_POOL_ABI, f, indent=4)
            return V3_POOL_ABI
        else:
            return self.V3_POOL_ABI_FALLBACK
    #
    #
    def GET_V4_PM_ABI(self, v4_pm_address: str=None) -> list:
        if v4_pm_address is None:
            v4_pm_address=self.net.v4_position_manager_address
        v4_pm_address=self.net.to_checksum_address(v4_pm_address)
        if v4_pm_address in self.abi_cache.keys():
            return self.abi_cache[v4_pm_address]
        V4_PM_ABI=self.net.fetch_abi_retry(v4_pm_address)
        if V4_PM_ABI:
            self.abi_cache[v4_pm_address]=V4_PM_ABI
            with open(f'abi_cache\\abi_{v4_pm_address}.json', 'w') as f:
                json.dump(V4_PM_ABI, f, indent=4)
            return V4_PM_ABI
        else:
            return self.V4_CONTRACT_ABI_FALLBACK
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
            with open(f'abi_cache\\abi_{router_address}.json', 'w') as f:
                json.dump(ROUTER_ABI, f, indent=4)
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
            with open(f'abi_cache\\abi_{factory_address}.json', 'w') as f:
                json.dump(FACTORY_ABI, f, indent=4)
            return FACTORY_ABI
        else:
            return self.FACTORY_ABI_FALLBACK
    #
    #
    def GET_UNIVERSALROUTER_ABI(self,universal_address:str=None):
        if universal_address is None:
            universal_address=self.net.universalrouter_address
        universal_address=self.net.to_checksum_address(universal_address)
        if universal_address in self.abi_cache.keys():
            return self.abi_cache[universal_address]
        UNIVERSALROUTER_ABI=self.net.fetch_abi_retry(universal_address)
        if UNIVERSALROUTER_ABI:
            self.abi_cache[universal_address]=UNIVERSALROUTER_ABI
            with open(f'abi_cache\\abi_{universal_address}.json', 'w') as f:
                json.dump(UNIVERSALROUTER_ABI, f, indent=4)
            return UNIVERSALROUTER_ABI
        else:
            return self.UNIVERSALROUTER_ABI_FALLBACK
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
            with open(f'abi_cache\\abi_{JITZAP_ADDRESS}.json', 'w') as f:
                json.dump(JITZAP_ABI, f, indent=4)
            return JITZAP_ABI
        else:
            self.abi_cache[self.net.jitzap_address]=self.JIT_ZAP_ABI_FALLBACK
            return self.JIT_ZAP_ABI_FALLBACK
    #
    #
    def GET_V4_POOL_MANAGER_ABI(self, v4_pool_manager_address: str=None) -> list:
        v4_pool_manager_address=self.net.to_checksum_address(v4_pool_manager_address)
        if v4_pool_manager_address in self.abi_cache.keys():
            return self.abi_cache[v4_pool_manager_address]
        V4_POOL_MANAGER_ABI=self.net.fetch_abi_retry(v4_pool_manager_address)
        if V4_POOL_MANAGER_ABI:
            self.abi_cache[v4_pool_manager_address]=V4_POOL_MANAGER_ABI
            with open(f'abi_cache\\abi_{v4_pool_manager_address}.json', 'w') as f:
                json.dump(V4_POOL_MANAGER_ABI, f, indent=4)
            return V4_POOL_MANAGER_ABI
        else:
            return self.V4_POOL_MANAGER_ABI_FALLBACK
    #
    #
    def GET_ANY_CONTRACT_ABI(self, contract_address: str) -> list:
        contract_address=self.net.to_checksum_address(contract_address)
        if contract_address in self.abi_cache.keys():
            return self.abi_cache[contract_address]
        ABI=self.net.fetch_abi_retry(contract_address)
        if ABI:
            self.abi_cache[contract_address]=ABI
            with open(f'abi_cache\\abi_{contract_address}.json', 'w') as f:
                json.dump(ABI, f, indent=4)
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
        ADDRESS_ZERO = "0x0000000000000000000000000000000000000000"
        ETH_PSEUDO_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
        super().__init__(net)
        self.abi_reg = abi_reg

        self.address = net.to_checksum_address(address)
        self.is_native = (self.address.lower() == ADDRESS_ZERO.lower()) or \
                         (self.address.lower() == ETH_PSEUDO_ADDRESS.lower())
        
        self.contract = None
        self.name: str | None = None
        self.symbol: str | None = None
        self.decimals: int | None = None
        self.load()
    #
    #
    def build_contract(self):
        if hasattr(self,'address') and not self.is_native:
            try:
                self.contract=self.net.eth.contract(
                    address=self.address,
                    abi=self.abi_reg.GET_ERC20_ABI(self.address)
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create ERC20 contract for {self.address}: {e}"
                )
    #
    #
    def load(self):
        if self.is_native:
            self.name = "Native Ether"
            self.symbol = "ETH"
            self.decimals = 18
            self.contract = None
            self.balance_of()
            return

        self.build_contract()

        self.meta_data()
        self.balance_of()
    #
    #
    def meta_data(self):
        if hasattr (self,'contract'):
            self.name = self.net.safe_retry_call(
                fn=lambda: self.contract.functions.name().call(),
                retries=5,
                delay=2
            )

            self.symbol = self.net.safe_retry_call(
                fn=lambda: self.contract.functions.symbol().call(),
                retries=5,
                delay=2
            )

            self.decimals = self.net.safe_retry_call(
                fn=lambda: self.contract.functions.decimals().call(),
                retries=5,
                delay=2
            )


    #
    def balance_of(self, address: str=None) -> int:
        if address is None:
            address = self.net.account.address
        if self.is_native:
            self.token_balance = self.net.eth.get_balance(address)
        else:
            self.token_balance = self.contract.functions.balanceOf(
                    self.net.to_checksum_address(address)
                    ).call()
    #
    #
    def allowance(self, owner: str, spender: str) -> int:
        if self.is_native:
            return True
        return self.contract.functions.allowance(
            self.net.to_checksum_address(owner),
            self.net.to_checksum_address(spender)
        ).call()
    #
    #
    def ensure_allowance(self, spender: str, amount: int, infinite: bool = True) -> bool:
        if self.is_native:
            return True
        
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
    def supports_permit(self) -> bool:
        """
        Checks whether token supports EIP-2612 permit
        """
        if self.is_native:
            return False

        try:
            # EIP-2612 requires nonces(address)
            self.contract.functions.nonces(
                self.net.account.address
            ).call()
            return True
        except Exception:
            return False
    #
    #
    def permit(
    self,
    spender: str,
    value: int,
    deadline: int,
    v: int,
    r: bytes,
    s: bytes
    ) -> bool:
        """
        Executes EIP-2612 permit
        """

        if self.is_native:
            return True

        owner = self.net.account.address
        spender = self.net.to_checksum_address(spender)

        tx = self.contract.functions.permit(
            owner,
            spender,
            value,
            deadline,
            v,
            r,
            s
        )

        tx_hash = self.net.build_and_send_transaction(
            tx,
            wait_for_confirmation=True
        )

        if not tx_hash:
            raise RuntimeError(f"Permit failed for {self.symbol}")

        return True
    #
    #
    def approve(
    self,
    spender: str,
    amount: int
    ) -> bool:
        """
        Standard ERC20 approve
        """

        if self.is_native:
            return True

        spender = self.net.to_checksum_address(spender)

        tx = self.contract.functions.approve(
            spender,
            amount
        )

        tx_hash = self.net.build_and_send_transaction(
            tx,
            wait_for_confirmation=True
        )

        if not tx_hash:
            raise RuntimeError(f"Approve failed for {self.symbol}")

        return True
    #
    #
    def read_domain(self) -> dict:
        if not self.supports_permit():
            raise RuntimeError("Token does not support permit")
        
        name = self.contract.functions.name().call()

        try:
            version = self.contract.functions.version().call()
        except:
            try:
                version = self.contract.functions.VERSION().call()
            except:
                version = "1"  # fallback safe default

        self.version=version

        return {
            "name": name,
            "version": version,
            "chainId": self.net.chain_id,
            "verifyingContract": self.address
        }
    #
    #
    def build_vrs(self,owner,spender,amount,nonce,deadline):
        self.types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Permit": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ],
        }
        message = {
        "owner": owner,
        "spender": spender,
        "value": amount,
        "nonce": nonce,
        "deadline": deadline,
            }

        domain=self.read_domain()
        typed_data = {
            "types": self.types,
            "primaryType": "Permit",
            "domain": domain,
            "message": message,
        }

        encoded = encode_typed_data(full_message=typed_data)

        '''encoded = encode_typed_data(
            domain_data=self.version,
            message_types=self.types,
            message_data=message
            )'''


        signed = Account.sign_message(
            encoded,
            private_key=self.net.private_key
        )

        v = signed.v
        r = signed.r
        s = signed.s

        message.update({
            'v':v,
            'r':r,
            's':s})

        return message
    #
    #
    def ensure_allowance_smart(
    self,
    spender: str,
    amount: int,
    deadline=None,
    infinite: bool = True,
    permit_data: dict | None = None
    ) -> bool:
        """
        Smart allowance handler:
        - If allowance sufficient → OK
        - If permit supported & data provided → try permit
        - Fallback to approve
        """

        if self.is_native:
            return True

        self.load()
        spender = self.net.to_checksum_address(spender)
        owner = self.net.account.address

        if deadline is None:
            deadline=int(time.time())+300

        current = self.allowance(owner, spender)
        if current >= amount:
            print("No need to approve...")
            return True

        # --- TRY PERMIT ---
        if self.supports_permit():
            if permit_data is None:
                nonce = self.contract.functions.nonces(owner).call()
                permit_data=self.build_vrs(owner,spender,amount,nonce,deadline)
            try:
                self.permit(
                    spender=spender,
                    value=permit_data["value"],
                    deadline=permit_data["deadline"],
                    v=permit_data["v"],
                    r=permit_data["r"],
                    s=permit_data["s"]
                )

                # re-check after permit
                if self.allowance(owner, spender) >= amount:
                    print("Permit Done for 5 Min ")
                    return True

            except Exception as e:
                print(f"⚠️ permit failed, fallback to approve: {e}")

        # --- FALLBACK APPROVE ---
        if current > 0:
            self.net.build_and_send_transaction(
                self.contract.functions.approve(spender, 0),
                wait_for_confirmation=True
            )

        approve_amount = (2**256 - 1) if infinite else amount

        tx_hash = self.net.build_and_send_transaction_advanced(
            self.contract.functions.approve(spender, approve_amount),
            wait_for_confirmation=True
        )

        if not tx_hash:
            raise RuntimeError(f"Approve failed for {self.symbol}")

        return True

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
    #-----------------------------------------------------------
    #
    def pool_state_after_swap_simple(
    self,
    swap_details,
    amount_in: int
    ):
        sqrtP = self.sqrtPriceX96
        L = self.liquidity
        amount_in_int = int(amount_in)

        #zero_for_one=True if swap_details=='token0 -> token1' else False
        zero_for_one = (swap_details == 'token0 -> token1')

        if zero_for_one:
            # token0 -> token1 → price decreases
            sqrtP_after = sqrtP - (amount_in * (1 << 96)) // L

        else:
            # token1 -> token0 → price increases
            sqrtP_after = sqrtP + (amount_in * (1 << 96)) // L

        tick_after = get_tick_from_sqrt_price(sqrtP_after)

        return tick_after

    #
    #---------------------------------------------------------
    def get_tokens(self)->tuple[Token,Token]:
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
class UniversalRouter(BaseEntity):
    def __init__(self, net: Web3_Network, abi_reg: ABIRegistry, address: str | None = None):
        super().__init__(net)
        self.abi_reg = abi_reg
        if address is None:
            address = self.net.universalrouter_address
        self.address = net.to_checksum_address(address)
        
        # Initialize contract with the correct ABI from Registry
        self.contract = net.eth.contract(
            address=self.address, 
            abi=self.abi_reg.GET_UNIVERSALROUTER_ABI(self.address)
        )

        self.codec=RouterCodec()

        # --- COMMANDS (Universal Router Top Level OpCodes) ---
        self.V4_SWAP = 0x10
        self.PERMIT2_PERMIT = 0x02
        self.PERMIT2_TRANSFER_FROM = 0x03
        self.SWEEP = 0x04
        
        # --- V4 ROUTER ACTIONS (Nested inside V4_SWAP / OpCode 0x10) ---
        self.ACTION_SWAP_EXACT_IN_SINGLE = 0x06
        self.ACTION_SETTLE_ALL = 0x0c      # Used for ERC20 payments
        self.ACTION_TAKE_ALL = 0x0f        # Used to receive output tokens
        self.ACTION_SETTLE_NATIVE = 0x0b   # Used for Native ETH payments
        self.ACTION_TAKE = 0x0e            # Used to receive output tokens
    #
    #
    def execute(self, commands: bytes, inputs: list[bytes], deadline: int, value: int = 0):
        """
        Returns the contract function object (tx_func) to be processed 
        by build_and_send_transaction_advanced.
        """
        # Create the function object without building/signing it yet
        tx_func = self.contract.functions.execute(commands, inputs, deadline)
        return tx_func
        
        # Delegate the rest (gas, nonce, sign, send) to your advanced sender
        return self.net.build_and_send_transaction_advanced(
            tx_func=tx_func,
            sender=self.net.address,
            value=value
        )
    #
    #
    @staticmethod
    def generate_safe_nonce():
        # uint48 max = 2**48 - 1
        return secrets.randbits(48) & ((1 << 48) - 1)
    #
    #
    def build_vrs(self, token_address: str, amount: int, nonce: int = None):
        if nonce is None:
            nonce = self.generate_safe_nonce()
        deadline = int(time.time()) + 300  #

        #
        domain = {
            "name": "Permit2",
            "chainId": self.net.chain_id,
            "verifyingContract": self.net.permit2_address
        }

        #
        types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "PermitSingle": [
                {"name": "permitted", "type": "TokenPermissions"},
                {"name": "nonce", "type": "uint256"},
                {"name": "deadline", "type": "uint256"},
            ],
            "TokenPermissions": [
                {"name": "token", "type": "address"},
                {"name": "amount", "type": "uint256"},
            ],
        }

        #
        message = {
            "permitted": {
                "token": token_address,
                "amount": amount,
            },
            "nonce": nonce,
            "deadline": deadline,
        }

        # 
        typed_data = {
            "types": types,
            "domain": domain,
            "primaryType": "PermitSingle",
            "message": message,
        }

        signable = encode_typed_data(full_message=typed_data)
        signed = Account.sign_message(signable, self.net.private_key)
        v,r,s=signed.v,signed.r,signed.s

        if isinstance(r, int):
            r = r.to_bytes(32, byteorder='big')
        if isinstance(s, int):
            s = s.to_bytes(32, byteorder='big')

        return v, r, s
    #
    #
    def build_pool_key(self,token0: str, token1: str, fee: int, tickspacing: int=None, hooks: str = "0x0000000000000000000000000000000000000000"):
        if tickspacing is None:
            tickspacing = calculate_tickspacing_by_feetier(fee)
        t0 = self.net.to_checksum_address(token0)
        t1 = self.net.to_checksum_address(token1)
        
        # V4 Requirement: token0 must be < token1
        if int(t0, 16) > int(t1, 16):
            t0, t1 = t1, t0
            
        return (t0, t1, int(fee), int(tickspacing), self.net.to_checksum_address(hooks))
    #
    #
    def create_permit_signature(self, token_address):
        """
        Create a Permit2 signature for a specific transaction (needed for each swap)
        """
        token_address = Web3.to_checksum_address(token_address)
        permit2_contract = self.net.eth.contract(address=self.net.permit2_address, abi=self.abi_reg.GET_ANY_CONTRACT_ABI(self.net.permit2_address))
        
        p2_amount, p2_expiration, p2_nonce = permit2_contract.functions.allowance(
            self.net.address,
            token_address,
            self.address
        ).call()
        
        print("p2_amount, p2_expiration, p2_nonce: ", p2_amount, p2_expiration, p2_nonce)
        
        allowance_amount = 2**160 - 1  # max/infinite
        permit_data, signable_message = self.codec.create_permit2_signable_message(
            token_address,
            allowance_amount,
            self.codec.get_default_expiration(),
            p2_nonce,
            self.address,
            self.codec.get_default_deadline(),
            self.net.eth.chain_id,
        )
        signed_message = self.net.account.sign_message(signable_message)
        return permit_data, signed_message
    #
    #
    def make_trade_unified(self, from_token: Token, to_token: Token, amount: int, fee: int, slippage: float = None, pool_version="v4"):
        """
        Execute a swap using Universal Router (Unified for V3 & V4).
        Supports: Token->Token, Token->Native, Native->Token.
        """
        
        # 0. Constants and Setup
        ADDRESS_ZERO = "0x0000000000000000000000000000000000000000"
        
        # Determine if tokens are Native (ETH/MATIC/etc.)
        is_native_input = from_token.is_native
        is_native_output = to_token.is_native

        # For V4, Native currency address MUST be ADDRESS_ZERO
        # Ensure your Token objects return ADDRESS_ZERO if they are native, 
        # otherwise we force it here for the protocol logic.
        addr_in = ADDRESS_ZERO if is_native_input else from_token.address
        addr_out = ADDRESS_ZERO if is_native_output else to_token.address

        # 1. Balance & Allowance Checks
        if not is_native_input:
            balance = from_token.token_balance
            if balance < amount:
                raise ValueError(f"Insufficient balance. Have: {balance}, Need: {amount}")

            # Check Permit2 / Allowance
            from_token.ensure_allowance_smart(self.address, amount)
            print("Allowance check passed")

            # Create Permit2 signature (Only needed for V3 or if V4 builder requires it explicitly)
            # Note: Some V4 SDKs handle permit automatically if integrated, 
            # but keeping your logic here is safe.
            permit_data, signed_message = self.create_permit_signature(from_token.address)
            if not permit_data or not signed_message:
                print("Failed to create permit signature")
                # Depending on SDK, you might proceed if allowance is infinite and direct transfer is used
                # return None 
        
        amount_in_wei = amount
        min_amount_out = 0  # Should be calculated based on slippage in a real app
        
        # Get deadline
        deadline = self.net.eth.get_block("latest")["timestamp"] + 300

        # 2. Logic Selection (V3 vs V4)
        if pool_version.lower() == "v3":
            # --- V3 Logic (Existing) ---
            # Note: For V3, the router handles wrapping/unwrapping automatically via specific functions
            # like v3_swap_exact_in (for tokens) or mixed logic.
            # Assuming your codec handles generic V3 structures:
            encoded_data = (
                self.codec.encode.chain()
                .permit2_permit(permit_data, signed_message) if (permit_data and signed_message) else self.codec.encode.chain()
                .v4_swap_exact_in( # Use v3_swap_exact_in typically, ensuring method name matches your SDK
                    FunctionRecipient.SENDER,
                    amount_in_wei,
                    min_amount_out,
                    [
                        from_token.address, # V3 typically uses WETH address, not Zero, unless using specific ETH funcs
                        fee,
                        to_token.address,
                    ],
                ).build(deadline)
            )

        elif pool_version.lower() == "v4":
            # --- V4 Logic (Unified) ---
            
            # A. Calculate Pool Key
            tick_spacing = calculate_tickspacing_by_feetier(fee)
            
            # Important: Pool Key MUST use ADDRESS_ZERO for native tokens in V4
            pool_key = self.codec.encode.v4_pool_key(
                addr_in,
                addr_out,
                fee,
                tick_spacing,
            )
            
            # Determine ZeroForOne (Token0 < Token1 logic)
            # We compare the sanitized addresses (where native is 0x00...00)
            zero_for_one = int(addr_in, 16) < int(addr_out, 16)

            # B. Start Building V4 Sequence
            builder = self.codec.encode.chain().v4_swap()

            # Action 1: Swap
            # This calculates the swap amounts but doesn't move funds yet.
            builder.swap_exact_in_single(
                pool_key=pool_key,
                zero_for_one=zero_for_one,
                amount_in=amount_in_wei,
                amount_out_min=min_amount_out,
                hook_data=b'' 
            )

            # Action 2: Settle (Input Side)
            # We must pay the PoolManager.
            if is_native_input:
                # User sends ETH with tx -> Router -> PoolManager.
                # 'settle' with payer_is_user=True usually instructs to use available funds/msg.value
                builder.settle(addr_in, amount_in_wei, payer_is_user=True)
            else:
                # Token Input. Use settle_all or settle.
                # payer_is_user=True triggers the Pull (Permit2) from user to PM.
                builder.settle(addr_in, amount_in_wei, payer_is_user=True)

            # Action 3: Take (Output Side)
            # We claim the output tokens from PoolManager.
            if is_native_output:
                # We take ETH. 
                # In V4, taking Native 0x00..00 sends ETH to the recipient.
                builder.take_all(addr_out, 0)
            else:
                # We take ERC20.
                builder.take_all(addr_out, 0)

            # C. Finalize Build
            # Note: We don't need .sweep() usually in pure V4 if we used take_all pointing to SENDER.
            encoded_data = builder.build_v4_swap().build(deadline)

        else:
            raise ValueError("Unsupported pool_version. Use 'v3' or 'v4'.")

        print(f"Encoded Data: {encoded_data}")

        # 3. Execute Transaction
        # If input is native, we must send value with the transaction
        tx_value = amount_in_wei if is_native_input else 0
        
        # self.net.send_transaction_flexible(
        #     to_address=self.address, 
        #     raw_data=encoded_data, 
        #     value=tx_value
        # )
        self.net.send_transaction_flexible(to_address=self.address,raw_data=encoded_data,value=tx_value)
        #return encoded_data
    #
    #
#
#
#
class LPPosition(BaseEntity):
    def __init__(self, net: Web3_Network,abi_reg:ABIRegistry ,token_id: int,metadata=None):
        super().__init__(net)
        self.abi_reg = abi_reg
        self.token_id = token_id
        self.metadata=metadata

        if metadata:
            self.liquidity = metadata.get('liquidity')
            self.tick_lower = metadata.get('tickLower')
            self.tick_upper = metadata.get('tickUpper')
            self.amount0_init = metadata.get('amount0')
            self.amount1_init = metadata.get('amount1')
            
        else:
            self.tick_lower: int | None = None
            self.tick_upper: int | None = None
            self.liquidity: int | None = None


        self.token0: str | None = None
        self.token1: str | None = None
        self.fee: int | None = None
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
        if self.metadata and self.tick_lower == pos[5] and self.tick_upper == pos[6] and self.liquidity== pos[7]:
            self.token0 = pos[2]
            self.token1 = pos[3]
            self.fee = pos[4]
            self.tokens_fee0 = pos[10]
            self.tokens_fee1 = pos[11]
        else:
            if self.metadata is None:
                print('None MetaData')
            elif self.tick_lower != pos[5] or self.tick_upper != pos[6] or self.liquidity != pos[7]:
                print('Mismatching MetaData and onchain data')

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
                    pos = LPPosition(self.net,self.abi_reg ,token_id,None)
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
        tick_after=pool.pool_state_after_swap_simple(res['swap_details'],res['swap_amount'])
        if tick_after<tick_lower or tick_after>tick_upper:
            raise RuntimeError("Tick out of range.")
        if res['amount0_target']<1 or res['amount1_target']<1:
            raise RuntimeError("Insufficient balance for JIT Zap minting.")

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
class LPPositionV4:
    def __init__(self, net, abi_registry, nft_id, manager_address=None,log_metadata=None):
        self.net = net
        self.nft_id = nft_id
        self.abi_reg=abi_registry
        self.log_metadat=log_metadata

        if manager_address is None:
            if not hasattr(net, "v4_positon_manager_address"):
                raise RuntimeError("v4_positon_manager_address not loaded in network")
            manager_address = net.v4_positon_manager_address

        self.manager_address = manager_address
        
        # Loading V4 ABI from registry
        self.abi = abi_registry.GET_V4_PM_ABI(manager_address)
        self.contract = net.eth.contract(address=net.to_checksum_address(manager_address), abi=self.abi)
        
        # Extracting V4 Data via getPoolAndPositionInfo
        # Returns: (PoolKey struct, PositionInfo uint256)


        self.pool_data = self.contract.functions.getPoolAndPositionInfo(nft_id).call()
        self.liquidity = self.contract.functions.getPositionLiquidity(nft_id).call()
        self.position_info = self.pool_data[1]
        if log_metadata:
            self.tickLower = log_metadata.get('tickLower')
            self.tickUpper = log_metadata.get('tickUpper')
            self.salt = log_metadata.get('salt')
            self.pool_id = log_metadata.get('poolId')
            self.liquiditydelta=log_metadata.get('liquidityDelta')
        else:
            self.extract_ticks_from_uri()
        
        self.parse_pool_key()
        
    #
    #
    def parse_pool_key(self):
        """Unpacks the PoolKey struct from V4"""
        key = self.pool_data[0]
        self.currency0 = key[0]
        self.currency1 = key[1]
        self.fee = key[2]
        self.tickSpacing = key[3]
        self.hooks = key[4]
    #
    #
    def decode_token_uri(self,token_id: str):
        token_uri = self.contract.functions.tokenURI(token_id).call()
        assert token_uri.startswith("data:application/json;base64,")
        b64 = token_uri.split(",")[1]
        decoded = base64.b64decode(b64)
        self.meta= json.loads(decoded)
    #
    #
    def extract_position_from_uri(self,meta: Dict=None) -> Dict:
        if meta is None:
            self.decode_token_uri(self.nft_id)
            meta = self.meta
        
        result = {}

        # ---------- 1️⃣ name ----------
        name = meta.get("name", "")
        result["name"] = name

        # fee tier
        fee_match = re.search(r"([\d.]+)%", name)
        result["fee_percent"] = float(fee_match.group(1)) if fee_match else None

        # price range
        price_match = re.search(r"([\d.]+)<>([\d.]+)", name)
        if price_match:
            result["price_lower"] = float(price_match.group(1))
            result["price_upper"] = float(price_match.group(2))
        else:
            result["price_lower"] = result["price_upper"] = None

        # ---------- 2️⃣ description ----------
        desc = meta.get("description", "")

        def extract_line(label):
            m = re.search(rf"{label}:\s*(.+)", desc)
            return m.group(1).strip() if m else None

        result["pool_manager"] = extract_line("Pool Manager Address")
        result["token0_address"] = extract_line("USDC Address")  # generic parse below
        result["token1_address"] = extract_line("ETH Address")
        result["hook"] = extract_line("Hook Address")
        result["token_id"] = int(extract_line("Token ID"))

        # ---------- 3️⃣ SVG decode ----------
        image = meta.get("image", "")
        if image.startswith("data:image/svg+xml;base64,"):
            svg_b64 = image.split(",")[1]
            svg = base64.b64decode(svg_b64).decode("utf-8")

            # tick lower / upper
            tick_matches = re.findall(r"(Min Tick|Max Tick):\s*(-?\d+)", svg)
            for k, v in tick_matches:
                if "Min" in k:
                    result["tick_lower"] = int(v)
                elif "Max" in k:
                    result["tick_upper"] = int(v)
        else:
            result["tick_lower"] = result["tick_upper"] = None

        # ---------- 4️⃣ fees (not in metadata) ----------
        result["fees_owed_0"] = None
        result["fees_owed_1"] = None
        result["fees_source"] = "NOT_IN_METADATA"

        return result
    #
    #
    def extract_ticks_from_uri(self,meta=None):
        if meta is None:
            self.decode_token_uri(self.nft_id)
            
        image = self.meta.get("image", "")
        if not image.startswith("data:image/svg+xml;base64,"):
            return {"min_tick": None, "max_tick": None}

        svg_b64 = image.split(",", 1)[1]
        svg = base64.b64decode(svg_b64).decode("utf-8", errors="ignore")

        patterns = [
            r"Min\s*Tick[^-0-9]*(-?\d+)",
            r"Max\s*Tick[^-0-9]*(-?\d+)",
            r"Tick\s*Lower[^-0-9]*(-?\d+)",
            r"Tick\s*Upper[^-0-9]*(-?\d+)",
        ]

        min_tick = None
        max_tick = None

        for p in patterns:
            if "Min" in p or "Lower" in p:
                m = re.search(p, svg, re.IGNORECASE)
                if m:
                    min_tick = int(m.group(1))
            if "Max" in p or "Upper" in p:
                m = re.search(p, svg, re.IGNORECASE)
                if m:
                    max_tick = int(m.group(1))

        self.tickLower=min_tick
        self.tickUpper=max_tick

    #
    #
    def get_token(self):
        print(f"Token0: {self.currency0}, Token1: {self.currency1}")
        return Token(self.net, self.abi_reg, self.currency0), Token(self.net, self.abi_reg, self.currency1)
    #
    #
    '''def is_in_range_extended(self):
        v4_position_manager=V4PositionManager(self.net,self.abi_reg)
        pool_manger=V4PoolManager(self.net,self.abi_reg,v4_position_manager)
        pool_info=pool_manger.pool_current_info()
        return self.tickLower<pool_info['currentTick']<self.tickUpper'''
    #
    #
    def info(self):
        pool_key=self.pool_data[0]
        if not hasattr(self, "tickLower") or not hasattr(self, "tickUpper"): self.extract_ticks_from_metadata()
        if not hasattr(self,'pool_id'):
            return {
            "nft_id": self.nft_id,
            "liquidity": self.liquidity,
            "tickLower": self.tickLower,
            "tickUpper": self.tickUpper,
            "token0": pool_key[0],
            "token1": pool_key[1],
            "fee": pool_key[2],
            "tickSpacing": pool_key[3]}
        else:
            return {
                "nft_id": self.nft_id,
                "liquidity": self.liquidity,
                "tickLower": self.tickLower,
                "tickUpper": self.tickUpper,
                "token0": pool_key[0],
                "token1": pool_key[1],
                "fee": pool_key[2],
                "tickSpacing": pool_key[3],
                "hooks": pool_key[4],
                "pool_id":self.pool_id if self.pool_id else None,
                "salt":self.salt if self.salt else None
            }
#
#
#
class V4PositionManager:
    def __init__(self, net, abi_reg, v4_pm_address=None):
        if v4_pm_address is None:
            if not hasattr(net, "v4_position_manager_address"):
                raise RuntimeError("v4_position_manager_address not loaded in network")
            self.address = net.v4_position_manager_address
        else:
            self.address = v4_pm_address
            
        self.net = net
        self.w3= net.eth
        self.abi_reg=abi_reg
        self.all_v4_positions=[]
        
        # Load ABI
        abi=self.abi_reg.GET_V4_PM_ABI(self.address)
        self.contract = self.w3.contract(
            address=net.to_checksum_address(self.address),
            abi=abi
        )
        
        # Action Constants (Uniswap v4 Standard)
        self.MINT_POSITION      = 0x02
        self.MODIFY_LIQUIDITY   = 0x0D
        self.BURN_POSITION      = 0x0E
        self.COLLECT_FEES       = 0x10
        self.SETTLE_PAIR        = 0x14
        self.SWAP                = 0x15
        self.PERMIT             = 0x23
    #
    #
    def extract_action_constants(self):
        """
        Scan the ABI cache for constants representing V4 actions
        and return a dictionary mapping action names to their numeric values.
        """
        constants = {}
        
        # ABI registry assumed to have a method returning full ABI for PM
        abi = self.abi_reg.GET_V4_PM_ABI(self.address)
        
        for item in abi:
            # We're looking for entries of type 'function' with constant outputs
            if item.get("type") == "function" and item.get("constant"):
                name = item.get("name")
                # Try to call the function to get its value
                try:
                    value = getattr(self.contract.functions, name)().call()
                    constants[name] = value
                except Exception:
                    continue
        
        return constants

    # ---------- HELPER: POOL KEY BUILDER ----------
    #
    def build_pool_key(self, tokenA: str, tokenB: str, fee: int, tick_spacing: int, hooks: str = "0x0000000000000000000000000000000000000000") -> tuple:
        """
        Sorts tokens and returns the PoolKey tuple required for encoding.
        """
        t0 = self.net.to_checksum_address(tokenA)
        t1 = self.net.to_checksum_address(tokenB)
        
        # V4 Requirement: token0 must be < token1
        if int(t0, 16) > int(t1, 16):
            t0, t1 = t1, t0
            
        return (t0, t1, int(fee), int(tick_spacing), self.net.to_checksum_address(hooks))
    #
    # ---------- ENCODING HELPERS ----------
    #
    def encode_mint_burn(self, owner: str, salt: int) -> bytes:
        return encode(["address", "uint256"], [owner, salt])
    #
    #
    def encode_modify_liquidity(self, pool_key: tuple, tick_lower: int, tick_upper: int, liquidity_delta: int, salt: bytes = b'\x00'*32) -> bytes:
        """
        Encodes parameters matching the V4 ABI structure.
        The first argument in ABI is the PoolKey struct.
        """
        return encode(
            # Signature: (PoolKeyStruct, tickLower, tickUpper, liquidityDelta, salt)
            ["(address,address,uint24,int24,address)", "int24", "int24", "int256", "bytes32"],
            [pool_key, tick_lower, tick_upper, liquidity_delta, salt]
        )
    #
    #
    def encode_collect_fees(self, pool_key: tuple, tick_lower: int, tick_upper: int, recipient: str, salt: int) -> bytes:
        return encode(
            ["(address,address,uint24,int24,address)", "int24", "int24", "address", "uint256"],
            [pool_key, tick_lower, tick_upper, recipient, salt]
        )
    #
    #
    def encode_settle_pair(self, currency0: str, currency1: str) -> bytes:
        return encode(["address", "address"], [currency0, currency1])
    #
    #
    def _encode_unlock(self, actions: bytes, params: list[bytes]) -> bytes:
        return encode(["bytes", "bytes[]"], [actions, params])
    #
    #
    def encode_swap_native_to_token(
        self,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        pool_key: tuple,
        owner: str
    ) -> bytes:
        """
        Encode Native -> ERC20 swap for V4 multicall
        """
        fn = self.contract.get_function_by_name("swapNativeToERC20")
        tx = fn(token_out, amount_in, min_amount_out, pool_key).buildTransaction({
            'from': owner
        })
        return tx['data'].encode()
    #
    #
    def encode_swap_erc20_to_erc20(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        pool_key: tuple,
        owner: str
    ) -> bytes:
        fn = self.contract.get_function_by_name("swapERC20ToERC20")
        tx = fn(token_in, token_out, amount_in, min_amount_out, pool_key).buildTransaction({
            'from': owner
        })
        return tx['data'].encode()
    #
    #
    def encode_permit(self, token, owner, spender, amount, salt, deadline) -> bytes:
        token = self.net.to_checksum_address(token)
        owner = self.net.to_checksum_address(owner)
        spender = self.net.to_checksum_address(spender)

        fn = self.contract.get_function_by_name("permit")(owner, spender, amount, deadline, salt)
        return fn._encode_transaction_data()
    #
    #
    def encode_permit_with_vrs(
        self,
        token: str,
        owner: str,
        spender: str,
        value: int,
        deadline: int,
        v: int,
        r: bytes,
        s: bytes
    ) -> bytes:
        """
        Encode EIP-2612 permit (v,r,s) for multicall in V4PositionManager.

        Args:
            token: address of ERC20 token
            owner: token owner
            spender: approved spender
            value: allowance amount
            deadline: permit expiry timestamp
            v, r, s: signature components

        Returns:
            bytes: calldata ready for multicall
        """
        token = self.net.to_checksum_address(token)
        owner = self.net.to_checksum_address(owner)
        spender = self.net.to_checksum_address(spender)

        # گرفتن تابع permit از ABI
        fn = self.contract.get_function_by_name("permit")(
            owner, spender, value, deadline, v, r, s
        )

        # خروجی bytes
        return fn._encode_transaction_data()

    #
    # ---------- BUILDERS ----------
    #
    def build_mint_liquidity(self, owner, pool_key, tick_lower, tick_upper, liquidity, salt_uint):
        # Ensure salt is bytes32 for modify_liquidity but uint256 for mint tracking if needed
        # Usually salt is passed as bytes32 in modifyLiquidity params
        salt_bytes = salt_uint.to_bytes(32, 'big')

        actions = bytes([
            self.MINT_POSITION,
            self.MODIFY_LIQUIDITY,
            self.SETTLE_PAIR
        ])

        params = [
            self.encode_mint_burn(owner, salt_uint),
            self.encode_modify_liquidity(pool_key, tick_lower, tick_upper, liquidity, salt_bytes),
            self.encode_settle_pair(pool_key[0], pool_key[1])
        ]

        return actions, params
    #
    #
    def build_collect_and_burn(self, owner, pool_key, tick_lower, tick_upper, liquidity, salt_uint):
        salt_bytes = salt_uint.to_bytes(32, 'big')
        
        actions = bytes([
            self.COLLECT_FEES,
            self.MODIFY_LIQUIDITY,
            self.BURN_POSITION,
            self.SETTLE_PAIR
        ])

        params = [
            self.encode_collect_fees(pool_key, tick_lower, tick_upper, owner, salt_uint),
            # liquidity_delta must be negative for burning
            self.encode_modify_liquidity(pool_key, tick_lower, tick_upper, -liquidity, salt_bytes),
            self.encode_mint_burn(owner, salt_uint),
            self.encode_settle_pair(pool_key[0], pool_key[1])
        ]

        return actions, params
    #
    # ---------- CORE FUNCTIONS ----------
    #
    def modify_liquidities(self, actions: bytes, params: list[bytes], deadline: int):
        """
        Directly calls modifyLiquidities (useful if not using ETH/Multicall)
        """
        unlock_data = self._encode_unlock(actions, params)
        return self.contract.functions.modifyLiquidities(
            unlock_data,
            deadline
        )
    #
    #
    def build_multicall_liquidity_transaction(
        self,
        actions: bytes,
        params: list[bytes],
        deadline: int
    ):
        """
        Builds multicall(bytes[]) containing modifyLiquidities calldata.
        """

        unlock_data = self._encode_unlock(actions, params)

        modify_data = self.contract.functions.modifyLiquidities(
            unlock_data,
            deadline
        ).build_transaction({"gas": 0})["data"]

        calls = [self.net.to_bytes(hexstr=modify_data)]

        return self.contract.functions.multicall(calls)
    #
    #
    def initialize_pool(self, pool_key: tuple, sqrt_price_x96: int):
        return self.contract.functions.initializePool(
            pool_key,
            sqrt_price_x96
        )
    #
    # ---------- UTILS ----------
    #
    @staticmethod
    def make_salt(owner, pool_key, tick_lower, tick_upper, strategy_id=1):
        """
        Generates a deterministic salt compatible with Solidity keccak256
        """
        # Packing types must match the data types
        # PoolKey is a struct: (address, address, uint24, int24, address)
        types = ["address", "(address,address,uint24,int24,address)", "int24", "int24", "uint256"]
        values = [owner, pool_key, tick_lower, tick_upper, strategy_id]
        
        encoded = encode(types, values)
        return int(Web3.keccak(encoded).hex(), 16)
    #------------------------------------------------------------------------------------------------------
    #
    def get_pool_id(self, token0=Token, token1=Token, fee=0, tick_spacing:int=None,         hook_address:str="0x0000000000000000000000000000000000000000"):
            if tick_spacing is None:
                tick_spacing = calculate_tickspacing_by_feetier(fee)
            pool_key = (token0.address, token1.address, fee, tick_spacing, hook_address)
            pool_id = self.net.keccak(
            encode(
                ["address","address","uint24","int24","address"],
                pool_key
            )
            )
            return pool_id
    #
    #
    def get_all_position(self):
        next_token_id=self.contract.functions.nextTokenId().call()
        #print(next_token_id)
        for i in tqdm(range(int(0.993*next_token_id),next_token_id)):
            if self.contract.functions.ownerOf(i).call().lower()==self.net.address.lower():
                #print(i)
                v4_lp=LPPositionV4(self.net,self.abi_reg,i,self.address)
                if v4_lp.liquidity>0:
                    self.all_v4_positions.append(v4_lp)
                time.sleep(0.2)
        print(f"Founding {len(self.all_v4_positions)} Active V4 Positions ")
    #
    #
    def mint(self,token0: Token, token1: Token, fee: int, tick_lower: int, tick_upper: int, amount0_desired: int, amount1_desired: int,deadline: int = None):
        if deadline is None:
            deadline = int(time.time())+300
        tickspacing=calculate_tickspacing_by_feetier(fee)
        pool_key=self.build_pool_key(token0.address, token1.address, fee,tickspacing)
        salt=self.make_salt(self.net.address,pool_key,tick_lower,tick_upper)
        liquidity=calculate_liquidity_inside_range(tick_lower,tick_upper,amount0_desired,amount1_desired)
        action,params= self.build_mint_liquidity(self.net.address,pool_key,tick_lower,tick_upper,liquidity,salt)
        token0.ensure_allowance_smart(self.address,amount0_desired)
        token1.ensure_allowance_smart(self.address,amount1_desired)
        tx=self.modify_liquidities(action,params,deadline=deadline)
        self.net.build_and_send_transaction_advanced(tx)
    #
    #
    def full_exit(self,v4nft:LPPositionV4,deadline:int=None):
        if deadline is None:
            deadline=int(time.time())+300
        nft_info=v4nft.info()
        pool_key=self.build_pool_key(nft_info['token0'], nft_info['token1'],nft_info['fee'] ,nft_info['tickSpacing'])
        salt=self.make_salt(self.net.address,pool_key,v4nft.tick_lower,v4nft.tick_upper)
        action,params=self.build_collect_and_burn(self.net.address,pool_key,v4nft.tick_lower,v4nft.tick_upper,v4nft.liquidity,salt)
        tx=self.modify_liquidities(action,params,deadline=deadline)
        self.net.build_and_send_transaction_advanced(tx)
    #
    #
    def swap_tokens(
        self,
        from_token: Token,
        to_token: Token,
        amount_in: int,
        owner: str,
        pool_key: tuple,
        min_amount_out: int=0,
        deadline: int = None,
        use_native: bool = None
    ):
        """
        Build and send a multicall for Permit + Swap only.
        This does NOT mint liquidity.
        
        Args:
            from_token: token to swap from (Token instance)
            to_token: token to swap to (Token instance)
            amount_in: amount of from_token to swap
            min_amount_out: minimum acceptable amount of to_token
            owner: address performing the swap
            pool_key: pool_key tuple (token0, token1, fee, tickSpacing, hooks)
            deadline: transaction deadline
            use_native: True if from_token is native (ETH/MATIC/BNB)
        """

        if deadline is None:
            deadline = int(time.time()) + 300

        # 1️⃣ Prepare permit calldata if ERC20 (skip for native)
        actions = []
        params = []
        use_native=True if from_token.is_native else False

        if not use_native:
            permit_salt = self.make_salt(owner, pool_key, 0, 0)  # dummy ticks for permit
            permit_data = self.encode_permit(from_token.address, owner, self.address, amount_in, permit_salt, deadline)
            actions.append(self.PERMIT)  # hypothetical PERMIT action constant
            params.append(permit_data)

        # 2️⃣ Prepare swap calldata
        if use_native:
            swap_data = self.encode_swap_native_to_token(to_token.address, amount_in, min_amount_out, pool_key,owner=owner)
        else:
            swap_data = self.encode_swap_erc20_to_erc20(from_token.address, to_token.address, amount_in, min_amount_out, pool_key,owner=owner)

        actions.append(self.SWAP)  # hypothetical SWAP action constant
        params.append(swap_data)
        #
        #
        from_token.ensure_allowance_smart(self.address,amount=amount_in)
        #
        # 3️⃣ Build multicall
        multicall_tx = self.build_multicall_liquidity_transaction(bytes(actions), params, deadline)

        # 4️⃣ Attach value for native swap
        if use_native:
            multicall_tx['value'] = amount_in

        # 5️⃣ Send transaction
        self.net.build_and_send_transaction_advanced(multicall_tx)

    #
    #
    def jit_mint(self,token0:Token,token1:Token,fee:int,slippage:float=0.01,step:int=None):

        pool_info=self.pool_current_info(token0, token1, fee)
        tickspacing=calculate_tickspacing_by_feetier(fee)
        current_tick=pool_info['currentTick']
        tick_lower, tick_upper = get_current_match_tick_range(current_tick,tickspacing,10,step=step)
  
        cp=calculate_raw_price_from_sqrt_price(pool_info['sqrtPriceX96'])
        lp=calculate_raw_price_by_tick(tick_lower)
        up=calculate_raw_price_by_tick(tick_upper)
        token0.balance_of()
        token1.balance_of()
        bal0=token0.token_balance
        bal1=token1.token_balance
        res=calculate_required_amount_and_swap(cp,lp,up,bal0,bal1)
        tick_after=pool_state_after_swap_simple(res['swap_details'],res['swap_amount'],pool_info['sqrtPriceX96'],pool_info['liquidity'])

        if tick_after<tick_lower or tick_after>tick_upper:
            raise RuntimeError("Tick out of range.")
        if res['amount0_target']<1 or res['amount1_target']<1:
            raise RuntimeError("Insufficient balance for JIT Zap minting.")

        if res['swap_details']=='token0 -> token1':
            swap_amount=int(res['swap_amount'])
            if swap_amount/10**token0.decimals<0.0001:
                pass
            else:
                print(f"Info: Swapping {res['amount0_target']} {token0.symbol} for {res['amount1_target']} {token1.symbol} to balance amounts.")
                min_amount_out=int(res['amount1_target']*(1-slippage))
                pool_key=self.build_pool_key(token0.address,token1.address,fee,tickspacing)
                self.swap_tokens(token0,token1,swap_amount,min_amount_out,self.net.address,pool_key)

        elif res['swap_details']=='token1 -> token0':
            swap_amount=int(res['swap_amount'])
            if swap_amount/10**token1.decimals<0.0001:
                pass
            else:
                print(f"Info: Swapping {res['amount1_target']} {token1.symbol} for {res['amount0_target']} {token0.symbol} to balance amounts.")
                router.swap_exact_input_single(token_in=token1, token_out=token0, fee=fee, amount_in=swap_amount, slippage=slippage)
                min_amount_out=int(res['amount0_target']*(1-slippage))
                pool_key=self.build_pool_key(token0.address,token1.address,fee,tickspacing)
                self.swap_tokens(token1,token0,swap_amount,min_amount_out,self.net.address,pool_key)


        
        token0.balance_of()
        token1.balance_of()
        
        self.mint(token0, token1, fee, tick_lower, tick_upper,token0.token_balance,token1.token_balance)
#
#
#
class V4PoolManager(BaseEntity):
    def __init__(self, net: Web3_Network, abi_registry: ABIRegistry,V4_PM:PositionManager):
        super().__init__(net)
        self.net = net
        self.abi_registry = abi_registry
        self.v4_pm=V4_PM
        self.address = V4_PM.contract.functions.poolManager().call()
        self.contract = net.eth.contract(
            address=self.address,
            abi=self.abi_registry.GET_V4_POOL_MANAGER_ABI(self.address)
        )
    #
    #
    def build_state_view_contract(self,state_view_address: str):
        self.state_view_address=self.net.to_checksum_address(state_view_address)
        abi_=self.abi_registry.GET_ANY_CONTRACT_ABI(self.state_view_address)
        self.state_view_contract=self.net.eth.contract(self.state_view_address,abi=abi_)
    #
    #
    

    def pool_current_info(self, token0=Token, token1=Token, fee:int=0, tick_spacing:int=None, hook_address: str="0x0000000000000000000000000000000000000000"):
        pool_id=self.v4_pm.get_pool_id(token0, token1, fee, tick_spacing, hook_address)
        slot0=self.state_view_contract.functions.getSlot0(pool_id).call()
        liquidity=self.state_view_contract.functions.getLiquidity(pool_id).call()
        return{
            "token0":token0.address,
            "token1":token1.address,
            "fee":fee,
            "tickSpacing":tick_spacing,
            "poolId":pool_id,
            "sqrtPriceX96":slot0[0],
            "currentTick":slot0[1],
            "liquidity":liquidity
        }
    #
    #
#
#
#
class TransactionAnalyzer(BaseEntity):
    def __init__(self, net: Web3_Network, abi_registry: ABIRegistry):
        super().__init__(net)
        self.abi_registry = abi_registry
        self.etherscan_base = "https://api.etherscan.io/v2/api"

    def fetch_all_transactions(self, startblock: int = 0, endblock: int = 99999999, page_size: int = 200) -> list:
        all_txs = []
        page = 1
        while True:
            params = {
                "module": "account", "action": "txlist",
                "address": self.net.address, "startblock": startblock,
                "endblock": endblock, "page": page,
                "offset": page_size, "sort": "asc",
                "apikey": self.net.explorer_api_key, "chainid": self.net.chain_id
            }
            try:
                resp = requests.get(self.etherscan_base, params=params, timeout=30)
                data = resp.json()
                result = data.get("result", [])
                if not result or (isinstance(result, str) and result == ""):
                    break
                all_txs.extend(result)
                if len(result) < page_size: break
                page += 1
                time.sleep(0.25)
            except Exception as e:
                print(f"Error fetching transactions: {e}")
                break
        self.all_transaction = all_txs
        
        os.makedirs('raw_transactions', exist_ok=True)
        with open('raw_transactions/transactions.json', 'w') as f:
            json.dump(all_txs, f, indent=4)
        #return all_txs

    def handle_bytes(self, obj):
        """convert byte to string json"""
        if isinstance(obj, dict):
            return {k: self.handle_bytes(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.handle_bytes(v) for v in obj]
        elif isinstance(obj, bytes):
            return "0x" + obj.hex()
        return obj

    def decode_transaction_logs(self, tx_hash: str) -> list:
        try:
            receipt = self.net.eth.get_transaction_receipt(tx_hash)
            decoded_results = []
            for log in receipt.get('logs', []):
                contract_address = log['address']
                abi = self.abi_registry.GET_ANY_CONTRACT_ABI(contract_address)
                if not abi: continue

                try:
                    contract = self.net.eth.contract(address=contract_address, abi=abi)
                    event_names = [e['name'] for e in abi if e['type'] == 'event']
                    
                    for event_name in event_names:
                        try:
                            decoded_log = contract.events[event_name]().process_log(log)
                            decoded_results.append({
                                "event_name": event_name,
                                "contract": contract_address,
                                "args": self.handle_bytes(dict(decoded_log['args'])), # استفاده از متد کلاس
                                "blockNumber": log.get('blockNumber'),
                                "transactionIndex": log.get('transactionIndex')
                            })
                            break 
                        except: continue
                except Exception as e:
                    print(f"Internal decoding error at {contract_address}: {e}")
            return decoded_results
        except Exception as e:
            print(f"Failed to fetch receipt for {tx_hash}: {e}")
            return []

    def get_wallet_history_report(self, last_n: int =None):
        #
        self.fetch_all_transactions()
        if last_n is None:
            last_n =len(self.all_transaction)
        tx_list = self.all_transaction
        report = []
        
        for tx in tx_list[-last_n:]:
            tx_hash = tx['hash']
            #
            decoded_logs = self.decode_transaction_logs(tx_hash)
            
            report.append({
                "hash": tx_hash,
                "timestamp": tx.get('timeStamp'),
                "function_name": tx.get('functionName'),
                "status": "Success" if tx.get('isError') == '0' else "Failed",
                "events": decoded_logs
            })

        self.report = report
        os.makedirs('decoded_transactions', exist_ok=True)
        with open('decoded_transactions/decoded_transactions.json', 'w') as f:
            json.dump(report, f, indent=4)
        print(f"✅ Report saved for last {len(report)} transactions.")
#
#
class Wallet(Web3_Network, TransactionAnalyzer):
    def __init__(self, net_instance: Web3_Network, abi_registry: ABIRegistry,scan_in_first:bool=True):
        self.__dict__.update(net_instance.__dict__)
        TransactionAnalyzer.__init__(self, net_instance, abi_registry)
        
        self.abi_registry = abi_registry
        self.wallet_address = self.account.address if hasattr(self, 'account') else None
        
        # Internal Storage (Environment)
        self.tokens = []           #
        self.lp_positions_v3 = []  #
        self.lp_positions_v4 = []  #
        self.v4_positions_metadata = {}
        self.v3_positions_metadata = {}
        self.erc20_address=set()
        
        self.api_url = "https://api.etherscan.io/v2/api"

        if scan_in_first and self.wallet_address:
            self.discover_assets_optimize(debug=True)
    #
    #
    def discover_assets_optimize(self, debug: bool = True):       
        """
        build wallet by scan all events
        """
        if debug: print(f"🔍 Starting asset discovery for {self.wallet_address}...")

        self.get_wallet_history_report(last_n=100) 
       
        discovered_erc20_addresses = set()
        
        
        v3_manager = getattr(self, 'position_manager_address', "").lower()
        v4_manager = getattr(self, 'v4_position_manager_address', "").lower()

        #
        for tx in self.report:
            if tx['status'] == "Failed": continue
            v4_tx_token_id = None
            v4_tx_metadata = None
            

            v3_tx_token_id=None
            v3_temp={}
            for event in tx.get('events', []):
                event_name = event['event_name']
                args = event['args']
                contract = event['contract'].lower()

                #
                if event_name == "Transfer" and contract not in [v3_manager, v4_manager]:
                    self.erc20_address.add(contract)


                if contract == v4_manager and event_name == "Transfer":
                    v4_tx_token_id = args.get('id') or args.get('tokenId')

                if event_name == "ModifyLiquidity":
                 
                    v4_tx_metadata = {
                        'poolId': args.get('id') or args.get('poolId'),
                        'tickLower': args.get('tickLower'),
                        'tickUpper': args.get('tickUpper'),
                        'liquidityDelta': args.get('liquidityDelta'),
                        'salt': args.get('salt'),
                        
                    }

                #

                if contract == v3_manager and event_name == "Transfer":
                    tid = args.get('tokenId')
                    if tid: v3_tx_token_id = tid


                if event_name == "Mint":
                    if args.get('owner').lower() == v3_manager:
                        v3_temp.update({
                            'tickLower': args.get('tickLower'),
                            'tickUpper': args.get('tickUpper'),
                            'contract': args.get('owner')
                        })

                if event_name == "IncreaseLiquidity" and contract == v3_manager:
                    tid = args.get('tokenId')
                    if tid:
                        v3_temp.update({
                            'liquidity': args.get('liquidity'),
                            'amount0': args.get('amount0'),
                            'amount1': args.get('amount1'),
                            'tickLower': v3_temp['tickLower'],
                            'tickUpper': v3_temp['tickUpper']
                            #'contract': v3_temp['contract']
                        })
                
            if v4_tx_token_id is not None and v4_tx_metadata is not None:
                self.v4_positions_metadata[v4_tx_token_id] = v4_tx_metadata
            if v4_tx_token_id is None and v4_tx_metadata is not None:
                self.v4_positions_metadata['burn'] = v4_tx_metadata

            if v3_temp and v3_tx_token_id:
                self.v3_positions_metadata[v3_tx_token_id] = v3_temp




        # 
        #
        discovered_erc20_addresses.add("0x0000000000000000000000000000000000000000")
        
        #
        self.tokens = self._get_token_objects(self.wallet_address, self.erc20_address)

        #
        #

        abi_v4=self.abi_registry.GET_V4_PM_ABI()
        v4_pm_contract=self.net.eth.contract(address=self.net.v4_position_manager_address,abi=abi_v4)
        for tid, meta in self.v4_positions_metadata.items():
            time.sleep(0.2)
            if tid == 'burn': continue
            try:
                if v4_pm_contract.functions.ownerOf(tid).call() == self.wallet_address:
                    lp_v4 = LPPositionV4(self, self.abi_registry, tid, v4_manager, meta)
                    if lp_v4.liquidity > 0:
                        self.lp_positions_v4.append(lp_v4)
            except Exception as e:
                print(f"Error skipping V4 tid {tid}: {e}")

        # 
        abi_v3=self.abi_registry.GET_NFPM_ABI()
        v3_pm_contract=self.net.eth.contract(address=self.net.position_manager_address,abi=abi_v3)
        for tid, meta in self.v3_positions_metadata.items():
            time.sleep(0.2)
            try:
                #
                if v3_pm_contract.functions.ownerOf(tid).call() == self.wallet_address:
                    lp_v3 = LPPosition(self.net,self.abi_registry,tid,metadata=meta)
                    if lp_v3.liquidity > 0:
                        self.lp_positions_v3.append(lp_v3)
            except Exception as e:
                print(f"Error skipping V3 tid {tid}: {e}")

        if debug:
            print(f"✅ Discovery finished: {len(self.tokens)} Tokens, {len(self.lp_positions_v3)} V3 LPs, {len(self.lp_positions_v4)} V4 LPs found.")
    #
    #
    def discover_assets(self, wallet_address: str = None, debug: bool = True):
        """
        Scans history, creates objects, and stores them in the class instance.
        """
        target_address = wallet_address or self.wallet_address
        if not target_address:
            raise ValueError("No wallet address provided.")
        
        target_address = self.to_checksum_address(target_address)
        discovered_erc20s = set()
        discovered_nfts = {} 

        common_params = {
            "address": target_address, "sort": "desc",
            "apikey": self.explorer_api_key, "chainid": self.chain_id
        }

        try:
            # Fetch ERC20s
            r_erc20 = requests.get(self.api_url, params={**common_params, "module": "account", "action": "tokentx"}).json()
            #print(r_erc20)
            if r_erc20.get("status") == "1":
                for tx in r_erc20["result"]:
                    discovered_erc20s.add(self.to_checksum_address(tx["contractAddress"]))

            # Fetch NFTs
            # Fetch ERC-721 NFTs (Like Uniswap v3 and some v4)
            try:
                #
                r_721 = requests.get(self.api_url, params={**common_params, "module": "account", "action": "tokennfttx"}).json()
                if r_721.get("status") == "1":
                    for tx in r_721["result"]:
                        contract = self.to_checksum_address(tx["contractAddress"])
                        tid = int(tx["tokenID"])
                        if contract not in discovered_nfts: discovered_nfts[contract] = []
                        if tid not in discovered_nfts[contract]: discovered_nfts[contract].append(tid)

                # 2
                r_1155 = requests.get(self.api_url, params={**common_params, "module": "account", "action": "token1155tx"}).json()
                if r_1155.get("status") == "1":
                    for tx in r_1155["result"]:
                        contract = self.to_checksum_address(tx["contractAddress"])
                        #
                        tid_raw = tx.get("tokenID") or tx.get("id")
                        if tid_raw:
                            tid = int(tid_raw)
                            if contract not in discovered_nfts: discovered_nfts[contract] = []
                            if tid not in discovered_nfts[contract]: discovered_nfts[contract].append(tid)

                # 3
                #
                r_txs = requests.get(self.api_url, params={**common_params, "module": "account", "action": "txlist"}).json()
                if r_txs.get("status") == "1":
                    for tx in r_txs["result"]:
                        # 
                        if tx.get("isError") == "0" and tx.get("to") and tx.get("input") and tx["input"].startswith("0x"):
                            contract_candidate = self.to_checksum_address(tx["to"])
                            #
                            if contract_candidate not in discovered_nfts:
                                discovered_nfts[contract_candidate] = []

            except Exception as e:
                if debug: print(f"Scan Error during discovery: {e}")
        except Exception as e:
            if debug: print(f"Scan Error: {e}")

        # Store in the instance instead of just returning
        #print(list(discovered_erc20s))
        
        discovered_erc20s=list(discovered_erc20s)
        discovered_erc20s.append("0x0000000000000000000000000000000000000000")
        self.tokens = self._get_token_objects(target_address, discovered_erc20s)
        self.all_lp_position=self._get_lp_position_objects(target_address, discovered_nfts)
        self.erc20_tokens=list(discovered_erc20s)
        self.nfts=discovered_nfts
        
        
        if debug:
            print(f"✅ Environment Updated: {len(self.tokens)} Tokens and {len(self.lp_positions_v3)} V3 LPs and {len(self.lp_positions_v4)} V4 LP Positions found.")
        #return discovered_nfts
    #
    #ُ
    def _get_token_objects(self, wallet_address, addresses):
        objs = []
        for addr in addresses:
            time.sleep(0.2)
            try:
                t=Token(self.net,self.abi_registry,addr)

                if t.token_balance > 0:
                    objs.append(t)
            except Exception as e:
                print(f"Error skipping token {addr}: {e}")

        #self.tokens=objs
        return objs
    #
    #
    def _get_lp_position_objects(self, wallet_address, nft_dict):
        self.lp_positions_v3 = []
        self.lp_positions_v4 = []
        
        v3_manager = getattr(self, 'position_manager_address', "").lower()
        v4_manager = getattr(self, 'v4_position_manager_address', "").lower()
        
        # Standard ERC721 ABI for ownership check
        owner_abi = [{"constant":True,"inputs":[{"name":"tokenId","type":"uint256"}],"name":"ownerOf","outputs":[{"name":"owner","type":"address"}],"type":"function"}]

        for contract_addr, ids in nft_dict.items():
            current_contract = contract_addr.lower()
            
            # --- Uniswap V3 Logic ---
            if v3_manager and current_contract == v3_manager:
                for tid in ids:
                    try:
                        temp_contract = self.eth.contract(address=self.to_checksum_address(current_contract), abi=owner_abi)
                        if temp_contract.functions.ownerOf(tid).call().lower() == wallet_address.lower():
                            lp_v3 = LPPosition(self, self.abi_registry, tid)
                            self.lp_positions_v3.append(lp_v3)
                    except: continue

            # --- Uniswap V4 Logic ---
            elif v4_manager and current_contract == v4_manager:
                for tid in ids:
                    try:
                        temp_contract = self.eth.contract(address=self.to_checksum_address(current_contract), abi=owner_abi)
                        if temp_contract.functions.ownerOf(tid).call().lower() == wallet_address.lower():
                            # Initialize V4 specific class
                            lp_v4 = LPPositionV4(self, self.abi_registry, tid, current_contract)
                            self.lp_positions_v4.append(lp_v4)
                    except: continue

        return {"v3": self.lp_positions_v3, "v4": self.lp_positions_v4}

    def get_summary(self):
        """Returns a readable summary of current environment assets."""
        return {
            "tokens": [f"{t.symbol()}: {t.balanceOf() / 10**t.decimals()}" for t in self.tokens],
            "lp_ids": [lp.nft_id for lp in self.lp_positions]
        }
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
        token0.ensure_allowance(self.address,amount0_total)
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
            print('need to swap')
            param=(
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
           
            return self.execute_jit(*param)
        else:
            print('no need to swap')
            param=(
                token0,
                token1,
                fee,
                tick_lower,
                tick_upper,
                amount0_total,
                amount1_total,
                False,
                False,
                0,
                0,
                int(amount0_total* (1 - slippage)),
                int(amount1_total* (1 - slippage))
            )
          
            return self.execute_jit(*param)
            #
            #
