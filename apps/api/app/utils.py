from __future__ import annotations

from fastapi import Request


def get_client_ip(request: Request) -> str:
    """Return the best-guess public IP of the actual user.

    Order of preference:
      1. ``X-Real-IP`` header — set by the FE after discovering its own
         public IP (via ipwho.is). This is what makes geolocation work in
         dev where the api would otherwise see only the docker bridge.
      2. ``X-Forwarded-For`` first hop — for the eventual real-deployment
         case behind a reverse proxy.
      3. ``request.client.host`` — the fallback (docker bridge in dev).

    NOTE: in a real deployment these headers must be sanitised by the proxy.
    For this POC they are accepted as-is.
    """
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    fwd = request.headers.get("x-forwarded-for", "").strip()
    if fwd:
        # XFF is a comma-separated chain; client IP is the leftmost.
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else ""
