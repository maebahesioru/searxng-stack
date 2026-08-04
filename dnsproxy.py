"""Tiny DNS-over-HTTPS proxy (pure stdlib).

Listens on UDP :53. Single-label names (Docker service names like "redis",
"tor") are forwarded to Docker's embedded DNS; public domains are resolved
via Cloudflare DoH so that the host VPN's DNS sinkhole is bypassed.
"""
import json
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request

DOH_URL = "https://1.1.1.1/dns-query"
EMBEDDED_DNS = "127.0.0.11"  # Docker embedded DNS (inside this container)
CACHE: dict = {}
CACHE_TTL = 300


def doh_query(name: str, qtype: int) -> tuple[list[str], int]:
    type_map = {1: "A", 28: "AAAA", 5: "CNAME"}
    url = f"{DOH_URL}?name={urllib.parse.quote(name)}&type={type_map.get(qtype, 'A')}"
    req = urllib.request.Request(url, headers={"Accept": "application/dns-json", "User-Agent": "dnsproxy/1.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read())
    answers: list[str] = []
    ttl = 300
    for a in data.get("Answer", []):
        if a.get("type") in (1, 28) and a.get("data"):
            answers.append(a["data"])
        if a.get("TTL"):
            ttl = min(ttl, a["TTL"])
    return answers, ttl


def build_response(query: bytes, answers: list[str], ttl: int) -> bytes:
    qid = query[:2]
    # echo the question section (name + type/class)
    qend = 12
    while query[qend] != 0:
        qend += query[qend] + 1
    qend += 5
    question = query[12:qend]
    header = qid + b"\x81\x80" + struct.pack(">HHHH", 1, len(answers), 0, 0)
    body = b""
    for ans in answers:
        ipv6 = ":" in ans
        rdata = socket.inet_pton(socket.AF_INET6, ans) if ipv6 else socket.inet_pton(socket.AF_INET, ans)
        atype = 28 if ipv6 else 1
        body += b"\xc0\x0c" + struct.pack(">HHIH", atype, 1, ttl, len(rdata)) + rdata
    return header + question + body


def handle(data: bytes, addr, sock: socket.socket) -> None:
    try:
        i = 12
        name_parts: list[str] = []
        while data[i] != 0:
            length = data[i]
            name_parts.append(data[i + 1 : i + 1 + length].decode(errors="ignore"))
            i += length + 1
        name = ".".join(name_parts)
        qtype = struct.unpack(">H", data[i + 1 : i + 3])[0]

        if "." not in name:
            # Docker service name -> Docker embedded DNS
            fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            fwd.settimeout(3)
            try:
                fwd.sendto(data, (EMBEDDED_DNS, 53))
                resp, _ = fwd.recvfrom(4096)
                sock.sendto(resp, addr)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            fwd.close()
            return

        cache_key = (name, qtype)
        now = time.time()
        cached = CACHE.get(cache_key)
        if cached and cached[0] > now:
            answers, ttl = cached[1], cached[2]
        else:
            answers, ttl = doh_query(name, qtype)
            if not answers and qtype == 28:
                answers, ttl = doh_query(name, 1)  # fall back to A when no AAAA
            CACHE[cache_key] = (now + CACHE_TTL, answers, ttl)
        sock.sendto(build_response(data, answers, ttl), addr)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def main() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 53))
    print("dnsproxy listening on :53", flush=True)
    while True:
        try:
            data, addr = sock.recvfrom(4096)
            threading.Thread(target=handle, args=(data, addr, sock), daemon=True).start()
        except Exception:  # pylint: disable=broad-exception-caught
            time.sleep(0.1)


if __name__ == "__main__":
    main()
