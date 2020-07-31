#!/usr/bin/env python3

import logging
import os

from itertools import product

import requests

from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import CommandHandler, Updater, InlineQueryHandler

logging.basicConfig(level=logging.DEBUG)

TG_TOKEN = os.environ["TG_TOKEN"]
MARKETS = [
    "btc_eur",
    "btc_usd",
    "btc_gbp",
    "xmr_btc",
]
DEFAULT_MARKETS = ["btc_eur", "btc_usd"]
OFFERS_URL = "https://markets.bisq.network/api/offers?market={}"
PRICE_URL = "https://api.coinbase.com/v2/prices/BTC-{}/spot"
POLINIEX_URL = "https://poloniex.com/public?command=returnTicker"
METHODS = {
    "NATIONAL_BANK": "National bank transfer",
    "SAME_BANK": "Transfer with same bank",
    "SPECIFIC_BANKS": "Transfers with specific banks",
    "US_POSTAL_MONEY_ORDER": "US Postal Money Order",
    "CASH_DEPOSIT": "Cash Deposit",
    "MONEY_GRAM": "MoneyGram",
    "WESTERN_UNION": "Western Union",
    "F2F": "Face to face (in person)",
    "JAPAN_BANK": "Japan Bank Furikomi",
    "NATIONAL_BANK_SHORT": "National banks",
    "SAME_BANK_SHORT": "Same bank",
    "SPECIFIC_BANKS_SHORT": "Specific banks",
    "US_POSTAL_MONEY_ORDER_SHORT": "US Money Order",
    "CASH_DEPOSIT_SHORT": "Cash Deposit",
    "MONEY_GRAM_SHORT": "MoneyGram",
    "WESTERN_UNION_SHORT": "Western Union",
    "F2F_SHORT": "F2F",
    "JAPAN_BANK_SHORT": "Japan Furikomi",
    "UPHOLD": "Uphold",
    "MONEY_BEAM": "MoneyBeam (N26)",
    "POPMONEY": "Popmoney",
    "REVOLUT": "Revolut",
    "PERFECT_MONEY": "Perfect Money",
    "ALI_PAY": "AliPay",
    "WECHAT_PAY": "WeChat Pay",
    "SEPA": "SEPA",
    "SEPA_INSTANT": "SEPA Instant Payments",
    "FASTER_PAYMENTS": "Faster Payments",
    "SWISH": "Swish",
    "CLEAR_X_CHANGE": "Zelle (ClearXchange)",
    "CHASE_QUICK_PAY": "Chase QuickPay",
    "INTERAC_E_TRANSFER": "Interac e-Transfer",
    "HAL_CASH": "HalCash",
    "BLOCK_CHAINS": "Altcoins",
    "PROMPT_PAY": "PromptPay",
    "ADVANCED_CASH": "Advanced Cash",
    "BLOCK_CHAINS_INSTANT": "Altcoins Instant",
    "OK_PAY": "OKPay",
    "CASH_APP": "Cash App",
    "VENMO": "Venmo",
    "UPHOLD_SHORT": "Uphold",
    "MONEY_BEAM_SHORT": "MoneyBeam (N26)",
    "POPMONEY_SHORT": "Popmoney",
    "REVOLUT_SHORT": "Revolut",
    "PERFECT_MONEY_SHORT": "Perfect Money",
    "ALI_PAY_SHORT": "AliPay",
    "WECHAT_PAY_SHORT": "WeChat Pay",
    "SEPA_SHORT": "SEPA",
    "SEPA_INSTANT_SHORT": "SEPA Instant",
    "FASTER_PAYMENTS_SHORT": "Faster Payments",
    "SWISH_SHORT": "Swish",
    "CLEAR_X_CHANGE_SHORT": "Zelle",
    "CHASE_QUICK_PAY_SHORT": "Chase QuickPay",
    "INTERAC_E_TRANSFER_SHORT": "Interac e-Transfer",
    "HAL_CASH_SHORT": "HalCash",
    "BLOCK_CHAINS_SHORT": "Altcoins",
    "PROMPT_PAY_SHORT": "PromptPay",
    "ADVANCED_CASH_SHORT": "Advanced Cash",
    "BLOCK_CHAINS_INSTANT_SHORT": "Altcoins Instant",
    "OK_PAY_SHORT": "OKPay",
    "CASH_APP_SHORT": "Cash App",
    "VENMO_SHORT": "Venmo",
}
PRECISION = {
    "eur": 2,
    "usd": 2,
    "gbp": 2,
    "btc": 4,
    "xmr": 4,
}

