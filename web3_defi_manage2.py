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

#
#
#
etherscan_apikey = "N68HP1FGB4UQQFBHZQUJIM12HVYWJME96M"
CHAIN_ID = 11155111  # Sepolia
#
#
def connect_to_chain(inp_private_key):
    RPC = "https://eth-sepolia.g.alchemy.com/v2/1d3m81eR2Kd2mrpuH6-bR"
    w3 = Web3(Web3.HTTPProvider(RPC))
    account = Account.from_key(inp_private_key)
    my_wallet_address = account.address
    if w3.is_connected():
        print(f"Connected to the network with address: {my_wallet_address}")
        return w3,my_wallet_address
    else:
        print("Failed to connect to the network")
        return None, None
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
#
def position_manager_contract(w3_instance:Web3,inp_position_manager_address):
  position_manager_address = w3_instance.to_checksum_address(inp_position_manager_address)
  position_manager_abi = fetch_abi_retry(position_manager_address,etherscan_apikey,CHAIN_ID)
  position_manager_contract = w3_instance.eth.contract(address=position_manager_address, abi=position_manager_abi)
  return position_manager_contract
#
#
def calculate_raw_price_from_sqrt_price(sqrt_price_raw: float) -> float:
    normalized_sqrt_price = sqrt_price_raw / (2 ** 96)
    raw_price_math = normalized_sqrt_price ** 2
    return raw_price_math
#
#
def calculate_price_from_sqrt_price(sqrt_price_raw: float, decimal_0: int, decimal_1: int) -> float:
    normalized_sqrt_price = sqrt_price_raw / (2 ** 96)
    raw_price_math = normalized_sqrt_price ** 2
    decimal_adjustment = decimal_0 - decimal_1
    final_price = raw_price_math * (10 ** decimal_adjustment)
    return final_price
#
#
def pool_current_info(inp_pool_contract):
  token0_address = inp_pool_contract.functions.token0().call()
  token1_address = inp_pool_contract.functions.token1().call()
  slot0 = inp_pool_contract.functions.slot0().call()
  liquidity = inp_pool_contract.functions.liquidity().call()
  fee = inp_pool_contract.functions.fee().call()
  tickspacing = inp_pool_contract.functions.tickSpacing().call()
  return {'token0_address':token0_address,'token1_address':token1_address,'sqrtprice':slot0[0],
          'current_tick':slot0[1],'liquidity':liquidity,'fee_tier':fee,'tick_spacing':tickspacing}
#
#
def check_token_raw_balance(w3_instance:Web3,token_list_address:list, inp_address):
  ERC20_ABI = [
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
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    }
]
  balances = []
  for token in token_list_address:
      contract = w3_instance.eth.contract(address=token, abi=ERC20_ABI)
      bal = contract.functions.balanceOf(inp_address).call()
      sym=contract.functions.symbol().call()
      balances.append({f'{sym}':{'address':token,'balance':bal}})
  eth_balance = w3_instance.eth.get_balance(inp_address)
  balances.append(["ETH", eth_balance])
  return balances
#
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
#
def calculate_raw_price_by_tick(tick):
    return 1.0001**tick
#
#
def calculate_price_by_tick(tick:int,decimal_0:int,decimal_1:int):
  return (10**(decimal_0-decimal_1))*calculate_raw_price_by_tick(tick)
#
#
#
#
def calculate_tick_by_human_price(price: float, decimal_0: int, decimal_1: int) -> int:
    if price <= 0:
        raise ValueError("Price must be greater than zero")
    decimal_factor = 10 ** (decimal_0 - decimal_1)
    val_to_log = math.log(price) - math.log(decimal_factor)
    tick_base = math.log(1.0001)
    tick = val_to_log / tick_base
    return int(round(tick))
