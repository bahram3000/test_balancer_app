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

#
etherscan_apikey = "N68HP1FGB4UQQFBHZQUJIM12HVYWJME96M"
CHAIN_ID = 11155111  # Sepolia
#
def connect_to_chain(inp_private_key):
    RPC = "https://eth-sepolia.g.alchemy.com/v2/1d3m81eR2Kd2mrpuH6-bR"
    w3 = Web3(Web3.HTTPProvider(RPC))
    account = Account.from_key(inp_private_key)
    my_wallet_address = account.address
    return w3,my_wallet_address
#
#w3=connect_to_chain(input('Enter your wallet privte key :'))
#
#
def check_liquidity_v3_nft(inp_wallet_address,inp_postion_manger_contract):
  pm_contract=inp_postion_manger_contract
  address=inp_wallet_address
  nfts=[]
  try:
    balance = pm_contract.functions.balanceOf(address).call()
    print(f"num of v3 lp nft : {balance}")


    if balance > 0:
        for i in range(balance):

            token_id = pm_contract.functions.tokenOfOwnerByIndex(address, i).call()

            pos = pm_contract.functions.positions(token_id).call()
            dct={'token_id':token_id,'token0':pos[2],'token1':pos[3],'fee_tier':pos[4],'liquidity':pos[7],'tick_range':[pos[5],pos[6]],'fee0':pos[10],'fee1':pos[11]}
            nfts.append(dct)
        return nfts
    else:
        print("lp nft not found")

  except Exception as e:
    print(f"error in read data --> {e}")
#
def calculate_raw_price_from_sqrt_price(sqrt_price_raw: float) -> float:
    normalized_sqrt_price = sqrt_price_raw / (2 ** 96)
    raw_price_math = normalized_sqrt_price ** 2
    return raw_price_math
#
def calculate_price_from_sqrt_price(sqrt_price_raw: float, decimal_0: int, decimal_1: int) -> float:
    normalized_sqrt_price = sqrt_price_raw / (2 ** 96)
    raw_price_math = normalized_sqrt_price ** 2
    decimal_adjustment = decimal_0 - decimal_1
    final_price = raw_price_math * (10 ** decimal_adjustment)
    return final_price
#
def pool_current_info(inp_pool_contract):
  token0_address = inp_pool_contract.functions.token0().call()
  token1_address = inp_pool_contract.functions.token1().call()
  slot0 = inp_pool_contract.functions.slot0().call()
  liquidity = inp_pool_contract.functions.liquidity().call()
  fee = inp_pool_contract.functions.fee().call()
  tickspacing = inp_pool_contract.functions.tickSpacing().call()
  return {'token0_address':token0_address,'token1_address':token1_address,'sqrtprice':slot0[0],'current_tick':slot0[1],'liquidity':liquidity,'fee_tier':fee,'tick_spacing':tickspacing}
#
def check_token_balance(w3_instance:Web3,token_list_address:list, inp_address):
  ERC20_ABI = '''
  [
  {"constant":true,"inputs":[{"name":"_owner","type":"address"}],
   "name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],
   "type":"function"},
  {"constant":true,"inputs":[],"name":"decimals",
   "outputs":[{"name":"","type":"uint8"}],"type":"function"},
  {"constant":true,"inputs":[],"name":"symbol",
   "outputs":[{"name":"","type":"string"}],"type":"function"}
  ]
  '''
  balances = []
  for token in token_list_address:
      contract = w3_instance.eth.contract(address=token, abi=ERC20_ABI)
      bal = contract.functions.balanceOf(inp_address).call()
      dec = contract.functions.decimals().call()
      sym = contract.functions.symbol().call()
      balances.append([sym, bal / (10 ** dec)])
  eth_balance = w3_instance.eth.get_balance(inp_address)
  balances.append(["ETH", w3_instance.from_wei(eth_balance, 'ether')])
  return balances
#
def raw_price_by_tick(tick):
    return 1.0001**tick
#
def calculate_price_by_tick(tick:int,decimal_0:int,decimal_1:int):
  return (10**(decimal_0-decimal_1))*raw_price_by_tick(tick)
#
def calculate_price_from_sqrt_price(sqrt_price_raw: float, decimal_0: int, decimal_1: int) -> float:
    normalized_sqrt_price = sqrt_price_raw / (2 ** 96)
    raw_price_math = normalized_sqrt_price ** 2
    decimal_adjustment = decimal_0 - decimal_1
    final_price = raw_price_math * (10 ** decimal_adjustment)
    return final_price
#
def calculate_tick_by_price(price: float, decimal_0: int, decimal_1: int) -> int:
    if price <= 0:
        raise ValueError("Price must be greater than zero")
    decimal_factor = 10 ** (decimal_0 - decimal_1)
    val_to_log = math.log(price) - math.log(decimal_factor)
    tick_base = math.log(1.0001)
    tick = val_to_log / tick_base
    return int(round(tick))
#
def calculate_required_amount_and_swap(
    current_price: float,
    price_lower: float,
    price_upper: float,
    amount0_wallet: float,
    amount1_wallet: float
) -> dict:
    if not (0 < price_lower < current_price < price_upper):
        return {
            "status": "Error",
            "message": "prices must be positive and current price should be between lower and upper"
        }

    sqrt_pc = math.sqrt(current_price)
    sqrt_pa = math.sqrt(price_lower)
    sqrt_pb = math.sqrt(price_upper)

    numerator = sqrt_pc - sqrt_pa

    denominator = (1 / sqrt_pc) - (1 / sqrt_pb)
    required_ratio = numerator / denominator
    v_total = (amount0_wallet * current_price) + amount1_wallet

    amount0_target = v_total / (current_price + required_ratio)

    amount1_target = amount0_target * required_ratio


    swap_diff_0 = amount0_wallet - amount0_target
    swap_diff_1 = amount1_wallet - amount1_target
    sell_token='token0'if swap_diff_0>0 else 'token1'
    swap_amount_abs=abs(swap_diff_0) if sell_token=='token0' else abs(swap_diff_1)

    swap_action = ""
    swap_amount_abs = abs(swap_diff_0)

    if swap_diff_0 > 0:
        swap_action = f" {swap_amount_abs:.8f}sell token0 to buy token1 "
    elif swap_diff_0 < 0:
        swap_action = f"{swap_amount_abs:.8f}buy token0 by sell token1 "
    else:
        swap_action = "balance of tokens are ok"

    liquidity_denominator = (1 / sqrt_pc) - (1 / sqrt_pb)
    final_liquidity = amount0_target / liquidity_denominator
    #
    return {
        "status": "Success",
        "final_liquidity_L": final_liquidity,
        "ratio_required": required_ratio,
        "amount0_target": amount0_target,
        "amount1_target": amount1_target,
        "swap_details": swap_action,
        f"swap_amount_{sell_token}": swap_amount_abs
    }

#
def calculate_new_amount_token_mix(current_price: float, lower: float, upper: float, liquidity: float):
    s = np.sqrt(current_price)
    su = np.sqrt(upper)
    sl = np.sqrt(lower)

    amount_0 = 0.0
    amount_1 = 0.0

    if current_price < lower:
        amount_0 = liquidity * ((1.0 / sl) - (1.0 / su))
        amount_1 = 0.0
    elif current_price > upper:
        amount_0 = 0.0
        amount_1 = liquidity * (su - sl)
    else:
        amount_0 = liquidity * ((1.0 / s) - (1.0 / su))
        amount_1 = liquidity * (s - sl)

    return amount_0, amount_1
#
def human_readable_amount_in_liquidity(current_price: float, lower: float, upper: float, liquidity: float,inp_decimal0,inp_deciaml1):
  amount_0,amount_1=calculate_new_amount_token_mix(current_price,lower,upper,liquidity)
  return amount_0/10**(inp_decimal0-inp_deciaml1),amount_1/10**(inp_deciaml1-inp_decimal0)
#
def final_true_amount_in_liquidity(current_price: float, lower: float, upper: float, liquidity: float,inp_decimal0,inp_deciaml1):
  amount_0,amount_1=calculate_new_amount_token_mix(current_price,lower,upper,liquidity)
  return amount_0*10**inp_deciaml1,amount_1*10**inp_decimal0
#
def get_pool_id(token0, token1, fee, tick_spacing, hook_address):
    
    token0 = Web3.to_checksum_address(token0)
    token1 = Web3.to_checksum_address(token1)
    hook_address = Web3.to_checksum_address(hook_address)

    encoded = encode(
        ['address', 'address', 'uint24', 'int24', 'address'],
        [token0, token1, fee, tick_spacing, hook_address]
    )

    pool_id = Web3.keccak(encoded).hex()
    return pool_id
#
def convert_fee_percentage_to_feetier(inp_fee_percentage):
  return int((inp_fee_percentage/100)*(10**6))
#
def calculate_tickspacing_by_feetier(inp_feetier):
  dct={10:1,500:10,3000:60,10000:200}
  return dct[inp_feetier]
#
def calculate_tick_by_price(price: float, decimal_0: int, decimal_1: int) -> int:
    if price <= 0:
        raise ValueError("Price must be greater than zero")
    decimal_factor = 10 ** (decimal_0 - decimal_1)
    val_to_log = math.log(price) - math.log(decimal_factor)
    tick_base = math.log(1.0001)
    tick = val_to_log / tick_base
    return int(round(tick))
#

