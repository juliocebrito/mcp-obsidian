MCP_PORT ?= 8001
ENV_FILE ?= .env

.PHONY: install check-env serve stdio inspector tunnel dev

install:
	uv sync

check-env:
	@test -f $(ENV_FILE) || { echo "Falta $(ENV_FILE). Copia .env.example y define OBSIDIAN_TOKEN."; exit 1; }

serve: check-env
	uv run --env-file $(ENV_FILE) python -m mcp_obsidian --transport streamable-http --port $(MCP_PORT)

stdio: check-env
	uv run --env-file $(ENV_FILE) python -m mcp_obsidian

inspector: check-env
	uv run --env-file $(ENV_FILE) mcp dev src/mcp_obsidian/server.py

tunnel:
	ngrok http $(MCP_PORT)

# Levanta el servidor en segundo plano y ngrok en primer plano; Ctrl+C detiene ambos.
dev: check-env
	@uv run --env-file $(ENV_FILE) python -m mcp_obsidian --transport streamable-http --port $(MCP_PORT) & \
	server_pid=$$!; \
	trap 'kill $$server_pid 2>/dev/null' EXIT INT TERM; \
	ngrok http $(MCP_PORT)
