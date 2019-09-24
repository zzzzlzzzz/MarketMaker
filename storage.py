import pickle
import collections.abc

class Storage(collections.abc.MutableMapping):
    def __init__(self, file_name: 'str' = 'storage.db'):
        """
        Выполняет инициализацию хранилища данных

        :param file_name: Имя файла-хранилища
        """
        self.__file_name = file_name
        try:
            with open(self.__file_name, 'rb') as storage_file:
                self.__storage = pickle.load(storage_file)
        except IOError:
            self.__storage = dict()

    def __delitem__(self, key):
        """
        Удаляет элемент из хранилища

        :param key: Ключ элемента

        :return: None
        """
        del self.__storage[key]

    def __setitem__(self, key, value):
        """
        Устанавливает значение элемента в хранилище

        :param key: Ключ элемента

        :param value: Новое значение элемента

        :return: None
        """
        self.__storage[key] = value

    def __iter__(self):
        """
        Возвращает итератор на хранилище

        :return: Итератор на хранилище
        """
        return iter(self.__storage)

    def __getitem__(self, key):
        """
        Возвращает элемент хранилища по ключу

        :param key: Ключ элемента

        :return: Значение элемента
        """
        return self.__storage[key]

    def __len__(self):
        """
        Возвращает длину хранилища

        :return: Длина хранилища
        """
        return len(self.__storage)

    def commit(self) -> None:
        """
        Выполняет сохранение хранилища на диск

        :return: None
        """
        with open(self.__file_name, 'wb') as storage_file:
            pickle.dump(self.__storage, storage_file)