#!/usr/bin/env python3

import json
import logging
import os
import time

from datetime import date
from functools import reduce
from itertools import product

import redis
import requests

from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ChosenInlineResultHandler, CommandHandler, MessageHandler, Updater, InlineQueryHandler
from telegram.ext.filters import Filters

logging.basicConfig(level=logging.DEBUG)
red = redis.StrictRedis()

TG_TOKEN = os.environ["TG_TOKEN"]
STATE_DIRECTORY = os.getenv("STATE_DIRECTORY", os.getcwd())
chosenquerylog = open(os.path.join(STATE_DIRECTORY, "chosen_query.ndjson"), "a")
MARKETS = [
    "btc_eur",
    "btc_usd",
    "btc_gbp",
    "xmr_btc",
    "bsq_btc",
    "btc_brl",
    "btc_cad",
]
COINBASE_MARKETS = []
KRAKEN_MARKETS = ["btc_eur", "btc_usd", "btc_gbp", "btc_cad", "xmr_btc"]
OFFERS_URL = "https://markets.bisq.network/api/offers?market={}"
KRAKEN_URL = "https://api.kraken.com/0/public/Ticker?pair={}"
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
    "bsq": 2,
    "brl": 2,
    "cad": 2,
}
ICONS = {
    "buy": "https://raw.githubusercontent.com/pingiun/BisqBot/1124f373edacf0da1c4cd20b5cc7fbb2cf6f2e95/buy_icon.png",
    "sell": "https://raw.githubusercontent.com/pingiun/BisqBot/1124f373edacf0da1c4cd20b5cc7fbb2cf6f2e95/sell_icon.png",
}

offers = {}
prices = {}
updater = None


def update_market(market):
    global offers
    logging.debug(f"Downloading {market} market")
    r = requests.get(OFFERS_URL.format(market))
    offers[market] = r.json()[market]
    logging.debug(f"Downloaded {market} market")


def update_prices_kraken(markets):
    repls = {"btc": "xxbt", "xmr": "xxmr", "eur": "zeur", "usd": "zusd", "cad": "zcad", "gbp": "zgbp", "_": ""}
    kraken_map = {market: reduce(lambda a, kv: a.replace(*kv), repls.items(), market).upper() for market in markets}
    try:
        r = requests.get(KRAKEN_URL.format(",".join(kraken_map.values())))
        data = r.json()
        for market, kraken_market in kraken_map.items():
            prices[market] = (float(data['result'][kraken_market]["b"][0]) + float(data['result'][kraken_market]["a"][0])) / 2
    except KeyError as e:
        logging.debug(r.text)
    logging.debug(prices)

def report(update, type_):
    try:
        red.sadd(f"bisqbot:{type_}_users_total", update.effective_user.id)
        red.sadd(f"bisqbot:{type_}_users:{date.today()}", update.effective_user.id)
        if type_ != "start":
            red.incr(f"bisqbot:amount_{type_}_total")
            red.incr(f"bisqbot:amount_{type_}:{date.today()}")
    except Exception as e:
        logging.exception(e)

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
    percentinfo = ""
    if prices.get(f"{quote}_{base}"):
        above_below = (
            "above" if float(offer["price"]) > prices[f"{quote}_{base}"] else "below"
        )
        percent = abs(1 - float(offer["price"]) / prices[f"{quote}_{base}"])
        percentinfo = f" ({percent:.2%} {above_below} market price)"

    return f"Use {METHODS[offer['payment_method']]} to buy {float(offer['amount'])} for {float(offer['price'])} per {quote.upper()}{percentinfo}"