offers = {}
prices = {}


def update_market(market):
    global offers
    logging.debug(f"Downloading {market} market")
    r = requests.get(OFFERS_URL.format(market))
    offers[market] = r.json()[market]
    logging.debug(f"Downloaded {market} market")


def update_price(currency):
    global prices
    logging.debug(f"Updating Coinbase {currency} price")
    r = requests.get(PRICE_URL.format(currency.upper()))
    prices[f"btc_{currency}"] = float(r.json()["data"]["amount"])
    logging.debug(prices)


def update_prices_poliniex(filters):
    r = requests.get(POLINIEX_URL)
    for market, values in r.json().items():
        if market in filters:
            logging.debug(f"Updating Poliniex {market} price")
            idx = f"{market.lower().split('_')[1]}_{market.lower().split('_')[0]}"
            prices[idx] = (float(values["lowestAsk"]) + float(values["highestBid"])) / 2
    logging.debug(prices)


def is_prefix(chk, x):
    return x[: len(chk)] == chk


def capitalize(x):
    return x[0].upper() + x[1:].lower()


def no_btc(x):
    return x.lower().replace("btc", "").replace("_", "")

def prec(value, cur):
    return format(float(value), f"0.{PRECISION[cur]}f")

def query_title(offer, quote, base):
    return f"You can {offer['direction'].lower()} {prec(offer['amount'], quote)} {quote.upper()} for {prec(offer['volume'], base)} {base.upper()}"


def query_desc(offer, quote, base):
    above_below = "above" if float(offer["price"]) > prices[f"{quote}_{base}"] else "below"
    percent = abs(1 - float(offer["price"]) / prices[f"{quote}_{base}"])
    return f"Use {METHODS[offer['payment_method']]} to buy {float(offer['amount'])} for {float(offer['price'])} per {quote.upper()} ({percent:.2%} {above_below} market price)"


def query_msg(offer, quote, base):
    percent = abs(1 - prices[f"{quote}_{base}"] / float(offer["price"]))
    if offer["amount"] != offer["min_amount"]:
        quote_minmax = f"{prec(offer['min_amount'], quote)}-{prec(offer['amount'], quote)}"
        base_minmax = f"{prec(float(offer['min_amount'])*float(offer['price']), base)}-{prec(float(offer['amount'])*float(offer['price']), base)}"
    else:
        quote_minmax = f"{prec(offer['min_amount'], quote)}"
        base_minmax = f"{prec(float(offer['min_amount'])*float(offer['price']), base)}"
    short_id = offer["offer_id"].split("-")[0]
    return InputTextMessageContent(
        message_text=f"<b><a href=\"https://bisq.network\">Bisq</a> currently has an offer to {offer['direction'].lower()} "
        f"{prec(offer['amount'], quote)} {quote.upper()} for {prec(offer['volume'], base)} {base.upper()}</b>\n\n"
        f"Price in {base.upper()} for 1 {quote.upper()}: {prec(offer['price'], quote)} ({percent:+.2%} market)\n"
        f"{quote.upper()} (min-max): {quote_minmax}\n"
        f"{base.upper()} (min-max): {base_minmax}\n"
        f"Payment method: {METHODS[offer['payment_method']]}\n"
        f"ID: {short_id}",
        parse_mode="html",
        disable_web_page_preview=True,
    )


