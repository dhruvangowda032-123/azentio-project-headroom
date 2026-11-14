"""Bound request bodies, including chunked requests without Content-Length."""

from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int = 1_500_000):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                return await JSONResponse({"detail": "invalid content-length"}, status_code=400)(scope, receive, send)
            if size < 0 or size > self.max_bytes:
                return await JSONResponse({"detail": "request too large"}, status_code=413)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                return await JSONResponse({"detail": "request too large"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        replayed = False

        async def replay_body():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay_body, send)

