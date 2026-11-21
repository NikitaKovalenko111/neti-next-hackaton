import json
import math

import httpx

DIMENSIONS = 1024
BATCH_SIZE = 16


async def embed(client: httpx.AsyncClient, model: str, texts: list[str]) -> list[str]:
    response = await client.post(
        "/api/embed",
        json={"model": model, "input": texts, "dimensions": DIMENSIONS, "truncate": False},
    )
    response.raise_for_status()
    vectors = response.json().get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError("Ollama returned an unexpected number of embeddings")

    for vector in vectors:
        if (
            not isinstance(vector, list)
            or len(vector) != DIMENSIONS
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector)
            or not any(vector)
        ):
            raise ValueError("Ollama returned an invalid embedding")

    return [json.dumps(vector) for vector in vectors]
