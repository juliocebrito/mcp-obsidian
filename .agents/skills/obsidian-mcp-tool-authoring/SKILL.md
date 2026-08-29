---
name: obsidian-mcp-tool-authoring
description: Añadir, modificar o depurar una herramienta MCP que llama a la Obsidian Local REST API en este proyecto. Úsalo cuando la tarea mencione crear una tool nueva, cambiar el esquema de entrada de una existente, o cuando una tool devuelva errores 4xx/5xx desde Obsidian.
---

# Herramientas MCP sobre la Obsidian Local REST API

## Antes de empezar

Lee `docs/plan-mcp-puro.md`. El proyecto está migrando del JSON-RPC escrito a mano en
`main.py` al SDK oficial (`mcp[cli]` v2). El estilo de la tool depende de en qué lado estés:

- **Antes de la migración**: cada tool son dos piezas separadas que hay que mantener en
  sincronía a mano — una entrada en la respuesta de `tools/list` con su `inputSchema` JSON
  Schema, y una rama en el despacho de `tools/call`. Si añades una y olvidas la otra, el
  agente ve una herramienta que falla al invocarse, o una que existe pero es invisible.
- **Después de la migración**: una función decorada con `@mcp.tool()`. El esquema se deriva
  de los type hints y la descripción del docstring. No escribas JSON Schema a mano.

## Contrato con la API de Obsidian

Base: `OBSIDIAN_URL` (por defecto `https://127.0.0.1:27124`), con cabecera
`Authorization: Bearer {OBSIDIAN_TOKEN}`.

| Operación | Petición |
| --- | --- |
| Buscar | `POST /search/simple/` con `query` como parámetro |
| Leer nota | `GET /vault/{path}` |
| Crear o reemplazar | `PUT /vault/{path}` con `Content-Type: text/markdown` |
| Añadir al final | `POST /vault/{path}` con el contenido precedido de salto de línea |
| Listar | `GET /vault/{dir}/`, o `GET /vault/` en la raíz |
| Mover | `POST /vault/{destino}` con cabecera `X-Moved-From: /{origen}` |
| Borrar | `DELETE /vault/{path}` |

La barra final en las rutas de directorio no es opcional: sin ella la API interpreta que
pides una nota y responde 404.

## Reglas

1. **Valida la ruta antes de meterla en la URL.** Un `path` con `..` no debe poder salir del
   vault. Este servidor se expone por ngrok; la ruta llega de un modelo, no de un humano.
2. **Distingue el fallo de conexión del fallo de la API.** `httpx.ConnectError` y
   `ConnectTimeout` significan que Obsidian no está corriendo o el plugin está apagado: eso
   merece un 502 con un mensaje que nombre la URL, no un error genérico.
3. **Devuelve texto que un modelo pueda usar.** Un cuerpo vacío con 204 en una operación de
   escritura no le dice nada al agente; confirma qué se escribió y dónde.
4. **Las operaciones destructivas se marcan como tales.** `delete_note` y `move_note` pierden
   datos si el modelo se equivoca de ruta. Descríbelas sin ambigüedad en la docstring.
5. **Ninguna tool nueva puede imprimir en stdout** si el servidor corre sobre stdio: rompe el
   canal JSON-RPC. Usa `logging`.

## Comprobación

- Con el SDK: `uv run mcp dev` abre el Inspector y permite invocar la tool contra un vault real.
- Sin él: `make serve` y una petición JSON-RPC directa a `/mcp` con `tools/call`.
- Verifica siempre el camino de error, no solo el feliz: ruta inexistente, Obsidian apagado y
  ruta con `..`.
