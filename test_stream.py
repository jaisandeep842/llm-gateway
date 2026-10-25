import httpx

KEY = "gw_N5fxEdksdfw8nyZZaLDwzC-Ymc5CQgJqKCMJjSHJKFQ"

body = {
    "messages": [{"role": "user", "content": "Count from one to five in words"}],
    "stream": True,
}

with httpx.stream(
    "POST",
    "http://localhost:8001/chat",
    json=body,
    headers={"X-API-Key": KEY},
    timeout=60,
) as r:
    print("status:", r.status_code, "| X-Cache:", r.headers.get("x-cache"))
    for line in r.iter_lines():
        if line:
            print(line)