#
def get_nearest_valid_tick(inp_current_tick, inp_tickspacing):
  return (inp_current_tick // inp_tickspacing) * inp_tickspacing
#
def fix_get_true_tick_range(inp_current_tick:int,inp_tickspacing:int,inp_divid:int):
  a=get_nearest_valid_tick(inp_current_tick,inp_tickspacing)
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
  return lowertick,uppertick
#
#
def get_nft_balances(nft_manager_contract, inp_token_id, inp_wallet_address):
  position_data = nft_manager_contract.functions.positions(inp_token_id).call()
  liquidity = position_data[7]
  if liquidity == 0:
    return 0, 0
  params = {
        'tokenId': inp_token_id,
        'liquidity': liquidity,
        'amount0Min': 0,
        'amount1Min': 0,
        'deadline': int(time.time() + 60)}
      #
  try:
    amount0, amount1 = nft_manager_contract.functions.decreaseLiquidity(params).call({'from': inp_wallet_address})
    return amount0, amount1
  except Exception as e:
    print(f"Error calculating balance: {e}")
    return None, None
#
# Helper function to ensure we have a valid timestamp for deadline
def get_deadline(ttl=1200):
    """Returns current timestamp + ttl (time to live in seconds)"""
    return int(time.time()) + ttl

#
#
#
def pair_slipage_check(way0_amount0, way1_amount0, way0_amount1, way1_amount1, slipage: float = 0.01):
    # Case 1: All amounts are non-zero
    if way0_amount0 != 0 and way0_amount1 != 0 and way1_amount0 != 0 and way1_amount1 != 0:
        # Check slipage for both tokens using way0 as reference
        token0_slipage = np.abs((way0_amount0 - way1_amount0) / way0_amount0)
        token1_slipage = np.abs((way0_amount1 - way1_amount1) / way0_amount1)

        if token0_slipage <= slipage and token1_slipage <= slipage:
            return min(way0_amount0, way1_amount0),min(way0_amount1, way1_amount1)

        else:
            return False

    # Case 2: Token0 amounts are zero, Token1 amounts are non-zero
    elif way0_amount0 == 0 and way1_amount0 == 0 and way0_amount1 != 0 and way1_amount1 != 0:
        token1_slipage = np.abs((way0_amount1 - way1_amount1) / way0_amount1)
        if token1_slipage <= slipage:
            return way0_amount0,min(way0_amount1, way1_amount1)  # Min amount for token1
        else:
            return False

    # Case 3: Token1 amounts are zero, Token0 amounts are non-zero
    elif way0_amount0 != 0 and way1_amount0 != 0 and way0_amount1 == 0 and way1_amount1 == 0:
        token0_slipage = np.abs((way0_amount0 - way1_amount0) / way0_amount0)
        if token0_slipage <= slipage:
            return min(way0_amount0, way1_amount0),way1_amount1  # Min amount for token0
        else:
            return False

    # Handle uncovered cases (optional but recommended)
    else:
        return False
from web3.exceptions import ContractLogicError
#chatgpt
def send_tx_unified(
    w3: Web3,
    tx_builder_fn,
    wallet: str,
    private_key: str,
    nonce: int,
    mode: str = "simulate",
    gas_multiplier: float = 1.1,
    legacy_first: bool = True
) -> dict:
    """
    tx_builder_fn(gas_params: dict) -> built_tx
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "gas_estimate": None,
        "used_eip1559": False,
        "error": None,
        "nonce": nonce
    }

    # ---------- Attempt 1: simulate + legacy gas ----------
    try:
        gas_price = w3.eth.gas_price
        tx_tmp = tx_builder_fn({
            "from": wallet,
            "nonce": nonce,
            "gasPrice": gas_price
        })

        gas_est = w3.eth.estimate_gas(tx_tmp)
        result["gas_estimate"] = gas_est

        if mode == "simulate":
            result["success"] = True
            return result

        tx_tmp["gas"] = int(gas_est * gas_multiplier)

        signed = w3.eth.account.sign_transaction(tx_tmp, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        result.update({
            "success": receipt.status == 1,
            "tx_hash": w3.to_hex(tx_hash),
            "receipt": receipt,
            "nonce": nonce + 1
        })
        return result

    except ContractLogicError as e:
        legacy_error = str(e)
    except Exception as e:
        legacy_error = str(e)

    # ---------- Attempt 2: EIP-1559 fallback ----------
    try:
        latest = w3.eth.get_block("latest")
        base_fee = latest["baseFeePerGas"]
        priority_fee = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")
        max_fee = base_fee + 2 * priority_fee

        tx_tmp = tx_builder_fn({
            "from": wallet,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        })

        try:
            gas_est = w3.eth.estimate_gas(tx_tmp)
            tx_tmp["gas"] = int(gas_est * gas_multiplier)
            result["gas_estimate"] = gas_est
        except Exception:
            tx_tmp["gas"] = 350_000

        if mode == "simulate":
            result["success"] = True
            result["used_eip1559"] = True
            return result

        signed = w3.eth.account.sign_transaction(tx_tmp, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        result.update({
            "success": receipt.status == 1,
            "tx_hash": w3.to_hex(tx_hash),
            "receipt": receipt,
            "used_eip1559": True,
            "nonce": nonce + 1
        })
        return result

    except Exception as e:
        result["error"] = f"Legacy error: {legacy_error} | EIP1559 error: {e}"
        return result
#
def approve_if_needed(
    w3: Web3,
    token_contract,
    router: str,
    amount: int,
    wallet: str,
    private_key: str,
    nonce: int,
    mode="send"
) -> dict:

    allowance = token_contract.functions.allowance(wallet, router).call()
    if allowance >= amount:
        return {"approved": False, "nonce": nonce}

    def build_tx(gas_params):
        return token_contract.functions.approve(
            router,
            amount
        ).build_transaction(gas_params)

    res = send_tx_unified(
        w3,
        build_tx,
        wallet,
        private_key,
        nonce,
        mode=mode
    )

    return {
        "approved": True,
        "nonce": res["nonce"],
        "tx": res
    }

#
def swap_v3_unified(
    w3: Web3,
    router_contract,
    pool_info: dict,
    token_in: str,
    token_out: str,
    amount_in_wei: int,
    min_out_wei: int,
    wallet: str,
    private_key: str,
    nonce: int,
    mode="send"
) -> dict:

    params = {
        "tokenIn": token_in,
        "tokenOut": token_out,
        "fee": pool_info["fee_tier"],
        "recipient": wallet,
        "amountIn": amount_in_wei,
        "amountOutMinimum": min_out_wei,
        "sqrtPriceLimitX96": 0
    }

    def build_tx(gas_params):
        return router_contract.functions.exactInputSingle(
            params
        ).build_transaction(gas_params)

    return send_tx_unified(
        w3,
        build_tx,
        wallet,
        private_key,
        nonce,
        mode=mode
    )

#
#chatgpt

from web3.exceptions import ContractLogicError, TimeExhausted
#gemini pro
def get_eip1559_fees(w3: Web3, priority_fee_gwei: float = 1.5):
    """
    Calculates EIP-1559 gas fees based on the latest block.
    Returns (max_fee_per_gas, max_priority_fee_per_gas).
    """
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block["baseFeePerGas"]
    
    # Use user preference or default to 1.5 Gwei for priority
    max_priority_fee = w3.to_wei(priority_fee_gwei, 'gwei')
    
    # Formula: Base + 2 * Priority to ensure inclusion
    max_fee = base_fee + (2 * max_priority_fee)
    
    return max_fee, max_priority_fee

def send_signed_transaction_safe(w3: Web3, signed_tx, wait_for_receipt: bool = True, timeout: int = 120):
    """
    Sends a signed transaction and optionally waits for the receipt.
    Returns a dictionary containing status, hash, receipt, and error details.
    """
    try:
        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)
        
        result = {
            "success": False,
            "tx_hash": tx_hash_hex,
            "receipt": None,
            "error": None
        }

        if wait_for_receipt:
            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=timeout)
                result["receipt"] = receipt
                
                if receipt["status"] == 1:
                    result["success"] = True
                else:
                    result["error"] = "Transaction Reverted On-Chain (Status 0)"
                    
            except TimeExhausted:
                result["error"] = "Timeout waiting for receipt (Transaction might still be pending)"
            except Exception as e:
                result["error"] = f"Error getting receipt: {str(e)}"
        else:
            result["success"] = True # Assume success if we don't wait
            
        return result

    except Exception as e:
        return {
            "success": False,
            "tx_hash": None,
            "receipt": None,
            "error": f"Failed to send transaction: {str(e)}"
        }

def handle_approval_hybrid(
    w3: Web3, 
    token_contract, 
    router_address: str, 
    amount_wei: int, 
    wallet_address: str, 
    private_key: str, 
    nonce: int
) -> dict:
    """
    Checks allowance and approves if necessary using hybrid gas estimation.
    Returns updated nonce and status.
    """
    try:
        current_allowance = token_contract.functions.allowance(wallet_address, router_address).call()
        
        if current_allowance >= amount_wei:
            return {"approved": True, "nonce": nonce, "tx_hash": None}

        # Prepare gas fees
        max_fee, max_priority = get_eip1559_fees(w3)
        
        tx_build = token_contract.functions.approve(router_address, amount_wei).build_transaction({
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": max_priority
        })

        # Hybrid Gas Strategy
        try:
            est_gas = w3.eth.estimate_gas(tx_build)
            tx_build["gas"] = int(est_gas * 1.1) # 10% buffer
        except Exception as e:
            # Fallback for approve
            tx_build["gas"] = 100000 
        
        signed_tx = w3.eth.account.sign_transaction(tx_build, private_key)
        
        # Send
        send_res = send_signed_transaction_safe(w3, signed_tx, wait_for_receipt=True)
        
        if send_res["success"]:
            return {"approved": True, "nonce": nonce + 1, "tx_hash": send_res["tx_hash"]}
        else:
            raise Exception(f"Approve failed: {send_res['error']}")

    except Exception as e:
        # Return error but keep the nonce sync attempt
        print(f"Approval Error: {e}")
        raise e

def make_swap_robust(
    w3: Web3,
    input_token_address: str,
    output_token_address: str,
    amount_input_float: float,
    wallet_address: str,
    private_key: str,
    pool_contract,       # Initialized Pool Contract
    router_contract,     # Initialized Router Contract
    input_token_contract, # Initialized Input Token Contract
    slippage: float = 0.05,
    gas_multiplier: float = 1.2
) -> dict:
    """
    Executes a swap with FULL logic:
    1. Calculates precise AmountOutMin based on pool tick and slippage.
    2. Checks and performs Approval if allowance is insufficient.
    3. Uses Hybrid Gas Strategy: Max(Simulation, SafeFallback) * Multiplier.
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "approve_tx": None,
        "error": None,
        "mode_used": "unknown"
    }

    try:
        # 1. Address Checksum
        input_token_address = w3.to_checksum_address(input_token_address)
        output_token_address = w3.to_checksum_address(output_token_address)
        wallet_address = w3.to_checksum_address(wallet_address)
        router_address = router_contract.address

        # 2. Get Pool Info (Token0/Token1/Fee/Tick)
        # Assuming `pool_current_info` helper returns {'token0_address': ..., 'current_tick': ..., 'fee_tier': ...}
        pool_info = pool_current_info(pool_contract) 
        token0 = w3.to_checksum_address(pool_info['token0_address'])
        token1 = w3.to_checksum_address(pool_info['token1_address'])
        current_tick = pool_info['current_tick']
        fee_tier = pool_info['fee_tier']

        # 3. Get Decimals (Crucial for Price Calculation)
        # We need decimals of both tokens to calculate the correct price from the tick
        # Note: input_token_contract is passed as argument, we might need output token contract too for decimals
        # For safety, let's fetch decimals from the contract calls.
        
        inp_decimals = input_token_contract.functions.decimals().call()
        
        # We need output decimals. If output_token_contract is not passed, we create a temporary instance
        # Assuming standard ERC20 ABI for decimals is available or minimal ABI
        minimal_abi = [{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]
        output_token_contract_temp = w3.eth.contract(address=output_token_address, abi=minimal_abi)
        out_decimals = output_token_contract_temp.functions.decimals().call()

        decimal0 = inp_decimals if input_token_address == token0 else out_decimals
        decimal1 = out_decimals if input_token_address == token0 else inp_decimals

        # 4. Calculate Amounts and Slippage
        amount_in_wei = int(amount_input_float * (10 ** inp_decimals))

        # Calculate Spot Price from Tick
        current_price = calculate_price_by_tick(current_tick, decimal0, decimal1)

        # Calculate Expected Output (Human Readable)
        amount_out_human = 0.0
        if input_token_address == token0:
            # Swapping Token0 -> Token1
            amount_out_human = amount_input_float * current_price
        else:
            # Swapping Token1 -> Token0
            amount_out_human = amount_input_float * (1 / current_price)

        # Apply Slippage to get Minimum Output in Wei
        amount_out_min_wei = int(amount_out_human * (10 ** out_decimals) * (1 - slippage))

        print(f"Swap Plan: {amount_input_float} In -> Min {amount_out_min_wei / (10**out_decimals)} Out (Slippage: {slippage*100}%)")

        # 5. Handle Approval (Auto-Execute)
        allowance = input_token_contract.functions.allowance(wallet_address, router_address).call()
        
        if allowance < amount_in_wei:
            print("Insufficient Allowance. Approving Router...")
            
            # Gas Params for Approve
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            prio_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, 'gwei')
            max_fee = base_fee + (2 * prio_fee)
            
            approve_nonce = w3.eth.get_transaction_count(wallet_address)
            
            app_tx_build = input_token_contract.functions.approve(router_address, 2**256 - 1).build_transaction({
                "from": wallet_address,
                "nonce": approve_nonce,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": prio_fee
            })

            # Hybrid Gas for Approve
            try:
                est_gas_app = w3.eth.estimate_gas(app_tx_build)
                app_tx_build['gas'] = int(est_gas_app * 1.1)
            except:
                app_tx_build['gas'] = 100000 # Safe fallback

            signed_app = w3.eth.account.sign_transaction(app_tx_build, private_key)
            app_hash = w3.eth.send_raw_transaction(signed_app.raw_transaction)
            
            print(f"Approve Sent: {w3.to_hex(app_hash)}. Waiting...")
            w3.eth.wait_for_transaction_receipt(app_hash)
            result["approve_tx"] = w3.to_hex(app_hash)

        # 6. Prepare Swap Parameters
        params = {
            "tokenIn": input_token_address,
            "tokenOut": output_token_address,
            "fee": fee_tier,
            "recipient": wallet_address,
            "amountIn": amount_in_wei,
            "amountOutMinimum": amount_out_min_wei,
            "sqrtPriceLimitX96": 0
        }

        # 7. Gas Preparation (EIP-1559)
        latest_block = w3.eth.get_block('latest')
        base_fee = latest_block['baseFeePerGas']
        priority_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, 'gwei')
        max_fee = base_fee + (2 * priority_fee)

        # Refresh nonce after potential approval
        nonce = w3.eth.get_transaction_count(wallet_address)

        tx_params = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee,
            "value": 0
        }

        # 8. Hybrid Max Strategy: Max(Simulation, Fallback) * Multiplier
        simulated_gas = 0
        fallback_gas = 450000 # Safe fallback for V3 Swap (usually ~150k-250k)

        try:
            # Try Simulation
            temp_tx = router_contract.functions.exactInputSingle(params).build_transaction(tx_params)
            simulated_gas = w3.eth.estimate_gas(temp_tx)
            result["mode_used"] = "simulated"
        except Exception as e:
            # Simulation Failed (Likely slippage or volatility)
            print(f"Swap Simulation Failed: {e}. Switching to MAX Fallback.")
            simulated_gas = 0
            result["mode_used"] = "fallback_blind"

        # The Key Robust Logic: Take the MAX
        base_limit = max(simulated_gas, fallback_gas)
        final_gas_limit = int(base_limit * gas_multiplier)
        
        tx_params["gas"] = final_gas_limit
        print(f"Gas Limit Set: {final_gas_limit} (Sim: {simulated_gas}, Fallback: {fallback_gas})")

        # 9. Build, Sign, Send
        final_tx = router_contract.functions.exactInputSingle(params).build_transaction(tx_params)
        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)
        result["tx_hash"] = tx_hash_hex
        
        print(f"Swap Tx Sent: {tx_hash_hex}. Waiting for receipt...")

        # 10. Wait for Receipt
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
            result["receipt"] = receipt
            
            if receipt['status'] == 1:
                result["success"] = True
            else:
                result["error"] = "Swap Reverted On-Chain (Status 0)"
        
        except TimeExhausted:
            result["error"] = "Timeout waiting for receipt"
        except Exception as e:
            result["error"] = f"Receipt Error: {e}"

        return result

    except Exception as e:
        result["error"] = f"Critical Swap Error: {str(e)}"
        return result
