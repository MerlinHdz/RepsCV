"""Single-worker entry point. Trust forwarded headers only from configured proxies."""

import os
import uvicorn


def main():
    uvicorn.run("backend.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
                workers=1, proxy_headers=True,
                forwarded_allow_ips=os.environ.get("REPSCV_PROXY_IPS", "127.0.0.1"),
                ws_max_size=8192, ws_ping_interval=20, ws_ping_timeout=20,
                access_log=False)


if __name__ == "__main__":
    main()
