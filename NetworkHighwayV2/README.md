# Snelweg A1 — live internetverkeer als snelweg

Elke auto die voorbijrijdt is één netwerkpakket op je machine.

- **Bovenste rijbaan (←)** = download (inkomend verkeer)
- **Onderste rijbaan (→)** = upload (uitgaand verkeer)
- **Kleur** = protocol (HTTPS groen, QUIC paars, DNS geel, …)
- **Lengte voertuig** = pakketgrootte: kleine ACK'jes zijn vlotte autootjes, volle 1500-byte MTU-pakketten zijn vrachtwagens (die rechts rijden, zoals het hoort)
- Het blauwe bewegwijzeringsbord toont live download-/uploadsnelheid en pakketten per seconde

## Starten

Draait als losse desktop-app: `python snelweg.py` opent een eigen venster (geen browser nodig).
Vereist eenmalig: `pip install pywebview`.

Beide bestanden (`snelweg.py` + `index.html`) in dezelfde map zetten.

**Demo (geen installatie of rechten nodig, buiten pywebview):**
```bash
pip install pywebview
python3 snelweg.py --demo
```

**Live capture van je echte verkeer:**
```bash
pip install scapy pywebview

# Linux / macOS (capture vereist root):
sudo python3 snelweg.py

# Windows: installeer eerst Npcap (https://npcap.com),
# open daarna een terminal als Administrator:
python snelweg.py
```

Er verschijnt automatisch een venster met de visualisatie.

Opties: `--iface en0` (specifieke interface), `--port 9000` (andere interne poort),
`--web` (open in de browser i.p.v. een desktop-venster, zoals voorheen).

## Privacy & techniek

- De webserver luistert alleen op `127.0.0.1` — niets verlaat je machine.
- Er wordt niets opgeslagen; alleen richting, protocol en grootte per pakket worden naar de browser gestreamd (geen IP's, geen payload).
- Bij extreem druk verkeer wordt het tekenen afgetopt (max ~260 auto's tegelijk); de teller rechtsboven laat zien hoeveel pakketten er "in de file" stonden.
- Stack: pure Python-stdlib webserver + Server-Sent Events, scapy voor capture, canvas-rendering in de browser.
