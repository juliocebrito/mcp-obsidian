import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from pydantic import AnyHttpUrl

from .auth import LocalAuthProvider
from .client import ObsidianClient
from .config import Settings, load_settings

logger = logging.getLogger(__name__)


class StaticTokenVerifier(TokenVerifier):
    """Acepta un único token compartido leído de MCP_AUTH_TOKEN."""

    def __init__(self, expected: str) -> None:
        self._expected = expected

    async def verify_token(self, token: str) -> AccessToken | None:
        if secrets.compare_digest(token, self._expected):
            return AccessToken(token=token, client_id="mcp-obsidian", scopes=[])
        return None


def _auth_kwargs(settings: Settings) -> dict:
    if not settings.auth_enabled:
        return {}
    auth = AuthSettings(
        issuer_url=AnyHttpUrl(settings.issuer_url),
        resource_server_url=AnyHttpUrl(settings.resource_url),
        client_registration_options=ClientRegistrationOptions(enabled=False),
        revocation_options=RevocationOptions(enabled=True),
    )
    # El provider OAuth también valida el token estático, así que sustituye al verifier.
    if settings.oauth_enabled:
        return {"auth_server_provider": LocalAuthProvider(settings), "auth": auth}
    return {"token_verifier": StaticTokenVerifier(settings.auth_token or ""), "auth": auth}


@asynccontextmanager
async def _lifespan(_: MCPServer) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await obsidian.aclose()


# Puntero, no copia: el protocolo vive en el vault y se versiona con las notas que rige.
# Un agente que entra por MCP no tiene dotfiles donde alojar el disparador, así que viaja
# aquí, en el initialize del protocolo, antes de su primer turno.
INSTRUCTIONS = """Este vault tiene un protocolo de escritura propio, en `AGENTS.md`
(raíz del vault).

Antes de escribir, crear o modificar cualquier nota, léelo con `get_note("AGENTS.md")`
y sigue lo que diga. Cubre dónde va cada cosa, el formato exacto y qué hacer al terminar.

No deduzcas la estructura del vault listando carpetas: las rutas correctas están en ese
fichero."""

settings = load_settings()
obsidian = ObsidianClient(settings)
mcp = MCPServer(
    "obsidian-local-rest-api",
    version="1.0.0",
    instructions=INSTRUCTIONS,
    lifespan=_lifespan,
    **_auth_kwargs(settings),
)


@mcp.tool()
async def search_notes(query: str) -> str:
    """Busca notas en el vault por término o palabra clave.

    Args:
        query: Término a buscar
    """
    return await obsidian.search(query)


@mcp.tool()
async def get_note(path: str) -> str:
    """Obtiene el contenido completo de una nota.

    Args:
        path: Nombre o ruta del archivo
    """
    return await obsidian.read(path)


@mcp.tool()
async def list_directory(path: str = "") -> str:
    """Lista el contenido de archivos y carpetas del vault.

    Args:
        path: Ruta del directorio (dejar vacío para la raíz)
    """
    return await obsidian.list_directory(path)


async def create_note(path: str, content: str) -> str:
    """Crea una nota en el vault. Salvo que el servidor permita sobrescribir, falla si la ruta ya existe.

    Args:
        path: Ruta/nombre del archivo .md
        content: Contenido Markdown
    """
    return await obsidian.write(path, content, overwrite=settings.allow_destructive)


async def append_note(path: str, content: str) -> str:
    """Añade texto al final de una nota existente sin sobrescribirla.

    Args:
        path: Ruta/nombre del archivo .md
        content: Contenido a anexar
    """
    return await obsidian.append(path, content)


async def move_note(source_path: str, destination_path: str) -> str:
    """Mueve o renombra una nota. La nota deja de existir en la ruta de origen.

    Args:
        source_path: Ruta de origen de la nota
        destination_path: Ruta de destino deseada
    """
    return await obsidian.move(source_path, destination_path)


async def delete_note(path: str) -> str:
    """Elimina una nota del vault de forma permanente e irreversible.

    Args:
        path: Ruta de la nota a eliminar
    """
    return await obsidian.delete(path)


# Una herramienta no registrada no existe para el modelo: no puede invocarla ni verla.
if not settings.read_only:
    mcp.tool()(create_note)
    mcp.tool()(append_note)
    if settings.allow_destructive:
        mcp.tool()(move_note)
        mcp.tool()(delete_note)

if settings.read_only:
    logger.info("Modo solo lectura: solo se publican search_notes, get_note y list_directory.")
elif not settings.allow_destructive:
    logger.info(
        "move_note y delete_note no se publican y create_note no sobrescribe notas existentes. "
        "Define MCP_ALLOW_DESTRUCTIVE=1 para levantar ambas restricciones."
    )
else:
    logger.warning(
        "MCP_ALLOW_DESTRUCTIVE=1: delete_note puede borrar notas y create_note puede "
        "reemplazarlas, en ambos casos de forma irreversible."
    )
