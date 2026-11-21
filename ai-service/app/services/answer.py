import re
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError

from app.models import Attachment, MapPoint, UserAnswer

HISTORY_SUMMARY_LIMIT = 2400

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
                "photo_ids": {"type": "array", "items": {"type": "string"}},
                "map_place_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["message", "source", "photo_ids", "map_place_ids"],
            "additionalProperties": False,
        },
    },
}


def answer_format_with_history() -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "university_answer_with_history",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    **ANSWER_FORMAT["json_schema"]["schema"]["properties"],
                    "history_summary": {"type": "string"},
                },
                "required": [
                    *ANSWER_FORMAT["json_schema"]["schema"]["required"],
                    "history_summary",
                ],
                "additionalProperties": False,
            },
        },
    }


_SOURCE_FIELDS = {"source", "sources", "source_url"}
_INTERNAL_FIELDS = {
    "verification",
    "checked_on",
    "checked_at",
    "similarity",
    "minio_bucket",
    "object_key",
    "content_type",
}
# Links belong in source even if the provider repeats them in the prose.
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)|https?://[^\s<>]+")
_JSON_FENCE = re.compile(r"\A```(?:json)?\s*([\s\S]+?)\s*```\Z", re.IGNORECASE)


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


def collect_campus_photos(result: dict) -> dict[str, Attachment]:
    if result.get("status") != "ok" or not isinstance(result.get("data"), list):
        return {}

    photos = {}
    for row in result["data"]:
        if not isinstance(row, dict):
            continue
        photo_id = row.get("id")
        key = row.get("object_key")
        bucket = row.get("minio_bucket")
        if (
            row.get("photo_available") is True
            and isinstance(photo_id, str)
            and re.fullmatch(r"[a-z0-9-]+", photo_id)
            and isinstance(key, str)
            and key.startswith("campus/")
            and isinstance(bucket, str)
            and bucket
            and row.get("content_type") == "image/jpeg"
        ):
            photos[photo_id] = Attachment(
                attachment_id=uuid4(),
                bucket=bucket,
                object_key=key,
                filename=f"{photo_id}.jpg",
                content_type="image/jpeg",
            )
    return photos


def collect_map_points(result: dict) -> dict[str, MapPoint]:
    if result.get("status") != "ok" or not isinstance(result.get("data"), list):
        return {}

    points = {}
    for row in result["data"]:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        data = row.get("data")
        if not isinstance(data, dict):
            continue
        try:
            point = MapPoint(
                title=row.get("title"),
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
            )
        except ValidationError:
            continue
        points[row["id"]] = point
    return points


def parse_user_answer(
    content: str,
    allowed_sources: set[str],
    allowed_photos: dict[str, Attachment],
    allowed_points: dict[str, MapPoint],
) -> UserAnswer:
    content = content.removesuffix("<|endoftext|>").strip()
    fenced = _JSON_FENCE.fullmatch(content)
    answer = UserAnswer.model_validate_json(fenced[1] if fenced else content)
    validated = sanitize_user_answer(answer, allowed_sources, allowed_photos)
    for place_id in dict.fromkeys(answer.map_place_ids):
        point = allowed_points.get(place_id)
        if point is not None and point not in validated.map_points:
            validated.map_points.append(point)
    return validated


def answer_from_draft(content: str, allowed_sources: set[str]) -> UserAnswer:
    content = content.removesuffix("<|endoftext|>").strip()
    prefix = content.casefold()
    if not prefix or prefix.startswith(
        ("{", "[{", "```json", "<think", "<tool", "thinking process:", "процесс рассуждения:")
    ):
        raise ValueError("OpenRouter did not return a usable text draft")

    return sanitize_user_answer(
        UserAnswer(message=content),
        allowed_sources,
        {},
        draft=True,
    )


def sanitize_user_answer(
    answer: UserAnswer,
    allowed_sources: set[str],
    allowed_photos: dict[str, Attachment],
    *,
    draft: bool = False,
) -> UserAnswer:
    cited = dict.fromkeys(url for url in answer.source if url in allowed_sources)

    def remove_citation(match: re.Match[str]) -> str:
        url = (match.group(2) or match.group(0)).rstrip(".,;!?)]")
        if url in allowed_sources:
            cited[url] = None
            return ""
        if url in answer.source:
            return ""
        if draft:
            return match.group(1) or ""
        return match.group(0)

    message = _LINK.sub(remove_citation, answer.message)
    message = re.sub(r"(?im)^[ \t]*(?:источники?|sources?)[ \t]*:[ \t]*$", "", message)
    message = re.sub(r"\s*\((?:status|verification)\s*:\s*[a-z]+(?:_[a-z]+)+\)", "", message)
    return UserAnswer(
        message=message,
        source=list(cited),
        photos=[allowed_photos[i] for i in dict.fromkeys(answer.photo_ids) if i in allowed_photos],
        history_summary=answer.history_summary.strip()[:HISTORY_SUMMARY_LIMIT],
    )
