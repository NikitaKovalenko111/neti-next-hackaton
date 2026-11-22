import json
from urllib.request import urlopen

API_BASE = 'https://dev.uust-time.ru/api/v/852972'


def searchable(value):
    return str(value or '').casefold().replace('ё', 'е')


def api_url(path, base=API_BASE):
    return f'{base.rstrip("/")}/{path}?site=schedule'


def read_json(url):
    with urlopen(url, timeout=10) as response:
        if response.headers.get_content_type() != 'application/json':
            raise ValueError('Источник расписания вернул ответ без JSON')
        return json.load(response)
