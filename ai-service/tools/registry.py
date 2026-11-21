import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import asyncpg
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tools import campus, support

logger = logging.getLogger(__name__)

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9_-]+$", max_length=100)]
Query = Annotated[str, Field(min_length=1, max_length=500)]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class OptionalBranch(Arguments):
    branch_id: Identifier | None = Field(None, description="ID филиала из list_branches")


class Branch(Arguments):
    branch_id: Identifier = Field(description="ID филиала из list_branches")


class BranchSearch(Arguments):
    query: Query | None = Field(None, description="Город, название или ID филиала")


class PlaceSearch(OptionalBranch):
    query: Query | None = Field(None, description="Название объекта, адрес или ID")
    kind: Literal["building", "dormitory"] | None = Field(None, description="Тип объекта")
    number: int | None = Field(None, ge=1, le=10000, description="Номер корпуса или общежития")
    limit: int = Field(10, ge=1, le=25, description="Количество результатов")
    offset: int = Field(0, ge=0, le=10000, description="next_offset из предыдущего ответа")


class PlaceDetails(Arguments):
    place_id: Identifier = Field(description="ID объекта из search_places")


class Photos(OptionalBranch):
    place_id: Identifier | None = Field(None, description="ID конкретного объекта из search_places")
    include_unverified: bool = Field(False, description="Включить фото с непроверенной привязкой")


class SemanticQuery(OptionalBranch):
    query: Query = Field(description="Вопрос пользователя или описание ситуации")


class CampusQuery(SemanticQuery):
    kind: Literal["branch", "building", "dormitory", "housing"] | None = None


class Grounds(OptionalBranch):
    query: Query | None = Field(None, description="Ключевые слова или ID основания")
    number: int | None = Field(None, ge=1, le=1000, description="Номер пункта в положении")


class Ground(OptionalBranch):
    ground_id: Identifier = Field(description="ID основания из списка или поиска")


class Programs(OptionalBranch):
    program_id: Identifier | None = Field(None, description="ID программы материальной поддержки")


class Channels(Branch):
    include_consultations: bool = Field(False, description="Включить профком и консультации")


async def campus_context(
    connection: asyncpg.Connection,
    client: httpx.AsyncClient,
    model: str,
    *,
    query: str,
    branch_id: str | None,
    kind: str | None,
) -> list[dict]:
    return await campus.search_campus(connection, client, model, query, branch_id, kind)


async def support_candidates(
    connection: asyncpg.Connection,
    client: httpx.AsyncClient,
    model: str,
    *,
    query: str,
    branch_id: str | None,
) -> list[dict]:
    matches = await support.search_material_support(connection, client, model, query, branch_id)
    return [
        {key: match[key] for key in ("id", "number_in_regulation", "title", "similarity")}
        for match in matches
    ]


async def ground_details(
    connection: asyncpg.Connection, ground_id: str, branch_id: str | None
) -> dict | None:
    return await support.find_ground(connection, ground_id, branch_id)


@dataclass(frozen=True)
class Tool:
    description: str
    arguments: type[Arguments]
    handler: Callable[..., Awaitable[Any]]
    embedding_table: str | None = None


