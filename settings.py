import json
import collections.abc

class Settings(collections.abc.MutableMapping):
    def __init__(self, file_name: 'str' = 'settings.json'):
        """
        Выполняет инициализацию класса для работы с настройками

        :param file_name: путь к файлу с настройками
        """
        with open(file_name) as settings_file:
            self.__settings = json.load(settings_file)

    def __delitem__(self, key):
        """
        Удалять из настроек запрещено

        :param key:

        :return: None
        """
        del self.__settings[key]

    def __setitem__(self, key, value):
        """
        Изменять настройки запрещено

        :param key:

        :param value:

        :return: None
        """
        self.__settings[key] = value

    def __iter__(self):
        """
        Возвращает итератор на настройки

        :return: Iterator
        """
        return iter(self.__settings)

    def __getitem__(self, key):
        """
        Возвращает элемент настроек

        :param key: Название ключа настроек

        :return: Настройка
        """
        return self.__settings[key]

    def __len__(self):
        """
        Возвращает длину словаря с настройками

        :return: Длина словаря
        """
        return len(self.__settings)