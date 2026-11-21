import argparse
import asyncio
import json

import httpx

from app.config import Settings
from app.storage import connect_rag
from tools import call_tool, tool_definitions


async def run_tool(name: str, arguments: dict) -> dict:
    settings = Settings()
    async with (
        connect_rag(settings) as connection,
        httpx.AsyncClient(
            base_url=str(settings.ollama_base_url), timeout=settings.ollama_timeout_seconds
        ) as client,
    ):
        return await call_tool(
            connection,
            name,
            arguments,
            embedding_client=client,
            embedding_model=settings.ollama_embedding_model,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="List and run university database tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    call = commands.add_parser("call")
    call.add_argument("name")
    call.add_argument("arguments", nargs="?", default="{}")
    args = parser.parse_args()

    if args.command == "list":
        result = tool_definitions()
    else:
        try:
            arguments = json.loads(args.arguments)
        except json.JSONDecodeError as error:
            parser.error(f"Invalid JSON: {error.msg}")
        if not isinstance(arguments, dict):
            parser.error("Arguments must be a JSON object")
        result = asyncio.run(run_tool(args.name, arguments))

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
