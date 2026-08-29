PORT ?= 8000
ENV_FILE ?= .env

.PHONY: install serve tunnel dev check-env

install:
	uv sync

check-env:
	@test -f $(ENV_FILE) || { echo "Falta $(ENV_FILE). Copia .env.example y define OBSIDIAN_TOKEN."; exit 1; }

serve: check-env
	uv run --env-file $(ENV_FILE) uvicorn main:app --port $(PORT) --reload

tunnel:
	ngrok http $(PORT)

# Levanta uvicorn en segundo plano y ngrok en primer plano; Ctrl+C detiene ambos.
dev: check-env
	@uv run --env-file $(ENV_FILE) uvicorn main:app --port $(PORT) --reload & \
	server_pid=$$!; \
	trap 'kill $$server_pid 2>/dev/null' EXIT INT TERM; \
	ngrok http $(PORT)
