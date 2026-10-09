"""Authentication and bounded body ingestion before FastAPI parses multipart."""
import ipaddress
import uuid

from starlette.responses import JSONResponse


class AdmissionMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        headers = {key.lower(): value for key, value in scope.get("headers", [])}

        async def response_send(message):
            if message["type"] == "http.response.start":
                response_headers = [(key, value) for key, value in message.get("headers", [])
                                    if key.lower() not in {b"x-request-id", b"cache-control", b"x-content-type-options"}]
                response_headers.extend([(b"x-request-id", request_id.encode()), (b"cache-control", b"no-store"),
                                         (b"x-content-type-options", b"nosniff")])
                message = {**message, "headers": response_headers}
            await send(message)

        async def reject(status, code, message):
            response = JSONResponse({"detail": message, "code": code, "request_id": request_id}, status_code=status,
                                    headers={"X-Request-ID": request_id})
            await response(scope, receive, response_send)

        sensitive_headers = {b"x-api-key", b"x-job-token", b"idempotency-key", b"content-length"}
        seen = set()
        for name, value in scope.get("headers", []):
            name = name.lower()
            if name in sensitive_headers:
                if name in seen:
                    return await reject(400, "DUPLICATE_HEADER", "Header xác thực hoặc độ dài không được lặp")
                seen.add(name)

        public_health = scope["path"] in {"/api/health", "/api/health/live", "/api/health/ready"}
        if not public_health:
            try:
                token = headers.get(b"x-api-key", b"").decode("ascii") or None
                state["principal"] = self.settings.principal(token)
            except (UnicodeDecodeError, ValueError):
                return await reject(401, "UNAUTHORIZED", "API key không đúng")
            if not self.settings.authentication_enabled:
                peer = (scope.get("client") or ("", 0))[0]
                try:
                    local = ipaddress.ip_address(peer).is_loopback
                except ValueError:
                    local = peer == "testclient"
                if not local:
                    return await reject(403, "LOCAL_ONLY", "Cấu hình API key trước khi truy cập qua mạng")
        limit = self.settings.upload_max_bytes + 65536 if scope["path"].startswith("/api/uploads/") else 131072
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await reject(400, "INVALID_CONTENT_LENGTH", "Content-Length không hợp lệ")
        if declared < 0 or declared > limit:
            return await reject(413, "BODY_TOO_LARGE", "Nội dung vượt giới hạn dung lượng")
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                return await reject(413, "BODY_TOO_LARGE", "Nội dung vượt giới hạn dung lượng")
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, response_send)
