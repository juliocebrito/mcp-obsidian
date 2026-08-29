# Plan: Migrar `mcp-obsidian` a MCP puro

> Estado: fases 1-3 implementadas en la rama `test-pure-mcp`. Última revisión: 2026-08-29.

Reemplazar el JSON-RPC escrito a mano en `main.py` por el **SDK oficial de Python (v2)**, dejando las 7 herramientas como funciones tipadas y eligiendo el transporte en tiempo de ejecución: `stdio` para agentes locales (Claude Desktop, VS Code, Cursor, Claude Code) y `streamable-http` para remotos (Gemini Spark). La lógica de las tools no cambia entre transportes.

## Qué existe ya

El paquete `src/mcp_obsidian/` es ya el único servidor; `main.py` está borrado:

| Archivo | Contenido |
| --- | --- |
| `config.py` | `Settings` congelado leído del entorno; falla en arranque sin `OBSIDIAN_TOKEN` |
| `client.py` | Wrapper httpx del vault + `safe_path()` que rechaza `..` |
| `auth.py` | Authorization server mínimo: `authorization_code` + PKCE, un cliente fijo |
| `server.py` | `MCPServer`, las 7 tools, `StaticTokenVerifier` y el lifespan que cierra httpx |
| `__main__.py` | Selección de transporte y `transport_security` |

Targets: `make serve` (HTTP en 8001), `make stdio`, `make inspector`, `make dev` (HTTP + ngrok)
y `make tunnel`.

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

### Fase 1 — Núcleo MCP (bloquea al resto) — hecha

1. ~~Crear `src/mcp_obsidian/`~~ con `client.py`, `server.py` y `config.py`.
2. ~~Portar las 7 herramientas a `@mcp.tool()` tipadas~~ — nombres, parámetros y `required` coinciden
   con los del `inputSchema` manual, verificado contra el vault real.
3. ~~Borrar `main.py`~~ una vez validado el servidor nuevo contra Gemini (`tools/list` y
   `tools/call` con respuestas reales del vault).

### Fase 2 — Transportes (depende de fase 1) — hecha

4. ~~`stdio` por defecto y `--transport streamable-http` por bandera~~; nada escribe en stdout.
5. ~~`transport_security` con la allowlist de ngrok~~ (`MCP_ALLOWED_HOSTS`), omitida cuando está
   vacía para conservar el localhost por defecto del SDK.

### Fase 3 — Autorización real (paralela a fase 4) — hecha en el núcleo nuevo

6. ~~Los `/authorize`, `/token` y `.well-known` simulados desaparecen~~ con `main.py`. Los reales
   los monta el SDK.
7. ~~`TokenVerifier` contra `MCP_AUTH_TOKEN`~~ con `secrets.compare_digest` y `AuthSettings`.
8. **Resuelto: Gemini solo habla OAuth.** Su diálogo de app conectada pide *ID de cliente* y
   *Secreto de cliente*; no admite pegar un Bearer. En vez de un shim se usa
   `auth_server_provider=` del SDK, que monta `/authorize`, `/token`, `/revoke` y los metadatos.
   `auth.py` implementa `authorization_code` + PKCE sobre un cliente preconfigurado.
   Diferencia clave con `main.py`: sin el secreto de cliente, el código no se canjea por un token.

### Fase 4 — Endurecimiento

9. Verificación TLS configurable (CA propia del certificado de Obsidian). Adelantado a medias:
   `OBSIDIAN_VERIFY_TLS` ya existe y avisa al arrancar, pero por defecto sigue desactivada.
10. ~~Validar rutas para impedir escapes del vault~~ (`safe_path`). ~~Modo de escritura opcional~~:
    `MCP_READ_ONLY` y `MCP_ALLOW_DESTRUCTIVE` deciden qué herramientas se registran. Falta que
    `create_note` se niegue a sobrescribir una nota existente.

### Fase 5 — Distribución multiagente

