"""Packet source for the Network Highway scene — ported from snelweg.py.

The classifier, the synthetic demo-traffic generator, and the scapy sniffer
are kept close to the original; only the HTTP server / Server-Sent-Events /
pywebview plumbing that used to carry packets to a browser tab is gone. Both
sources now just hand small packet dicts (``{"d": 0/1, "p": proto, "s": size}``)
straight to the scene each frame, in-process.
"""
import queue
import random
import socket
import threading
import time

PROTOCOLS = {
    "https": {"color": (53, 208, 127), "name": "HTTPS"},
    "quic":  {"color": (176, 123, 255), "name": "QUIC"},
    "http":  {"color": (255, 159, 64), "name": "HTTP"},
    "dns":   {"color": (255, 210, 63), "name": "DNS"},
    "tcp":   {"color": (79, 163, 255), "name": "TCP"},
    "udp":   {"color": (255, 111, 145), "name": "UDP"},
    "icmp":  {"color": (255, 71, 87), "name": "ICMP"},
    "other": {"color": (154, 160, 166), "name": "Other"},
}


def local_ips():
    """Local IP addresses, used to tell inbound apart from outbound traffic."""
    ips = {"127.0.0.1", "::1"}
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ips.add(info[4][0])
    except socket.gaierror:
        pass
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


def classify(proto, sport, dport):
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
    return proto if proto in ("tcp", "udp") else "other"


class DemoSource:
    """Synthesizes realistic-looking traffic: quiet browsing with occasional
    bursts — ported from ``start_demo()``, but time-driven instead of a
    sleeping background thread."""

    def __init__(self):
        weighted = [("https", 0.55), ("quic", 0.2), ("dns", 0.07), ("http", 0.05),
                    ("tcp", 0.08), ("udp", 0.04), ("icmp", 0.01)]
        self._names = [w[0] for w in weighted]
        self._weights = [w[1] for w in weighted]
        self._next_burst = random.uniform(0.05, 0.45)
        self._timer = 0.0

    def poll(self, dt):
        self._timer += dt
        packets = []
        while self._timer >= self._next_burst:
            self._timer -= self._next_burst
            burst = random.random() < 0.08
            n = random.randint(25, 90) if burst else random.randint(1, 6)
            for _ in range(n):
                proto = random.choices(self._names, self._weights)[0]
                down = random.random() < 0.72
                size = random.choice((
                    random.randint(60, 120),
                    random.randint(300, 900),
                    random.randint(1000, 1500),
                ))
                packets.append({"d": 0 if down else 1, "p": proto, "s": size})
            self._next_burst = random.uniform(0.05, 0.45)
        return packets


class LiveSource:
    """Real packet capture via scapy — requires Administrator/root and, on
    Windows, Npcap. Runs the sniffer in a daemon thread and drains its queue
    each frame."""

    def __init__(self, iface=None):
        self._q = queue.Queue()
        self._local_ips = local_ips()
        self.available = False
        self.error = None
        try:
            from scapy.all import sniff  # noqa: F401
        except ImportError:
            self.error = "scapy is not installed (pip install scapy)"
            return
        self._thread = threading.Thread(target=self._run, args=(iface,), daemon=True)
        self._thread.start()
        time.sleep(0.3)
        self.available = self._thread.is_alive()
        if not self.available:
            self.error = "Packet capture failed to start — run as Administrator/root."

    def _run(self, iface):
        from scapy.all import ICMP, IP, IPv6, TCP, UDP, sniff

        def on_packet(pkt):
            ip = pkt.getlayer(IP) or pkt.getlayer(IPv6)
            if ip is None:
                return
            size = len(pkt)
            proto, sport, dport = "other", 0, 0
            if pkt.haslayer(TCP):
                proto, sport, dport = "tcp", pkt[TCP].sport, pkt[TCP].dport
            elif pkt.haslayer(UDP):
                proto, sport, dport = "udp", pkt[UDP].sport, pkt[UDP].dport
            elif pkt.haslayer(ICMP):
                proto = "icmp"
            outgoing = ip.src in self._local_ips
            self._q.put({"d": 1 if outgoing else 0, "p": classify(proto, sport, dport), "s": size})

        kwargs = {"prn": on_packet, "store": False}
        if iface:
            kwargs["iface"] = iface
        try:
            sniff(**kwargs)
        except Exception as exc:
            self.error = str(exc)

    def poll(self, dt):
        packets = []
        while not self._q.empty() and len(packets) < 400:
            try:
                packets.append(self._q.get_nowait())
            except queue.Empty:
                break
        return packets


class TrafficStats:
    """Rolling packet/byte counters and a packets-per-second estimate —
    ported from the broadcaster's stats bookkeeping."""

    def __init__(self):
        self.pkts = 0
        self.in_bytes = 0
        self.out_bytes = 0
        self.per_protocol = {k: 0 for k in PROTOCOLS}
        self._pps_window = []

    def ingest(self, packets, now):
        for pkt in packets:
            self.pkts += 1
            if pkt["d"] == 0:
                self.in_bytes += pkt["s"]
            else:
                self.out_bytes += pkt["s"]
            self.per_protocol[pkt["p"] if pkt["p"] in PROTOCOLS else "other"] += 1
        self._pps_window.append((now, len(packets)))
        self._pps_window[:] = [(t, c) for t, c in self._pps_window if now - t <= 2.0]

    @property
    def pps(self):
        if not self._pps_window:
            return 0.0
        span = max(self._pps_window[-1][0] - self._pps_window[0][0], 0.1)
        return sum(c for _, c in self._pps_window) / span
