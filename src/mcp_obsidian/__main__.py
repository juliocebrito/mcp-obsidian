import argparse
import logging
import sys

from mcp.server.transport_security import TransportSecuritySettings

from .config import ConfigError, default_port


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="mcp-obsidian")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=default_port())
    # Gemini Spark habla el JSON-RPC plano y sin sesión del proxy antiguo.
    parser.add_argument("--sse", dest="json_response", action="store_false")
    parser.add_argument("--stateful", dest="stateless", action="store_false")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    try:
        from .server import mcp, settings
    except ConfigError as exc:
        logging.error("%s", exc)
        return 1

    if args.transport == "stdio":
        mcp.run()
        return 0

    if not settings.auth_enabled:
        logging.warning(
            "MCP_AUTH_TOKEN no está definido: el endpoint HTTP queda sin autenticar. "
            "Aceptable solo en localhost, nunca detrás de ngrok."
        )

    # Sin allowlist el SDK solo acepta Host de localhost y devuelve 421 detrás de ngrok.
    security = None
    if settings.allowed_hosts:
        security = TransportSecuritySettings(
            allowed_hosts=settings.allowed_hosts,
            allowed_origins=settings.allowed_origins,
        )
    mcp.run(
        transport="streamable-http",
        host=args.host,
        port=args.port,
        json_response=args.json_response,
        stateless_http=args.stateless,
        transport_security=security,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
