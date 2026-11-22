import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from http.client import HTTPException
from pathlib import Path
from time import time

from groups_service import GroupDirectory
from schedule_api import API_BASE, api_url, read_json, searchable

SCHEDULE_TYPES = {'group': 0, 'teacher': 1, 'room': 2}
# Семестр и начало учебного года совпадают с настройками веб-расписания УУНиТ.
ACADEMIC_YEAR = 2026
SEMESTER_ID = 241
UFA_TIME = timezone(timedelta(hours=5))
TIME_PATTERN = re.compile(r'^\s*(\d{1,2}):(\d{2})')
TEACHERS_CACHE = Path(__file__).resolve().parent / '.runtime' / 'schedule.sqlite3'
TEACHERS_CACHE_SECONDS = 3600


def _name_key(value):
    return ' '.join(searchable(value).split())


def _find_id(entries, query, label, id_option='--id'):
    key = _name_key(query)
    if not key:
        raise ValueError(f'Укажите значение для поиска: {label}')

    exact = []
    partial = []
    for entity_id, name in entries:
        name_key = _name_key(name)
        if key == name_key:
            exact.append((entity_id, name))
        elif key in name_key:
            partial.append((entity_id, name))

    matches = exact or partial
    if not matches:
        raise ValueError(f'Не удалось найти {label} по запросу «{query}»')
    if len(matches) > 1:
        choices = ', '.join(f'{name} ({entity_id})' for entity_id, name in matches[:8])
        raise ValueError(f'Уточните {label} или укажите {id_option}. Совпадения: {choices}')
    return matches[0][0]


def _directory(path, api_base):
    rows = read_json(api_url(path, api_base))
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f'Неожиданный формат справочника {path}')
    return rows


def _teachers(api_base):
    source_url = api_url('teachers', api_base)
    TEACHERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(TEACHERS_CACHE, timeout=30)) as cache, cache:
        # Другие запуски перепроверят срок кеша после завершения обновления.
        cache.execute('BEGIN IMMEDIATE')
        cache.execute('''
            CREATE TABLE IF NOT EXISTS teachers (
                source_url TEXT PRIMARY KEY,
                fetched_at REAL NOT NULL,
                entries TEXT NOT NULL
            )
        ''')
        entry = cache.execute(
            'SELECT fetched_at, entries FROM teachers WHERE source_url = ?', (source_url,),
        ).fetchone()
        if entry is not None and time() - entry[0] < TEACHERS_CACHE_SECONDS:
            return json.loads(entry[1])

        name_fields = ('surname', 'name', 'patronymic')
        teachers = [
            [row['isu_person_id'], ' '.join(row.get(part) or '' for part in name_fields)]
            for row in _directory('teachers', api_base)
        ]
        cache.execute('''
            INSERT OR REPLACE INTO teachers (source_url, fetched_at, entries) VALUES (?, ?, ?)
        ''', (source_url, time(), json.dumps(teachers, ensure_ascii=False)))
        return teachers


def find_entity_id(kind, name, *, building_id=None, organization_id=1, api_base=API_BASE):
    """Найти ID по названию группы, ФИО или номеру аудитории в корпусе."""
    if kind == 'group':
        groups = GroupDirectory(api_url('groups', api_base)).search(name)
        return _find_id(((row['group_id'], row['group_title']) for row in groups), name, 'группу')
    if kind == 'teacher':
        return _find_id(_teachers(api_base), name, 'ФИО преподавателя')
    if kind != 'room':
        raise ValueError(f'Неизвестный тип расписания: {kind}')
    if building_id is None:
        raise ValueError('Для поиска аудитории по номеру укажите корпус')
    if isinstance(building_id, str):
        rows = _directory(f'buildings/{organization_id}', api_base)
        buildings = ((row['building_id'], row['building_title']) for row in rows)
        building_id = _find_id(buildings, building_id, 'корпус', '--building-id')
    rows = _directory(f'audiences/{building_id}', api_base)
    return _find_id(((row['room_id'], row['room_title']) for row in rows), name, 'аудиторию')


def _week_start(day):
    return day - timedelta(days=day.weekday())


def _period(academic_year, on_date, week, all_weeks):
    year_start = _week_start(date(academic_year, 9, 1))
    year_end = _week_start(date(academic_year + 1, 9, 1)) - timedelta(days=1)
    if sum((on_date is not None, week is not None, all_weeks)) > 1:
        raise ValueError('Выберите один период: день, неделя или весь учебный год')
    if all_weeks:
        return year_start, year_start, year_end
    if on_date is not None:
        start = end = on_date
    else:
        max_week = (year_end - year_start).days // 7 + 1
        if week is not None and not 1 <= week <= max_week:
            raise ValueError(f'Номер учебной недели должен быть от 1 до {max_week}')
        start = (_week_start(datetime.now(UFA_TIME).date()) if week is None
                 else year_start + timedelta(weeks=week - 1))
        end = start + timedelta(days=6)
    if start < year_start or end > year_end:
        raise ValueError(f'Период вне учебного года {academic_year}/{academic_year + 1}')
    return year_start, start, end