TOOLS = {
    "list_branches": Tool(
        "Найти филиал по городу или получить список филиалов, адреса и сайты.",
        BranchSearch,
        campus.list_branches,
    ),
    "search_places": Tool(
        "Найти корпуса и общежития по названию, адресу, типу, филиалу или номеру. "
        "Если номер встречается в нескольких городах, покажи варианты или уточни филиал.",
        PlaceSearch,
        campus.search_places,
    ),
    "get_place": Tool(
        "Узнать точный адрес, спорные варианты адреса, ссылку на карту и известные "
        "сведения об объекте, включая телефон и опубликованную вместимость общежития.",
        PlaceDetails,
        campus.find_place,
    ),
    "get_housing": Tool(
        "Узнать, есть ли общежития у филиала, сколько их заявлено, какие адреса известны "
        "и упоминается ли партнёрское жильё. Вместимость не означает наличие свободных мест.",
        Branch,
        campus.get_housing,
    ),
    "list_photos": Tool(
        "Найти ссылки на фотографии объекта или филиала и проверить статус их привязки. "
        "Фото со статусом branch_only показывают филиал, а не конкретный объект.",
        Photos,
        campus.list_photos,
    ),
    "search_campus_context": Tool(
        "Найти кандидатов по свободному описанию кампуса. Для точных адресов, номеров "
        "и сведений об объекте используй search_places и get_place.",
        CampusQuery,
        campus_context,
        "rag.campus_embeddings",
    ),
    "list_support_grounds": Tool(
        "Получить перечень оснований материальной помощи или найти пункт по номеру, ID "
        "или ключевым словам. Для документов, суммы и сроков вызови get_support_ground.",
        Grounds,
        support.list_grounds,
    ),
    "search_support_grounds": Tool(
        "Подобрать основания помощи по свободному описанию ситуации. Это кандидаты, "
        "правила по выбранному основанию вернёт get_support_ground.",
        SemanticQuery,
        support_candidates,
        "rag.support_embeddings",
    ),
    "get_support_ground": Tool(
        "Получить требования, документы, сроки и событие отсчёта, периодичность, сумму "
        "или коэффициент, ограничения и страницы приказа по основанию помощи.",
        Ground,
        ground_details,
    ),
    "get_support_programs": Tool(
        "Получить общий порядок материальной помощи: кто может обратиться, как подать "
        "заявление, общий срок, формы и порядок рассмотрения.",
        Programs,
        support.get_programs,
    ),
    "list_support_channels": Tool(
        "Узнать, куда подать заявление в конкретном филиале, доступна ли онлайн-подача "
        "и какие консультации доступны по запросу.",
        Channels,
        support.list_channels,
    ),
    "get_data_scope": Tool(
        "Узнать даты снимков данных и какие темы база пока не покрывает.",
        Arguments,
        campus.get_data_scope,
    ),
}


def tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tool.description,
                "parameters": tool.arguments.model_json_schema(),
            },
        }
        for name, tool in TOOLS.items()
    ]


async def call_tool(
    connection: asyncpg.Connection,
    name: str,
    arguments: Mapping[str, Any],
    *,
    embedding_client: httpx.AsyncClient | None = None,
    embedding_model: str | None = None,
) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        return {"status": "unknown_tool"}

    try:
        params = tool.arguments.model_validate(arguments).model_dump()
    except ValidationError as error:
        return {
            "status": "invalid_arguments",
            "errors": [
                {"field": ".".join(map(str, x["loc"])), "type": x["type"]} for x in error.errors()
            ],
        }

    try:
        async with connection.transaction(readonly=True):
            if tool.embedding_table is None:
                result = await tool.handler(connection, **params)
            else:
                if embedding_client is None or not embedding_model:
                    return {"status": "unavailable", "reason": "embedding_service_not_configured"}
                # Table names are fixed in the registry. Model names are bound parameters.
                indexed = await connection.fetchval(
                    f"SELECT EXISTS (SELECT 1 FROM {tool.embedding_table} WHERE model = $1)",
                    embedding_model,
                )
                if not indexed:
                    return {"status": "unavailable", "reason": "embeddings_not_indexed"}
                result = await tool.handler(connection, embedding_client, embedding_model, **params)
    except (asyncpg.PostgresError, asyncpg.InterfaceError, TimeoutError, OSError):
        logger.exception("Database failure in %s", name)
        return {"status": "unavailable", "reason": "database_error"}
    except (httpx.HTTPError, ValueError):
        logger.exception("Embedding or decoding failure in %s", name)
        return {"status": "unavailable", "reason": "tool_runtime_error"}

    items = result.get("items", result) if isinstance(result, dict) else result
    return {"status": "ok" if items else "not_found", "data": result}
