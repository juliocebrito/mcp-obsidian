import logging
import ssl
from urllib.parse import quote

import httpx
from mcp import MCPError
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import INTERNAL_ERROR

from .config import Settings

logger = logging.getLogger(__name__)

_MARKDOWN = {"Content-Type": "text/markdown"}
_WRITE_OK = (200, 201, 204)
_DELETE_OK = (200, 204)


def safe_path(path: str, *, allow_empty: bool = False) -> str:
    """Normaliza la ruta y rechaza cualquier intento de salir del vault."""
    cleaned = path.strip().replace("\\", "/").strip("/")
    if not cleaned:
        if allow_empty:
            return ""
        raise ToolError("La ruta no puede estar vacía.")
    if any(segment == ".." for segment in cleaned.split("/")):
        raise ToolError(f"Ruta no permitida: {path!r}. No se puede salir del vault con '..'.")
    return quote(cleaned, safe="/")


def _es_fallo_tls(exc: BaseException) -> bool:
    """httpx anida el SSLError bajo su propio ConnectError y el de httpcore."""
    causa: BaseException | None = exc
    for _ in range(10):
        if causa is None:
            return False
        if isinstance(causa, ssl.SSLError):
            return True
        causa = causa.__cause__ or causa.__context__
    return False


class ObsidianClient:
    """Cliente HTTP contra la Obsidian Local REST API."""

    def __init__(self, settings: Settings) -> None:
        self._url = settings.obsidian_url
        if not settings.verify_tls:
            logger.warning(
                "Verificación TLS desactivada contra %s. Descarga el certificado con "
                "`make cert` y apunta OBSIDIAN_VERIFY_TLS a él.",
                self._url,
            )
        self._client = httpx.AsyncClient(
            base_url=self._url,
            headers={
                "Authorization": f"Bearer {settings.obsidian_token}",
                "Accept": "application/json",
            },
            verify=settings.verify_tls,
            timeout=60.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Sin distinguirlos, un certificado rechazado se anuncia como "Obsidian no
            # está abierto" y manda a mirar donde no es.
            if _es_fallo_tls(exc):
                message = (
                    f"El certificado de Obsidian en {self._url} no supera la verificación. "
                    "Descarga el actual con `make cert` y apunta OBSIDIAN_VERIFY_TLS a él."
                )
            else:
                message = (
                    f"No se pudo conectar con Obsidian en {self._url}. "
                    "Comprueba que Obsidian esté abierto y el plugin Local REST API activo."
                )
            raise MCPError(code=INTERNAL_ERROR, message=message) from exc

    @staticmethod
    def _body(response: httpx.Response) -> str:
        if response.status_code != 200:
            raise ToolError(f"Error {response.status_code}: {response.text}")
        return response.text

    @staticmethod
    def _confirm(response: httpx.Response, message: str, expected=_WRITE_OK) -> str:
        if response.status_code not in expected:
            raise ToolError(f"Error {response.status_code}: {response.text}")
        return message

    async def search(self, query: str) -> str:
        response = await self._request("POST", "/search/simple/", params={"query": query})
        return self._body(response)

    async def read(self, path: str) -> str:
        response = await self._request("GET", f"/vault/{safe_path(path)}")
        return self._body(response)

    async def _exists(self, target: str) -> bool:
        response = await self._request("GET", f"/vault/{target}")
        return response.status_code == 200

    async def write(self, path: str, content: str, *, overwrite: bool = False) -> str:
        target = safe_path(path)
        if not overwrite and await self._exists(target):
            raise ToolError(
                f"La nota '{path}' ya existe y no se sobrescribe. Usa append_note para "
                "añadir contenido al final, o elige otra ruta."
            )
        response = await self._request(
            "PUT", f"/vault/{target}", headers=_MARKDOWN, content=content.encode("utf-8")
        )
        return self._confirm(response, "Nota guardada con éxito.")

    async def append(self, path: str, content: str) -> str:
        target = safe_path(path)
        response = await self._request(
            "POST", f"/vault/{target}", headers=_MARKDOWN, content=f"\n{content}".encode("utf-8")
        )
        return self._confirm(response, "Contenido anexado con éxito.")

    async def list_directory(self, path: str) -> str:
        # La barra final no es opcional: sin ella la API cree que pides una nota y devuelve 404.
        directory = safe_path(path, allow_empty=True)
        response = await self._request("GET", f"/vault/{directory}/" if directory else "/vault/")
        return self._body(response)

    async def move(self, source_path: str, destination_path: str) -> str:
        source = safe_path(source_path)
        destination = safe_path(destination_path)
        response = await self._request(
            "POST", f"/vault/{destination}", headers={"X-Moved-From": f"/{source}"}
        )
        return self._confirm(response, f"Nota movida con éxito a {destination_path}.")

    async def delete(self, path: str) -> str:
        response = await self._request("DELETE", f"/vault/{safe_path(path)}")
        return self._confirm(response, "Nota eliminada con éxito.", expected=_DELETE_OK)