def _dated_lessons(rows, year_start, start, end):
    if not isinstance(rows, list):
        raise ValueError('Источник вернул расписание в неожиданном формате')

    lessons = []
    first_week = (start - year_start).days // 7 + 1
    last_week = (end - year_start).days // 7 + 1
    for row in rows:
        if not isinstance(row, dict) or 'schedule_id' not in row:
            raise ValueError('Источник вернул занятие в неожиданном формате')
        if row['schedule_id'] == 0:
            continue
        weekday = row.get('schedule_weekday_id')
        weeks = row.get('schedule_weeks')
        if type(weekday) is not int or not 1 <= weekday <= 7 or not isinstance(weeks, list):
            raise ValueError('Источник вернул неверный день или список недель занятия')

        for week in sorted({int(value) for value in weeks if value != ''}):
            if first_week <= week <= last_week:
                day = year_start + timedelta(weeks=week - 1, days=weekday - 1)
                if start <= day <= end:
                    lessons.append({**row, 'date': day.isoformat()})

    def order(lesson):
        time = TIME_PATTERN.match(lesson.get('schedule_time_title') or '')
        minutes = 60 * int(time[1]) + int(time[2]) if time else 24 * 60
        return lesson['date'], minutes

    return sorted(lessons, key=order)


def get_schedule(kind, entity_id, *, on_date=None, week=None, all_weeks=False,
                 semester_id=SEMESTER_ID, academic_year=ACADEMIC_YEAR, api_base=API_BASE):
    """Получить занятия в JSON-совместимом виде за выбранный период."""
    if kind not in SCHEDULE_TYPES:
        raise ValueError(f'Неизвестный тип расписания: {kind}')
    if any(type(value) is not int or value < 1 for value in (entity_id, semester_id)):
        raise ValueError('ID должен быть положительным целым числом')
    year_start, start, end = _period(academic_year, on_date, week, all_weeks)
    path = f'schedule/{SCHEDULE_TYPES[kind]}/{entity_id}/semester/{semester_id}'
    rows = read_json(api_url(path, api_base))
    return {
        'kind': kind,
        'id': entity_id,
        'semester_id': semester_id,
        'date_from': start.isoformat(),
        'date_to': end.isoformat(),
        'lessons': _dated_lessons(rows, year_start, start, end),
    }


def _positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('ожидается положительное целое число')
    return value


def main():
    parser = argparse.ArgumentParser(
        description='Расписание группы, преподавателя или аудитории УУНиТ в JSON'
    )
    parser.add_argument('kind', choices=SCHEDULE_TYPES)
    entity = parser.add_mutually_exclusive_group(required=True)
    entity.add_argument('--id', type=_positive_int, help='ID группы, преподавателя или аудитории')
    entity.add_argument('--name', help='Название группы, ФИО или номер аудитории')
    building = parser.add_mutually_exclusive_group()
    building.add_argument('--building-id', type=int, help='ID корпуса для поиска аудитории')
    building.add_argument('--building', help='Название или часть адреса корпуса')
    parser.add_argument(
        '--organization-id', type=_positive_int, default=1, help='ID организации для поиска корпуса'
    )
    period = parser.add_mutually_exclusive_group()
    period.add_argument('--date', type=date.fromisoformat, help='Дата в формате ГГГГ-ММ-ДД')
    period.add_argument('--week', type=_positive_int, help='Номер учебной недели')
    period.add_argument('--all', action='store_true', help='Весь учебный год')
    parser.add_argument(
        '--semester-id', type=_positive_int, default=SEMESTER_ID, help='ID семестра в API'
    )
    parser.add_argument(
        '--academic-year', type=_positive_int, default=ACADEMIC_YEAR,
        help='Первый год учебного периода',
    )
    parser.add_argument('--api-base', default=API_BASE, help='Базовый адрес API расписания')
    options = parser.parse_args()

    building_ref = options.building_id if options.building_id is not None else options.building
    if options.building_id is not None and options.building_id < 0:
        parser.error('--building-id должен быть неотрицательным')
    if building_ref is not None and (options.kind != 'room' or options.name is None):
        parser.error('--building-id и --building применяются с room --name')

    try:
        entity_id = options.id if options.name is None else find_entity_id(
            options.kind, options.name, building_id=building_ref,
            organization_id=options.organization_id, api_base=options.api_base,
        )
        result = get_schedule(
            options.kind, entity_id, on_date=options.date, week=options.week, all_weeks=options.all,
            semester_id=options.semester_id, academic_year=options.academic_year,
            api_base=options.api_base,
        )
    except (OSError, ValueError, HTTPException, KeyError, TypeError, sqlite3.Error) as error:
        parser.exit(1, f'Ошибка получения расписания: {error}\n')
    output = json.dumps(result, ensure_ascii=False, indent=2)
    sys.stdout.buffer.write((output + '\n').encode('utf-8'))


if __name__ == '__main__':
    main()
