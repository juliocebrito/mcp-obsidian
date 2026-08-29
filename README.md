cp .env.example .env
# Edit .env and set the real Obsidian token before starting the server.

make install   # install dependencies
make dev       # run uvicorn + ngrok together
make serve     # run only uvicorn (PORT=8000 by default)
make tunnel    # run only ngrok

# Servidor MCP con el SDK oficial (src/mcp_obsidian), en paralelo al proxy de main.py.
# Ver docs/plan-mcp-puro.md.
make stdio      # transporte stdio, para agentes locales
make serve-mcp  # streamable-http (MCP_PORT=8001 por defecto)
make dev-mcp    # el anterior + ngrok
make inspector  # MCP Inspector por stdio
