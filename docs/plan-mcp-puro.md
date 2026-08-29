# Plan: Migrar `mcp-obsidian` a MCP puro

> Estado: propuesta. Última revisión: 2026-08-17.

Reemplazar el JSON-RPC escrito a mano en `main.py` por el **SDK oficial de Python (v2)**, dejando las 7 herramientas como funciones tipadas y eligiendo el transporte en tiempo de ejecución: `stdio` para agentes locales (Claude Desktop, VS Code, Cursor, Claude Code) y `streamable-http` para remotos (Gemini Spark). La lógica de las tools no cambia entre transportes.

## Opciones evaluadas

| Opción | Qué implica | Veredicto |
| --- | --- | --- |
| **A. SDK oficial `mcp[cli]` v2** | `MCPServer` + `@mcp.tool()`; stdio y HTTP nativos; auth OAuth 2.1 incluida | **Recomendada** |
| B. SDK oficial montado dentro de FastAPI | `mcp.streamable_http_app()` bajo `Mount` | Solo si Gemini exige conservar rutas OAuth propias |
| C. FastMCP v2 (tercero) | Más baterías, pero dependencia extra fuera del SDK oficial | Descartada |
| D. Mantener JSON-RPC manual | Obliga a seguir la spec a mano; sin sesiones ni negociación | Descartada |

## Hallazgos que condicionan el diseño

Verificados en la documentación oficial (`py.sdk.modelcontextprotocol.io`):

- El SDK va por **v2.0.0**, con API nueva: `from mcp.server import MCPServer`. La spec vigente es `2026-07-28` (el código actual anuncia `2024-11-05`).
- La autorización es solo HTTP: `TokenVerifier` + `AuthSettings` publican RFC 9728 en `/.well-known/oauth-protected-resource/mcp` y devuelven 401 con `WWW-Authenticate`. **stdio nunca la consulta.**
- Al montar dentro de otra app, el lifespan del host debe entrar `mcp.session_manager.run()`, o la primera petición falla con `RuntimeError: Task group is not initialized`.
- Detrás de un hostname real (ngrok) hay que pasar `transport_security` con la allowlist, o todo responde `421`.
- Los tests usan un cliente in-memory (`Client(mcp)`): sin puerto ni subproceso.

## Riesgos de seguridad en el código actual

Motivan las fases 3 y 4:

1. `/authorize` y `/token` entregan credenciales dummy a cualquiera: quien tenga la URL de ngrok obtiene lectura, escritura y borrado del vault.
2. `httpx.AsyncClient(verify=False)` desactiva la verificación TLS.
3. Los parámetros `path` se concatenan a la URL sin validar `..`.

## Fases

### Fase 1 — Núcleo MCP (bloquea al resto)

1. Crear `src/mcp_obsidian/` con `client.py` (wrapper HTTP a Obsidian), `server.py` (instancia y tools) y `config.py` (lectura de entorno).
2. Portar las 7 herramientas a `@mcp.tool()` tipadas — `search_notes`, `get_note`, `create_note`, `append_note`, `list_directory`, `move_note`, `delete_note` — usando firmas y docstrings en vez del `inputSchema` manual. *Depende de 1.*
3. Eliminar de `main.py` el handshake, `tools/list` y el despacho de `tools/call`: el SDK los cubre.

### Fase 2 — Transportes (depende de fase 1)

4. `stdio` por defecto y `--transport streamable-http` por bandera; nunca escribir en stdout (usar `logging`).
5. Añadir `transport_security` con la allowlist de ngrok para el modo HTTP.

### Fase 3 — Autorización real (paralela a fase 4)

6. Borrar `/authorize`, `/token` y los `.well-known` simulados.
7. Implementar `TokenVerifier` contra un token de entorno (`MCP_AUTH_TOKEN`) y declarar `AuthSettings`, dejando que el SDK publique el documento RFC 9728.
8. Si Gemini rechaza el descubrimiento estándar, reintroducir *solo* los metadatos del authorization server con `@mcp.custom_route()`, nunca un `/token` que emita credenciales a cualquiera.

### Fase 4 — Endurecimiento

9. Verificación TLS configurable (CA propia del certificado de Obsidian) en lugar de `verify=False`.
10. Validar rutas para impedir escapes del vault, y poner `delete_note`/`move_note` tras un modo de escritura opcional.

### Fase 5 — Distribución multiagente

11. `[project.scripts]` en `pyproject.toml` para exponer un ejecutable `mcp-obsidian`.
12. Actualizar el `Makefile`: `make dev` sigue sirviendo HTTP+ngrok, y se añade un target stdio.
13. Documentar en `README.md` los snippets de conexión para cada agente.

## Archivos

- `main.py` — origen de las 7 tools; se reduce o desaparece a favor de `src/`.
- `pyproject.toml` — cambiar `fastapi`/`uvicorn` por `mcp[cli]`; añadir entry point. El `name` sigue siendo `proxy-oauth` y debe actualizarse.
- `Makefile` — reutilizar `check-env` y el patrón `--env-file`.
- `.env.example` — añadir `MCP_AUTH_TOKEN` y el modo de escritura.

## Verificación

1. `uv run mcp dev` → abrir el Inspector y ejecutar cada una de las 7 tools contra un vault real.
2. Tests con el cliente in-memory (`Client(mcp)`), sin puerto ni subproceso.
3. `curl` al endpoint sin token → debe dar 401 con `WWW-Authenticate`; y al `.well-known` → documento RFC 9728.
4. Conectar por stdio desde VS Code o Claude Desktop y verificar que las tools aparecen.
5. Reconectar Gemini Spark por ngrok y confirmar `tools/list` y una llamada de escritura.
6. Verificar que un `path` con `..` es rechazado.

## Decisiones

- El token actual de Obsidian sigue siendo secreto de servidor (variable de entorno); el nuevo token MCP es independiente y protege el endpoint HTTP.
- Fuera de alcance por ahora: resources y prompts MCP, y publicar en PyPI.

## Consideraciones abiertas

1. **¿Gemini Spark acepta el descubrimiento RFC 9728 estándar, o exige los endpoints `/authorize` y `/token`?** Probar primero sin shim (fase 3, paso 7) y añadirlo solo si falla. Es lo que decide si conservamos FastAPI.
2. **¿Distribución?** Opción A: solo local vía `uv run`. Opción B: publicar para `uvx mcp-obsidian`, más cómodo para otros agentes. Recomendado A ahora, B cuando esté estable.
3. **¿`delete_note` activa por defecto?** Recomendado un modo de solo lectura por defecto y escritura explícita por variable de entorno, dado que el endpoint estará expuesto por ngrok.
