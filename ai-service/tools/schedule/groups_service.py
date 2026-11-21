import argparse
import json
import re
from functools import partial
from http import HTTPStatus
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs

from schedule_api import api_url, read_json
from student_lookup import searchable

GROUPS_URL = api_url("groups")
CACHE_SECONDS = 60


class GroupDirectory:
    def __init__(self, source_url=GROUPS_URL):
        self.source_url = source_url
        self._groups = {}
        self._expires_at = 0
        self._lock = Lock()

    def _load(self):
        with self._lock:
            if monotonic() >= self._expires_at:
                rows = read_json(self.source_url)
                if not isinstance(rows, list) or any(
                    not isinstance(row, dict)
                    or type(row.get("group_id")) is not int
                    or not isinstance(row.get("group_title"), str)
                    for row in rows
                ):
                    raise ValueError("Источник вернул список групп в неожиданном формате")

                self._groups = {str(row["group_id"]): row for row in rows}
                self._expires_at = monotonic() + CACHE_SECONDS
            return self._groups

    def search(self, query=""):
        groups = self._load().values()
        needle = searchable(query.strip())
        if not needle:
            return list(groups)

        exact = []
        partial_matches = []
        for group in groups:
            title = searchable(group["group_title"])
            if title == needle:
                exact.append(group)
            elif needle in title:
                partial_matches.append(group)
        return exact + partial_matches

    def get(self, group_id):
        return self._load().get(str(group_id))


class GroupsHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, directory, **kwargs):
        self.directory = directory
        super().__init__(*args, **kwargs)

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, _, query = self.path.partition("?")
        path = path.rstrip("/")
        group = re.fullmatch(r"/groups/([0-9]+)", path)
        if path != "/groups" and group is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Маршрут не найден"})
            return

        try:
            if group is None:
                name = parse_qs(query, keep_blank_values=True).get("q", [""])[0]
                result = self.directory.search(name)
            else:
                result = self.directory.get(group[1])
        except (OSError, ValueError, HTTPException) as error:
            self.log_error("Ошибка источника групп: %s", error)
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": "Источник расписания недоступен"})
            return

        if result is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Группа не найдена"})
            return
        self._send_json(HTTPStatus.OK, result)


def main():
    parser = argparse.ArgumentParser(description="HTTP-сервис для поиска учебных групп УУНиТ")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--source-url", default=GROUPS_URL, help="URL JSON-списка групп")
    options = parser.parse_args()

    handler = partial(GroupsHandler, directory=GroupDirectory(options.source_url))
    with ThreadingHTTPServer((options.host, options.port), handler) as server:
        print(
            f"Список групп доступен по адресу http://{options.host}:{server.server_port}/groups",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