#gemini pro

#
def check_transaction_status_and_log_gas(w3_instance, tx_hash: str,
                                         inp_time_out:int=60 ):

    try:
        # 1
        print(f"Waiting for TX confirmation...")
        receipt = w3_instance.eth.wait_for_transaction_receipt(tx_hash, timeout=inp_time_out)

        # 2
        if receipt.status == 1:
            status_text = "SUCCESS"
        else:
            status_text = "FAILED (Reverted)"

        # 3
        gas_used = receipt.gasUsed
        effective_gas_price = receipt.effectiveGasPrice

        #
        transaction_cost_wei = gas_used * effective_gas_price

        print(f"Status: {status_text}")
        print(f"Block Number: {receipt.blockNumber}")
        print(f"Gas Used: {gas_used}")
        print(f"Effective Gas Price (Wei): {effective_gas_price}")
        print(f"Total Cost (Wei): {transaction_cost_wei}")
        print("-" * 30)

        return receipt

    except Exception as e:
        print(f"transaction failed or timed out: {e}")
        return None
#
def decrease_liquidity_v3_nft1(
    inp_position_id: int,
    inp_liquidity_amount: int,
    inp_position_manager_contract,
    inp_expected_token0: int,
    inp_expected_token1: int,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    slippage: float = 0.05
) -> dict:

    if slippage <= 0 or slippage >= 1:
        slippage = 0.05

    # --- read expected outputs ---
    amount_out0, amount_out1 = get_nft_balances(
        inp_position_manager_contract,
        inp_position_id,
        wallet_address
    )

    if amount_out0 is None or amount_out1 is None:
        return {"error": "Unable to read NFT balances"}
    P=pair_slipage_check(inp_expected_token0, amount_out0, inp_expected_token1, amount_out1, slippage)
    # --- slippage guard (off-chain check) ---
    if P:
        pass
    else:
        return {"error": "Slippage check failed before tx"}

    params = {
        "tokenId": inp_position_id,
        "liquidity": inp_liquidity_amount,
        "amount0Min": amount_out0,
        "amount1Min": amount_out1,
        "deadline": int(time.time()) + 1200
    }

    # --- gas params (EIP-1559 safe) ---
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block["baseFeePerGas"]
    priority_fee = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")
    max_fee = base_fee + 2 * priority_fee

    nonce = w3.eth.get_transaction_count(wallet_address)

    tx_base = {
        "from": wallet_address,
        "nonce": nonce,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee
    }

    estimation_failed = False
    estimation_error = None

    # --- try gas estimation (but DO NOT block send) ---
    try:
        tx_for_estimate = inp_position_manager_contract.functions.decreaseLiquidity(
            params
        ).build_transaction(tx_base)

        estimated_gas = w3.eth.estimate_gas(tx_for_estimate)
        tx_base["gas"] = int(estimated_gas * 1.1)

    except Exception as e:
        estimation_failed = True
        estimation_error = str(e)
        tx_base["gas"] = 300_000  # safe fallback for decreaseLiquidity

    # --- build & sign final tx ---
    final_tx = inp_position_manager_contract.functions.decreaseLiquidity(
        params
    ).build_transaction(tx_base)

    signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

    # --- send tx safely ---
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = w3.to_hex(tx_hash)

    receipt = None
    send_error = None

    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    except Exception as e:
        send_error = str(e)

    return {
        "tx_hash": tx_hash_hex,
        "status": (
            "success" if receipt and receipt.status == 1 else "reverted"
        ),
        "receipt": receipt,
        "logs": receipt.logs if receipt else [],
        "estimation_failed": estimation_failed,
        "estimation_error": estimation_error,
        "send_error": send_error
    }
#
def decrease_liquidity_v3_nft2(
    inp_position_id,
    inp_liquidity_amount,
    inp_position_manager_contract,
    inp_expected_token0,
    inp_expected_token1,
    w3_instance: Web3,
    wallet_address,
    private_key,
    mode: str = 'simulate',
    slippage: float = 0.05
):
    #
    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "error": None,
        "gas_estimate": 0
    }

    if slippage > 1 or slippage < 0:
        slippage = 0.05

    try:
        # 1. Check Balances / Slippage Calculation
        #
        amount_out0, amount_out1 = get_nft_balances(inp_position_manager_contract, inp_position_id, wallet_address)

        if amount_out0 is None or amount_out1 is None:
            result["error"] = "Failed to fetch NFT balances"
            return result

        #
        #
        if inp_expected_token0 > 0:
            if abs(inp_expected_token0 - amount_out0) / inp_expected_token0 > slippage:
                result["error"] = f"Slippage Error: Expected {inp_expected_token0}, Got {amount_out0}"
                return result

        if inp_expected_token1 > 0:
            if abs(inp_expected_token1 - amount_out1) / inp_expected_token1 > slippage:
                result["error"] = f"Slippage Error: Expected {inp_expected_token1}, Got {amount_out1}"
                return result

        #
        #
        #
        amount0_min = int(amount_out0)
        amount1_min = int(amount_out1)

        params_decrease = {
            "tokenId": int(inp_position_id),
            "liquidity": int(inp_liquidity_amount),
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "deadline": int(time.time()) + 1200
        }

        # 2. Gas Parameters (EIP-1559)
        latest_block = w3_instance.eth.get_block('latest')
        base_fee_per_gas = latest_block['baseFeePerGas']
        #
        max_priority_fee_per_gas = w3_instance.eth.max_priority_fee if w3_instance.eth.max_priority_fee else w3_instance.to_wei(1, 'gwei')
        max_fee_per_gas = base_fee_per_gas + 2 * max_priority_fee_per_gas

        nonce = w3_instance.eth.get_transaction_count(wallet_address)

        tx_build_params = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas
        }

        # 3. Estimate Gas
        try:
            tx_for_estimate = inp_position_manager_contract.functions.decreaseLiquidity(params_decrease).build_transaction(tx_build_params)
            estimated_gas = w3_instance.eth.estimate_gas(tx_for_estimate)

            #
            safe_gas_limit = int(estimated_gas * 1.2)
            tx_build_params['gas'] = safe_gas_limit
            result['gas_estimate'] = estimated_gas

        except exceptions.ContractLogicError as e:
            result["error"] = f"Execution Reverted during Gas Estimate: {e}"
            return result
        except Exception as e:
            #
            result["error"] = f"Gas Estimation Failed: {e}"
            result['gas_estimate']=500000
            return result

        if mode == 'simulate':
            result["success"] = True
            return result

        elif mode == 'send_raw':
            # 4. Build Final Transaction
            final_tx = inp_position_manager_contract.functions.decreaseLiquidity(params_decrease).build_transaction(tx_build_params)

            # 5. Sign Transaction
            signed_tx = w3_instance.eth.account.sign_transaction(final_tx, private_key)

            # 6. Send Transaction
            tx_hash_bytes = w3_instance.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = w3_instance.to_hex(tx_hash_bytes)

            result["tx_hash"] = tx_hash_hex
            print(f"Decrease Liquidity Tx Sent: {tx_hash_hex}. Waiting for receipt...")

            # 7. Wait for Receipt
            try:
                receipt = w3_instance.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
                result["receipt"] = receipt

                # Check Status (1 = Success, 0 = Fail)
                if receipt['status'] == 1:
                    result["success"] = True
                else:
                    result["success"] = False
                    result["error"] = "Transaction Reverted On-Chain (Status 0)"

            except Exception as e:
                result["success"] = False
                result["error"] = f"Tx sent but wait failed (timeout?): {e}"

            return result

        else:
            result["error"] = "Invalid mode selected"
            return result

    except Exception as e:
        result["error"] = f"Unexpected Error: {e}"
        return result
