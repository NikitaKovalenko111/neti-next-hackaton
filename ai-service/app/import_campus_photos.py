import asyncio
import hashlib
import io
import logging
import re
from importlib.resources import files
from urllib.parse import urlsplit

import httpx
from minio import Minio
from minio.error import S3Error

from app.config import Settings
from app.storage import connect_rag, migrate

PHOTO_PREFIX = "campus/"
CONTENT_TYPE = "image/jpeg"
MAX_IMAGE_BYTES = 12 * 1024 * 1024
PHOTO_HOSTS = {"uust.ru", "birsk.uust.ru", "static.tildacdn.com", "i.vuzopedia.ru"}
logger = logging.getLogger(__name__)


async def download_photo(client: httpx.AsyncClient, url: str) -> bytes:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in PHOTO_HOSTS
        or parsed.username is not None
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Unsupported photo source")

    async with client.stream("GET", url) as response:
        response.raise_for_status()
        image = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
            if len(image) + len(chunk) > MAX_IMAGE_BYTES:
                raise ValueError("Photo exceeds the download limit")
            image.extend(chunk)
    if not image.startswith(b"\xff\xd8\xff") or not image.endswith(b"\xff\xd9"):
        raise ValueError("Photo source did not return a JPEG image")
    return bytes(image)


async def stored_photo(storage: Minio, bucket: str, key: str) -> bool:
    try:
        await asyncio.to_thread(storage.stat_object, bucket, key)
    except S3Error as error:
        if error.code in {"NoSuchKey", "NoSuchObject"}:
            return False
        raise
    return True


async def import_photos(settings: Settings) -> int:
    storage = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key.get_secret_value(),
        secret_key=settings.minio_secret_key.get_secret_value(),
        secure=settings.minio_secure,
        region=settings.minio_region,
    )
    bucket = settings.minio_bucket
    if not await asyncio.to_thread(storage.bucket_exists, bucket):
        try:
            await asyncio.to_thread(storage.make_bucket, bucket, location=settings.minio_region)
        except S3Error as error:
            if error.code != "BucketAlreadyOwnedByYou":
                raise

    uploaded = 0
    async with connect_rag(settings) as connection, httpx.AsyncClient(timeout=20) as client:
        await migrate(connection)
        rows = await connection.fetch("SELECT id, url FROM rag.campus_photos ORDER BY id")
        for row in rows:
            photo_id, url = row["id"], row["url"]
            if not re.fullmatch(r"[a-z0-9-]+", photo_id):
                raise ValueError(f"Invalid photo ID: {photo_id}")
            bundled = files("app.migrations").joinpath("campus_photos", f"{photo_id}.jpg")
            embedded_image = bundled.read_bytes() if bundled.is_file() else None
            version = hashlib.sha256(embedded_image or url.encode()).hexdigest()[:16]
            key = f"{PHOTO_PREFIX}{photo_id}-{version}.jpg"

            if not await stored_photo(storage, bucket, key):
                try:
                    image = embedded_image or await download_photo(client, url)
                except (httpx.HTTPError, ValueError) as error:
                    logger.warning("Photo %s unavailable: %s", photo_id, error)
                    await connection.execute(
                        """
                        UPDATE rag.campus_photos
                        SET minio_bucket = NULL, object_key = NULL, content_type = NULL
                        WHERE id = $1 AND url = $2
                        """,
                        photo_id,
                        url,
                    )
                    continue
                await asyncio.to_thread(
                    storage.put_object,
                    bucket,
                    key,
                    io.BytesIO(image),
                    len(image),
                    content_type=CONTENT_TYPE,
                )
                uploaded += 1

            await connection.execute(
                """
                UPDATE rag.campus_photos
                SET minio_bucket = $1, object_key = $2, content_type = $3
                WHERE id = $4 AND url = $5
                """,
                bucket,
                key,
                CONTENT_TYPE,
                photo_id,
                url,
            )
    return uploaded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("Uploaded %d campus photos", asyncio.run(import_photos(Settings())))
