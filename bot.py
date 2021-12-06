import websocket, json, pprint, talib, numpy
import config
from binance.client import Client
from binance.enums import *

import talib as ta
import math

obj = {}
closes = []
openOrder = ["ETHEUR"] # placeholder to avoid a starting bug
in_position = False

client = Client(config.API_KEY, config.API_SECRET)

############
# Put every asset in a list (text file) 
############

i_run_once_has_been_run = False
def i_run_once():
    global i_run_once_has_been_run

    if i_run_once_has_been_run:
        return
    ###
    global obj
    exchangeInfo = client.get_exchange_info()
    totalSymbols = exchangeInfo["symbols"]

    txt_file = open("assets.txt", "w+")
    txt_file.truncate(0)
    for symbol in totalSymbols:
        s0 = symbol
        st = symbol["symbol"]
        if st.endswith(config.QUOTE_ASSET):
            stt = st.lower()
            obj[str(st)] = []
            sttt = stt + "@kline_" + str(config.TIMING)
            txt_file.write(sttt + "\n")
    txt_file.close()

    txt1_file = open("stepSize.txt", "w+")
    txt1_file.truncate(0)
    for symbol in totalSymbols:
        s01 = symbol
        st1 = symbol["symbol"]
        sz1 = symbol["filters"][2]["stepSize"]
        tt1 = st1 + ": " + sz1
        txt1_file.write(tt1 + "\n")
    txt1_file.close()
    ###
    i_run_once_has_been_run = True
i_run_once()

###########################
# stepSize calculation
###########################

def stepSizer(sy):
    with open("stepSize.txt") as f:
        for num, line in enumerate(f, 1):
            if sy in line:
                lineDect = line
                lineDetected = lineDect.replace("\n", "")
                stepSize_raw = lineDetected.partition(": ")[2]

                stepSize_raw_position = stepSize_raw.find("1")
                stepSize_pre_raw = stepSize_raw.partition(".")[2]
                stepSize_pre_raw_raw = stepSize_pre_raw.partition("1")[0]
                if stepSize_raw_position == 0:
                    noDec = True
                    return 0 
                else:
                    noDec = False
                    return stepSize_pre_raw_raw.count("0") + 1

###########################
# Truncate decimals
###########################
def truncate(f, n):
    return math.floor(f * 10 ** n) / 10 ** n

###########################

assets = []
with open("assets.txt") as file:
    for asset in file: 
        asset = asset.strip() 
        assets.append(asset) 

socketJoin = '/'.join(assets)
SOCKET = "wss://stream.binance.com:9443/ws/" + str(socketJoin)

###########################

def order(side, quantity, symbol,order_type=ORDER_TYPE_MARKET):
    global in_position

    try:
        buy_order = client.create_order(symbol=symbol, side=side, type=order_type, quantity=quantity)
        bo = buy_order["fills"][0]["price"]
        print("buy")
        
    except Exception as e:
        print("buy: an exception occured - {}".format(e))
        return False

###########################
# Take profit and stop loss calculation
###########################

    symbols = client.get_all_tickers()
    for each in symbols:
        if each["symbol"] == str(symbol):
            currentPrice = each["price"]
    
    minPrice_symbol = int(len(str(str(client.get_symbol_info(str(symbol))["filters"][0]["minPrice"]).split(".")[1]).split("1")[0])) + 1
    lenDec = len(str(currentPrice).split(".")[1])

    pt = float(currentPrice) + ((float(currentPrice) * config.TAKE_PROFIT) / 100) 
    price_take = round(float(pt), int(minPrice_symbol))

    pss = float(currentPrice) - ((float(currentPrice) * (config.STOP_LOSS - (config.STOP_LOSS / 2))) / 100)  
    price_semi_stop = round(float(pss), int(minPrice_symbol))

    ps = float(currentPrice) - ((float(currentPrice) * config.STOP_LOSS) / 100) 
    price_stop = round(float(ps), int(minPrice_symbol))

    qq = float(quantity) - ((float(quantity) * config.FEE) / 100) 
    quantity_q = truncate(float(qq), stepSizer(str(symbol)))

###########################

    openOrder.append(str(symbol))

    try: 
        sell_order= client.order_oco_sell(
            symbol= symbol,                                            
            quantity= quantity_q,                                            
            price= price_take,                                            
            stopPrice= price_semi_stop,                                            
            stopLimitPrice= price_stop,                                            
            stopLimitTimeInForce= 'GTC')
        so_sl = sell_order["orderReports"][0]["price"]
        so_tk = sell_order["orderReports"][1]["price"]
        print("sell")

    except Exception as er: 
        print("sell: an exception occured - {}".format(er))
        return False
    return True

###########################

def on_open(ws):
    print('opened connection')

def on_close(ws):
    print('closed connection')

###########################

def on_message(ws, message):
    global closes, in_position, obj

    json_message = json.loads(message)
    TRADE_SYMBOL = json_message["s"].strip('\'')

    candle = json_message['k']

    is_candle_closed = candle['x']
    close = candle['c']

    if is_candle_closed:
        obj[str(TRADE_SYMBOL)].append(float(close))

        if len(obj[str(TRADE_SYMBOL)]) > config.EMA_SLOW_PERIOD:
            np_closes = numpy.array(obj[str(TRADE_SYMBOL)]) 
              
            ema_slow = talib.EMA(np_closes, config.EMA_SLOW_PERIOD)
            ema_fast = talib.EMA(np_closes, config.EMA_FAST_PERIOD)

            last_ema_slow = ema_slow[-1]
            last_ema_fast = ema_fast[-1]

            previous_slow = ema_slow[-2]
            previous_fast = ema_fast[-2]

            crossing_up = ((last_ema_fast >= last_ema_slow) & (previous_fast <= previous_slow))
            crossing_down = ((last_ema_fast <= last_ema_slow) & (previous_fast >= previous_slow))  

            inverted_np_closes = 1 / np_closes[-1]
            TRADE_DEF_QUANTITY = config.TRADE_QUANTITY * inverted_np_closes

            TRADE_DEFINITIVE_QUANTITY = truncate(float(TRADE_DEF_QUANTITY), stepSizer(str(TRADE_SYMBOL)))     
            
            if crossing_up:
                if TRADE_SYMBOL not in config.BLACK_LIST:
                    if "DOWN" or "UP" not in str(TRADE_SYMBOL): # remove leveraged assets
                        if not client.get_open_orders(symbol=str(openOrder[-1])):
                            print(TRADE_SYMBOL)
                            order_succeeded = order(SIDE_BUY, TRADE_DEFINITIVE_QUANTITY, TRADE_SYMBOL) 
                                       
ws = websocket.WebSocketApp(SOCKET, on_open=on_open, on_close=on_close, on_message=on_message)
ws.run_forever() 