def overview(quote, base):
    market = f"{quote}_{base}"
    best_buy = offers[market]["buys"][1]
    buy_percent = abs(1 - prices[f"{quote}_{base}"] / float(best_buy["price"]))
    if buy_percent < -0.01:
        buy_prct = "<b>{:+.2%}</b>".format(buy_percent)
    else:
        buy_prct = "{:+.2%}".format(buy_percent)

    best_sell = offers[market]["sells"][1]
    sell_percent = abs(1 - prices[f"{quote}_{base}"] / float(best_sell["price"]))
    if sell_percent < -0.01:
        sell_prct = "<b>{:+.2%}</b>".format(sell_percent)
    else:
        sell_prct = "{:+.2%}".format(sell_percent)
    market_txt = market.replace("_", "/").upper()
    content = InputTextMessageContent(
        message_text=f"Offer size: <b>{prec(best_sell['volume'], base)} {base.upper()}</b> / {prec(best_sell['amount'], quote)} {quote.upper()}\n"
        f"Price: {prec(best_sell['price'], base)} ({sell_prct} market)\n\n"
        f"↑ Lowest ask / Spread: {1 - float(best_buy['price']) / float(best_sell['price']):.2%} / Highest bid ↓\n\n"
        f"Offer size: <b>{prec(best_buy['volume'], base)} {base.upper()}</b> / {prec(best_buy['amount'], quote)} {quote.upper()}\n"
        f"Price: {prec(best_buy['price'], base)} ({buy_prct} market)",
        parse_mode="html",
    )
    return InlineQueryResultArticle(
        id=f"overview{market} - {len(offers[market]["buys"])} bids / {len(offers[market]["sells"])} asks",
        title=f"{market_txt}",
        description=f"Overview of the {market_txt} Bisq market",
        input_message_content=content,
    )


def empty_query():
    return [overview("btc", "usd"), overview("btc", "eur"), overview("xmr", "btc")] + [
        InlineQueryResultArticle(
            id=offer["offer_id"][:64],
            title=query_title(offer, "btc", cur),
            description=query_desc(offer, "btc", cur),
            input_message_content=query_msg(offer, "btc", cur),
        )
        for cur, what in product(["usd", "eur"], ["buys", "sells"])
        for offer in offers[f"btc_{cur}"][what][:2]
    ]


def query(update, context):
    words = update.inline_query.query.split()
    markets = []
    filters = []
    answers = []
    for word in words:
        for cur, market in [
            ("usd", "btc_usd"),
            ("dollar", "btc_usd"),
            ("euro", "btc_eur"),
            ("gbp", "btc_gbp"),
            ("pound", "btc_gbp"),
            ("british", "btc_gbp"),
            ("xmr", "xmr_btc"),
            ("monero", "xmr_btc"),
        ]:
            if word.lower() in cur.lower():
                markets.append(market)
        if is_prefix(word.lower(), "buys"):
            filters.append("buys")
        if is_prefix(word.lower(), "sells"):
            filters.append("sells")
    if not markets and not filters:
        update.inline_query.answer(empty_query(), cache_time=60)
    if not filters:
        answers += [overview(market.split("_")[0], market.split("_")[1]) for market in markets]
        filters = ["buys", "sells"]
    if not markets:
        markets = DEFAULT_MARKETS
    markets = [(market.split("_")[0], market.split("_")[1]) for market in markets]
    answers += [
        InlineQueryResultArticle(
            id=offer["offer_id"][:64],
            title=query_title(offer, quote, base),
            description=query_desc(offer, quote, base),
            input_message_content=query_msg(offer, quote, base),
        )
        for (quote, base), what in product(markets, filters)
        for offer in offers[f"{quote}_{base}"][what][:10]
    ]
    update.inline_query.answer(answers, cache_time=60)


def start(update, context):
    update.message.reply_text(
        "You found the BisqBot! Currently I don't do anything in private chats, but"
        " feel free to try my inline mode in this chat.\n Just start by typing @BisqBot, then you can search for"
        " markets and offers with keywords like eur, usd, buy and sell."
    )


def update_all(*args):
    for market in MARKETS:
        update_market(market)
    for market in DEFAULT_MARKETS:
        update_price(market.replace("btc_", ""))
    update_prices_poliniex(["BTC_XMR"])


def main():
    update_all()
    updater = Updater(token=TG_TOKEN, use_context=True)
    job_queue = updater.job_queue
    job_queue.run_repeating(callback=update_all, interval=60)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(InlineQueryHandler(callback=query))
    dispatcher.add_handler(CommandHandler(callback=start, command="start"))
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
