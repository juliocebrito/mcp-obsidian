"""Authorization server mínimo para clientes que solo hablan OAuth, como Gemini.

Un único cliente preconfigurado (`MCP_OAUTH_CLIENT_ID` / `MCP_OAUTH_CLIENT_SECRET`) y el flujo
`authorization_code` con PKCE. No hay pantalla de consentimiento: no existe un usuario al que
preguntar, así que `/authorize` aprueba siempre. Lo que protege el vault es el secreto de cliente,
sin el cual el código de autorización no puede canjearse por un token.
"""

import logging
import secrets
import time
from urllib.parse import urlencode, urlparse, urlunparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from .config import Settings
from .store import TokenStore

logger = logging.getLogger(__name__)

CODE_TTL_SECONDS = 300
TOKEN_TTL_SECONDS = 3600
REFRESH_TTL_SECONDS = 30 * 24 * 3600


class LocalAuthProvider(OAuthAuthorizationServerProvider):
    def __init__(self, settings: Settings) -> None:
        self._static_token = settings.auth_token
        self._resource = settings.resource_url
        self._codes: dict[str, AuthorizationCode] = {}
        self._store = TokenStore(settings.token_store_path)
        redirect_uris = [AnyUrl(uri) for uri in settings.oauth_redirect_uris] or None
        if redirect_uris is None:
            logger.warning(
                "MCP_OAUTH_REDIRECT_URIS está vacío: /authorize rechazará cualquier intento. "
                "Conecta el cliente una vez y lee la redirect_uri del error 400 para fijarla aquí."
            )
        self._client = OAuthClientInformationFull(
            client_id=settings.oauth_client_id or "",
            client_secret=settings.oauth_client_secret,
            redirect_uris=redirect_uris,
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="client_secret_post",
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        if secrets.compare_digest(client_id, self._client.client_id):
            return self._client
        logger.warning("client_id desconocido en la petición OAuth.")
        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise NotImplementedError("El registro dinámico de clientes está deshabilitado.")

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        code = AuthorizationCode(
            code=secrets.token_urlsafe(32),
            scopes=params.scopes or [],
            expires_at=time.time() + CODE_TTL_SECONDS,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )
        self._codes[code.code] = code

        query = {"code": code.code}
        if params.state:
            query["state"] = params.state
        parsed = urlparse(str(params.redirect_uri))
        merged = f"{parsed.query}&{urlencode(query)}" if parsed.query else urlencode(query)
        return urlunparse(parsed._replace(query=merged))

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self._codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        if code.expires_at < time.time():
            del self._codes[authorization_code]
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # De un solo uso: si el código se filtra, ya no sirve una segunda vez.
        self._codes.pop(authorization_code.code, None)
        logger.info("Token de acceso emitido para el cliente OAuth.")
        return self._issue(
            client.client_id, authorization_code.scopes, authorization_code.resource
        )

    def _issue(
        self, client_id: str, scopes: list[str], resource: str | None
    ) -> OAuthToken:
        now = int(time.time())
        access = AccessToken(
            token=secrets.token_urlsafe(32),
            client_id=client_id,
            scopes=scopes,
            expires_at=now + TOKEN_TTL_SECONDS,
            resource=resource,
        )
        refresh = RefreshToken(
            token=secrets.token_urlsafe(32),
            client_id=client_id,
            scopes=scopes,
            expires_at=now + REFRESH_TTL_SECONDS,
        )
        self._store.put("access", access.token, access.model_dump(mode="json"))
        # RefreshToken no tiene campo resource, pero el access token que salga de él sí lo necesita.
        self._store.put(
            "refresh",
            refresh.token,
            refresh.model_dump(mode="json") | {"resource": resource},
        )
        return OAuthToken(
            access_token=access.token,
            token_type="Bearer",
            expires_in=TOKEN_TTL_SECONDS,
            refresh_token=refresh.token,
            scope=" ".join(scopes) or None,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        if self._static_token and secrets.compare_digest(token, self._static_token):
            return AccessToken(
                token=token,
                client_id="mcp-obsidian",
                scopes=[],
                resource=self._resource,
            )
        data = self._store.get("access", token)
        if data is None:
            return None
        access = AccessToken.model_validate(data)
        if access.expires_at is not None and access.expires_at < time.time():
            self._store.pop("access", token)
            return None
        return access

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        data = self._store.get("refresh", refresh_token)
        if data is None:
            return None
        token = RefreshToken.model_validate(data)
        if token.client_id != client.client_id:
            return None
        if token.expires_at is not None and token.expires_at < time.time():
            self._store.pop("refresh", refresh_token)
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        data = self._store.get("refresh", refresh_token.token)
        resource = data.get("resource") if data else None
        # Rotación: el refresh usado deja de valer, así que uno robado sirve una vez como mucho.
        self._store.pop("refresh", refresh_token.token)
        logger.info("Token de acceso renovado para el cliente OAuth.")
        return self._issue(client.client_id, scopes, resource)

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        self._store.pop("access", token.token)
        self._store.pop("refresh", token.token)
