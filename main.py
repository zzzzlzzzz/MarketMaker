from argparse import ArgumentParser
import logging.config
from settings import Settings
from storage import Storage
from bot import MarketMakerBot

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('-r', '--reset', help='reset all bot orders', action='store_true')
    args = parser.parse_args()
    settings = Settings()
    storage = Storage()
    logging.config.dictConfig(settings['logging'])
    mm_bot = MarketMakerBot(settings, storage)
    if args.reset:
        mm_bot.reset()
    mm_bot.loop()
    storage.commit()
