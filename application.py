#!/usr/bin/env python3
import asyncio
from datetime import datetime
import sys
import pandas as pd
import numpy as np
import boto3
from decimal import Decimal
from dateutil.relativedelta import relativedelta
from cbpro import PublicClient
import math
import time
import matplotlib.pyplot as plt
from copra.websocket import Channel, Client
from copra.rest import Client as CopraClient


def flatten(l): return [item for sublist in l for item in sublist]


def plot_multi(data, cols=None, spacing=.1, **kwargs):

    from pandas import plotting

    # Get default color style from pandas - can be changed to any other color list
    if cols is None:
        cols = data.columns
    if len(cols) == 0:
        return
    colors = getattr(getattr(plotting, '_matplotlib').style,
                     '_get_standard_colors')(num_colors=len(cols))

    # First axis
    ax = data.loc[:, cols[0]].plot(label=cols[0], color=colors[0], **kwargs)
    ax.set_ylabel(ylabel=cols[0])
    lines, labels = ax.get_legend_handles_labels()

    for n in range(1, len(cols)):
        # If you need multiple y-axes
        # ax_new = ax.twinx()
        # ax.spines['right'].set_position(('axes', 1 + spacing * (n - 1)))

        # Plot using the existing y-axis
        data.loc[:, cols[n]].plot(
            ax=ax, label=cols[n], color=colors[n % len(colors)])
        ax.set_ylabel(ylabel=cols[n])

        # Proper legend position
        line, label = ax.get_legend_handles_labels()
        lines += line
        labels += label

    ax.legend(lines, labels, loc=0)
    return ax


class Data:
    def __init__(self, n):
        self.public_client = PublicClient()
        self.end_time = datetime.now()
        self.increment = relativedelta(minutes=200)
        self.start_time = self.end_time - self.increment
        self.period = n
        self.runs = 2 * int(math.ceil(n / 200))

    def get_data(self):
        data = []
        while self.runs > 0:
            response = self.public_client.get_product_historic_rates(
                'BTC-USD', start=self.start_time, end=(self.end_time), granularity=60)
            if 'message' in response:
                self.runs += 1
                time.sleep(0.5)
            else:
                data.append(response)
                self.start_time -= self.increment
                self.end_time -= self.increment
                self.runs -= 1
                time.sleep(0.5)
        return (flatten(data))

    def get_ewm(self):
        data = self.get_data()
        labels = ['timestamp', 'low', 'high', 'open', 'close', 'volume']
        df = pd.DataFrame.from_records(data, columns=labels)
        df = df.set_index('timestamp')
        df = df.sort_index(ascending=True)
        df['ewm'] = df['close'].ewm(
            span=self.period, min_periods=0, adjust=False, ignore_na=False).mean()
        # plt.figure()
        # df.plot()
        # plot_multi(df, cols=["close", "ewm"])
        return df['ewm'].iloc[-1]


class EWM:
    def __init__(self, average, period):
        self.average = average
        self.period = period
        self.multiplier = 2.0 / float(1.0 + period)

    def next(self, value):
        self.average = ((value - self.average) *
                        self.multiplier) + self.average

    def get(self):
        return self.average


class Tick:
    def __init__(self, tick_dict, ewm):
        self.sequence = tick_dict['sequence']
        self.product_id = tick_dict['product_id']
        self.best_bid = float(tick_dict['best_bid'])
        self.best_ask = float(tick_dict['best_ask'])
        self.price = float(tick_dict['price'])
        self.side = tick_dict['side']
        self.size = float(tick_dict['last_size'])
        self.time = datetime.strptime(
            tick_dict['time'], '%Y-%m-%dT%H:%M:%S.%fZ')
        self.ewm = ewm

    def get_price(self):
        return self.price

    @property
    def spread(self):
        return self.best_ask - self.best_bid

    def __repr__(self):
        rep = "{}\t\t\t\t {}\n".format(self.product_id, self.time)
        rep += "======================================================================================\n"
        rep += "Price: ${:.2f}\t\tSize: {:.8f}\tSide: {: >5}\tewm: {: >5}\n".format(
            self.price, self.size, self.side, self.ewm)
        rep += "Best ask: ${:.2f}\tBest bid: ${:.2f}\tSpread: ${:.2f}\tSequence: {}\n".format(
            self.best_ask, self.best_bid, self.spread, self.sequence)
        rep += "======================================================================================\n"
        return rep


class Ticker(Client):
    def __init__(self, ewm, loop, channels):
        super().__init__(loop=loop, channels=channels)
        self.ewm = ewm

    def on_message(self, message):
        if message['type'] == 'ticker' and 'time' in message:
            average = self.ewm.get()
            tick = Tick(message, average)
            price = tick.get_price()
            self.ewm.next(price)
            print(tick, "\n\n")
        if message['type'] == 'heartbeat':
            print(message)
        if message['type'] == 'level1':
            print(message)


class Trade:
    def __init__(self, bids, asks, ewm):
        self.bids = bids
        self.asks = asks
        self.ewm = ewm


"""
    def should_buy():
        if price < ewm & (price / ewm) < pct:
            return True
        else:
            return False

    def should_sell():
        if price > ewm & (price / ewm) > pct:
            return True
        else:
            return False
            """


period = 200
data = Data(period)
starter = data.get_ewm()
average = EWM(starter, period)

#plt.show()

"""

loop = asyncio.get_event_loop()
channels = Channel('heartbeat', 'BTC-USD')
ticker = Ticker(ewm=average, loop=loop, channels=channels)

"""
loop2 = asyncio.get_event_loop()

client = CopraClient(loop2)

async def get_order_book():
    book = await client.order_book(product_id='BTC-USD', level=1)
    book['time'] = datetime.now().isoformat()
    print(book)
    


while True:
    starttime=time.time()
    loop2.run_until_complete(get_order_book())
    time.sleep(1.0 - ((time.time() - starttime) % 1.0))


loop2.run_until_complete(get_order_book())


try:
    loop.run_forever()
except KeyboardInterrupt:
    loop.run_until_complete(ticker.close())
    loop.close()