#

#chatgpt
def full_decrease_liquidity_v3_nft_safe(
    position_id: int,
    liquidity: int,
    position_manager,
    expected_token0: int,
    expected_token1: int,
    w3: Web3,
    wallet: str,
    private_key: str,
    mode: str = "simulate",
    slippage: float = 0.05,
    gas_multiplier: float = 1.2,
    fallback_gas: int = 300_000
) -> dict:

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "gas_estimate": None,
        "gas_used": None,
        "error": None
    }

    # ---------- slippage sanity ----------
    if slippage <= 0 or slippage >= 1:
        slippage = 0.05

    # ---------- read NFT balances ----------
    amount0, amount1 = get_nft_balances(
        position_manager,
        position_id,
        wallet
    )

    if amount0 is None or amount1 is None:
        result["error"] = "Unable to read NFT balances"
        return result

    # ---------- off-chain slippage guard ----------
    if not pair_slipage_check(
        expected_token0, amount0,
        expected_token1, amount1,
        slippage
    ):
        result["error"] = "Slippage check failed (off-chain)"
        return result

    # ---------- tx params ----------
    params = {
        "tokenId": int(position_id),
        "liquidity": int(liquidity),
        "amount0Min": int(amount0),
        "amount1Min": int(amount1),
        "deadline": int(time.time()) + 1200
    }

    nonce = w3.eth.get_transaction_count(wallet)

    # =====================================================
    # GAS SOURCE A: estimateGas
    # =====================================================
    gas_estimate = None

    try:
        tx_tmp = position_manager.functions.decreaseLiquidity(
            params
        ).build_transaction({
            "from": wallet,
            "nonce": nonce,
            "gasPrice": w3.eth.gas_price
        })

        gas_estimate = w3.eth.estimate_gas(tx_tmp)

    except ContractLogicError:
        gas_estimate = None
    except Exception:
        gas_estimate = None

    # =====================================================
    # GAS SOURCE B: fallback (latest block)
    # =====================================================
    gas_fallback = fallback_gas

    # =====================================================
    # FINAL GAS SELECTION
    # =====================================================
    base_gas = max(
        gas_estimate if gas_estimate else 0,
        gas_fallback
    )

    gas_limit = int(base_gas * gas_multiplier)

    result["gas_estimate"] = gas_estimate
    result["gas_used"] = gas_limit

    if mode == "simulate":
        result["success"] = True
        return result

    # =====================================================
    # FINAL TX (EIP-1559 SAFE)
    # =====================================================
    latest = w3.eth.get_block("latest")
    base_fee = latest["baseFeePerGas"]
    priority_fee = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")
    max_fee = base_fee + 2 * priority_fee

    final_tx = position_manager.functions.decreaseLiquidity(
        params
    ).build_transaction({
        "from": wallet,
        "nonce": nonce,
        "gas": gas_limit,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee
    })

    signed = w3.eth.account.sign_transaction(final_tx, private_key)

    try:
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        result.update({
            "success": receipt.status == 1,
            "tx_hash": w3.to_hex(tx_hash),
            "receipt": receipt
        })
        return result

    except Exception as e:
        result["error"] = f"Send failed: {e}"
        return result
#

#gemini pro
def full_decrease_liquidity_v3_hybrid(
    inp_position_id: int,
    inp_liquidity_amount: int,
    inp_position_manager_contract,
    inp_expected_token0: int,
    inp_expected_token1: int,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = 'send_raw', # 'simulate' or 'send_raw'
    slippage: float = 0.05,
    gas_multiplier: float = 1.2 # Safety buffer multiplier
) -> dict:
    
    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "error": None,
        "gas_used_limit": 0,
        "mode_used": "unknown"
    }

    try:
        # 1. Checksum Addresses
        wallet_address = w3.to_checksum_address(wallet_address)
        
        # 2. Fetch Balances & Slippage Check
        # Assuming get_nft_balances and pair_slipage_check are predefined helpers
        amount_out0, amount_out1 = get_nft_balances(
            inp_position_manager_contract, 
            inp_position_id, 
            wallet_address
        )

        if amount_out0 is None or amount_out1 is None:
            result["error"] = "Failed to fetch NFT balances"
            return result

        # Perform off-chain slippage guard
        is_slippage_ok = pair_slipage_check(
            inp_expected_token0, amount_out0, 
            inp_expected_token1, amount_out1, 
            slippage
        )
        
        if not is_slippage_ok:
            result["error"] = "Pre-transaction slippage check failed"
            return result

        # 3. Prepare Transaction Parameters
        params = {
            "tokenId": int(inp_position_id),
            "liquidity": int(inp_liquidity_amount),
            "amount0Min": int(amount_out0 * (1 - slippage)),
            "amount1Min": int(amount_out1 * (1 - slippage)),
            "deadline": int(time.time()) + 1200
        }

        # 4. Gas & Fee Preparation (EIP-1559)
        latest_block = w3.eth.get_block("latest")
        base_fee = latest_block["baseFeePerGas"]
        priority_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, "gwei")
        max_fee = base_fee + (2 * priority_fee)

        nonce = w3.eth.get_transaction_count(wallet_address)

        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # 5. Hybrid Gas Strategy (Maximize Simulation vs Fallback)
        simulated_gas = 0
        fallback_gas = 350000 # Standard safe limit for Uniswap V3 decreaseLiquidity
        
        try:
            # Try precise simulation
            temp_tx = inp_position_manager_contract.functions.decreaseLiquidity(params).build_transaction(tx_base)
            simulated_gas = w3.eth.estimate_gas(temp_tx)
            result["mode_used"] = "simulated"
        except Exception as e:
            # If simulation fails, we use the fallback
            simulated_gas = 0
            result["mode_used"] = "fallback_blind_send"
            print(f"Simulation failed ({e}), using fallback gas limit.")

        # Pick the maximum of both and apply the user's safety multiplier
        final_gas_limit = int(max(simulated_gas, fallback_gas) * gas_multiplier)
        tx_base["gas"] = final_gas_limit
        result["gas_used_limit"] = final_gas_limit

        if mode == 'simulate':
            result["success"] = True
            return result

        # 6. Build, Sign, and Send
        final_tx = inp_position_manager_contract.functions.decreaseLiquidity(params).build_transaction(tx_base)
        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)
        result["tx_hash"] = tx_hash_hex

        # 7. Wait for Confirmation
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=180)
            result["receipt"] = receipt
            if receipt["status"] == 1:
                result["success"] = True
            else:
                result["error"] = "Transaction Reverted on Blockchain"
        except Exception as e:
            result["error"] = f"Transaction sent but receipt not found: {e}"

        return result

    except Exception as e:
        result["error"] = f"Unexpected Exception: {str(e)}"
        return result

def collect_liquidity_v3_nft2(
    inp_position_id,
    inp_position_manager_contract,
    w3_instance: Web3,
    wallet_address,
    private_key,
    mode: str = 'simulate'):

    #
    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "error": None,
        "gas_estimate": 0
    }

    MAX_UINT128 = 2**128 - 1

    # 
    # 
    params_collect = {
        "tokenId": int(inp_position_id),
        "recipient": wallet_address,
        "amount0Max": MAX_UINT128,
        "amount1Max": MAX_UINT128
    }

    try:
        # 1
        # 
        latest_block = w3_instance.eth.get_block('latest')
        base_fee_per_gas = latest_block['baseFeePerGas']
        
        # 
        max_priority_fee_per_gas = w3_instance.eth.max_priority_fee if w3_instance.eth.max_priority_fee else w3_instance.to_wei(1, 'gwei')
        # 
        max_fee_per_gas = base_fee_per_gas + 2 * max_priority_fee_per_gas

        nonce = w3_instance.eth.get_transaction_count(wallet_address)

        tx_build_params = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas
        }

        # 2. 
        try:
            tx_for_estimate = inp_position_manager_contract.functions.collect(params_collect).build_transaction(tx_build_params)
            estimated_gas = w3_instance.eth.estimate_gas(tx_for_estimate)
            
            #  
            safe_gas_limit = int(estimated_gas * 1.15)
            tx_build_params['gas'] = safe_gas_limit
            result['gas_estimate'] = estimated_gas

        except exceptions.ContractLogicError as e:
            result["error"] = f"Execution Reverted during Collect Estimate: {e}"
            return result
        except Exception as e:
            result["error"] = f"Gas Estimation Failed: {e}"
            return result

        if mode == 'simulate':
            result["success"] = True
            return result

        elif mode == 'send_raw':
            # 3
            final_tx = inp_position_manager_contract.functions.collect(params_collect).build_transaction(tx_build_params)

            signed_tx = w3_instance.eth.account.sign_transaction(final_tx, private_key)
            
            #
            tx_hash_bytes = w3_instance.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = w3_instance.to_hex(tx_hash_bytes)
            
            result["tx_hash"] = tx_hash_hex
            print(f"Collect Tx Sent: {tx_hash_hex}. Waiting for receipt...")

            # 4.
            try:
                receipt = w3_instance.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
                result["receipt"] = receipt

                #
                if receipt['status'] == 1:
                    result["success"] = True
                else:
                    result["success"] = False
                    result["error"] = "Transaction Reverted On-Chain (Status 0)"

            except Exception as e:
                #
                result["success"] = False
                result["error"] = f"Tx sent but wait failed: {e}"
            
            return result

        else:
            result["error"] = "Invalid mode selected"
            return result

    except Exception as e:
        result["error"] = f"Unexpected Error: {e}"
        return result
#
def collect_liquidity_v3_nft1(
    inp_position_id: int,
    inp_position_manager_contract,
    w3: Web3,
    wallet_address: str,
    private_key: str
) -> dict:

    MAX_UINT128 = 2**128 - 1

    params = {
        "tokenId": inp_position_id,
        "recipient": wallet_address,
        "amount0Max": MAX_UINT128,
        "amount1Max": MAX_UINT128
    }

    # --- gas params (EIP-1559) ---
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block["baseFeePerGas"]
    priority_fee = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")
    max_fee = base_fee + 2 * priority_fee

    nonce = w3.eth.get_transaction_count(wallet_address)

    tx_base = {
        "from": wallet_address,
        "nonce": nonce,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee
    }

    estimation_failed = False
    estimation_error = None

    # --- try gas estimation (non-blocking) ---
    try:
        tx_for_estimate = inp_position_manager_contract.functions.collect(
            params
        ).build_transaction(tx_base)

        estimated_gas = w3.eth.estimate_gas(tx_for_estimate)
        tx_base["gas"] = int(estimated_gas * 1.1)

    except Exception as e:
        estimation_failed = True
        estimation_error = str(e)
        tx_base["gas"] = 250_000  # safe fallback for collect

    # --- build & sign tx ---
    final_tx = inp_position_manager_contract.functions.collect(
        params
    ).build_transaction(tx_base)

    signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

    # --- send tx ---
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = w3.to_hex(tx_hash)

    receipt = None
    send_error = None

    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    except Exception as e:
        send_error = str(e)

    return {
        "tx_hash": tx_hash_hex,
        "status": (
            "success" if receipt and receipt.status == 1 else "reverted"
        ),
        "receipt": receipt,
        "logs": receipt.logs if receipt else [],
        "estimation_failed": estimation_failed,
        "estimation_error": estimation_error,
        "send_error": send_error
    }
