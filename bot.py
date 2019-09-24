import logging
import time
from decimal import Decimal as D
import ccxt
from settings import Settings
from storage import Storage


class MarketMakerBot:
    """
    Бот маркет-мейкер. Основной принцип работы: Создание сетки ордеров.
    После активации одной из сеток ордеров бот начинает процесс "выруливания",
    методом выставления корректирующего ордера на нужной цене
    """
    def __init__(self, settings: 'Settings', storage: 'Storage'):
        """
        Инициализация бота маркет-мейкера
        """
        self._settings = settings
        self._storage = storage

        exchange_settings = {'apiKey': self._settings['exchange']['apiKey'],
                             'secret': self._settings['exchange']['secret'],
                             'timeout': self._settings['exchange']['timeout'],
                             'nonce': self._nonce_generator}
        if self._settings['exchange']['uid']:
            exchange_settings['uid'] = self._settings['exchange']['uid']
        if self._settings['exchange']['password']:
            exchange_settings['password'] = self._settings['exchange']['password']
        exchange_class = getattr(ccxt, self._settings['exchange']['id'])
        self._exchange = exchange_class(exchange_settings)

        self._logger = logging.getLogger(self.__class__.__name__)
        self._looped = False

    def _nonce_generator(self) -> int:
        """
        Выполняет генерацию последовательности nonce для биржи.
        Fix-Me: Для некоторых бирж (возможно) потребуется значение миллисекунд!

        :return: Уникальный идентификатор запроса
        """
        if self._settings['nonce_as_time']:
            return ccxt.Exchange.milliseconds()

        current_nonce = self._storage.setdefault('nonce', 1)
        self._storage['nonce'] += 1
        return current_nonce

    def _reload_markets(self) -> None:
        """
        Выполняет принудительное обновление информации о рынке

        :return: None
        """
        self._logger.debug('Запрошено обновление рыночной информации')
        while True:
            try:
                self._exchange.load_markets(True)
                return
            except ccxt.BaseError:
                self._logger.exception('Ошибка получения рыночной информации. Повторяю...')

    def _get_bid_ask(self) -> tuple:
        """
        Получает текущий bid/ask (None если нет хотя бы одного)

        :return: None, None
        """
        self._logger.debug('Запрошены значения bid/ask')
        symbol = self._settings['trade_symbol']
        while True:
            try:
                orderbook = self._exchange.fetch_order_book(symbol)
                if not len(orderbook['bids']) or not len(orderbook['asks']):
                    return None, None
                return D(self._exchange.price_to_precision(symbol, orderbook['bids'][0][0])), \
                       D(self._exchange.price_to_precision(symbol, orderbook['asks'][0][0]))
            except ccxt.BaseError:
                self._logger.exception('Ошибка получения значений bid/ask. Повторяю...')

    def _request_balance(self) -> None:
        """
        Выполняет запрос и сохранение баланса в лог-файл

        :return: None
        """
        if not self._settings['request_balances']:
            return

        try:
            balances = self._exchange.fetch_balance()
        except ccxt.BaseError:
            self._logger.warning('Ошибка получения текущего баланса. Игнорируем...')
        else:
            balance_info = ('{0} = {1}'.format(c, v) for c, v in balances.get('total', dict()).items() if v > 0)
            self._logger.debug('Текущий баланс | {0}'.format(' | '.join(balance_info)))

    def reset(self) -> None:
        """
        Выполняет сброс всех ордеров

        :return: None
        """
        self._cancel_all_orders()

    def loop(self) -> None:
        """
        Основной цикл работы бота маркет-мейкера

        :return: None
        """
        self._looped = True

        self._reload_markets()

        while self._looped:
            next_activity_time = time.time() + self._settings['bot_behaviour_update_period']

            self._behaviour()
            self._exchange.purge_cached_orders(self._exchange.milliseconds())
            self._storage.commit()

            activity_delta = next_activity_time - time.time()
            if activity_delta > 0:
                time.sleep(activity_delta)

    def _behaviour(self) -> None:
        """
        Функция основного поведения бота. Вызывается через фиксированные временные интервалы.
        Выполняет установку ордеров, их проверку и корректирование.

        :return: None
        """
        symbol = self._settings['trade_symbol']
        market = self._exchange.market(symbol)

        sell_orders = self._storage.setdefault('sell_orders', list())
        buy_orders = self._storage.setdefault('buy_orders', list())

        if not(len(sell_orders)) and not(len(buy_orders)):
            self._request_balance()
            bid, ask = self._get_bid_ask()
            avg_price = (bid + ask) / D('2')
            avg_profit = (D('1') + D(str(self._settings['minimal_profit'])) + D('1') + D(str(self._settings['maximal_profit']))) / D('2')
            fee = D('1') - D(str(market['maker']))
            delta = avg_price * ((avg_profit / (fee * fee)) - D('1'))
            self._storage['avg_price'] = str(avg_price)
            self._storage['delta'] = str(delta)
            sell_amount = D(str(self._settings['trade_amount']))
            self._logger.debug('Начинаю построение сетки: bid={0}; ask={1}; средняя цена={2}; дельта={3}'.format(bid, ask, self._storage['avg_price'], self._storage['delta']))
            skip_sell = skip_buy = False
            for i in range(1, self._settings['orders_count'] + 1):
                sell_price = D(self._storage['avg_price']) + D(self._storage['delta']) * D(i)
                prepared_sell_amount = float(self._exchange.amount_to_precision(symbol, sell_amount))
                prepared_sell_price = float(self._exchange.price_to_precision(symbol, sell_price))
                if not skip_sell:
                    while True:
                        try:
                            sell_order = self._exchange.create_limit_sell_order(symbol, prepared_sell_amount, prepared_sell_price)
                        except ccxt.InsufficientFunds:
                            skip_sell = True
                            self._logger.warning('Нет средств для продажи с шага {0}'.format(i))
                            break
                        except ccxt.NetworkError:
                            self._logger.exception('Сетевая ошибка создания ордера на продажу (множитель {0}, цена {1}, объем {2})'.format(i, prepared_sell_price, prepared_sell_amount))
                        except ccxt.ExchangeError:
                            self._logger.exception('Ошибка создания ордера на продажу (множитель {0}, цена {1}, объем {2})'.format(i, prepared_sell_price, prepared_sell_amount))
                            break
                        else:
                            sell_orders.append({'multiplier': i, 'id': sell_order['id']})
                            self._logger.debug('Ордер на продажу (множитель {0}, цена {1}, объем {2})'.format(i, prepared_sell_price, prepared_sell_amount))
                            break

                buy_price = D(self._storage['avg_price']) - D(self._storage['delta']) * D(i)
                buy_amount = self._get_buy_amount(sell_amount, buy_price)
                prepared_buy_amount = float(self._exchange.amount_to_precision(symbol, buy_amount))
                prepared_buy_price = float(self._exchange.price_to_precision(symbol, buy_price))
                if not skip_buy:
                    while True:
                        try:
                            buy_order = self._exchange.create_limit_buy_order(symbol, prepared_buy_amount, prepared_buy_price)
                        except ccxt.InsufficientFunds:
                            skip_buy = True
                            self._logger.warning('Нет средств для покупки с шага {0}'.format(-i))
                            break
                        except ccxt.NetworkError:
                            self._logger.exception('Сетевая ошибка создания ордера на покупку (множитель {0}, цена {1}, объем {2})'.format(-i, prepared_buy_price, prepared_buy_amount))
                        except ccxt.ExchangeError:
                            self._logger.exception('Ошибка создания ордера на покупку (множитель {0}, цена {1}, объем {2})'.format(-i, prepared_buy_price, prepared_buy_amount))
                            break
                        else:
                            buy_orders.append({'multiplier': -i, 'id': buy_order['id']})
                            self._logger.debug('Ордер на покупку (множитель {0}, цена {1}, объем {2})'.format(-i, prepared_buy_price, prepared_buy_amount))
                            break
            return

        last_closed_sell_multiplier, last_closed_buy_multiplier = self._check_all_orders()

        if (last_closed_sell_multiplier is None) and (last_closed_buy_multiplier is None):
            return

        last_closed_sell_multiplier = last_closed_sell_multiplier if last_closed_sell_multiplier is not None else last_closed_buy_multiplier
        last_closed_buy_multiplier = last_closed_buy_multiplier if last_closed_buy_multiplier is not None else last_closed_sell_multiplier
        if (last_closed_sell_multiplier == last_closed_buy_multiplier) and self._check_profit(last_closed_sell_multiplier):
            return

        self._request_balance()

        new_sell_orders = []
        new_buy_orders = []

        sell_amount = D(str(self._settings['trade_amount']))
        skip_sell = skip_buy = False
        for i in range(1, self._settings['orders_count'] + 1):
            sell_multiplier = last_closed_sell_multiplier + i

            if len(sell_orders) and sell_orders[0]['multiplier'] == sell_multiplier:
                new_sell_orders.append(sell_orders.pop(0))
                self._logger.debug('Использую установленный ордер на продажу (множитель {0})'.format(sell_multiplier))
            else:
                sell_price = D(self._storage['avg_price']) + D(self._storage['delta']) * D(sell_multiplier)
                prepared_sell_amount = float(self._exchange.amount_to_precision(symbol, sell_amount))
                prepared_sell_price = float(self._exchange.price_to_precision(symbol, sell_price))
                if not skip_sell:
                    while True:
                        try:
                            sell_order = self._exchange.create_limit_sell_order(symbol, prepared_sell_amount, prepared_sell_price)
                        except ccxt.InsufficientFunds:
                            skip_sell = True
                            self._logger.warning('Нет средств для продажи с шага {0}'.format(sell_multiplier))
                            break
                        except ccxt.NetworkError:
                            self._logger.exception('Сетевая ошибка создания ордера на продажу (множитель {0}, цена {1}, объем {2})'.format(sell_multiplier, prepared_sell_price, prepared_sell_amount))
                        except ccxt.ExchangeError:
                            self._logger.exception('Ошибка создания ордера на продажу (множитель {0}, цена {1}, объем {2})'.format(sell_multiplier, prepared_sell_price, prepared_sell_amount))
                            break
                        else:
                            new_sell_orders.append({'multiplier': sell_multiplier, 'id': sell_order['id']})
                            self._logger.debug('Ордер на продажу (множитель {0}, цена {1}, объем {2})'.format(sell_multiplier, prepared_sell_price, prepared_sell_amount))
                            break

            buy_multiplier = last_closed_buy_multiplier - i

            if len(buy_orders) and buy_orders[0]['multiplier'] == buy_multiplier:
                new_buy_orders.append(buy_orders.pop(0))
                self._logger.debug('Использую установленный ордер на покупку (множитель {0})'.format(buy_multiplier))
            else:
                buy_price = D(self._storage['avg_price']) + D(self._storage['delta']) * D(buy_multiplier)
                buy_amount = self._get_buy_amount(sell_amount, buy_price)
                prepared_buy_amount = float(self._exchange.amount_to_precision(symbol, buy_amount))
                prepared_buy_price = float(self._exchange.price_to_precision(symbol, buy_price))
                if not skip_buy:
                    while True:
                        try:
                            buy_order = self._exchange.create_limit_buy_order(symbol, prepared_buy_amount, prepared_buy_price)
                        except ccxt.InsufficientFunds:
                            skip_buy = True
                            self._logger.warning('Нет средств для покупки с шага {0}'.format(buy_multiplier))
                            break
                        except ccxt.NetworkError:
                            self._logger.exception('Сетевая ошибка создания ордера на покупку (множитель {0}, цена {1}, объем {2})'.format(buy_multiplier, prepared_buy_price, prepared_buy_amount))
                        except ccxt.BaseError:
                            self._logger.exception('Ошибка создания ордера на покупку (множитель {0}, цена {1}, объем {2})'.format(buy_multiplier, prepared_buy_price, prepared_buy_amount))
                            break
                        else:
                            new_buy_orders.append({'multiplier': buy_multiplier, 'id': buy_order['id']})
                            self._logger.debug('Ордер на покупку (множитель {0}, цена {1}, объем {2})'.format(buy_multiplier, prepared_buy_price, prepared_buy_amount))
                            break

        self._cancel_all_orders()
        sell_orders.extend(new_sell_orders)
        buy_orders.extend(new_buy_orders)
        if self._settings['stop_after_pump'] and not sell_orders:
            self._looped = False
            self._cancel_all_orders()
            self._logger.warning('Сработал STOP_AFTER_PUMP. Завершаю...')

    def _check_profit(self, multiplier: int) -> bool:
        """
        Проверяет на вхождение отношения цены/дельты в заданный диапазон профита

        :param multiplier: Множитель центральной цены
        :return: True - Следует перезапустится
        """
        market = self._exchange.market(self._settings['trade_symbol'])
        fee = D('1') - D(str(market['maker']))
        zero_price = D(self._storage['avg_price']) + D(multiplier) * D(self._storage['delta'])
        cprofit = (fee * fee * ((D(self._storage['delta']) / zero_price) + D('1'))) - D('1')
        if (cprofit < D(str(self._settings['minimal_profit']))) or (cprofit > D(str(self._settings['maximal_profit']))):
            self._logger.debug('Текущий профит = {0} не совпадает с целевым диапазоном'.format(cprofit))
            self._cancel_all_orders()
            return True
        return False

    def _check_all_orders(self) -> tuple:
        """
        Проверяет списки ордеров на наличие в них исполненных

        :return: tuple(Последняя исполненная продажа или None, Последняя исполненная покупка или None)
        """
        while True:
            try:
                opened_orders = self._exchange.fetch_open_orders(self._settings['trade_symbol'])
                break
            except ccxt.NetworkError:
                self._logger.error('Сетевая ошибка получения информации о ордерах. Жду и повторяю...')
                time.sleep(self._settings['exchange']['timeout'] / 1000)
            except ccxt.ExchangeError:
                self._logger.exception('Биржевая ошибка получения информации о ордерах. Повторяю...')
        opened_orders_id = [order['id'] for order in opened_orders]

        sell_orders = self._storage.setdefault('sell_orders', list())
        buy_orders = self._storage.setdefault('buy_orders', list())

        my_orders_id = [_['id'] for _ in sell_orders + buy_orders]
        for order_id in opened_orders_id:
            if order_id not in my_orders_id:
                self._logger.debug('Найден несвязанный ордер {0}. Пробую отменить...'.format(order_id))
                try:
                    self._exchange.cancel_order(id=order_id, symbol=self._settings['trade_symbol'])
                except ccxt.BaseError:
                    self._logger.warning('Ошибка отмены несвязанного ордера. Оставляю...')

        def _check_orders(orders: list) -> int:
            last_closed = None
            while orders:
                if orders[0]['id'] in opened_orders_id:
                    return last_closed
                else:
                    self._logger.debug('Найден исполненный ордер с множителем {0}'.format(orders[0]['multiplier']))
                    last_closed = orders.pop(0)['multiplier']
            return last_closed

        return _check_orders(sell_orders), _check_orders(buy_orders)

    def _cancel_all_orders(self) -> None:
        """
        Выполняет отмену всех ордеров

        :return: None
        """
        def _cancel_orders(orders: list) -> None:
            while orders:
                try:
                    self._exchange.cancel_order(id=orders[0]['id'], symbol=self._settings['trade_symbol'])
                except ccxt.NetworkError:
                    self._logger.exception('Сетевая ошибка отмены ордера. Повторяю...')
                except ccxt.ExchangeError:
                    orders.pop(0)
                    self._logger.exception('Ошибка отмены ордера. Игнорирую ордер')
                else:
                    orders.pop(0)

        self._logger.debug('Отмена ордеров на продажу')
        _cancel_orders(self._storage.setdefault('sell_orders', list()))
        self._logger.debug('Отмена ордеров на покупку')
        _cancel_orders(self._storage.setdefault('buy_orders', list()))

    def _get_buy_amount(self, sell_amount: 'D', price: 'D') -> 'D':
        """
        Вычисляет размер покупки в соответствии с политикой по прибыли

        :param sell_amount: Размер позиции на продажу
        :param price: Цена, по которой происходит покупка
        :return: Размер покупки
        """
        market = self._exchange.market(self._settings['trade_symbol'])

        mode = self._settings['accumulate']
        if mode == 'all':
            fee = D('1') - D(str(market['maker']))
            buy_amount = (sell_amount * (fee * fee * ((D(self._storage['delta']) / price) + D('1')) + D('1'))) / D('2')
        elif mode == 'crypto':
            fee = D('1') - D(str(market['maker']))
            buy_amount = sell_amount * fee * fee * ((D(self._storage['delta']) / price) + D('1'))
        elif mode == 'fiat':
            buy_amount = sell_amount
        else:
            raise NotImplementedError()

        return buy_amount