#
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
        swap_action = f" {swap_amount_abs:.8f} sell token0 to buy token1"
    elif swap_diff_0 < 0:
        swap_action = f"{swap_amount_abs:.8f} sell token1 to buy token0"
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
#
def calculate_new_amount_token_mix(current_price: float, lowerprice: float, upperprice: float, liquidity: float):
    s = np.sqrt(current_price)
    su = np.sqrt(upperprice)
    sl = np.sqrt(lowerprice)

    amount_0 = 0.0
    amount_1 = 0.0

    if current_price < lowerprice:
        amount_0 = liquidity * ((1.0 / sl) - (1.0 / su))
        amount_1 = 0.0
    elif current_price > upperprice:
        amount_0 = 0.0
        amount_1 = liquidity * (su - sl)
    else:
        amount_0 = liquidity * ((1.0 / s) - (1.0 / su))
        amount_1 = liquidity * (s - sl)

    return amount_0, amount_1
#
#
def human_readable_amount_in_liquidity(current_price: float, lower: float, upper: float, liquidity: float,inp_decimal0,inp_deciaml1):
  amount_0,amount_1=calculate_new_amount_token_mix(current_price,lower,upper,liquidity)
  return amount_0/10**(inp_decimal0-inp_deciaml1),amount_1/10**(inp_deciaml1-inp_decimal0)
#
#
def final_true_amount_in_liquidity(current_price: float, lower: float, upper: float, liquidity: float,inp_decimal0,inp_deciaml1):
  amount_0,amount_1=calculate_new_amount_token_mix(current_price,lower,upper,liquidity)
  return amount_0*10**inp_deciaml1,amount_1*10**inp_decimal0
#
#
def get_pool_id(token0, token1, fee, tick_spacing, hook_address):
    "work for to get v4 then v3 pool id"
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
#
def get_pool_address_from_pool_id(pool_id, factory_address):
    factory_address = Web3.to_checksum_address(factory_address)
    encoded = encode(
        ['address', 'bytes32'],
        [factory_address, bytes.fromhex(pool_id[2:])]
    )
    pool_address = Web3.to_checksum_address(Web3.keccak(encoded)[12:].hex())
    return pool_address
#
#
def convert_fee_percentage_to_feetier(inp_fee_percentage):
  return int((inp_fee_percentage/100)*(10**6))
#
#
def calculate_tickspacing_by_feetier(inp_feetier):
  dct={10:1,500:10,3000:60,10000:200}
  return dct[inp_feetier]