#


#chatgpt
def collect_liquidity_v3_nft_safe(
    position_id: int,
    position_manager_contract,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = "simulate",
    gas_buffer: float = 1.15,
    fallback_gas: int = 250_000,
    receipt_timeout: int = 180
) -> dict:
    """
    Safely collect fees from a Uniswap V3 position NFT.
    Supports simulation and guaranteed send with gas fallback.
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "gas_estimated": None,
        "gas_used": None,
        "estimation_failed": False,
        "error": None
    }

    MAX_UINT128 = 2**128 - 1

    # --- collect params ---
    params = {
        "tokenId": int(position_id),
        "recipient": wallet_address,
        "amount0Max": MAX_UINT128,
        "amount1Max": MAX_UINT128
    }

    try:
        # --- EIP-1559 gas pricing ---
        latest_block = w3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", w3.eth.gas_price)

        priority_fee = (
            w3.eth.max_priority_fee
            if hasattr(w3.eth, "max_priority_fee") and w3.eth.max_priority_fee
            else w3.to_wei(1, "gwei")
        )

        max_fee = base_fee + (2 * priority_fee)

        nonce = w3.eth.get_transaction_count(wallet_address)

        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # --- gas estimation (non-blocking) ---
        try:
            tx_for_estimate = position_manager_contract.functions.collect(
                params
            ).build_transaction(tx_base)

            estimated_gas = w3.eth.estimate_gas(tx_for_estimate)
            gas_limit = int(estimated_gas * gas_buffer)

            result["gas_estimated"] = estimated_gas

        except ContractLogicError as e:
            result["estimation_failed"] = True
            result["error"] = f"Collect reverted during estimation: {e}"
            gas_limit = fallback_gas

        except Exception as e:
            result["estimation_failed"] = True
            result["error"] = f"Gas estimation failed: {e}"
            gas_limit = fallback_gas

        tx_base["gas"] = gas_limit

        # --- simulation only ---
        if mode == "simulate":
            result["success"] = True
            return result

        if mode != "send_raw":
            result["error"] = "Invalid mode (use simulate or send_raw)"
            return result

        # --- build final tx ---
        final_tx = position_manager_contract.functions.collect(
            params
        ).build_transaction(tx_base)

        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)

        result["tx_hash"] = tx_hash_hex

        # --- wait for receipt ---
        try:
            receipt = w3.eth.wait_for_transaction_receipt(
                tx_hash_bytes,
                timeout=receipt_timeout
            )

            result["receipt"] = receipt
            result["gas_used"] = receipt.get("gasUsed")

            if receipt.status == 1:
                result["success"] = True
            else:
                result["error"] = "Transaction reverted on-chain (status=0)"

        except Exception as e:
            result["error"] = f"Tx sent but receipt wait failed: {e}"

        return result

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        return result

#gemini pro
def collect_liquidity_v3_hybrid(
    inp_position_id: int,
    inp_position_manager_contract,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = 'send_raw',  # 'simulate' or 'send_raw'
    gas_multiplier: float = 1.2
) -> dict:
    """
    Collects fees (liquidity) from a Uniswap V3 NFT position using a robust hybrid gas strategy.
    
    Strategy:
    1. Attempt to simulate the transaction to get precise gas usage.
    2. Define a safe 'fallback' gas limit (blind guess).
    3. Use the MAXIMUM of (Simulation, Fallback) * Multiplier to ensure success.
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "error": None,
        "gas_limit_used": 0,
        "mode_used": "unknown"
    }

    MAX_UINT128 = 2**128 - 1

    try:
        # 1. Address Checksum
        wallet_address = w3.to_checksum_address(wallet_address)

        # 2. Build Collect Parameters
        # collect() params: tokenId, recipient, amount0Max, amount1Max
        params_collect = {
            "tokenId": int(inp_position_id),
            "recipient": wallet_address,
            "amount0Max": MAX_UINT128,
            "amount1Max": MAX_UINT128
        }

        # 3. Calculate Gas Fees (EIP-1559)
        latest_block = w3.eth.get_block('latest')
        base_fee = latest_block['baseFeePerGas']
        
        # Set priority fee (User preferred or default 1.5 Gwei)
        priority_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, 'gwei')
        
        # Max Fee = Base + (2 * Priority) for high inclusion probability
        max_fee = base_fee + (2 * priority_fee)

        nonce = w3.eth.get_transaction_count(wallet_address)

        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # 4. Hybrid Gas Logic (The Max Strategy)
        simulated_gas = 0
        fallback_gas = 300000  # Safe upper bound for a simple 'collect' call
        
        try:
            # Attempt Simulation
            tx_for_estimate = inp_position_manager_contract.functions.collect(params_collect).build_transaction(tx_base)
            simulated_gas = w3.eth.estimate_gas(tx_for_estimate)
            result["mode_used"] = "simulated"
        except Exception as e:
            # Simulation Failed (e.g., node issue or RPC error)
            print(f"Simulation failed during collect ({e}). Switching to fallback.")
            simulated_gas = 0
            result["mode_used"] = "fallback"

        # CORE LOGIC: Take the MAX of simulated or fallback, then multiply
        # If simulation was 0 (failed), fallback takes over.
        # If simulation was 150k, and fallback is 300k, we use 300k (safer).
        # If simulation was 400k (complex state), we use 400k.
        base_gas_limit = max(simulated_gas, fallback_gas)
        final_gas_limit = int(base_gas_limit * gas_multiplier)

        tx_base['gas'] = final_gas_limit
        result['gas_limit_used'] = final_gas_limit

        if mode == 'simulate':
            result["success"] = True
            return result

        # 5. Build Final Transaction
        final_tx = inp_position_manager_contract.functions.collect(params_collect).build_transaction(tx_base)

        # 6. Sign Transaction
        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

        # 7. Send Transaction
        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)
        result["tx_hash"] = tx_hash_hex

        # 8. Wait for Receipt
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
            result["receipt"] = receipt

            if receipt['status'] == 1:
                result["success"] = True
            else:
                result["success"] = False
                result["error"] = "Transaction Reverted On-Chain (Status 0)"

        except TimeExhausted:
            result["error"] = "Timeout waiting for receipt (Transaction might still be pending)"
        except Exception as e:
            result["error"] = f"Error during wait: {str(e)}"

        return result

    except Exception as e:
        result["error"] = f"Unexpected Error: {str(e)}"
        return result

#
def burn_liquidity_v3_nft1(
    inp_position_id,
    inp_position_manager_contract,
    w3_instance: Web3,
    wallet_address,
    private_key,
    mode: str = 'simulate'
):
    # 
    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "error": None,
        "gas_estimate": 0
    }

    try:
        # 1
        # 
        latest_block = w3_instance.eth.get_block('latest')
        base_fee_per_gas = latest_block['baseFeePerGas']
        
        max_priority_fee_per_gas = w3_instance.eth.max_priority_fee if w3_instance.eth.max_priority_fee else w3_instance.to_wei(1, 'gwei')
        max_fee_per_gas = base_fee_per_gas + 2 * max_priority_fee_per_gas

        nonce = w3_instance.eth.get_transaction_count(wallet_address)

        tx_build_params = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": max_priority_fee_per_gas
        }

        # 2
        #
        try:
            tx_for_estimate = inp_position_manager_contract.functions.burn(int(inp_position_id)).build_transaction(tx_build_params)
            estimated_gas = w3_instance.eth.estimate_gas(tx_for_estimate)
            
            #
            safe_gas_limit = int(estimated_gas * 1.15)
            tx_build_params['gas'] = safe_gas_limit
            result['gas_estimate'] = estimated_gas

        except exceptions.ContractLogicError as e:
            result["error"] = f"Burn Logic Error (Liquidity not 0 or Fees not collected?): {e}"
            return result
        except Exception as e:
            result["error"] = f"Gas Estimation Failed: {e}"
            return result

        if mode == 'simulate':
            result["success"] = True
            return result

        elif mode == 'send_raw':
            # 3
            final_tx = inp_position_manager_contract.functions.burn(int(inp_position_id)).build_transaction(tx_build_params)

            signed_tx = w3_instance.eth.account.sign_transaction(final_tx, private_key)
            
            #
            tx_hash_bytes = w3_instance.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = w3_instance.to_hex(tx_hash_bytes)
            
            result["tx_hash"] = tx_hash_hex
            print(f"Burn Tx Sent: {tx_hash_hex}. Waiting for receipt...")

            # 4
            try:
                receipt = w3_instance.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
                result["receipt"] = receipt

                #
                if receipt['status'] == 1:
                    result["success"] = True
                else:
                    result["success"] = False
                    result["error"] = "Transaction Reverted On-Chain (Status 0)"

            except Exception as e:
                #
                result["success"] = False
                result["error"] = f"Tx sent but wait failed: {e}"
            
            return result

        else:
            result["error"] = "Invalid mode selected"
            return result

    except Exception as e:
        result["error"] = f"Unexpected Error: {e}"
        return result
#
def burn_liquidity_v3_nft2(
    inp_position_id: int,
    inp_position_manager_contract,
    w3: Web3,
    wallet_address: str,
    private_key: str
) -> dict:

    # --- gas params (EIP-1559) ---
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block["baseFeePerGas"]
    priority_fee = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")
    max_fee = base_fee + 2 * priority_fee

    nonce = w3.eth.get_transaction_count(wallet_address)

    tx_base = {
        "from": wallet_address,
        "nonce": nonce,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee
    }

    estimation_failed = False
    estimation_error = None

    # --- try gas estimation (non-blocking) ---
    try:
        tx_for_estimate = inp_position_manager_contract.functions.burn(
            inp_position_id
        ).build_transaction(tx_base)

        estimated_gas = w3.eth.estimate_gas(tx_for_estimate)
        tx_base["gas"] = int(estimated_gas * 1.1)

    except Exception as e:
        estimation_failed = True
        estimation_error = str(e)
        tx_base["gas"] = 200_000  # safe fallback for burn

    # --- build & sign final tx ---
    final_tx = inp_position_manager_contract.functions.burn(
        inp_position_id
    ).build_transaction(tx_base)

    signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

    # --- send tx ---
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = w3.to_hex(tx_hash)

    receipt = None
    send_error = None

    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    except Exception as e:
        send_error = str(e)

    return {
        "tx_hash": tx_hash_hex,
        "status": (
            "success" if receipt and receipt.status == 1 else "reverted"
        ),
        "receipt": receipt,
        "logs": receipt.logs if receipt else [],
        "estimation_failed": estimation_failed,
        "estimation_error": estimation_error,
        "send_error": send_error
    }

#

