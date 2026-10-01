import os
import socket
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
parsed = urlparse(url)
host, port = parsed.hostname, parsed.port or 5432

print(f"Host: {host}  Port: {port}  User: {parsed.username}  DB: {parsed.path.lstrip('/')}")
print("Using pooled host:", "-pooler" in host)

t = time.time()
try:
    ips = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    print(f"1. DNS OK: {sorted({i[4][0] for i in ips})} ({time.time() - t:.1f}s)")
except Exception as e:
    print("1. DNS FAILED:", e)
    raise SystemExit(1)

t = time.time()
try:
    socket.create_connection((host, port), timeout=10).close()
    print(f"2. TCP connection OK ({time.time() - t:.1f}s)")
except Exception as e:
    print("2. TCP connection FAILED:", e)
    raise SystemExit(1)

import psycopg

t = time.time()
try:
    with psycopg.connect(url, connect_timeout=30) as conn:
        print("3. Login OK:", conn.execute("select 1").fetchone(), f"({time.time() - t:.1f}s)")
except Exception as e:
    print("3. Login FAILED:", e)