def query_msg(offer, quote, base):
    percentinfo = ""
    if prices.get(f"{quote}_{base}"):
        percent = abs(1 - prices[f"{quote}_{base}"] / float(offer["price"]))
        percentinfo = f" ({percent:+.2%} market)"
    if offer["amount"] != offer["min_amount"]:
        quote_minmax = (
            f"{prec(offer['min_amount'], quote)}-{prec(offer['amount'], quote)}"
        )
        base_minmax = f"{prec(float(offer['min_amount'])*float(offer['price']), base)}-{prec(float(offer['amount'])*float(offer['price']), base)}"
    else:
        quote_minmax = f"{prec(offer['min_amount'], quote)}"
        base_minmax = f"{prec(float(offer['min_amount'])*float(offer['price']), base)}"
    short_id = offer["offer_id"].split("-")[0]
    return InputTextMessageContent(
        message_text=f"<b><a href=\"https://bisq.network\">Bisq</a> currently has an offer to {offer['direction'].lower()} "
        f"{prec(offer['amount'], quote)} {quote.upper()} for {prec(offer['volume'], base)} {base.upper()}</b>\n\n"
        f"Price in {base.upper()} for 1 {quote.upper()}: {prec(offer['price'], quote)}{percentinfo}\n"
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
    best_sell = offers[market]["sells"][1]
    buy_prct = ""
    sell_prct = ""
    if prices.get(f"{quote}_{base}"):
        buy_percent = abs(1 - prices[f"{quote}_{base}"] / float(best_buy["price"]))
        if buy_percent < -0.01:
            buy_prct = "<b>{:+.2%}</b>".format(buy_percent)
        else:
            buy_prct = "{:+.2%}".format(buy_percent)

        sell_percent = abs(1 - float(best_sell["price"]) / prices[f"{quote}_{base}"])
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
        id=f"overview{market}",
        title=f"{market_txt} - {len(offers[market]['buys'])} bids / {len(offers[market]['sells'])} asks",
        description=f"Overview of the {market_txt} Bisq market",
        input_message_content=content,
    )


def empty_query():
    return [
        overview(market.split("_")[0], market.split("_")[1]) for market in MARKETS
    ] + [
        InlineQueryResultArticle(
            id=offer["offer_id"][:64],
            title=query_title(offer, "btc", cur),
            description=query_desc(offer, "btc", cur),
            input_message_content=query_msg(offer, "btc", cur),
            thumb_url=ICONS[offer["direction"].lower()],
        )
        for cur, what in product(["usd", "eur"], ["buys", "sells"])
        for offer in offers[f"btc_{cur}"][what][:1]
    ]


def query(update, context):
    report(update, "query")
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
            ("bsq", "bsq_btc"),
            ("bisq", "bsq_btc"),
            ("brl", "btc_brl"),
            ("brazilian", "btc_brl"),
            ("brasil", "btc_brl"),
            ("real", "btc_brl"),
            ("dollar", "btc_cad"),
            ("canadian", "btc_cad"),
            ("canada", "btc_cad"),
            ("cad", "btc_cad"),
            ("loonie", "btc_cad"),
        ]:
            if word.lower() in cur.lower():
                markets.append(market)
        if is_prefix(word.lower(), "buys") or is_prefix(word.lower(), "asks"):
            filters.append("buys")
        if is_prefix(word.lower(), "sells") or is_prefix(word.lower(), "bids"):
            filters.append("sells")
    if not markets and not filters:
        update.inline_query.answer(empty_query(), cache_time=60)
    markets = set(markets)
    if not filters:
        answers += [
            overview(market.split("_")[0], market.split("_")[1]) for market in markets
        ]
        filters = ["buys", "sells"]
    if not markets:
        markets = MARKETS
    markets = [(market.split("_")[0], market.split("_")[1]) for market in markets]
    for i in range(10):
        for (quote, base) in markets:
            for what in filters:
                try:
                    offer = offers[f"{quote}_{base}"][what][i]
                    answers.append(
                        InlineQueryResultArticle(
                            id=offer["offer_id"][:64],
                            title=query_title(offer, quote, base),
                            description=query_desc(offer, quote, base),
                            input_message_content=query_msg(offer, quote, base),
                            thumb_url=ICONS[offer["direction"].lower()],
                        )
                    )
                except IndexError:
                    pass
    update.inline_query.answer(answers[:10], cache_time=60)


def start(update, context):
    report(update, "start")
    update.message.reply_text(
        "You found the BisqBot! Currently I don't do anything in private chats, but"
        " feel free to try my inline mode in this chat.\n Just start by typing @BisqBot, then you can search for"
        " markets and offers with keywords like eur, usd, buy and sell.\n\n"
        "Follow @bitcoinbuys or @bitcoinbuyseuro to receive notifications on good BTC buy offers. Contact @pingiun for feedback on this bot."
    )