#chatgpt
def burn_liquidity_v3_nft_safe(
    position_id: int,
    position_manager_contract,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = "simulate",
    gas_buffer: float = 1.15,
    fallback_gas: int = 200_000,
    receipt_timeout: int = 180
) -> dict:
    """
    Safely burn a Uniswap V3 position NFT.
    Requires liquidity = 0 and fees already collected.
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "gas_estimated": None,
        "gas_used": None,
        "estimation_failed": False,
        "error": None
    }

    try:
        # --- EIP-1559 gas pricing ---
        latest_block = w3.eth.get_block("latest")
        base_fee = latest_block.get("baseFeePerGas", w3.eth.gas_price)

        priority_fee = (
            w3.eth.max_priority_fee
            if hasattr(w3.eth, "max_priority_fee") and w3.eth.max_priority_fee
            else w3.to_wei(1, "gwei")
        )

        max_fee = base_fee + (2 * priority_fee)

        nonce = w3.eth.get_transaction_count(wallet_address)

        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # --- gas estimation (non-blocking) ---
        try:
            tx_for_estimate = position_manager_contract.functions.burn(
                int(position_id)
            ).build_transaction(tx_base)

            estimated_gas = w3.eth.estimate_gas(tx_for_estimate)
            gas_limit = int(estimated_gas * gas_buffer)

            result["gas_estimated"] = estimated_gas

        except ContractLogicError as e:
            # Common case: liquidity not zero or fees not collected
            result["estimation_failed"] = True
            result["error"] = f"Burn reverted during estimation: {e}"
            gas_limit = fallback_gas

        except Exception as e:
            result["estimation_failed"] = True
            result["error"] = f"Gas estimation failed: {e}"
            gas_limit = fallback_gas

        tx_base["gas"] = gas_limit

        # --- simulation only ---
        if mode == "simulate":
            result["success"] = True
            return result

        if mode != "send_raw":
            result["error"] = "Invalid mode (use simulate or send_raw)"
            return result

        # --- build final tx ---
        final_tx = position_manager_contract.functions.burn(
            int(position_id)
        ).build_transaction(tx_base)

        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)

        result["tx_hash"] = tx_hash_hex

        # --- wait for receipt ---
        try:
            receipt = w3.eth.wait_for_transaction_receipt(
                tx_hash_bytes,
                timeout=receipt_timeout
            )

            result["receipt"] = receipt
            result["gas_used"] = receipt.get("gasUsed")

            if receipt.status == 1:
                result["success"] = True
            else:
                result["error"] = "Transaction reverted on-chain (status=0)"

        except Exception as e:
            result["error"] = f"Tx sent but receipt wait failed: {e}"

        return result

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        return result

#gemini pro
def burn_liquidity_v3_hybrid(
    inp_position_id: int,
    inp_position_manager_contract,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = 'send_raw',  # 'simulate' or 'send_raw'
    gas_multiplier: float = 1.2
) -> dict:
    """
    Burns a Uniswap V3 NFT position using a hybrid gas strategy.
    
    Strategy:
    1. Simulation: Tries 'estimate_gas' to get precise usage.
    2. Fallback: Uses a hardcoded safe gas limit if simulation fails.
    3. Execution: Uses MAX(Simulation, Fallback) * Multiplier to guarantee mining.
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "error": None,
        "gas_limit_used": 0,
        "mode_used": "unknown",
        "estimation_error": None
    }

    try:
        # 1. Address Checksum
        wallet_address = w3.to_checksum_address(wallet_address)
        position_id = int(inp_position_id)

        # 2. Calculate Gas Fees (EIP-1559)
        latest_block = w3.eth.get_block('latest')
        base_fee = latest_block['baseFeePerGas']
        
        # Priority Fee: User default or safe 1.5 Gwei
        priority_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, 'gwei')
        
        # Max Fee: Base + 2 * Priority
        max_fee = base_fee + (2 * priority_fee)

        nonce = w3.eth.get_transaction_count(wallet_address)

        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # 3. Hybrid Gas Logic (Maximize Simulation vs Fallback)
        simulated_gas = 0
        fallback_gas = 250000  # Safe upper bound for 'burn' (usually costs ~100k-150k)
        
        try:
            # Attempt Simulation
            tx_for_estimate = inp_position_manager_contract.functions.burn(position_id).build_transaction(tx_base)
            simulated_gas = w3.eth.estimate_gas(tx_for_estimate)
            result["mode_used"] = "simulated"
            
        except ContractLogicError as e:
            # Specific logic error (e.g., Not owner, Liquidity not 0 yet)
            result["estimation_error"] = f"Logic Error: {e}"
            simulated_gas = 0
            result["mode_used"] = "fallback_logic_error"
            
        except Exception as e:
            # General RPC error
            result["estimation_error"] = f"General Error: {e}"
            simulated_gas = 0
            result["mode_used"] = "fallback_general_error"

        # CORE STRATEGY: Use the higher of the two values to prevent OutOfGas
        base_gas_limit = max(simulated_gas, fallback_gas)
        
        # Apply Safety Multiplier
        final_gas_limit = int(base_gas_limit * gas_multiplier)

        tx_base['gas'] = final_gas_limit
        result['gas_limit_used'] = final_gas_limit

        if mode == 'simulate':
            result["success"] = True
            return result

        # 4. Build Final Transaction
        final_tx = inp_position_manager_contract.functions.burn(position_id).build_transaction(tx_base)

        # 5. Sign Transaction
        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)

        # 6. Send Transaction
        tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash_bytes)
        result["tx_hash"] = tx_hash_hex

        # 7. Wait for Receipt
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=120)
            result["receipt"] = receipt

            if receipt['status'] == 1:
                result["success"] = True
            else:
                result["success"] = False
                result["error"] = "Transaction Reverted On-Chain (Status 0)"

        except TimeExhausted:
            result["error"] = "Timeout waiting for receipt (Transaction might still be pending)"
        except Exception as e:
            result["error"] = f"Error during wait: {str(e)}"

        return result

    except Exception as e:
        result["error"] = f"Unexpected Error: {str(e)}"
        return result

#
#
def mint_liquidity_v3_nft1(
    token0_contract,
    token1_contract,
    inp_position_manager_contract,
    inp_fee,
    inp_tick_lower,
    inp_tick_upper,
    inp_amount0_desired,
    inp_amount1_desired,
    w3_instance: Web3,
    wallet_address,
    private_key,
    mode: str = 'simulate',
    slippage: float = 0.05
):
    """
    Mints a new position (adds liquidity) to Uniswap V3.
    Handles approvals automatically if allowances are insufficient.
    Returns a dictionary with transaction details and status.
    """
    
    # Standard result structure to track progress and errors
    result = {
        "success": False,
        "tx_hash": None,         # The Mint transaction hash
        "receipt": None,         # The Mint transaction receipt
        "approve_hashes": [],    # List of approval tx hashes sent
        "error": None,
        "gas_estimate": 0
    }

    # 1. Validate Slippage
    if slippage > 1 or slippage < 0:
        slippage = 0.05

    try:
        # 2. Calculate Minimum Amounts (Slippage protection)
        amount0_min = int(inp_amount0_desired * (1 - slippage))
        amount1_min = int(inp_amount1_desired * (1 - slippage))

        pm_address = inp_position_manager_contract.address
        
        # 3. Gas Fee Setup (EIP-1559)
        # Helper lambda to fetch fresh gas params for each tx
        def get_gas_params():
            latest_block = w3_instance.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            priority_fee = w3_instance.eth.max_priority_fee if w3_instance.eth.max_priority_fee else w3_instance.to_wei(1, 'gwei')
            max_fee = base_fee + 2 * priority_fee
            return max_fee, priority_fee

        # ---------------------------------------------------------
        # Handle Approvals (Only in 'send_raw' mode)
        # ---------------------------------------------------------
        if mode == 'send_raw':
            
            # --- Approve Token 0 ---
            allowance0 = token0_contract.functions.allowance(wallet_address, pm_address).call()
            if allowance0 < inp_amount0_desired:
                print(f"Approving Token 0...")
                max_fee, priority_fee = get_gas_params()
                
                # Build Approve Tx
                nonce = w3_instance.eth.get_transaction_count(wallet_address)
                approve_tx0 = token0_contract.functions.approve(pm_address, 2**256 - 1).build_transaction({
                    "from": wallet_address,
                    "nonce": nonce,
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": priority_fee
                })
                
                # Estimate and Sign
                est_gas0 = w3_instance.eth.estimate_gas(approve_tx0)
                approve_tx0['gas'] = int(est_gas0 * 1.1)
                
                signed_app0 = w3_instance.eth.account.sign_transaction(approve_tx0, private_key)
                hash0_bytes = w3_instance.eth.send_raw_transaction(signed_app0.raw_transaction)
                hash0_hex = w3_instance.to_hex(hash0_bytes)
                
                result['approve_hashes'].append({"token": "token0", "hash": hash0_hex})
                print(f"Token 0 Approve Sent: {hash0_hex}. Waiting for receipt...")

                # Wait for confirmation before proceeding
                receipt0 = w3_instance.eth.wait_for_transaction_receipt(hash0_bytes)
                if receipt0['status'] != 1:
                    result['error'] = f"Token 0 Approve Failed. Hash: {hash0_hex}"
                    return result

            # --- Approve Token 1 ---
            allowance1 = token1_contract.functions.allowance(wallet_address, pm_address).call()
            if allowance1 < inp_amount1_desired:
                print(f"Approving Token 1...")
                max_fee, priority_fee = get_gas_params()

                nonce = w3_instance.eth.get_transaction_count(wallet_address)
                approve_tx1 = token1_contract.functions.approve(pm_address, 2**256 - 1).build_transaction({
                    "from": wallet_address,
                    "nonce": nonce,
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": priority_fee
                })

                est_gas1 = w3_instance.eth.estimate_gas(approve_tx1)
                approve_tx1['gas'] = int(est_gas1 * 1.1)

                signed_app1 = w3_instance.eth.account.sign_transaction(approve_tx1, private_key)
                hash1_bytes = w3_instance.eth.send_raw_transaction(signed_app1.raw_transaction)
                hash1_hex = w3_instance.to_hex(hash1_bytes)
                
                result['approve_hashes'].append({"token": "token1", "hash": hash1_hex})
                print(f"Token 1 Approve Sent: {hash1_hex}. Waiting for receipt...")

                receipt1 = w3_instance.eth.wait_for_transaction_receipt(hash1_bytes)
                if receipt1['status'] != 1:
                    result['error'] = f"Token 1 Approve Failed. Hash: {hash1_hex}"
                    return result

        # ---------------------------------------------------------
        # Prepare Mint Parameters
        # ---------------------------------------------------------
        token0_addr = token0_contract.address
        token1_addr = token1_contract.address

        params_mint = {
            "token0": token0_addr,
            "token1": token1_addr,
            "fee": inp_fee,
            "tickLower": int(inp_tick_lower),
            "tickUpper": int(inp_tick_upper),
            "amount0Desired": int(inp_amount0_desired),
            "amount1Desired": int(inp_amount1_desired),
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "recipient": wallet_address,
            "deadline": int(time.time()) + 1200
        }

        # ---------------------------------------------------------
        # Estimate and Send Mint Transaction
        # ---------------------------------------------------------
        
        # Refresh gas params for the main transaction
        max_fee, priority_fee = get_gas_params()
        # Refresh nonce (crucial after approvals)
        nonce = w3_instance.eth.get_transaction_count(wallet_address)

        tx_build_params = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # Estimate Gas
        try:
            tx_for_estimate = inp_position_manager_contract.functions.mint(params_mint).build_transaction(tx_build_params)
            estimated_gas = w3_instance.eth.estimate_gas(tx_for_estimate)
            
            # Add buffer
            safe_gas_limit = int(estimated_gas * 1.15)
            tx_build_params['gas'] = safe_gas_limit
            result['gas_estimate'] = estimated_gas

        except exceptions.ContractLogicError as e:
            result['error'] = f"Mint Simulation Reverted: {e}"
            return result
        except Exception as e:
            result['error'] = f"Gas Estimate Failed: {e}"
            return result

        if mode == 'simulate':
            result["success"] = True
            return result

        elif mode == 'send_raw':
            # Build Final Transaction
            final_tx = inp_position_manager_contract.functions.mint(params_mint).build_transaction(tx_build_params)

            # Sign
            signed_tx = w3_instance.eth.account.sign_transaction(final_tx, private_key)
            
            # Send
            mint_hash_bytes = w3_instance.eth.send_raw_transaction(signed_tx.raw_transaction)
            mint_hash_hex = w3_instance.to_hex(mint_hash_bytes)
            
            result["tx_hash"] = mint_hash_hex
            print(f"Mint Tx Sent: {mint_hash_hex}. Waiting for receipt...")

            # Wait for Receipt
            try:
                receipt = w3_instance.eth.wait_for_transaction_receipt(mint_hash_bytes, timeout=180)
                result["receipt"] = receipt

                if receipt['status'] == 1:
                    result["success"] = True
                else:
                    result["success"] = False
                    result["error"] = "Mint Transaction Reverted On-Chain (Status 0)"
            
            except Exception as e:
                result["success"] = False
                result["error"] = f"Tx sent but wait failed: {e}"

            return result

        else:
            result['error'] = "Invalid mode"
            return result

    except Exception as e:
        result['error'] = f"Unexpected Error: {e}"
        return result
