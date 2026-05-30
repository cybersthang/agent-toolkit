from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


JsonDict = Dict[str, Any]
ToolHandler = Callable[[JsonDict], Any]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: JsonDict
    handler: ToolHandler

    def as_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class SimpleMcpServer:
    def __init__(self, name: str, version: str, tools: list[ToolDefinition]) -> None:
        self.name = name
        self.version = version
        self.tools = {tool.name: tool for tool in tools}
        self.transport_style = "jsonl"

    def serve(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                return
            self._handle_message(message)

    def _handle_message(self, message: JsonDict) -> None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params", {})

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                }
            elif method == "notifications/initialized":
                return
            elif method == "ping":
                result = {}
            elif method == "resources/list":
                result = {"resources": []}
            elif method == "resources/templates/list":
                result = {"resourceTemplates": []}
            elif method == "tools/list":
                result = {"tools": [tool.as_dict() for tool in self.tools.values()]}
            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                tool = self.tools.get(tool_name)
                if tool is None:
                    raise ValueError(f"Unknown tool: {tool_name}")
                try:
                    payload = tool.handler(arguments)
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": payload
                                if isinstance(payload, str)
                                else json.dumps(payload, ensure_ascii=False, indent=2),
                            }
                        ]
                    }
                except Exception as exc:
                    result = {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    }
            elif method in ("$/cancelRequest",):
                return
            else:
                self._send_error(request_id, -32601, f"Method not found: {method}")
                return
        except Exception as exc:  # pragma: no cover - defensive path
            traceback.print_exc(file=sys.stderr)
            self._send_error(request_id, -32000, str(exc))
            return

        if request_id is not None:
            self._send_response(request_id, result)

    def _send_response(self, request_id: Any, result: JsonDict) -> None:
        self._send_message({"jsonrpc": "2.0", "id": request_id, "result": result})

    def _send_error(self, request_id: Any, code: int, message: str) -> None:
        if request_id is None:
            return
        self._send_message(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": code, "message": message},
            }
        )

    def _send_message(self, payload: JsonDict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self.transport_style == "headers":
            sys.stdout.buffer.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
            sys.stdout.buffer.write(raw)
        else:
            sys.stdout.buffer.write(raw + b"\n")
        sys.stdout.buffer.flush()

    def _read_message(self) -> Optional[JsonDict]:
        first_line = sys.stdin.buffer.readline()
        while first_line in (b"\r\n", b"\n"):
            first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None
        stripped = first_line.strip()
        if stripped.startswith(b"{"):
            self.transport_style = "jsonl"
            return json.loads(stripped.decode("utf-8"))

        self.transport_style = "headers"
        headers: dict[str, str] = {}
        key, _, value = first_line.decode("utf-8").partition(":")
        headers[key.strip().lower()] = value.strip()
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            key, _, value = line.decode("utf-8").partition(":")
            headers[key.strip().lower()] = value.strip()

        content_length = int(headers.get("content-length", "0"))
        if content_length <= 0:
            return None

        body = sys.stdin.buffer.read(content_length)
        if not body:
            return None
        return json.loads(body.decode("utf-8"))
