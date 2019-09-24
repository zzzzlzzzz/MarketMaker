from time import time, sleep
from datetime import datetime
from functools import partial
from decimal import Decimal as D
from os import path
import csv
import ccxt
from settings import Settings
from storage import Storage


if __name__ == '__main__':
    settings = Settings('settings-stat.json')
    storage = Storage('storage-stat.db')

    def nonce(name, use_time):
        if use_time:
            return ccxt.Exchange.milliseconds()
        n = storage.setdefault(name, 1)
        storage[name] += 1
        storage.commit()
        return n

    exchanges = []  # [{'exchange': e, 'file': fn, 'base': 'BASE', 'quote': ['QUOTE']}]
    for account in settings['accounts']:
        ex_setting = {'apiKey': account['apiKey'], 'secret': account['secret'], 'timeout': account['timeout'],
                      'nonce': partial(nonce, 'nonce-{0}'.format(account['file']), account['nonce_as_time'])}
        if account['uid']:
            ex_setting['uid'] = account['uid']
        if account['password']:
            ex_setting['password'] = account['password']
        exchanges.append({'exchange': getattr(ccxt, account['id'])(ex_setting),
                          'file': account['file'],
                          'base': account['base'],
                          'quote': account['quote']})
        exchanges[-1]['exchange'].load_markets()

    while True:
        next_time = time() + settings['period']
        row_time = datetime.utcnow().strftime('%d.%m.%y %H:%M')

        for account in exchanges:
            row_headers = ['Time', 'Total({0})'.format(account['base']), account['base'],
                           *account['quote'], *('Price({0})'.format(_) for _ in account['quote'])]
            row = {'Time': row_time}
            try:
                balances = account['exchange'].fetch_balance().get('total', {})
                b_a = str(balances.get(account['base'], '0'))
                row[account['base']] = b_a
                total = D(b_a)
                for q in account['quote']:
                    pair = '{0}/{1}'.format(q, account['base'])

                    q_a = str(balances.get(q, '0'))

                    order_book = account['exchange'].fetch_order_book(pair)
                    q_p = D(str(order_book['asks'][0][0])) if order_book['asks'] else D('0')
                    q_p += D(str(order_book['bids'][0][0])) if order_book['bids'] else D('0')
                    q_p = q_p / D('2') if order_book['asks'] and order_book['bids'] else q_p
                    q_p = str(account['exchange'].price_to_precision(pair, q_p))

                    row[q] = q_a
                    row['Price({0})'.format(q)] = q_p
                    total += D(q_a) * D(q_p)
                row['Total({0})'.format(account['base'])] = str(total)

                write_header = not path.exists(account['file'])
                with open(account['file'], 'a', encoding='utf8', newline='') as f:
                    writer = csv.DictWriter(f, row_headers)
                    if write_header:
                        writer.writeheader()
                    writer.writerow(row)
            except (ccxt.BaseError, OSError, csv.Error) as e:
                print(e)

        wait_time = next_time - time()
        if wait_time > 0:
            sleep(wait_time)
