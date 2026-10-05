"""Dependency-free HTTP client for the AI Bus Whisper test flow."""

from __future__ import annotations

import json
import mimetypes
import ssl
import uuid
from dataclasses import dataclass
from http.cookiejar import CookieJar
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener


LOGIN_PATH = "/api/auth/login"
TRANSCRIPTIONS_PATH = "/api/gateway/stt-custom-mock/v1/audio/transcriptions"
SESSION_COOKIE_NAME = "aibus_admin"


class NetworkError(RuntimeError):
    """A transport, TLS, or timeout error while calling AI Bus."""


@dataclass
class ApiResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


def extract_session_token(response: ApiResponse) -> str | None:
    """Read the documented session token from the Set-Cookie response header."""
    set_cookie = response.headers.get("Set-Cookie", "")
    if not set_cookie:
        return None
    cookie = SimpleCookie()
    try:
        cookie.load(set_cookie)
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE_NAME)
    return morsel.value if morsel else None


class ApiBusClient:
    def __init__(self, base_url: str, verify_tls: bool = True) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.verify_tls = verify_tls
        self.cookie_jar = CookieJar()
        handlers: list[Any] = [HTTPCookieProcessor(self.cookie_jar)]
        if not verify_tls:
            handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
        self.opener = build_opener(*handlers)
        self.session_token: str | None = None

    def url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _post(self, url: str, data: bytes, headers: dict[str, str], timeout: int) -> ApiResponse:
        request = Request(url, data=data, headers=headers, method="POST")
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return ApiResponse(response.status, dict(response.headers.items()), response.read())
        except HTTPError as response:
            return ApiResponse(response.code, dict(response.headers.items()), response.read())
        except (URLError, TimeoutError, OSError) as exc:
            raise NetworkError(str(exc)) from exc

    def login(self, username: str, password: str) -> ApiResponse:
        body = json.dumps({"username": username, "password": password}).encode("utf-8")
        response = self._post(
            self.url(LOGIN_PATH),
            body,
            {"Content-Type": "application/json", "Accept": "application/json"},
            timeout=30,
        )
        if response.ok:
            self.session_token = extract_session_token(response) or self._cookie_token()
        return response

    def _cookie_token(self) -> str | None:
        for cookie in self.cookie_jar:
            if cookie.name == SESSION_COOKIE_NAME:
                return cookie.value
        return None

    def transcribe(
        self,
        audio_path: str | Path,
        api_key: str,
        model: str = "whisper-1",
        language: str = "fa",
        timeout: int = 180,
    ) -> ApiResponse:
        if not self.session_token:
            raise RuntimeError("ابتدا وارد شوید تا توکن نشست دریافت شود.")
        if not api_key.strip():
            raise ValueError("API Key وارد نشده است.")

        path = Path(audio_path)
        if not path.is_file():
            raise FileNotFoundError(f"فایل صوتی پیدا نشد: {path}")

        boundary = uuid.uuid4().hex
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = bytearray()
        fields = {"model": model.strip(), "language": language.strip()}
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode("ascii"))
            body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
            body.extend(value.encode("utf-8"))
            body.extend(b"\r\n")

        body.extend(f"--{boundary}\r\n".encode("ascii"))
        body.extend(
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("ascii"))
        body.extend(path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("ascii"))

        headers = {
            "Authorization": f"Bearer {self.session_token}",
            "X-API-Key": api_key.strip(),
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        }
        return self._post(self.url(TRANSCRIPTIONS_PATH), bytes(body), headers, timeout)