#
def mint_liquidity_v3_nft2(
    token0_contract,
    token1_contract,
    position_manager_contract,
    fee: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    slippage: float = 0.05
) -> dict:

    if slippage <= 0 or slippage >= 1:
        slippage = 0.05

    amount0_min = int(amount0_desired * (1 - slippage))
    amount1_min = int(amount1_desired * (1 - slippage))

    pm_address = position_manager_contract.address
    nonce = w3.eth.get_transaction_count(wallet_address)

    results = []

    # --- gas params (EIP-1559) ---
    latest_block = w3.eth.get_block("latest")
    base_fee = latest_block["baseFeePerGas"]
    priority_fee = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")
    max_fee = base_fee + 2 * priority_fee

    def send_tx(tx):
        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hash_hex = w3.to_hex(tx_hash)

        receipt = None
        error = None
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        except Exception as e:
            error = str(e)

        return {
            "tx_hash": tx_hash_hex,
            "receipt": receipt,
            "logs": receipt.logs if receipt else [],
            "status": "success" if receipt and receipt.status == 1 else "reverted",
            "error": error
        }

    # --------------------------------------------------
    # Approve Token0 if needed
    # --------------------------------------------------
    allowance0 = token0_contract.functions.allowance(wallet_address, pm_address).call()
    if allowance0 < amount0_desired:
        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        estimation_failed = False
        try:
            tx_est = token0_contract.functions.approve(
                pm_address, 2**256 - 1
            ).build_transaction(tx_base)
            gas_est = w3.eth.estimate_gas(tx_est)
            tx_base["gas"] = int(gas_est * 1.1)
        except Exception:
            estimation_failed = True
            tx_base["gas"] = 80000

        tx_final = token0_contract.functions.approve(
            pm_address, 2**256 - 1
        ).build_transaction(tx_base)

        result = send_tx(tx_final)
        result["type"] = "approve_token0"
        result["estimation_failed"] = estimation_failed
        results.append(result)

        nonce += 1

    # --------------------------------------------------
    # Approve Token1 if needed
    # --------------------------------------------------
    allowance1 = token1_contract.functions.allowance(wallet_address, pm_address).call()
    if allowance1 < amount1_desired:
        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        estimation_failed = False
        try:
            tx_est = token1_contract.functions.approve(
                pm_address, 2**256 - 1
            ).build_transaction(tx_base)
            gas_est = w3.eth.estimate_gas(tx_est)
            tx_base["gas"] = int(gas_est * 1.1)
        except Exception:
            estimation_failed = True
            tx_base["gas"] = 80000

        tx_final = token1_contract.functions.approve(
            pm_address, 2**256 - 1
        ).build_transaction(tx_base)

        result = send_tx(tx_final)
        result["type"] = "approve_token1"
        result["estimation_failed"] = estimation_failed
        results.append(result)

        nonce += 1

    # --------------------------------------------------
    # Mint Position
    # --------------------------------------------------
    params = {
        "token0": token0_contract.address,
        "token1": token1_contract.address,
        "fee": fee,
        "tickLower": tick_lower,
        "tickUpper": tick_upper,
        "amount0Desired": amount0_desired,
        "amount1Desired": amount1_desired,
        "amount0Min": amount0_min,
        "amount1Min": amount1_min,
        "recipient": wallet_address,
        "deadline": int(time.time()) + 1200
    }

    tx_base = {
        "from": wallet_address,
        "nonce": nonce,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority_fee
    }

    estimation_failed = False
    estimation_error = None

    try:
        tx_est = position_manager_contract.functions.mint(
            params
        ).build_transaction(tx_base)
        gas_est = w3.eth.estimate_gas(tx_est)
        tx_base["gas"] = int(gas_est * 1.1)
    except Exception as e:
        estimation_failed = True
        estimation_error = str(e)
        tx_base["gas"] = 500_000

    tx_final = position_manager_contract.functions.mint(
        params
    ).build_transaction(tx_base)

    mint_result = send_tx(tx_final)
    mint_result["type"] = "mint"
    mint_result["estimation_failed"] = estimation_failed
    mint_result["estimation_error"] = estimation_error

    results.append(mint_result)

    return {
        "transactions": results,
        "final_tx_hash": mint_result["tx_hash"],
        "status": mint_result["status"]
    }
#
import time
from web3 import Web3
from web3.exceptions import ContractLogicError
#chatgpt
def mint_liquidity_v3_nft_safe(
    token0_contract,
    token1_contract,
    position_manager_contract,
    fee: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = "simulate",
    slippage: float = 0.05,
    gas_buffer: float = 1.15,
    fallback_gas_mint: int = 550_000,
    fallback_gas_approve: int = 90_000,
    receipt_timeout: int = 180
) -> dict:
    """
    Safe & deterministic Uniswap V3 mint with approval handling.
    Gas = max(estimate, fallback) * gas_buffer
    """

    result = {
        "success": False,
        "tx_hash": None,
        "receipt": None,
        "approve_txs": [],
        "gas_estimated": None,
        "gas_used": None,
        "error": None
    }

    try:
        # ---------------- Slippage ----------------
        if slippage <= 0 or slippage >= 1:
            slippage = 0.05

        amount0_min = int(amount0_desired * (1 - slippage))
        amount1_min = int(amount1_desired * (1 - slippage))

        pm_address = position_manager_contract.address

        # ---------------- Gas helpers ----------------
        def get_gas_params():
            block = w3.eth.get_block("latest")
            base_fee = block.get("baseFeePerGas", w3.eth.gas_price)
            priority_fee = (
                w3.eth.max_priority_fee
                if hasattr(w3.eth, "max_priority_fee") and w3.eth.max_priority_fee
                else w3.to_wei(1, "gwei")
            )
            return base_fee + 2 * priority_fee, priority_fee

        nonce = w3.eth.get_transaction_count(wallet_address)

        # ==================================================
        # Approvals (ONLY send_raw)
        # ==================================================
        if mode == "send_raw":

            def approve_if_needed(token_contract, amount_needed, label):
                nonlocal nonce

                allowance = token_contract.functions.allowance(
                    wallet_address, pm_address
                ).call()

                if allowance >= amount_needed:
                    return

                max_fee, priority_fee = get_gas_params()

                tx_base = {
                    "from": wallet_address,
                    "nonce": nonce,
                    "maxFeePerGas": max_fee,
                    "maxPriorityFeePerGas": priority_fee
                }

                try:
                    tx_est = token_contract.functions.approve(
                        pm_address, 2**256 - 1
                    ).build_transaction(tx_base)

                    gas_est = w3.eth.estimate_gas(tx_est)
                    gas_limit = max(gas_est, fallback_gas_approve)

                except Exception:
                    gas_limit = fallback_gas_approve

                tx_base["gas"] = int(gas_limit * gas_buffer)

                tx_final = token_contract.functions.approve(
                    pm_address, 2**256 - 1
                ).build_transaction(tx_base)

                signed = w3.eth.account.sign_transaction(tx_final, private_key)
                tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

                receipt = w3.eth.wait_for_transaction_receipt(
                    tx_hash, timeout=receipt_timeout
                )

                if receipt.status != 1:
                    raise Exception(f"{label} approve failed")

                result["approve_txs"].append({
                    "token": label,
                    "tx_hash": w3.to_hex(tx_hash),
                    "gas_used": receipt.gasUsed
                })

                nonce += 1

            approve_if_needed(token0_contract, amount0_desired, "token0")
            approve_if_needed(token1_contract, amount1_desired, "token1")

        # ==================================================
        # Mint params
        # ==================================================
        params = {
            "token0": token0_contract.address,
            "token1": token1_contract.address,
            "fee": fee,
            "tickLower": int(tick_lower),
            "tickUpper": int(tick_upper),
            "amount0Desired": int(amount0_desired),
            "amount1Desired": int(amount1_desired),
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "recipient": wallet_address,
            "deadline": int(time.time()) + 1200
        }

        max_fee, priority_fee = get_gas_params()

        tx_base = {
            "from": wallet_address,
            "nonce": nonce,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": priority_fee
        }

        # ==================================================
        # Gas estimation (dual-path)
        # ==================================================
        try:
            tx_est = position_manager_contract.functions.mint(
                params
            ).build_transaction(tx_base)

            gas_est = w3.eth.estimate_gas(tx_est)
            result["gas_estimated"] = gas_est

            gas_limit = max(gas_est, fallback_gas_mint)

        except ContractLogicError as e:
            result["error"] = f"Mint reverted in simulation: {e}"
            return result

        except Exception:
            gas_limit = fallback_gas_mint

        tx_base["gas"] = int(gas_limit * gas_buffer)

        if mode == "simulate":
            result["success"] = True
            return result

        if mode != "send_raw":
            result["error"] = "Invalid mode"
            return result

        # ==================================================
        # Send mint
        # ==================================================
        final_tx = position_manager_contract.functions.mint(
            params
        ).build_transaction(tx_base)

        signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=receipt_timeout
        )

        result["tx_hash"] = w3.to_hex(tx_hash)
        result["receipt"] = receipt
        result["gas_used"] = receipt.gasUsed

        if receipt.status == 1:
            result["success"] = True
        else:
            result["error"] = "Mint reverted on-chain"

        return result

    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        return result

