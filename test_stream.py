import httpx

KEY = "gw_N5fxEdksdfw8nyZZaLDwzC-Ymc5CQgJqKCMJjSHJKFQ"

body = {
    "messages": [{"role": "user", "content": "Who painted the Mona Lisa in one word"}],
    "temperature": 0,
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