#
#
def get_nearest_valid_tick(inp_current_tick, inp_tickspacing):
  return (inp_current_tick // inp_tickspacing) * inp_tickspacing
#
#
#
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
#
def get_deadline(ttl=1200):
    """Returns current timestamp + ttl (time to live in seconds)"""
    return int(time.time()) + ttl
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
    
#
#
def calculate_liquidity_from_amounts(current_sqrt_price: float, lower_sqrt_price: float, upper_sqrt_price: float, amount0: float, amount1: float) -> float:
    if current_sqrt_price <= lower_sqrt_price:
        liquidity = amount0 * (lower_sqrt_price * upper_sqrt_price) / (upper_sqrt_price - lower_sqrt_price)
    elif current_sqrt_price < upper_sqrt_price:
        liquidity0 = amount0 * (current_sqrt_price * upper_sqrt_price) / (upper_sqrt_price - current_sqrt_price)
        liquidity1 = amount1 / (current_sqrt_price - lower_sqrt_price)
        liquidity = min(liquidity0, liquidity1)
    else:
        liquidity = amount1 / (upper_sqrt_price - lower_sqrt_price)
    return liquidity
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

        time.sleep(2)

    return False
#
#
def nft_pos_id_info(inp_token_id,inp_position_manager_contract):
  pos = inp_position_manager_contract.functions.positions(inp_token_id).call()
  dct={'token_id':inp_token_id,'token0':pos[2],'token1':pos[3],'fee_tier':pos[4],'liquidity':pos[7],'tick_range':[pos[5],pos[6]],'fee0':pos[10],'fee1':pos[11]}
  return dct
#
#
def factory_pool_address(w3_instance:Web3,inp_token0,inp_token1,inp_fee,factory_address:str=None):
    factory_address = w3_instance.to_checksum_address("0x0227628f3F023bb0B980b67D528571c95c6DaC1c")
    factory_abi =fetch_abi_retry(factory_address,etherscan_apikey,CHAIN_ID)
    if factory_abi:
        pass
    else:
        factory_abi = [
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
    
    factory=w3_instance.eth.contract(address=factory_address, abi=factory_abi)
    factory_pool_address=factory.functions.getPool(inp_token0,inp_token1,inp_fee).call()
    return factory_pool_address
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
        
        # Call the mint function in read-only mode to preview amounts
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
#
'''chatgpt swap codes start'''
def get_recent_basefee_stats(w3: Web3, blocks: int = 5) -> dict:
    latest = w3.eth.block_number
    base_fees = []

    for i in range(blocks):
        blk = w3.eth.get_block(latest - i)
        if "baseFeePerGas" in blk:
            base_fees.append(blk["baseFeePerGas"])

    avg = sum(base_fees) // len(base_fees)
    max_fee = max(base_fees)

    return {
        "avg_base_fee": avg,
        "max_base_fee": max_fee
    }
#
#
def offchain_slipage_check(input_token_address,amount_input,inp_pool_contract,slipage:float=0.1):

    pool_info=pool_current_info(inp_pool_contract)
    lowertick=get_nearest_valid_tick(pool_info['current_tick'],pool_info['tick_spacing'])
    uppertick=lowertick+pool_info['tick_spacing']
    lp=calculate_raw_price_by_tick(lowertick)
    up=calculate_raw_price_by_tick(uppertick)
    cp=calculate_raw_price_from_sqrt_price(pool_info['sqrtprice'])
    am0,am1=calculate_new_amount_token_mix(cp,lp,up,pool_info['liquidity'])
    #P=am1/am0
    if input_token_address==pool_info['token0_address']:
        #P=(am0-amount_input)/am1
        P=am1/(am0-amount_input)
    elif input_token_address==pool_info['token1_address']:
        #P=am0/(am1-amount_input)
        P=(am1-amount_input)/am0
    else:
        return False
    #return (cp,P)
    price_impact=abs(cp-P)/cp
    if price_impact < slipage:
        return True
    else:
        return False

#
#

def check_oracle_slippage(
    w3: Web3,
    router_contract_address: str,
    router_abi: list,
    token0: str,
    token1: str,
    amount_in: int,
    fee: int,
    tick_spacing: int,
    hook_address: str,
    maximum_tick_divergence: int = 10,
    seconds_ago: int = 30
):
    """
    Checks oracle slippage for a given token swap path on Uniswap V3.
    """
    ZERO_ADDRESS ="0x0000000000000000000000000000000000000000"
    # 
    token0 = Web3.to_checksum_address(token0)
    token1 = Web3.to_checksum_address(token1)
    hook_address = Web3.to_checksum_address(
        hook_address if hook_address else ZERO_ADDRESS)

    contract_address = Web3.to_checksum_address(router_contract_address)

    #
    path_bytes = encode(
        ['address', 'address', 'uint24', 'int24', 'address'],
        [token0, token1, fee, tick_spacing, hook_address]
    )
    paths = [path_bytes]

    #
    amounts = [amount_in]

    #
    contract = w3.eth.contract(address=contract_address, abi=router_abi)

    #
    try:
        result = contract.functions.checkOracleSlippage(
            paths,
            amounts,
            maximum_tick_divergence,
            seconds_ago
        ).call()
        return result
    except Exception as e:
        print("Error calling checkOracleSlippage:", e)
        return None
    #


#
#
def simulate_swap_output(
    router_contract,
    params: dict,
    wallet: str
) -> int:
    try:
        amount_out = router_contract.functions.exactInputSingle(
            params
        ).call({"from": wallet})
        return amount_out
    except Exception as e:
        raise RuntimeError(f"Swap simulation failed: {e}")
#
#
def apply_slippage(amount_out: int, slippage_bps: int) -> int:
    return amount_out * (10_000 - slippage_bps) // 10_000
#
#
def simulate_gas(
    w3: Web3,
    tx_builder_fn,
    wallet: str,
    nonce: int
) -> int:
    tx = tx_builder_fn({
        "from": wallet,
        "nonce": nonce
    })
    return w3.eth.estimate_gas(tx)
#
#
def build_eip1559_gas_params(
    w3: Web3,
    buffer_multiplier: float = 1.15
) -> dict:
    stats = get_recent_basefee_stats(w3, blocks=5)
    priority = w3.eth.max_priority_fee or w3.to_wei(1, "gwei")

    max_fee = int(
        (stats["avg_base_fee"] + priority * 2) * buffer_multiplier
    )

    return {
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": priority
    }
#
#
def send_tx_with_fallback(
    w3: Web3,
    tx_builder_fn,
    wallet: str,
    private_key: str,
    nonce: int,
    gas_limit: int,
    mode="send"
) -> dict:

    # Primary strategy
    try:
        gas_params = build_eip1559_gas_params(w3)
        tx = tx_builder_fn({
            "from": wallet,
            "nonce": nonce,
            "gas": gas_limit,
            **gas_params
        })

        if mode == "simulate":
            return {"success": True, "used": "primary"}

        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        return {
            "success": receipt.status == 1,
            "tx_hash": w3.to_hex(tx_hash),
            "receipt": receipt,
            "nonce": nonce + 1
        }

    except Exception as primary_error:
        fallback_error = None

    # Fallback strategy
    try:
        latest = w3.eth.get_block("latest")
        base = latest["baseFeePerGas"]
        priority = w3.to_wei(2, "gwei")

        tx = tx_builder_fn({
            "from": wallet,
            "nonce": nonce,
            "gas": gas_limit,
            "maxFeePerGas": base * 2 + priority,
            "maxPriorityFeePerGas": priority
        })

        signed = w3.eth.account.sign_transaction(tx, private_key)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        return {
            "success": receipt.status == 1,
            "tx_hash": w3.to_hex(tx_hash),
            "receipt": receipt,
            "used": "fallback",
            "nonce": nonce + 1
        }

    except Exception as fallback_error:
        return {
            "success": False,
            "error": f"Primary: {primary_error} | Fallback: {fallback_error}",
            "nonce": nonce
        }
#
#
def swap_v3_safe(
    w3: Web3,
    router_contract,
    pool_info: dict,
    token_in: str,
    token_out: str,
    amount_in: int,
    slippage_bps: int,
    wallet: str,
    private_key: str,
    nonce: int,
    mode="send"
) -> dict:

    base_params = {
        "tokenIn": token_in,
        "tokenOut": token_out,
        "fee": pool_info["fee_tier"],
        "recipient": wallet,
        "amountIn": amount_in,
        "sqrtPriceLimitX96": 0
    }

    # 1. Output simulation
    quoted_out = simulate_swap_output(
        router_contract,
        {**base_params, "amountOutMinimum": 0},
        wallet
    )

    # 2. Slippage
    min_out = apply_slippage(quoted_out, slippage_bps)

    final_params = {
        **base_params,
        "amountOutMinimum": min_out
    }

    def build_tx(gas_params):
        return router_contract.functions.exactInputSingle(
            final_params
        ).build_transaction(gas_params)

    # 3. Gas simulation
    gas_est = simulate_gas(w3, build_tx, wallet, nonce)
    gas_limit = int(gas_est * 1.2)

    # 4. Send
    return send_tx_with_fallback(
        w3,
        build_tx,
        wallet,
        private_key,
        nonce,
        gas_limit,
        mode
    )
#
#
'''chatgpt swap codes end'''
#
#

#
#
'''def build_transaction_by_smart_gas(w3, contract_function, params, my_address):
    """
    Builds a transaction by auto-detecting gas mechanism (EIP-1559 vs Legacy)
    and uses simulation (estimate_gas) to set accurate gas limits.
    """
    # 1. Fetch basic network data
    nonce = w3.eth.get_transaction_count(my_address)
    latest_block = w3.eth.get_block('latest')
    supports_eip1559 = 'baseFeePerGas' in latest_block
    chain_id = w3.eth.chain_id

    # 2. Simulate transaction to get precise Gas Limit
    try:
        # We simulate the call to see how much gas it actually consumes
        gas_estimate = contract_function(params).estimate_gas({'from': my_address})
        
        # Add a 10-20% buffer to account for state changes between simulation and inclusion
        gas_limit = int(gas_estimate * 1.15)
    except Exception as e:
        # If simulation fails, the swap would likely fail on-chain (e.g., price impact or balance)
        print(f"Transaction Simulation Failed: {e}")
        return None

    # 3. Construct the base transaction object
    base_tx = {
        'from': my_address,
        'gas': gas_limit,
        'nonce': nonce,
        'chainId': chain_id
    }

    # 4. Handle Gas Pricing based on network capability
    if supports_eip1559:
        # Modern EIP-1559 logic
        fee_data = w3.eth.fee_data()
        base_fee = latest_block['baseFeePerGas']
        
        # Priority fee (tip) to incentivize miners
        priority_fee = fee_data.max_priority_fee_per_gas or w3.to_wei(1.5, 'gwei')
        
        # Max fee = (2 * Base Fee) + Priority Fee
        max_fee = (base_fee * 2) + priority_fee
        
        base_tx.update({
            'maxFeePerGas': max_fee,
            'maxPriorityFeePerGas': priority_fee
        })
    else:
        # Standard Legacy logic (for BSC or older chains)
        # Here we use the simulated gas_limit combined with current market gasPrice
        base_tx.update({
            'gasPrice': w3.eth.gas_price
        })

    # 5. Build and return the final transaction hex
    return contract_function(params).build_transaction(base_tx)'''
#
#
'''def build_transaction_by_smart_gas(w3, contract_function, params, my_address):
    """
    Builds a transaction with automatic gas estimation and
    EIP-1559 / legacy compatibility (Web3.py safe).
    """

    # 1. Basic network info
    nonce = w3.eth.get_transaction_count(my_address)
    latest_block = w3.eth.get_block('latest')
    chain_id = w3.eth.chain_id

    supports_eip1559 = 'baseFeePerGas' in latest_block

    # 2. Gas estimation (simulation)
    try:
        gas_estimate = contract_function(params).estimate_gas({
            'from': my_address
        })
        gas_limit = int(gas_estimate * 1.15)
    except Exception as e:
        print(f"Transaction Simulation Failed: {e}")
        return None

    base_tx = {
        'from': my_address,
        'nonce': nonce,
        'gas': gas_limit,
        'chainId': chain_id
    }

    # 3. Gas pricing
    if supports_eip1559:
        base_fee = latest_block['baseFeePerGas']

        # Web3.py compatibility: max_priority_fee may or may not exist
        try:
            priority_fee = w3.eth.max_priority_fee
        except Exception:
            priority_fee = w3.to_wei(1.5, 'gwei')

        max_fee = (base_fee * 2) + priority_fee

        base_tx.update({
            'maxFeePerGas': int(max_fee),
            'maxPriorityFeePerGas': int(priority_fee)
        })

    else:
        # Legacy gas pricing
        base_tx.update({
            'gasPrice': w3.eth.gas_price
        })

    # 4. Build transaction
    return contract_function(params).build_transaction(base_tx)'''
#
#
def build_transaction_by_smart_gas(w3, contract_function, params, my_address):
    nonce = w3.eth.get_transaction_count(my_address)
    latest_block = w3.eth.get_block('latest')
    chain_id = w3.eth.chain_id

    supports_eip1559 = 'baseFeePerGas' in latest_block

    try:
        gas_estimate = contract_function.estimate_gas({
            'from': my_address
        })
        gas_limit = int(gas_estimate * 1.15)
    except Exception as e:
        print(f"Transaction Simulation Failed: {e}")
        return None

    tx = {
        'from': my_address,
        'nonce': nonce,
        'gas': gas_limit,
        'chainId': chain_id
    }

    if supports_eip1559:
        base_fee = latest_block['baseFeePerGas']
        try:
            priority_fee = w3.eth.max_priority_fee
        except Exception:
            priority_fee = w3.to_wei(1.5, 'gwei')

        tx.update({
            'maxFeePerGas': int(base_fee * 2 + priority_fee),
            'maxPriorityFeePerGas': int(priority_fee)
        })
    else:
        tx['gasPrice'] = w3.eth.gas_price

    return contract_function.build_transaction(tx)

#
#
'''def handle_approve(w3_instance, inp_token_contract, inp_my_address, inp_router_address, inp_amount_in, private_key):
    """Approves the router to spend the specified amount of tokens."""
    allowance = inp_token_contract.functions.allowance(inp_my_address, inp_router_address).call()
    
    if allowance >= inp_amount_in:
        print("Token already approved.")
        return True  # یا یک مقدار ثابت مثل "approved_already"

    print("Approving token...")
    try:
        #
        approve_tx = build_transaction_by_smart_gas(
            w3_instance,
            inp_token_contract.functions.approve,
            {'guy':inp_router_address,'wad':inp_amount_in},
            #(inp_router_address, inp_amount_in),
            inp_my_address
        )
    except Exception as e:
        print(f"Smart gas build failed, falling back: {e}")
        # روش پشتیبان
        approve_tx = inp_token_contract.functions.approve(
            inp_router_address, inp_amount_in
        ).build_transaction({
            'from': inp_my_address,
            'nonce': w3_instance.eth.get_transaction_count(inp_my_address),
            'gasPrice': w3_instance.eth.gas_price,
            'gas': 100000 
        })

    signed_approve = w3_instance.eth.account.sign_transaction(approve_tx, private_key)
    tx_hash = w3_instance.eth.send_raw_transaction(signed_approve.raw_transaction)
    receipt = w3_instance.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    
    # اختیاری: بررسی موفقیت تراکنش
    if receipt.status != 1:
        raise Exception("Approval transaction failed!")

    tx_hex = w3_instance.to_hex(tx_hash)
    print(f"Approved! TX: {tx_hex}")
    return tx_hex'''
#
#

#
#
def handle_approve(
    w3,
    token_contract,
    owner_address,
    spender_address,
    amount,
    private_key
):
    """
    Ensures ERC20 allowance is sufficient.
    Sends approve tx ONLY if needed.
    Returns tx_hash or None if already approved.
    """

    allowance = token_contract.functions.allowance(
        owner_address, spender_address
    ).call()

    if allowance >= amount:
        print("Token already approved.")
        return True  # ← بسیار مهم

    print("Approving token...")

    # درست: پاس دادن پارامترها به صورت positional
    approve_fn = token_contract.functions.approve(
        spender_address,
        int(amount)
    )

    approve_tx = build_transaction_by_smart_gas(
        w3,
        approve_fn,
        None,               # پارامتر لازم نیست
        owner_address
    )

    if approve_tx is None:
        raise Exception("Failed to build approve transaction")

    signed = w3.eth.account.sign_transaction(
        approve_tx, private_key
    )

    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt.status != 1:
        raise Exception("Approval transaction failed")

    tx_hex = w3.to_hex(tx_hash)
    print(f"Approved! TX: {tx_hex}")
    return tx_hex

#
#

router_address = '0x3bFA4769FB09eefC5a80d6E87c3B9C650f7Ae48E'

def swap_raw_v3_single(w3_instance, token_in, token_out, raw_amount_in, pool_fee, private_key,inp_router_address ,nonce,slipage:float=0.01 ,mode="send"):
    """
    Performs a single-hop swap on Uniswap V3 using the ExactInputSingle method by raw amount.
    """
    raw_amount_in=int(raw_amount_in)
    token_in = w3_instance.to_checksum_address(token_in)
    V3_ROUTER_ABI=fetch_abi_retry(router_address,etherscan_apikey,w3_instance.eth.chain_id)
    if V3_ROUTER_ABI == False:
        V3_ROUTER_ABI = V3_ROUTER_ABI_FALLBACK
    ERC20_ABI = fetch_abi_retry(token_in,etherscan_apikey,w3_instance.eth.chain_id)
    if ERC20_ABI == False:
        ERC20_ABI = ERC20_ABI_FALLBACK
    
    account = w3_instance.eth.account.from_key(private_key)
    my_address = account.address

    token_out = w3_instance.to_checksum_address(token_out)

    #amount_in = w3_instance.eth.to_wei(amount_in, 'ether')
    inp_router_address = w3_instance.to_checksum_address(inp_router_address)
    token_contract = w3_instance.eth.contract(address=token_in, abi=ERC20_ABI)
    #
    #
    tx_hash = None
    for attempt in range(3):
        print(f"Attempt {attempt + 1} to approve...")
        tx_hash = handle_approve(
            w3_instance,
            token_contract,
            my_address,
            inp_router_address,
            raw_amount_in,
            private_key)
    
    #
        if tx_hash:
            print("No approval needed.")
            break

        try:
            receipt = w3_instance.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            if receipt.status == 1:
                print("Approval confirmed!")
                break
            else:
                print("Approval transaction reverted. Retrying...")
                time.sleep(10)
        except Exception as e:
            print(f"Error waiting for receipt: {e}")
            time.sleep(10)
    else:
        raise Exception("Failed to approve after 3 attempts")
    
    # swap params
    router_contract = w3_instance.eth.contract(address=inp_router_address, abi=V3_ROUTER_ABI)

    params = {
        "tokenIn": token_in,
        "tokenOut": token_out,
        "fee": pool_fee,
        "recipient": my_address,
        #"deadline": int(time.time()) + 600,
        "amountIn": raw_amount_in,
        "amountOutMinimum": 0, # 
        "sqrtPriceLimitX96": 0 #
    }
    #
    pool_address=factory_pool_address(w3_instance,token_in,token_out,pool_fee)
    pool_contract_abi=fetch_abi_retry(pool_address,etherscan_apikey,CHAIN_ID)
    pool_contract=w3_instance.eth.contract(address=pool_address,abi=pool_contract_abi)
    pool_info=pool_current_info(pool_contract)
    cp=calculate_raw_price_by_tick(pool_info['current_tick'])
    if pool_info['token0_address']==token_in and pool_info['token1_address']==token_out:
        amount_out_min=raw_amount_in*cp
    else:
        amount_out_min=raw_amount_in/cp
    #
    try:
        # 
        predicted_output = router_contract.functions.exactInputSingle(params).call({
        'from': my_address})
        print(f"Predicted Output: {predicted_output}")
    except Exception as e:
        print(f"Simulation failed: {e}")
    # 
    if predicted_output != 0:
        of_sl=offchain_slipage_check(token_in,raw_amount_in,pool_contract,slipage=0.12)
        
        if of_sl ==False:
            print("High slippage detected, aborting swap in offchain.")
            #return None
        if (predicted_output/amount_out_min)<(1-slipage):
            print("High slippage detected, aborting swap in onchain.")
            return None
         #
        params.update({
            "amountOutMinimum": int(predicted_output * (1 - slipage))})

    swap_fn = router_contract.functions.exactInputSingle(params)

    swap_tx = build_transaction_by_smart_gas(
            w3_instance,
            swap_fn,
            None,
            my_address)
    
    if swap_tx is None:
            print("Swap transaction build failed.")
            return None

    print("Executing V3 Swap...")

    signed_swap = w3_instance.eth.account.sign_transaction(
        swap_tx,
        private_key)

    tx_hash = w3_instance.eth.send_raw_transaction(
    signed_swap.raw_transaction
)

    return w3_instance.to_hex(tx_hash)


#
#
#
ERC20_ABI_FALLBACK = [
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
NFPM_ABI_FALLBACK = [
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
V3_POOL_ABI_FALLBACK = [
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
V4_POOL_ABI_FALLBACK = [
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
V3_ROUTER_ABI_FALLBACK = [
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