#

#gemini pro
def mint_liquidity_v3_hybrid(
    token0_contract,
    token1_contract,
    inp_position_manager_contract,
    inp_fee: int,
    inp_tick_lower: int,
    inp_tick_upper: int,
    inp_amount0_desired: int,
    inp_amount1_desired: int,
    w3: Web3,
    wallet_address: str,
    private_key: str,
    mode: str = 'send_raw',  # 'simulate' or 'send_raw'
    slippage: float = 0.05,
    gas_multiplier: float = 1.2
) -> dict:
    """
    Mints a new Uniswap V3 position using a robust Hybrid Gas Strategy.
    
    Features:
    1. Checks Allowances and auto-approves tokens if necessary.
    2. Uses Max(Simulation, Fallback) * Multiplier for gas limits.
    3. Handles EIP-1559 fees automatically.
    """

    result = {
        "success": False,
        "mint_tx_hash": None,
        "approve_txs": [],  # List of dictionaries for approval txs
        "error": None,
        "logs": []
    }

    # Internal helper to execute transactions with the Hybrid Strategy
    def execute_tx_with_hybrid_gas(contract_func, fallback_gas_limit, description):
        tx_res = {"type": description, "hash": None, "status": "failed"}
        
        try:
            # 1. Prepare Fee Data
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block['baseFeePerGas']
            priority_fee = w3.eth.max_priority_fee or w3.to_wei(1.5, 'gwei')
            max_fee = base_fee + (2 * priority_fee)

            # 2. Prepare Base Transaction
            current_nonce = w3.eth.get_transaction_count(wallet_address)
            tx_base = {
                "from": wallet_address,
                "nonce": current_nonce,
                "maxFeePerGas": max_fee,
                "maxPriorityFeePerGas": priority_fee
            }

            # 3. Hybrid Estimation (Max Strategy)
            simulated_gas = 0
            try:
                # Attempt Simulation
                temp_tx = contract_func.build_transaction(tx_base)
                simulated_gas = w3.eth.estimate_gas(temp_tx)
            except Exception as e:
                print(f"Simulation failed for {description}: {e}. Using fallback.")
                simulated_gas = 0
            
            # Use the higher value to ensure execution, then apply multiplier
            base_limit = max(simulated_gas, fallback_gas_limit)
            final_gas_limit = int(base_limit * gas_multiplier)
            tx_base["gas"] = final_gas_limit

            if mode == 'simulate':
                tx_res["status"] = "simulated"
                tx_res["gas_limit"] = final_gas_limit
                return True, tx_res

            # 4. Build, Sign, Send
            final_tx = contract_func.build_transaction(tx_base)
            signed_tx = w3.eth.account.sign_transaction(final_tx, private_key)
            
            tx_hash_bytes = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            tx_hash_hex = w3.to_hex(tx_hash_bytes)
            tx_res["hash"] = tx_hash_hex

            print(f"Sent {description}: {tx_hash_hex}. Waiting for receipt...")

            # 5. Wait for Receipt
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash_bytes, timeout=180)
            if receipt['status'] == 1:
                tx_res["status"] = "success"
                return True, tx_res
            else:
                tx_res["status"] = "reverted"
                result["error"] = f"{description} reverted on-chain."
                return False, tx_res

        except Exception as e:
            tx_res["error"] = str(e)
            result["error"] = f"Error in {description}: {str(e)}"
            return False, tx_res

    try:
        wallet_address = w3.to_checksum_address(wallet_address)
        pm_address = inp_position_manager_contract.address

        # --------------------------------------------------
        # 1. Handle Approvals (Token 0)
        # --------------------------------------------------
        allowance0 = token0_contract.functions.allowance(wallet_address, pm_address).call()
        if allowance0 < inp_amount0_desired:
            print("Approving Token 0...")
            approve_func0 = token0_contract.functions.approve(pm_address, 2**256 - 1)
            # Fallback for Approve is low (~100k)
            success0, res0 = execute_tx_with_hybrid_gas(approve_func0, 100000, "Approve Token0")
            result["approve_txs"].append(res0)
            if not success0 or mode == 'simulate':
                if mode == 'simulate': pass # Continue simulation
                else: return result # Stop if approve failed

        # --------------------------------------------------
        # 2. Handle Approvals (Token 1)
        # --------------------------------------------------
        allowance1 = token1_contract.functions.allowance(wallet_address, pm_address).call()
        if allowance1 < inp_amount1_desired:
            print("Approving Token 1...")
            approve_func1 = token1_contract.functions.approve(pm_address, 2**256 - 1)
            success1, res1 = execute_tx_with_hybrid_gas(approve_func1, 100000, "Approve Token1")
            result["approve_txs"].append(res1)
            if not success1 or mode == 'simulate':
                if mode == 'simulate': pass
                else: return result

        # --------------------------------------------------
        # 3. Prepare Mint Parameters
        # --------------------------------------------------
        # Valid slippage check
        if slippage < 0 or slippage > 1: slippage = 0.05

        amount0_min = int(inp_amount0_desired * (1 - slippage))
        amount1_min = int(inp_amount1_desired * (1 - slippage))

        params_mint = {
            "token0": token0_contract.address,
            "token1": token1_contract.address,
            "fee": inp_fee,
            "tickLower": int(inp_tick_lower),
            "tickUpper": int(inp_tick_upper),
            "amount0Desired": int(inp_amount0_desired),
            "amount1Desired": int(inp_amount1_desired),
            "amount0Min": amount0_min,
            "amount1Min": amount1_min,
            "recipient": wallet_address,
            "deadline": int(time.time()) + 1200
        }

        # --------------------------------------------------
        # 4. Execute Mint
        # --------------------------------------------------
        print("Executing Mint...")
        mint_func = inp_position_manager_contract.functions.mint(params_mint)
        
        # Fallback for Mint is high (~600k) because it initializes storage slots
        success_mint, res_mint = execute_tx_with_hybrid_gas(mint_func, 600000, "Mint Liquidity")
        
        if mode == 'simulate':
            result["success"] = True
            result["gas_estimate_mint"] = res_mint.get("gas_limit", 0)
            return result

        result["mint_tx_hash"] = res_mint.get("hash")
        
        if success_mint:
            result["success"] = True
        
        return result

    except Exception as e:
        result["error"] = f"Critical Error: {str(e)}"
        return result
#
def factory_pool_address(w3_instance:Web3):
    v3factoryaddress="0x0227628f3F023bb0B980b67D528571c95c6DaC1c"
    factory_address = w3_instance.to_checksum_address(v3factoryaddress)
    factory_abi =fetch_abi_retry(factory_address,etherscan_apikey,CHAIN_ID)
    factory=w3_instance.eth.contract(address=factory_address, abi=factory_abi)
#
#
#
def fetch_implementation_address(contract_address: str, api_key: str, inp_chain_id: int):
    try:
        contract_address = Web3.to_checksum_address(contract_address)
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

            if implementation_address and implementation_address != '0x0000000000000000000000000000000000000000':
                return Web3.to_checksum_address(implementation_address)

    except Exception as e:
        print(f"Error checking implementation for {contract_address}: {e}")

    return None
#
def fetch_abi_retry(contract_address: str, api_key: str, inp_chain_id: int, retries=3):
    try:
        initial_address = Web3.to_checksum_address(contract_address)
    except ValueError:
        return None

    implementation_address = fetch_implementation_address(initial_address, api_key, inp_chain_id)

    addresses_to_check = []
    if implementation_address:
        addresses_to_check.append(implementation_address)
    addresses_to_check.append(initial_address)

    for current_addr in addresses_to_check:
        url = "https://api.etherscan.io/v2/api"
        params = {
            "module": "contract",
            "action": "getabi",
            "address": current_addr,
            "apikey": api_key,
            "chainid": inp_chain_id
        }

        for attempt in range(retries):
            try:
                resp = requests.get(url, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                if data.get("status") == "1":
                    print(f"Successfully fetched ABI from: {current_addr}")
                    return json.loads(data["result"])


            except requests.exceptions.RequestException as e:
                time.sleep(1)

        time.sleep(0.5)

    return None
#
def v3_nft_pos_id_info(inp_token_id,inp_position_manager_contract):
  pos = inp_position_manager_contract.functions.positions(inp_token_id).call()
  dct={'token_id':inp_token_id,'token0':pos[2],'token1':pos[3],'fee_tier':pos[4],'liquidity':pos[7],'tick_range':[pos[5],pos[6]],'fee0':pos[10],'fee1':pos[11]}
  return dct
#
#
def preview_mint_requirements(
        
    position_manager_contract,
    token0_addr: str,
    token1_addr: str,
    fee: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int,
    w3: Web3
) -> dict:
    """
    Previews the minting requirements for a Uniswap V3 position without executing a transaction.
    """
    try:
        params = {
            "token0": token0_addr,
            "token1": token1_addr,
            "fee": fee,
            "tickLower": tick_lower,
            "tickUpper": tick_upper,
            "amount0Desired": amount0_desired,
            "amount1Desired": amount1_desired,
            "amount0Min": 0,  #
            "amount1Min": 0,
            "recipient": "0x0000000000000000000000000000000000000000",  #
            "deadline": 2**256 - 1
        }
        
        # این فقط محاسبه می‌کنه، تراکنشی نمی‌فرسته
        liquidity, amount0_used, amount1_used = position_manager_contract.functions.mint(
            params
        ).call()
        
        return {
            "liquidity": liquidity,
            "amount0_used": amount0_used,
            "amount1_used": amount1_used,
            "amount0_remaining": amount0_desired - amount0_used,
            "amount1_remaining": amount1_desired - amount1_used,
            "exact_ratio": amount0_used / amount1_used if amount1_used > 0 else 0
        }
    except Exception as e:
        return {"error": str(e)}
#
#QUOTER_ADDRESS = "0x61fFE014bA17989E743c5F6cB21bF9697530B21e"  # Uniswap QuoterV2

#quoter_abi = '[...]'  # ABI quoter

def get_exact_mint_amounts(
    w3: Web3,
    qouter_address: str,
    token0: str,
    token1: str,
    fee: int,
    tick_lower: int,
    tick_upper: int,
    amount0_desired: int,
    amount1_desired: int
):
    quoter_abi = fetch_abi_retry(qouter_address, etherscan_apikey, CHAIN_ID)
    quoter = w3.eth.contract(address=qouter_address, abi=quoter_abi)
    
    # محاسبه دقیق
    amount0, amount1 = quoter.functions.mint(
        token0, token1, fee, tick_lower, tick_upper, amount0_desired, amount1_desired
    ).call()
    
    return amount0, amount1
#
#0x3344BBDCeb8f6fb52de759c127E4A44EFb40432A
'''params = {
    "token0": token0,
    "token1": token1,
    "fee": fee,
    "tickLower": tick_lower,
    "tickUpper": tick_upper,
    "amount0Desired": amount0_desired,
    "amount1Desired": amount1_desired,
    "amount0Min": 0,
    "amount1Min": 0,
    "recipient": wallet_address,
    "deadline": int(time.time()) + 60
}

result = nft_manager_contract.functions.mint(
    params
).call({"from": wallet_address})'''

