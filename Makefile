ENV_FILE ?= .env
-include $(ENV_FILE)
MCP_PORT ?= 8001
OBSIDIAN_URL ?= https://127.0.0.1:27124
CERT ?= $(HOME)/.local/state/mcp-obsidian/obsidian.crt

.PHONY: install check-env cert serve stdio inspector tunnel dev

install:
	uv sync

# Descarga la CA que firma el certificado de Obsidian. El -k es inevitable: es la primera
# vez que se ve ese certificado y no hay nada contra lo que validarlo todavía.
cert:
	@mkdir -p $(dir $(CERT))
	@curl -sfk -o $(CERT) $(OBSIDIAN_URL)/obsidian-local-rest-api.crt
	@echo "Certificado en $(CERT)"
	@echo "Pon OBSIDIAN_VERIFY_TLS=$(CERT) en $(ENV_FILE)."

# No compara .env con .env.example: .env es personal y diverge de forma legítima. Lo que
# comprueba es que toda variable leída por config.py esté documentada en .env.example.
check-env:
	@test -f $(ENV_FILE) || { echo "Falta $(ENV_FILE). Copia .env.example y define OBSIDIAN_TOKEN."; exit 1; }
	@missing=""; \
	for var in $$(grep -ohE '"(OBSIDIAN|MCP)_[A-Z_]+"' src/mcp_obsidian/*.py | tr -d '"' | sort -u); do \
		grep -qE "^#? *$$var=" .env.example || missing="$$missing $$var"; \
	done; \
	test -z "$$missing" || { echo "Sin documentar en .env.example:$$missing"; exit 1; }

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
