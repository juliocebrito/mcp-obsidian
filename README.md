## Puesta en marcha

```sh
cp .env.example .env
# Edita .env y pon el token real de Obsidian antes de arrancar el servidor.

make install    # instala dependencias
make cert       # descarga la CA de Obsidian para verificar TLS
make stdio      # transporte stdio, para agentes locales
make serve      # streamable-http (MCP_PORT=8001 por defecto)
make dev        # el anterior + ngrok
make tunnel     # solo ngrok
make inspector  # MCP Inspector por stdio
```

## Conectar un agente por stdio

El servidor arranca con `uv run --env-file .env python -m mcp_obsidian` y el `cwd` en la
raíz del repositorio. El token se queda en `.env`: ningún cliente necesita copiarlo.

### OpenClaw

```sh
openclaw mcp add obsidian --command=$(command -v uv) \
  --arg=run --arg=--env-file --arg=.env --arg=python --arg=-m --arg=mcp_obsidian \
  --cwd=$PWD
openclaw mcp reload
```

Los valores que empiezan por `--` exigen la forma `--arg=valor`; separados fallan con un
`node: --arg: not found` que no dice nada. Para comprobarlo: `openclaw mcp probe obsidian`
debe listar 5 herramientas, y `openclaw mcp doctor` responder `ok`.

