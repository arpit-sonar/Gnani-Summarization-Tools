import httpx

from .config import settings

_BASE = f"{settings.SUPABASE_URL}/storage/v1"
_HEADERS = {
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    "apikey": settings.SUPABASE_SERVICE_KEY,
}


class StorageError(RuntimeError):
    pass


def create_signed_upload_url(key: str) -> str:
    url = f"{_BASE}/object/upload/sign/{settings.SUPABASE_BUCKET}/{key}"
    r = httpx.post(url, headers=_HEADERS, timeout=20)
    if r.status_code >= 400:
        raise StorageError(f"signed upload url failed: {r.status_code} {r.text}")
    path = r.json()["url"]
    return path if path.startswith("http") else f"{_BASE}{path}"


def create_signed_download_url(key: str, expires_in: int = 3600) -> str:
    url = f"{_BASE}/object/sign/{settings.SUPABASE_BUCKET}/{key}"
    r = httpx.post(url, headers=_HEADERS, json={"expiresIn": expires_in}, timeout=20)
    if r.status_code >= 400:
        raise StorageError(f"signed download url failed: {r.status_code} {r.text}")
    return f"{_BASE}{r.json()['signedURL']}"


def object_exists(key: str) -> tuple[bool, int | None]:
    try:
        signed = create_signed_download_url(key, expires_in=60)
    except StorageError:
        return False, None
    r = httpx.head(signed, timeout=20, follow_redirects=True)
    if r.status_code != 200:
        return False, None
    length = r.headers.get("content-length")
    return True, int(length) if length else None