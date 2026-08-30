---
name: obsidian-mcp-tool-authoring
description: Añadir, modificar o depurar una herramienta MCP que llama a la Obsidian Local REST API en este proyecto. Úsalo cuando la tarea mencione crear una tool nueva, cambiar el esquema de entrada de una existente, o cuando una tool devuelva errores 4xx/5xx desde Obsidian.
---

# Herramientas MCP sobre la Obsidian Local REST API

## Antes de empezar

Una tool son dos piezas en dos archivos:

- **`client.py`** hace la llamada HTTP. Usa siempre `self._request()`, que traduce los fallos
  de red y de TLS, y cierra con `_body()` para lecturas o `_confirm()` para escrituras. No
  instancies httpx por tu cuenta ni llames a `self._client` directamente.
- **`server.py`** declara la función decorada con `@mcp.tool()`, que solo delega en el
  cliente. El esquema se deriva de los type hints y del docstring, así que no escribas JSON
  Schema a mano.

Si la tool escribe o borra, no la decores: defínela suelta y regístrala al final del módulo
dentro del bloque que comprueba `settings.read_only` y `settings.allow_destructive`. Una
herramienta no registrada no existe para el modelo.

Contexto de las decisiones de diseño: `docs/arquitectura.md`.

## Contrato con la API de Obsidian

Base: `OBSIDIAN_URL` (por defecto `https://127.0.0.1:27124`), con cabecera
`Authorization: Bearer {OBSIDIAN_TOKEN}`. Las operaciones ya implementadas se leen en
`client.py`; estas tres son las que no se adivinan:

- **Listar un directorio exige barra final**: `GET /vault/{dir}/`. Sin ella la API cree que
  pides una nota y responde 404. En la raíz, `GET /vault/`.
- **Anexar es `POST /vault/{path}`** con el contenido precedido de un salto de línea; el
  `PUT` reemplaza la nota entera.
- **Mover es `POST /vault/{destino}`** con la cabecera `X-Moved-From: /{origen}`, no un verbo
  propio.

Las escrituras responden 200, 201 o 204 según el caso, así que no compares con un único
código: usa las constantes `_WRITE_OK` y `_DELETE_OK`.

## Reglas

1. **Valida la ruta con `safe_path()` antes de meterla en la URL.** Un `path` con `..` no debe
   poder salir del vault. Este servidor se expone por ngrok; la ruta llega de un modelo, no de
   un humano.
2. **Usa el error que corresponde.** `ToolError` para lo que falla dentro de la tool —un 4xx
   de Obsidian, una ruta prohibida, una nota que ya existe—: el modelo lo recibe como
   resultado y puede reaccionar. `MCPError` queda para lo que rompe la conversación con
   Obsidian, y de eso ya se encarga `_request()`, que además distingue un certificado
   rechazado de un Obsidian apagado. No lo dupliques en cada método.
3. **Devuelve texto que un modelo pueda usar.** Un cuerpo vacío con 204 en una operación de
   escritura no le dice nada al agente; confirma qué se escribió y dónde.
4. **Lo irreversible se pide explícitamente.** `delete_note` y `move_note` solo se registran
   con `MCP_ALLOW_DESTRUCTIVE`, y sobrescribir cuenta como irreversible: `write()` se niega si
   la nota existe salvo que reciba `overwrite=True`. Descríbelo sin ambigüedad en la docstring,
   porque quien decide invocarla es un modelo.
5. **Ninguna tool nueva puede imprimir en stdout** si el servidor corre sobre stdio: rompe el
   canal JSON-RPC. Usa `logging`.
6. **Los mensajes de error, en español**, como el resto del proyecto.

## Comprobación

- `make inspector` abre el MCP Inspector y permite invocar la tool contra el vault real.
- Alternativa sin interfaz: `make stdio` y un cliente del SDK que lance el proceso, o
  `make serve` con una petición `tools/call` a `/mcp`.
- Cualquier arranque necesita `uv run --env-file .env`, o el servidor aborta sin
  `OBSIDIAN_TOKEN`. Los targets del Makefile ya lo hacen.
- Verifica siempre el camino de error, no solo el feliz: ruta inexistente, Obsidian apagado y
  ruta con `..`.
