import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import asyncpg
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import university_knowledge
from tools import campus, education, support

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


class KnowledgeSearch(OptionalBranch):
    query: Query | None = Field(None, description="Ключевые слова по названию или теме")
    category: Identifier | None = None
    reference_code: Annotated[str, Field(max_length=60)] | None = None


class KnowledgeRecord(Arguments):
    record_id: Identifier


class KnowledgeNotes(Arguments):
    query: Query
    category: Identifier | None = None


ProgramCode = Annotated[str, Field(pattern=r"^[0-9]{2}\.[0-9]{2}\.[0-9]{2}$")]
StudyForm = Literal["очная", "очно-заочная", "заочная"]
AcademicYear = Annotated[int, Field(ge=2000, le=2100)]


class AdmissionOptions(OptionalBranch):
    query: Query | None = Field(None, description="Название программы или направления")
    codes: list[ProgramCode] = Field(default_factory=list, max_length=5)
    metric: Literal["all", "programs", "tuition_fees", "passing_scores", "entrance_tests"] = "all"
    form: StudyForm | None = Field(None, description="Фильтр цен и проходных баллов")
    funding: Literal["budget", "contract"] | None = Field(
        None, description="Фильтр проходных баллов"
    )
    exam_scope: (
        Literal[
            "secondary_school_budget",
            "vocational_or_higher",
            "vocational_or_higher_contract",
            "english_language",
        ]
        | None
    ) = Field(None, description="Категория вступительных испытаний")
    year: AcademicYear | None = Field(None, description="Год приёмной кампании")
    max_annual_rub: int | None = Field(None, ge=0, description="Максимальная стоимость в год")
    max_passing_score: int | None = Field(None, ge=0, description="Верхняя граница прошлых баллов")


class Curricula(OptionalBranch):
    query: Query | None = Field(None, description="Название профиля или направления")
    reference_code: ProgramCode | None = None
    form: StudyForm | None = None
    entry_year: AcademicYear | None = None
    subject: Query | None = Field(None, description="Дисциплина из опубликованного списка")


class AdmissionRules(Arguments):
    topic: Literal["olympiads", "achievements", "medical_exam"]
    reference_code: ProgramCode | None = Field(None, description="Код для поиска медосмотра")
    year: AcademicYear | None = None


class UniversityContacts(OptionalBranch):
    person: Query | None = Field(None, description="Фамилия, имя или должность")
    unit: Query | None = Field(None, description="Фрагмент названия кафедры или института")
    kind: Literal[
        "all", "institutes", "departments", "staff", "leadership", "pedagogical_register"
    ] = "all"


class UniversityDates(OptionalBranch):
    topic: Literal["admission_deadlines", "housing_schedule"]
    year: AcademicYear | None = None


class Scholarships(Arguments):
    query: Query | None = Field(None, description="Имя стипендии или ключевые слова")
    kind: (
        Literal[
            "gas",
            "pgas",
            "gss",
            "increased_gss",
            "named",
            "federal",
            "external",
            "regional",
            "postgraduate",
            "freshmen",
        ]
        | None
    ) = None


class UniversityDocumentLinks(Arguments):
    query: Query | None = Field(None, description="Название, например академический отпуск")
    act_number: Annotated[str, Field(pattern=r"^0*[1-9][0-9]*$", max_length=12)] | None = None
    year: AcademicYear | None = None


class CampusDetails(OptionalBranch):
    query: Query | None = Field(None, description="Название объекта или адрес")
    kind: Literal["building", "dormitory", "education_site"] | None = None
    purpose: Literal["address", "accessibility", "history", "map"] = "address"


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
    "get_admission_options": Tool(
        "Сравнить программы, стоимость за год, прошлые проходные баллы и вступительные "
        "испытания. При точном вопросе укажи metric, коды направлений и известные фильтры.",
        AdmissionOptions,
        education.get_admission_options,
    ),
    "find_curricula": Tool(
        "Найти учебный план, календарный график, примеры практик и дисциплины по коду, "
        "профилю, форме или году набора. Учебный план не является расписанием занятий.",
        Curricula,
        education.find_curricula,
    ),
    "get_admission_rules": Tool(
        "Узнать условия приёма по олимпиаде (БВИ или 100 баллов), баллы за индивидуальные "
        "достижения либо требование о медосмотре. Для медосмотра укажи код направления.",
        AdmissionRules,
        education.get_admission_rules,
    ),
    "find_university_contacts": Tool(
        "Найти опубликованные контакты, адрес подразделения, руководителя или сотрудника "
        "по фамилии, должности, кафедре, институту или филиалу.",
        UniversityContacts,
        education.find_university_contacts,
    ),
    "get_university_dates": Tool(
        "Получить даты приёмной кампании или опубликованный график заселения по филиалу. "
        "Уточняй период и группу, к которым относятся даты.",
        UniversityDates,
        education.get_university_dates,
    ),
    "find_scholarships": Tool(
        "Найти размеры, условия и даты стипендий, включая академические, социальные, "
        "именные и выплаты первокурсникам. Для матпомощи используй инструменты поддержки.",
        Scholarships,
        education.find_scholarships,
    ),
    "find_university_document_links": Tool(
        "Найти оригинал приказа, положения или бланка по названию, номеру или году. "
        "Для объяснения правил по смыслу используй search_university_documents.",
        UniversityDocumentLinks,
        education.find_university_document_links,
    ),
    "find_campus_details": Tool(
        "Найти карточки из нового архива с адресом, координатами, доступной средой, "
        "паспортами доступности или историей здания. Для карты укажи purpose=map, "
        "филиал и название или тип объекта. Индивидуальную доступность уточняй.",
        CampusDetails,
        education.find_campus_details,
    ),
    "search_university_records": Tool(
        "Найти точные данные УУНиТ по ключевым словам, филиалу или коду направления. "
        "Категории включают programs, curricula, entrance_tests, passing_scores, tuition_fees, "
        "scholarships, admissions_rules, admission_deadlines, documents, staff, departments, "
        "campus_places, housing_schedule.",
        KnowledgeSearch,
        university_knowledge.search_records,
    ),
    "get_university_record": Tool(
        "Получить полную карточку и источники по идентификатору из search_university_records.",
        KnowledgeRecord,
        university_knowledge.get_record,
    ),
    "search_university_documents": Tool(
        "Найти по смыслу аннотации университетских документов, даты, правила и источники.",
        KnowledgeNotes,
        university_knowledge.search_notes,
        "rag.knowledge_embeddings",
    ),
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
