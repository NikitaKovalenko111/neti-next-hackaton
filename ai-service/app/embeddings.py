import json
import math

import httpx

DIMENSIONS = 1024
BATCH_SIZE = 16


async def embed(client: httpx.AsyncClient, model: str, texts: list[str]) -> list[str]:
    response = await client.post(
        "embeddings",
        json={"model": model, "input": texts, "dimensions": DIMENSIONS, "encoding_format": "float"},
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) != len(texts):
        raise ValueError("OpenRouter returned an unexpected number of embeddings")

    by_index = {}
    for item in items:
        index = item.get("index") if isinstance(item, dict) else None
        if type(index) is not int or not 0 <= index < len(texts) or index in by_index:
            raise ValueError("OpenRouter returned an invalid embedding index")
        by_index[index] = item.get("embedding")
    vectors = [by_index[index] for index in range(len(texts))]

    for vector in vectors:
        if (
            not isinstance(vector, list)
            or len(vector) != DIMENSIONS
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
            or not any(vector)
        ):
            raise ValueError("OpenRouter returned an invalid embedding")

    return [json.dumps(vector) for vector in vectors]
