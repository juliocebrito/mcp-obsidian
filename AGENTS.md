# AGENTS.md

Guía para agentes de código que trabajen en este repositorio.

## Qué es este proyecto

Servidor MCP que expone un vault de Obsidian a asistentes de IA. Actúa como proxy hacia la
**Obsidian Local REST API** (`https://127.0.0.1:27124`), autenticándose con un token Bearer.

Hoy son 7 herramientas: `search_notes`, `get_note`, `create_note`, `append_note`,
`list_directory`, `move_note`, `delete_note`.

## Estado actual y dirección

El código en `main.py` es una app **FastAPI** que implementa el JSON-RPC de MCP a mano y
expone endpoints OAuth **simulados** para satisfacer el conector de Gemini Spark.

Está previsto migrarlo al SDK oficial de Python (`mcp[cli]` v2). Antes de hacer cambios
estructurales, lee `docs/plan-mcp-puro.md`: define las fases, las decisiones ya tomadas y
las preguntas todavía abiertas. No rehagas ese análisis desde cero.

Los skills específicos del proyecto viven en `.agents/skills/`.

## Comandos

| Comando | Uso |
| --- | --- |
| `make install` | Instala dependencias con `uv sync` |
| `make serve` | Levanta uvicorn en el puerto 8000 con recarga |
| `make tunnel` | Expone el puerto por ngrok |
| `make dev` | Ambos a la vez; Ctrl+C detiene los dos |

Sobrescribe `PORT` o `ENV_FILE` por variable: `make serve PORT=9000`.

## Entorno

- Gestor de paquetes: **uv**. No uses `pip install` directamente ni crees venvs a mano.
- Ejecuta siempre a través de `uv run --env-file .env`; el servidor falla al arrancar si
  `OBSIDIAN_TOKEN` no está definido.
- Copia `.env.example` a `.env` para empezar. `.env` está en `.gitignore` y debe seguir así.
- En este equipo el shim `python` de pyenv está roto: usa `python3`.

## Reglas de seguridad

Son las restricciones que más fácilmente se rompen sin darse cuenta:

1. **Nunca escribas secretos en el código ni en el historial.** Los tokens van solo en `.env`.
2. El servidor se expone públicamente por ngrok. Cualquier endpoint nuevo hay que asumirlo
   alcanzable desde internet: no añadas rutas sin autenticar que toquen el vault.
3. Los endpoints `/authorize` y `/token` actuales devuelven credenciales dummy. Son un
   parche conocido, no un modelo a imitar ni a extender.
4. Valida las rutas de nota antes de concatenarlas a una URL: `..` no debe permitir salir
   del vault.
5. `httpx.AsyncClient(verify=False)` está pendiente de corregir. No copies ese patrón.

## Convenciones

- Mensajes de error de cara al usuario en español, igual que el resto del proyecto.
- Si el servidor pasa a transporte stdio, **nada puede escribir en stdout**: `print()` corrompe
  el canal JSON-RPC. Usa el módulo `logging`.
- No crees archivos markdown de documentación salvo que se pidan.
