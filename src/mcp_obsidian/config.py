import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Falta configuración obligatoria o tiene un valor inaceptable."""


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    obsidian_url: str
    obsidian_token: str
    verify_tls: bool
    read_only: bool
    allow_destructive: bool
    auth_token: str | None
    oauth_client_id: str | None
    oauth_client_secret: str | None
    oauth_redirect_uris: list[str]
    issuer_url: str
    resource_url: str
    allowed_hosts: list[str]
    allowed_origins: list[str]

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_token) or self.oauth_enabled

    @property
    def oauth_enabled(self) -> bool:
        return bool(self.oauth_client_id and self.oauth_client_secret)


def default_port() -> int:
    return int(os.environ.get("MCP_PORT", "8001"))


def load_settings() -> Settings:
    token = os.environ.get("OBSIDIAN_TOKEN")
    if not token:
        raise ConfigError(
            "OBSIDIAN_TOKEN debe estar configurado como variable de entorno. "
            "Copia .env.example a .env y ejecuta con `uv run --env-file .env`."
        )

    default_resource = f"http://127.0.0.1:{default_port()}/mcp"
    return Settings(
        obsidian_url=os.environ.get("OBSIDIAN_URL", "https://127.0.0.1:27124").rstrip("/"),
        obsidian_token=token,
        verify_tls=_flag("OBSIDIAN_VERIFY_TLS", default=False),
        read_only=_flag("MCP_READ_ONLY", default=False),
        allow_destructive=_flag("MCP_ALLOW_DESTRUCTIVE", default=False),
        auth_token=os.environ.get("MCP_AUTH_TOKEN") or None,
        oauth_client_id=os.environ.get("MCP_OAUTH_CLIENT_ID") or None,
        oauth_client_secret=os.environ.get("MCP_OAUTH_CLIENT_SECRET") or None,
        oauth_redirect_uris=_list("MCP_OAUTH_REDIRECT_URIS"),
        issuer_url=os.environ.get("MCP_ISSUER_URL", default_resource),
        resource_url=os.environ.get("MCP_RESOURCE_URL", default_resource),
        allowed_hosts=_list("MCP_ALLOWED_HOSTS"),
        allowed_origins=_list("MCP_ALLOWED_ORIGINS"),
    )
