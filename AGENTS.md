# AGENTS.md

Guía para agentes de código que trabajen en este repositorio.

## Qué es este proyecto

Servidor MCP que expone un vault de Obsidian a asistentes de IA. Actúa como proxy hacia la
**Obsidian Local REST API** (`https://127.0.0.1:27124`), autenticándose con un token Bearer.

Son 7 herramientas: `search_notes`, `get_note`, `create_note`, `append_note`,
`list_directory`, `move_note`, `delete_note`. Solo las cinco primeras se publican por defecto:
`move_note` y `delete_note` exigen `MCP_ALLOW_DESTRUCTIVE=1`, y `MCP_READ_ONLY=1` deja
únicamente las de lectura.

## Estado actual

El paquete `src/mcp_obsidian/` usa el **SDK oficial de Python** (`mcp[cli]` v2) con
`MCPServer`. Elige transporte en tiempo de ejecución: `stdio` para agentes locales y
`streamable-http` para remotos. Con `MCP_OAUTH_CLIENT_ID`/`SECRET` definidos, el propio
servidor hace de authorization server (`auth.py`), que es lo que exige el conector de Gemini.

El antiguo proxy FastAPI de `main.py` ya no existe. `docs/plan-mcp-puro.md` recoge las
decisiones tomadas durante la migración.

Los skills específicos del proyecto viven en `.agents/skills/`.

## Comandos

| Comando | Uso |
| --- | --- |
| `make install` | Instala dependencias con `uv sync` |
| `make stdio` | Transporte stdio, para agentes locales |
| `make serve` | streamable-http en el puerto 8001 |
| `make dev` | El anterior + ngrok; Ctrl+C detiene los dos |
| `make inspector` | MCP Inspector por stdio |

Sobrescribe `MCP_PORT` o `ENV_FILE` por variable: `make serve MCP_PORT=9000`.

## Entorno

- Gestor de paquetes: **uv**. No uses `pip install` directamente ni crees venvs a mano.
- Ejecuta siempre a través de `uv run --env-file .env`; el servidor falla al arrancar si
  `OBSIDIAN_TOKEN` no está definido.
- Copia `.env.example` a `.env` para empezar. `.env` está en `.gitignore` y debe seguir así.
- No compares `.env` con `.env.example`: el primero es personal y diverge de forma legítima.
  Lo que sí exige el proyecto es que toda variable leída en `src/` esté documentada en
  `.env.example`, y de eso se encarga `make check-env`.
- En este equipo el shim `python` de pyenv está roto: usa `python3`.

## Reglas de seguridad

Son las restricciones que más fácilmente se rompen sin darse cuenta:

1. **Nunca escribas secretos en el código ni en el historial.** Los tokens van solo en `.env`.
2. El servidor se expone públicamente por ngrok. Cualquier endpoint nuevo hay que asumirlo
   alcanzable desde internet: no añadas rutas sin autenticar que toquen el vault.
3. Una herramienta destructiva nueva no se registra sin comprobar `MCP_ALLOW_DESTRUCTIVE`.
   No basta con avisar en el docstring: quien decide invocarla es un modelo.
4. Valida las rutas de nota antes de concatenarlas a una URL: `..` no debe permitir salir
   del vault.
5. `OBSIDIAN_VERIFY_TLS` admite `0` (no verificar), `1` (CA del sistema, que no sirve para
   un autofirmado) o la ruta a una CA. `make cert` descarga la de Obsidian. El certificado
   solo cubre `127.0.0.1`: con `localhost` en `OBSIDIAN_URL` la verificación falla.
6. El almacén de `store.py` guarda tokens en claro. Se crea con `0600` y por defecto vive
   fuera del repositorio; si cambias `MCP_TOKEN_STORE`, que no apunte al árbol de trabajo.

## Convenciones

- Mensajes de error de cara al usuario en español, igual que el resto del proyecto.
- El transporte stdio comparte canal con stdout: `print()` corrompe el JSON-RPC. Usa el
  módulo `logging`, que ya escribe a stderr.
- No crees archivos markdown de documentación salvo que se pidan.
