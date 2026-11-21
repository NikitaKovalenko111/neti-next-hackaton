import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "data" / "student-info"
DATASETS = (
    "programs",
    "entrance-tests",
    "passing-scores",
    "tuition-fees",
    "bvi",
    "freshmen-scholarship",
    "scholarships",
    "material-aid",
    "documents",
    "institutes",
    "departments",
    "staff",
    "leadership",
    "pedagogical-register",
    "manifest",
    "admission-seats",
    "admission-calendar",
    "transfer-vacancies",
    "mavlyutov-readings",
)


def load(dataset):
    return json.loads((ROOT / f"{dataset}.json").read_text(encoding="utf-8"))


def searchable(value):
    return str(value or "").casefold().replace("ё", "е")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=DATASETS)
    parser.add_argument("--query")
    parser.add_argument("--branch")
    parser.add_argument("--code")
    parser.add_argument("--unit")
    parser.add_argument("--department")
    parser.add_argument("--scope")
    parser.add_argument("--funding", choices=("budget", "contract"))
    parser.add_argument("--limit", type=int)
    options = parser.parse_args()
    if options.limit is not None and options.limit < 1:
        parser.error("--limit должен быть положительным")
    try:
        data = load(options.dataset)
        if isinstance(data, list):
            department_branches = (
                {row["id"]: row["branch"] for row in load("departments")}
                if options.dataset == "staff" and options.branch
                else {}
            )
            unit_branches = (
                {row["id"]: row["branch"] for row in load("institutes")}
                if options.dataset == "leadership" and options.branch
                else {}
            )
            checks = {
                "code": options.code,
                "scope": options.scope,
                {"leadership": "unit_id", "institutes": "id"}.get(
                    options.dataset, "parent_unit_id"
                ): options.unit,
                "id" if options.dataset == "departments" else "department_id": options.department,
            }
            data = [
                row
                for row in data
                if all(value is None or row.get(field) == value for field, value in checks.items())
                and (
                    options.funding is None
                    or row.get("funding") == options.funding
                    or isinstance(row.get("funding"), list)
                    and options.funding in row["funding"]
                )
                and (
                    not options.branch
                    or options.branch
                    == (
                        row.get("branch")
                        or department_branches.get(row.get("department_id"))
                        or unit_branches.get(row.get("unit_id"))
                    )
                )
                and (
                    not options.query
                    or searchable(options.query)
                    in searchable(
                        " ".join(
                            str(row.get(field) or "")
                            for field in (
                                "name",
                                "full_name",
                                "direction",
                                "program",
                                "title",
                                "role",
                                "academic_unit",
                            )
                        )
                    )
                )
            ]
            if options.limit is not None:
                data = data[: options.limit]
        elif any(
            (
                options.query,
                options.branch,
                options.code,
                options.unit,
                options.department,
                options.scope,
                options.funding,
                options.limit,
            )
        ):
            parser.error("Фильтры доступны только для файлов-массивов")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    sys.stdout.buffer.write((json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
