# Arquitectura

Servidor MCP que expone un vault de Obsidian a asistentes de IA. No lee el vault del disco:
actúa como proxy sobre la **Obsidian Local REST API**, que publica el plugin homónimo en
`https://127.0.0.1:27124` y se autentica con un token Bearer.

```
agente MCP  ──stdio o streamable-http──▶  mcp-obsidian  ──HTTPS+Bearer──▶  Obsidian
```

Está construido sobre el **SDK oficial de Python** (`mcp[cli]` v2, `MCPServer`). El transporte
se elige al arrancar y la lógica de las herramientas es la misma en ambos casos.

## Módulos

| Archivo | Responsabilidad |
| --- | --- |
| `config.py` | Lee el entorno a un `Settings` congelado. Aborta el arranque si falta `OBSIDIAN_TOKEN` o si la CA de TLS no existe |
| `client.py` | Cliente httpx del vault. `safe_path()` valida las rutas; traduce fallos de red y de TLS a mensajes distintos |
| `server.py` | Instancia `MCPServer`, define las herramientas y decide cuáles se registran |
| `auth.py` | Authorization server OAuth 2.1: `authorization_code` + PKCE y refresh rotatorio |
| `store.py` | Persiste los tokens emitidos en disco con permisos `0600` |
| `__main__.py` | Elige transporte, puerto y `transport_security` |

## Herramientas

Siete en total, pero **solo se registran las que la configuración permite**: una herramienta no
registrada no aparece en `tools/list` y el modelo no puede invocarla.

| Herramienta | Qué hace | Se publica si |
| --- | --- | --- |
| `search_notes` | Busca por término | siempre |
| `get_note` | Devuelve una nota entera | siempre |
| `list_directory` | Lista archivos y carpetas | siempre |
| `create_note` | Crea una nota | `MCP_READ_ONLY=0` |
| `append_note` | Anexa al final de una nota | `MCP_READ_ONLY=0` |
| `move_note` | Mueve o renombra | `MCP_ALLOW_DESTRUCTIVE=1` |
| `delete_note` | Borra de forma irreversible | `MCP_ALLOW_DESTRUCTIVE=1` |

`MCP_ALLOW_DESTRUCTIVE=1` además deja que `create_note` sobrescriba notas existentes. Por
defecto se niega, porque sobrescribir es tan irreversible como borrar.

Los esquemas de entrada los deriva el SDK de las anotaciones de tipo y del docstring; no hay
`inputSchema` escrito a mano.

## Transportes

| Modo | Comando | Para qué |
| --- | --- | --- |
| `stdio` | `make stdio` | Agentes locales. El cliente lanza el proceso; sin puerto ni red |
| `streamable-http` | `make serve` | Agentes remotos. `make dev` añade el túnel de ngrok |

En stdio, **stdout es el canal JSON-RPC**: cualquier `print()` corrompe la sesión. El logging
va a stderr.

## Autorización

Dos capas independientes que se confunden con facilidad:

- **Hacia Obsidian**, `OBSIDIAN_TOKEN`. Es secreto de servidor y ningún cliente lo ve.
- **Hacia el agente**, solo en HTTP. `stdio` nunca la consulta, porque quien lanza el proceso
  ya tiene acceso a la máquina.

La capa HTTP tiene dos modos:

1. `MCP_AUTH_TOKEN` — un Bearer compartido, comparado con `secrets.compare_digest`.
2. `MCP_OAUTH_CLIENT_ID` + `MCP_OAUTH_CLIENT_SECRET` — el servidor actúa como authorization
   server y el SDK monta `/authorize`, `/token`, `/revoke` y los metadatos. Es lo que exige el
   conector de Gemini, que pide ID y secreto de cliente y no admite pegar un Bearer.

El registro dinámico de clientes está desactivado: solo vale el cliente preconfigurado, y sin
su secreto un código de autorización no se canjea por nada. Los códigos caducan a los 5 min,
los access token a la hora y los refresh a los 30 días, rotando en cada uso. `store.py` los
guarda en `~/.local/state/mcp-obsidian/tokens.json`, fuera del repositorio a propósito, así
que un reinicio no tira la sesión del agente.

## Decisiones de seguridad

- **Verificación TLS contra Obsidian.** Su certificado es autofirmado, así que
  `OBSIDIAN_VERIFY_TLS=1` no sirve de nada: hay que pasarle la ruta de su propia CA, que
  descarga `make cert`. El SAN cubre solo `IP:127.0.0.1`, de modo que `OBSIDIAN_URL` no puede
  usar `localhost`. Con `0` se acepta cualquier certificado y el servidor avisa al arrancar.
- **Rutas validadas.** `safe_path()` rechaza `..` antes de concatenar nada a la URL, para que
  una ruta no pueda salir del vault.
- **Expuesto a internet.** Con `make dev` el endpoint es alcanzable desde fuera. Cualquier ruta
  nueva hay que pensarla con eso en mente, y detrás de un hostname real el SDK exige
  `MCP_ALLOWED_HOSTS` o responde `421` a todo.
- **Los secretos solo en `.env`**, que está en `.gitignore`. `make check-env` no compara `.env`
  con `.env.example` —divergen de forma legítima— sino que comprueba que toda variable leída
  en `src/` esté documentada en `.env.example`.

## Estado

Verificado contra el vault real: el flujo OAuth completo con Gemini Spark por ngrok, la
supervivencia de la sesión a un reinicio del servidor, la verificación TLS con y sin la CA
correcta, y el transporte stdio desde un cliente externo y desde OpenClaw.

Pendiente: un `[project.scripts]` que exponga un ejecutable `mcp-obsidian`, y una suite de
tests con el cliente in-memory (`Client(mcp)`), que hoy no existe.
