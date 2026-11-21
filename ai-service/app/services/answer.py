import re
from typing import get_args
from urllib.parse import urlsplit

from app.models import Audience, MapPoint, UserAnswer

ANSWER_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "university_answer",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "source": {"type": "array", "items": {"type": "string"}},
                "audience": {"type": "string", "enum": list(get_args(Audience))},
                "map_point": {"type": "string", "enum": list(get_args(MapPoint))},
            },
            "required": ["message", "source", "audience", "map_point"],
            "additionalProperties": False,
        },
    },
}

_SOURCE_FIELDS = {"source", "sources", "source_url"}
_INTERNAL_FIELDS = {"verification", "checked_on", "checked_at", "similarity"}
# Links belong in source even if the provider repeats them in the prose.
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)|https?://[^\s<>]+")


def collect_source_urls(data: object) -> set[str]:
    if isinstance(data, list):
        return {url for item in data for url in collect_source_urls(item)}
    if not isinstance(data, dict):
        return set()

    urls = set()
    for key, value in data.items():
        if key in _SOURCE_FIELDS:
            entries = value if isinstance(value, list) else [value]
            for entry in entries:
                url = entry.get("url") if isinstance(entry, dict) else entry
                if isinstance(url, str):
                    try:
                        parsed = urlsplit(url)
                        if parsed.scheme in {"http", "https"} and parsed.hostname:
                            urls.add(url)
                    except ValueError:
                        continue
        elif isinstance(value, (dict, list)):
            urls.update(collect_source_urls(value))
    return urls


def model_tool_data(data: object) -> object:
    if isinstance(data, dict):
        return {
            key: model_tool_data(value)
            for key, value in data.items()
            if key not in _INTERNAL_FIELDS
        }
    if isinstance(data, list):
        return [model_tool_data(value) for value in data]
    return data


def parse_user_answer(content: str, allowed_sources: set[str]) -> UserAnswer:
    answer = UserAnswer.model_validate_json(content.removesuffix("<|endoftext|>").rstrip())
    cited = dict.fromkeys(url for url in answer.source if url in allowed_sources)

    def remove_citation(match: re.Match[str]) -> str:
        url = (match.group(2) or match.group(0)).rstrip(".,;!?)]")
        if url in allowed_sources:
            cited[url] = None
            return ""
        if url in answer.source:
            return ""
        return match.group(0)

    message = _LINK.sub(remove_citation, answer.message)
    message = re.sub(r"(?im)^[ \t]*(?:источники?|sources?)[ \t]*:[ \t]*$", "", message)
    message = re.sub(r"\s*\((?:status|verification)\s*:\s*[a-z]+(?:_[a-z]+)+\)", "", message)
    return UserAnswer(
        message=message, source=list(cited), audience=answer.audience, map_point=answer.map_point
    )
