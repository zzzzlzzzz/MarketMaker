"""
CLI-интерфейс для работы с биржей
"""
from decimal import Decimal
from argparse import ArgumentParser, ArgumentTypeError
import ccxt
from settings import Settings
from storage import Storage


if __name__ == '__main__':
    def arg_decimal(val):
        try:
            res = Decimal(val)
        except Exception:
            raise ArgumentTypeError('{0} is not a Decimal'.format(val))
        return res

    parser = ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-b', '--buy', type=arg_decimal, nargs=2, help='Buy AMOUNT by PRICE', metavar=('AMOUNT', 'PRICE'))
    group.add_argument('-s', '--sell', type=arg_decimal, nargs=2, help='Sell AMOUNT by PRICE', metavar=('AMOUNT', 'PRICE'))
    group.add_argument('-l', '--list', action='store_true', help='List balances')
    args = parser.parse_args()
    settings = Settings()
    storage = Storage()

    def nonce_generator():
        if settings['nonce_as_time']:
            return ccxt.Exchange.milliseconds()
        current_nonce = storage.setdefault('nonce', 1)
        storage['nonce'] += 1
        storage.commit()
        return current_nonce

    exchange_settings = {'apiKey': settings['exchange']['apiKey'], 'secret': settings['exchange']['secret'],
                         'timeout': settings['exchange']['timeout'], 'nonce': nonce_generator}
    if settings['exchange']['uid']:
        exchange_settings['uid'] = settings['exchange']['uid']
    if settings['exchange']['password']:
        exchange_settings['password'] = settings['exchange']['password']
    exchange = getattr(ccxt, settings['exchange']['id'])(exchange_settings)
    exchange.load_markets()

    symb = settings['trade_symbol']
    try:
        if args.buy:
            amount = float(exchange.amount_to_precision(symb, args.buy[0]))
            price = float(exchange.price_to_precision(symb, args.buy[1]))
            order = exchange.create_limit_buy_order(symb, amount, price)
            print('ORDER_ID:\t{0}'.format(order['id']))
        elif args.sell:
            amount = float(exchange.amount_to_precision(symb, args.sell[0]))
            price = float(exchange.price_to_precision(symb, args.sell[1]))
            order = exchange.create_limit_sell_order(symb, amount, price)
            print('ORDER_ID:\t{0}'.format(order['id']))
        elif args.list:
            balances = exchange.fetch_balance()
            print('\n'.join('{0}:\t{1}'.format(name, amount) for name, amount in balances.get('total', {}).items() if amount > 0))
    except ccxt.InsufficientFunds as e:
        print('Not enought money: ', e)
    except ccxt.BaseError as e:
        print('ExchangeError: ', e)
    except Exception as e:
        print('Exception: ', e)
