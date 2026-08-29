from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
import httpx
import json
import os

app = FastAPI()

OBSIDIAN_URL = os.environ.get("OBSIDIAN_URL", "https://127.0.0.1:27124")
OBSIDIAN_TOKEN = os.environ.get("OBSIDIAN_TOKEN")

if not OBSIDIAN_TOKEN:
    raise RuntimeError("OBSIDIAN_TOKEN debe estar configurado como variable de entorno")


# 1. Rutas de descubrimiento OAuth
@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/openid-configuration")
@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_config(request: Request):
    base_url = str(request.base_url).rstrip("/")
    return {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/authorize",
        "token_endpoint": f"{base_url}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["plain", "S256"]
    }


# 2. Endpoints OAuth simulados
@app.get("/authorize")
async def authorize(redirect_uri: str = None, state: str = None):
    if redirect_uri:
        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}code=dummy_code"
        if state:
            url += f"&state={state}"
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url)
    return {"status": "authorized", "code": "dummy_code"}


@app.post("/token")
async def token():
    return {
        "access_token": "dummy_access_token",
        "token_type": "bearer",
        "expires_in": 3600
    }


# 3. Router MCP Ampliado
@app.api_route("/mcp", methods=["GET", "POST", "HEAD", "OPTIONS"])
@app.api_route("/", methods=["GET", "POST", "HEAD", "OPTIONS"])
async def proxy_mcp_http(request: Request):
    if request.method == "OPTIONS":
        return Response(
            status_code=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )

    if request.method == "HEAD":
        return Response(
            status_code=200,
            headers={
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            }
        )

    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        try:
            content = await request.body()
            req_data = {}
            if content:
                try:
                    req_data = json.loads(content.decode("utf-8"))
                except Exception:
                    pass

            req_id = req_data.get("id", 0)
            method = req_data.get("method", "")

            # Responder a notificaciones sin ID
            if "notifications" in method or (req_id is None and "jsonrpc" in req_data):
                return JSONResponse(content={"jsonrpc": "2.0", "result": {}}, status_code=200)

            # Handshake initialize
            if method == "initialize":
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {"listChanged": True}},
                            "serverInfo": {"name": "obsidian-local-rest-api", "version": "1.0.0"}
                        }
                    },
                    status_code=200
                )

            # Catálogo completo de herramientas MCP
            if method == "tools/list":
                tools_list = [
                    {
                        "name": "search_notes",
                        "description": "Busca notas en el vault por término o palabra clave",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string", "description": "Término a buscar"}},
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "get_note",
                        "description": "Obtiene el contenido completo de una nota",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"path": {"type": "string", "description": "Nombre o ruta del archivo"}},
                            "required": ["path"]
                        }
                    },
                    {
                        "name": "create_note",
                        "description": "Crea o sobrescribe una nota en el vault",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "Ruta/nombre del archivo .md"},
                                "content": {"type": "string", "description": "Contenido Markdown"}
                            },
                            "required": ["path", "content"]
                        }
                    },
                    {
                        "name": "append_note",
                        "description": "Añade texto al final de una nota existente sin sobrescribirla",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "Ruta/nombre del archivo .md"},
                                "content": {"type": "string", "description": "Contenido a anexar"}
                            },
                            "required": ["path", "content"]
                        }
                    },
                    {
                        "name": "list_directory",
                        "description": "Lista el contenido de archivos y carpetas del vault",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "Ruta del directorio (dejar vacío para la raíz)"}
                            }
                        }
                    },
                    {
                        "name": "move_note",
                        "description": "Mueve o renombra una nota de una ubicación a otra",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "source_path": {"type": "string", "description": "Ruta de origen de la nota"},
                                "destination_path": {"type": "string", "description": "Ruta de destino deseada"}
                            },
                            "required": ["source_path", "destination_path"]
                        }
                    },
                    {
                        "name": "delete_note",
                        "description": "Elimina una nota del vault",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "Ruta de la nota a eliminar"}
                            },
                            "required": ["path"]
                        }
                    }
                ]
                return JSONResponse(
                    content={"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools_list}},
                    status_code=200
                )

            # Invocación de herramientas (tools/call)
            if method == "tools/call":
                params = req_data.get("params", {})
                tool_name = params.get("name", "")
                args = params.get("arguments", {})

                headers = {
                    "Authorization": f"Bearer {OBSIDIAN_TOKEN}",
                    "Accept": "application/json"
                }

                # 1. Buscar notas
                if tool_name == "search_notes":
                    query = args.get("query", "")
                    r = await client.post(f"{OBSIDIAN_URL}/search/simple/", headers=headers, params={"query": query})
                    res_text = r.text if r.status_code == 200 else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

                # 2. Leer nota
                elif tool_name == "get_note":
                    path = args.get("path", "").lstrip("/")
                    r = await client.get(f"{OBSIDIAN_URL}/vault/{path}", headers=headers)
                    res_text = r.text if r.status_code == 200 else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

                # 3. Crear/Sobrescribir nota
                elif tool_name == "create_note":
                    path = args.get("path", "").lstrip("/")
                    content_str = args.get("content", "")
                    headers["Content-Type"] = "text/markdown"
                    r = await client.put(f"{OBSIDIAN_URL}/vault/{path}", headers=headers, content=content_str.encode("utf-8"))
                    res_text = "Nota guardada con éxito." if r.status_code in [200, 201, 204] else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

                # 4. Anexar contenido al final de la nota (append_note)
                elif tool_name == "append_note":
                    path = args.get("path", "").lstrip("/")
                    content_str = args.get("content", "")
                    headers["Content-Type"] = "text/markdown"
                    r = await client.post(f"{OBSIDIAN_URL}/vault/{path}", headers=headers, content=f"\n{content_str}".encode("utf-8"))
                    res_text = "Contenido anexado con éxito." if r.status_code in [200, 201, 204] else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

                # 5. Listar directorio (list_directory)
                elif tool_name == "list_directory":
                    dir_path = args.get("path", "").strip("/")
                    target_url = f"{OBSIDIAN_URL}/vault/{dir_path}/" if dir_path else f"{OBSIDIAN_URL}/vault/"
                    r = await client.get(target_url, headers=headers)
                    res_text = r.text if r.status_code == 200 else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

                # 6. Mover / Renombrar nota (move_note)
                elif tool_name == "move_note":
                    src = args.get("source_path", "").lstrip("/")
                    dst = args.get("destination_path", "").lstrip("/")
                    headers["X-Moved-From"] = f"/{src}"
                    r = await client.post(f"{OBSIDIAN_URL}/vault/{dst}", headers=headers)
                    res_text = f"Nota movida con éxito a {dst}." if r.status_code in [200, 201, 204] else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

                # 7. Eliminar nota (delete_note)
                elif tool_name == "delete_note":
                    path = args.get("path", "").lstrip("/")
                    r = await client.delete(f"{OBSIDIAN_URL}/vault/{path}", headers=headers)
                    res_text = "Nota eliminada con éxito." if r.status_code in [200, 204] else f"Error {r.status_code}: {r.text}"
                    return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res_text}]}}, status_code=200)

            return JSONResponse(content={"jsonrpc": "2.0", "id": req_id, "result": {}}, status_code=200)

        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            print(f"Error conectando con Obsidian: {e}")
            return JSONResponse(
                status_code=502,
                content={"error": f"No se pudo conectar con Obsidian en {OBSIDIAN_URL}."}
            )