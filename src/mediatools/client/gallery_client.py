from __future__ import annotations

import types
import typing
from urllib.parse import quote

try:
    import httpx
except ImportError as e:  # pragma: no cover
    raise ImportError("mediatools.client requires the 'client' extra: pip install 'mediatools[client]'") from e

from ..application.errors import DirectoryNotIndexedError, GalleryError
from ..contracts import DirectoryPage, ErrorResponse, PathList


class GalleryClientError(GalleryError):
    '''Unexpected error response from the gallery API.'''

    def __init__(self, status_code: int, detail: str):
        super().__init__(f"HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class GalleryClient:
    '''Typed HTTP client for the gallery JSON API under `/api`.'''

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 10.0,
        headers: typing.Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ):
        if http_client is None:
            if base_url is None:
                raise ValueError("Either base_url or http_client must be provided.")
            http_client = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)
        self._http = http_client

    def get_directory(self, rel_path: str = ".") -> DirectoryPage:
        '''Get the page data for a directory relative to the gallery root.'''
        response = self._http.get(f"/api/directory/{quote(rel_path)}")
        if response.status_code == 404:
            raise DirectoryNotIndexedError(self._detail(response))
        return DirectoryPage.model_validate(self._ok(response).json())

    def list_directories(self) -> list[str]:
        '''List all indexed directories relative to the gallery root.'''
        return PathList.model_validate(self._ok(self._http.get("/api/directories")).json()).paths

    def list_videos(self) -> list[str]:
        '''List all indexed videos relative to the gallery root.'''
        return PathList.model_validate(self._ok(self._http.get("/api/videos")).json()).paths

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> typing.Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> None:
        self.close()

    @classmethod
    def _ok(cls, response: httpx.Response) -> httpx.Response:
        if response.is_error:
            raise GalleryClientError(response.status_code, cls._detail(response))
        return response

    @staticmethod
    def _detail(response: httpx.Response) -> str:
        try:
            return ErrorResponse.model_validate(response.json()).detail
        except ValueError:
            return response.text