def send_to_channel(context):
    for market, channel in [
        ("btc_usd", "@bitcoinbuys"),
        ("btc_eur", "@bitcoinbuyseuro"),
    ]:
        logging.debug(f"Checking good buys for {market}")
        quote, base = market.split("_")[0], market.split("_")[1]
        for offer in offers[market]["sells"]:
            percent = 1 - prices[market] / float(offer["price"])
            logging.debug(f"Found trade with {percent}")
            if percent > -0.005:
                continue
            if red.sismember("bisqoffers", offer["offer_id"]):
                continue
            red.sadd("bisqoffers", offer["offer_id"])
            if offer["amount"] != offer["min_amount"]:
                quote_minmax = (
                    f"{prec(offer['min_amount'], quote)}-{prec(offer['amount'], quote)}"
                )
                base_minmax = f"{prec(float(offer['min_amount'])*float(offer['price']), base)}-{prec(float(offer['amount'])*float(offer['price']), base)}"
            else:
                quote_minmax = f"{prec(offer['min_amount'], quote)}"
                base_minmax = (
                    f"{prec(float(offer['min_amount'])*float(offer['price']), base)}"
                )
            context.bot.send_message(
                channel,
                ("❇️" * round(abs(percent) * 100))
                + f'<b>{abs(percent):.2%} lower than market price BTC available on <a href="https://bisq.network">Bisq</a></b>\n\n'
                f"Price in {base.upper()} for 1 {quote.upper()}: {prec(offer['price'], quote)} (current market price: {prices[market]})\n"
                f"{quote.upper()} (min-max): {quote_minmax}\n"
                f"{base.upper()} (min-max): {base_minmax}\n"
                f"Payment method: {METHODS[offer['payment_method']]}\n"
                f"Offer ID: {offer['offer_id'].split('-')[0]}",
                parse_mode="html",
                disable_web_page_preview=True,
            )


def other(update, context):
    text = update.message.text
    if update.message.via_bot:
        return
    if any(
        [
            word in text
            for word in ["usd", "eur", "buy", "sell", "cad", "btc", "xmr", "@BisqBot"]
        ]
    ):
        report(update, "hint")
        update.message.reply_text(
            'Psst this bot only works in <a href="https://telegram.org/blog/inline-bots">inline mode</a>. Start by typing @BisqBot and check out the inline results. You can narrow down your search with keywords like usd, brl, or buy/sell.',
            parse_mode="html",
            disable_web_page_preview=True,
        )


def update_all(context=None):
    for market in MARKETS:
        if updater is not None and not updater.is_idle:
            return
        update_market(market)
    update_prices_kraken(KRAKEN_MARKETS)
    if context:
        context.job_queue.run_once(callback=send_to_channel, when=1)

def inline_result(update, context):
    report(update, "query_result")
    chosenquerylog.write(update.chosen_inline_result.to_json())
    chosenquerylog.write("\n")

def main():
    global offers
    global prices
    global updater

    first = 0
    offers_file = os.path.join(STATE_DIRECTORY, "offers.json")
    prices_file = os.path.join(STATE_DIRECTORY, "prices.json")
    try:
        if time.time() - os.path.getmtime(offers_file) > 180:
            raise Exception("File too old")
        if time.time() - os.path.getmtime(prices_file) > 180:
            raise Exception("File too old")
        with open(offers_file, "r") as f:
            offers = json.load(f)
        with open(prices_file, "r") as f:
            prices = json.load(f)
        if not offers or not prices:
            raise Exception("Empty file")
    except Exception as e:
        logging.debug(e)
        update_all()
        first = 90

    updater = Updater(token=TG_TOKEN, use_context=True)
    job_queue = updater.job_queue
    # job_queue.run_once(callback=send_to_channel, when=1)
    job_queue.run_repeating(callback=update_all, first=first, interval=90)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(InlineQueryHandler(callback=query))
    dispatcher.add_handler(CommandHandler(callback=start, command="start"))
    dispatcher.add_handler(MessageHandler(callback=other, filters=Filters.text))
    dispatcher.add_handler(ChosenInlineResultHandler(callback=inline_result))
    updater.start_polling()
    updater.idle()

    with open(offers_file, "w") as f:
        json.dump(offers, f)
    with open(prices_file, "w") as f:
        json.dump(prices, f)
    chosenquerylog.close()


if __name__ == "__main__":
    main()
