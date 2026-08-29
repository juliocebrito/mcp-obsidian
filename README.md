cp .env.example .env
# Edit .env and set the real Obsidian token before starting the server.

make install    # instala dependencias
make stdio      # transporte stdio, para agentes locales
make serve      # streamable-http (MCP_PORT=8001 por defecto)
make dev        # el anterior + ngrok
make tunnel     # solo ngrok
make inspector  # MCP Inspector por stdio
