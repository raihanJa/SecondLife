#!/usr/bin/env python3
"""
Snelweg A1 — live visualisatie van je internetverkeer als een nachtelijke snelweg.

Elke auto = één netwerkpakket. Richting van de rijbaan = download/upload.
Kleur = protocol, lengte van het voertuig = pakketgrootte.

Gebruik:
    sudo python3 snelweg.py            # echte packet capture (Linux/macOS), opent als venster
    python3 snelweg.py                 # Windows: als Administrator, met Npcap geïnstalleerd
    python3 snelweg.py --demo          # demo zonder capture (geen scapy/rechten nodig)
    python3 snelweg.py --iface eth0    # specifieke netwerkinterface
    python3 snelweg.py --port 8765     # andere poort voor de interne webserver
    python3 snelweg.py --web           # oude modus: in de browser i.p.v. als desktop-venster

Vereisten voor het venster:  pip install pywebview
Vereisten voor live capture:  pip install scapy
(Windows: installeer ook Npcap via https://npcap.com)
De demo-modus heeft géén scapy nodig.
"""
import argparse
import json
import queue
import random
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HTML_PATH = Path(__file__).parent / "index.html"

# ---------------------------------------------------------------- state ----

clients_lock = threading.Lock()
clients: list[queue.Queue] = []          # één queue per verbonden browser
packet_q: queue.Queue = queue.Queue()    # ruwe pakketten vanuit de sniffer

stats = {"pkts": 0, "in_bytes": 0, "out_bytes": 0}
stats_lock = threading.Lock()