11. `[project.scripts]` en `pyproject.toml` para exponer un ejecutable `mcp-obsidian`.
12. ~~Actualizar el `Makefile`~~: `serve`, `stdio`, `dev`, `tunnel` e `inspector` apuntan ya al
    paquete nuevo.
13. Documentar en `README.md` los snippets de conexión para cada agente.

## Archivos

- ~~`main.py`~~ — borrado; las 7 tools viven en `src/mcp_obsidian/server.py`.
- `pyproject.toml` — ~~`name` y dependencias corregidos~~; falta el entry point.
- ~~`Makefile`~~ y ~~`.env.example`~~ — al día.

## Verificación

Hecho en la rama `test-pure-mcp`, con el servidor nuevo en el puerto 8001:

1. Cliente in-memory (`Client(mcp)`): las 7 tools se registran con los mismos nombres, parámetros
   y `required` que el `inputSchema` manual; `list_directory` devuelve el vault real.
2. `curl` sin cabecera `Accept` ni `Mcp-Session-Id` → `initialize`, `tools/list` y `tools/call`
   responden `200` con `application/json` plano. Es la misma forma que servía `main.py`, así que
   `--json-response` + stateless (los valores por defecto) deberían bastar para Gemini.
3. Con `MCP_AUTH_TOKEN`: sin token → `401` + `WWW-Authenticate` apuntando al documento; token
   inválido → `401`; token válido → `200`. El `.well-known/oauth-protected-resource/mcp` se publica.
4. Transporte stdio: subproceso levantado por el cliente del SDK, `tools/call` correcto, sin
   contaminación de stdout (`grep -r "print(" src/` vacío).
5. `get_note` con `../fuera.md` → `is_error=True` y mensaje en español; un `404` de Obsidian llega
   como error de tool, no como error de protocolo.
6. Flujo OAuth completo contra el propio servidor: `/authorize` 302 con `state`; verifier PKCE
   incorrecto → `400`; secreto incorrecto → `401`; canje correcto → `200`; reutilizar el código →
   `400`; token inventado → `401`.
7. **Gemini Spark conectado por ngrok**, con las 7 acciones sincronizadas. Secuencia real leída en
   el inspector, sin ningún atajo por nuestra parte:

   ```
   HEAD /mcp                                      -> 401
   GET  /.well-known/oauth-protected-resource/mcp -> 200
   GET  /.well-known/oauth-authorization-server   -> 200
   GET  /authorize                                -> 302
   POST /token                                    -> 200
   POST /mcp                                      -> 200  (con Authorization)
   ```

Pendiente:

8. Conectar por stdio desde VS Code o Claude Desktop.

## Decisiones

- El token actual de Obsidian sigue siendo secreto de servidor (variable de entorno); el nuevo token MCP es independiente y protege el endpoint HTTP.
- Fuera de alcance por ahora: resources y prompts MCP, y publicar en PyPI.

## Consideraciones abiertas

1. ~~**¿Gemini Spark acepta el descubrimiento RFC 9728 estándar?**~~ Resuelta: sí, y además exige
   OAuth con client_id/secret. El SDK lo cubre con `auth_server_provider`. Ver fase 3, paso 8.
   Su `redirect_uri` hay que registrarla en `MCP_OAUTH_REDIRECT_URIS`: el diálogo del conector
   tiene un botón *Copiar URI de redireccionamiento*. Es un valor por cliente y por dominio, así
   que cambiar de túnel obliga a volver a copiarla.
2. **¿Distribución?** Opción A: solo local vía `uv run`. Opción B: publicar para `uvx mcp-obsidian`, más cómodo para otros agentes. Recomendado A ahora, B cuando esté estable.
3. **¿`delete_note` activa por defecto?** Recomendado un modo de solo lectura por defecto y escritura explícita por variable de entorno, dado que el endpoint estará expuesto por ngrok.
4. ~~**Los tokens viven en memoria.**~~ Resuelto: `store.py` los guarda en
   `~/.local/state/mcp-obsidian/tokens.json` con permisos `0600` y el proveedor emite refresh
   tokens rotatorios, así que ni el reinicio ni la caducidad de una hora tiran la sesión.