def local_ips() -> set[str]:
    """Bepaal lokale IP-adressen om in-/uitgaand verkeer te onderscheiden."""
    ips = {"127.0.0.1", "::1"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
    # UDP-truc: verbinden hoeft niet echt te lukken om het bron-IP te leren
    for probe in ("8.8.8.8", "2001:4860:4860::8888"):
        try:
            fam = socket.AF_INET6 if ":" in probe else socket.AF_INET
            s = socket.socket(fam, socket.SOCK_DGRAM)
            s.connect((probe, 80))
            ips.add(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    return ips


LOCAL_IPS = local_ips()

# ------------------------------------------------------------ classifier ----

def classify(proto: str, sport: int, dport: int) -> str:
    ports = {sport, dport}
    if proto == "udp" and 443 in ports:
        return "quic"
    if 443 in ports:
        return "https"
    if 80 in ports or 8080 in ports:
        return "http"
    if 53 in ports or 5353 in ports:
        return "dns"
    if proto == "icmp":
        return "icmp"
    return proto  # "tcp" / "udp" / "other"


# --------------------------------------------------------------- sniffer ----

def start_sniffer(iface: str | None) -> None:
    """Live capture met scapy. Draait in een daemon-thread."""
    from scapy.all import sniff, IP, IPv6, TCP, UDP, ICMP  # noqa: import hier zodat --demo zonder scapy werkt

    def on_packet(pkt):
        ip = pkt.getlayer(IP) or pkt.getlayer(IPv6)
        if ip is None:
            return
        size = len(pkt)
        src = ip.src
        proto, sport, dport = "other", 0, 0
        if pkt.haslayer(TCP):
            proto, sport, dport = "tcp", pkt[TCP].sport, pkt[TCP].dport
        elif pkt.haslayer(UDP):
            proto, sport, dport = "udp", pkt[UDP].sport, pkt[UDP].dport
        elif pkt.haslayer(ICMP):
            proto = "icmp"
        outgoing = src in LOCAL_IPS
        packet_q.put({
            "d": 1 if outgoing else 0,                 # 0 = download, 1 = upload
            "p": classify(proto, sport, dport),
            "s": size,
        })

    kwargs = {"prn": on_packet, "store": False}
    if iface:
        kwargs["iface"] = iface
    sniff(**kwargs)


# ------------------------------------------------------------------ demo ----

def start_demo() -> None:
    """Genereert realistisch ogend nepverkeer: rustig surfen met af en toe een burst."""
    protos_in = [("https", 0.55), ("quic", 0.2), ("dns", 0.07), ("http", 0.05),
                 ("tcp", 0.08), ("udp", 0.04), ("icmp", 0.01)]
    names, weights = zip(*protos_in)

    def run():
        while True:
            burst = random.random() < 0.08
            n = random.randint(25, 90) if burst else random.randint(1, 6)
            for _ in range(n):
                p = random.choices(names, weights)[0]
                down = random.random() < 0.72
                size = random.choice((
                    random.randint(60, 120),       # ACK's, DNS
                    random.randint(300, 900),
                    random.randint(1000, 1500),    # volle MTU
                ))
                packet_q.put({"d": 0 if down else 1, "p": p, "s": size})
                if burst:
                    time.sleep(random.uniform(0.002, 0.015))
            time.sleep(random.uniform(0.05, 0.45))

    threading.Thread(target=run, daemon=True).start()


# ------------------------------------------------------------ broadcaster ----

def start_broadcaster() -> None:
    """Bundelt pakketten elke 100 ms en stuurt ze naar alle browsers (SSE)."""
    def run():
        last_stats = time.monotonic()
        pps_window: list[tuple[float, int]] = []
        while True:
            time.sleep(0.1)
            batch = []
            while not packet_q.empty() and len(batch) < 400:
                try:
                    batch.append(packet_q.get_nowait())
                except queue.Empty:
                    break
            # leeg de rest zonder ze te tekenen, maar tel ze wel mee
            overflow = 0
            while not packet_q.empty():
                try:
                    pkt = packet_q.get_nowait()
                    overflow += 1
                    with stats_lock:
                        stats["pkts"] += 1
                        stats["in_bytes" if pkt["d"] == 0 else "out_bytes"] += pkt["s"]
                except queue.Empty:
                    break
            now = time.monotonic()
            with stats_lock:
                for pkt in batch:
                    stats["pkts"] += 1
                    stats["in_bytes" if pkt["d"] == 0 else "out_bytes"] += pkt["s"]
                snapshot = dict(stats)
            pps_window.append((now, len(batch) + overflow))
            pps_window[:] = [(t, c) for t, c in pps_window if now - t <= 2.0]
            pps = sum(c for _, c in pps_window) / max(now - pps_window[0][0], 0.1) if pps_window else 0

            if not batch and now - last_stats < 1.0:
                continue
            last_stats = now
            msg = json.dumps({
                "packets": batch,
                "skipped": overflow,
                "stats": {"pps": round(pps), **snapshot},
            })
            with clients_lock:
                for q in clients:
                    if q.qsize() < 50:
                        q.put(msg)

    threading.Thread(target=run, daemon=True).start()


# -------------------------------------------------------------- webserver ----

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # geen request-spam in de terminal
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q: queue.Queue = queue.Queue()
            with clients_lock:
                clients.append(q)
            try:
                self.wfile.write(f"data: {json.dumps({'mode': MODE})}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=15)
                        self.wfile.write(f"data: {msg}\n\n".encode())
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with clients_lock:
                    if q in clients:
                        clients.remove(q)
        else:
            self.send_error(404)


MODE = "live"


def main():
    global MODE
    ap = argparse.ArgumentParser(description="Snelweg — live internetverkeer-visualisatie")
    ap.add_argument("--demo", action="store_true", help="gesimuleerd verkeer, geen capture-rechten nodig")
    ap.add_argument("--iface", help="netwerkinterface (bijv. eth0, en0, Wi-Fi)")
    ap.add_argument("--port", type=int, default=8766, help="poort voor de interne webserver (standaard 8766)")
    ap.add_argument("--web", action="store_true", help="open in de browser i.p.v. als desktop-venster")
    args = ap.parse_args()

    if args.demo:
        MODE = "demo"
        start_demo()
    else:
        try:
            import scapy  # noqa
        except ImportError:
            sys.exit("scapy is niet geïnstalleerd. Installeer met:  pip install scapy\n"
                     "Of start zonder capture:  python3 snelweg.py --demo")
        t = threading.Thread(target=start_sniffer, args=(args.iface,), daemon=True)
        t.start()
        time.sleep(1.0)
        if not t.is_alive():
            sys.exit("Packet capture kon niet starten. Start met sudo/Administrator,\n"
                     "of probeer de demo:  python3 snelweg.py --demo")

    start_broadcaster()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    threading.Thread(target=server.serve_forever, daemon=True).start()

    if args.web:
        print(f"\n  Snelweg A1 — {'DEMO-verkeer' if MODE == 'demo' else 'live capture'}")
        print(f"  Open je browser op:  {url}\n")
        print("  Stoppen met Ctrl+C")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nTot ziens!")
        return

    try:
        import webview
    except ImportError:
        sys.exit("pywebview is niet geïnstalleerd. Installeer met:  pip install pywebview\n"
                  "Of open in de browser met:  python3 snelweg.py --web")

    webview.create_window(
        "Snelweg A1 — Internetverkeer",
        url,
        width=1280,
        height=800,
        min_size=(720, 480),
        background_color="#04060f",
    )
    webview.start()


if __name__ == "__main__":
    main()
