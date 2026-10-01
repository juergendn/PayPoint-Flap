"""Start: python -m hwsim

Modbus  :5021, :5022, :5023   (Waveshare-Modul #1–#3)
Leser   :7000                 (TWN4-Zeilenformat)
Web-UI  :8080                 (Türen, Module, Chips)
"""

import asyncio
import logging
import os

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from hwsim.anlage import Anlage
from hwsim.leser import LeserSim
from hwsim.modbus import ModbusSimServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

# Dieselben Kennungen legt app.seed als Testchips an; „DEADBEEF“ bleibt unbekannt.
TESTCHIPS = {
    "04A1B2C3D4": "Anna Becker",
    "04A1B2C3D5": "Bernd Schmitz",
    "04A1B2C3D6": "Clara Wolf",
    "DEADBEEF": "unbekannt",
}

anlage = Anlage(
    ports=[5021, 5022, 5023],
    min_impuls_ms=int(os.environ.get("SIM_MIN_IMPULS_MS", "1000")),
    tuer_zu_nach_s=float(os.environ.get("SIM_TUER_ZU_NACH_S", "8")),
)
leser = LeserSim()
web = FastAPI(title="MVT Hardware-Simulator")


class Scan(BaseModel):
    kennung: str


def _modul(m: int):
    if not 1 <= m <= len(anlage.module):
        raise HTTPException(404, "Modul unbekannt")
    return anlage.module[m - 1]


@web.get("/api/status")
async def status() -> dict:
    return {
        "module": anlage.status(),
        "leser_clients": leser.verbunden,
        "tuer_zu_nach_s": anlage.tuer_zu_nach_s,
    }


@web.post("/api/tuer/{m}/{k}/{aktion}")
async def tuer(m: int, k: int, aktion: str) -> dict:
    modul = _modul(m)
    if not 1 <= k <= 8 or aktion not in ("auf", "zu"):
        raise HTTPException(400)
    (anlage.oeffnen if aktion == "auf" else anlage.schliessen)(modul, k - 1)
    return {"ok": True}


@web.post("/api/modul/{m}/online/{an}")
async def modul_online(m: int, an: int) -> dict:
    _modul(m).online = bool(an)
    logging.getLogger("hwsim").info("Modul #%d %s", m, "online" if an else "OFFLINE")
    return {"ok": True}


@web.post("/api/scan")
async def scan(s: Scan) -> dict:
    return {"empfaenger": await leser.vorhalten(s.kennung.strip())}


@web.get("/", response_class=HTMLResponse)
async def index() -> str:
    knoepfe = "".join(
        f'<button class="btn" onclick="scan(\'{k}\')">{n}<br><small>{k}</small></button>'
        for k, n in TESTCHIPS.items()
    )
    return SEITE.replace("{{CHIPS}}", knoepfe)


SEITE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hardware-Simulator</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--panel-2:#1c2128;--border:#30363d;--text:#e6eef3;
--muted:#8b949e;--accent:#1f6feb;--success:#3fb950;--error:#f85149;--warning:#d29922}
body{margin:0;padding:20px;background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
h1,h2{font-weight:normal;margin:0 0 12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(8,1fr);gap:8px}
.k{background:var(--panel-2);border:1px solid var(--border);border-radius:6px;padding:8px;text-align:center;font-size:.85rem}
.k.offen{border-color:var(--warning);background:rgba(210,153,34,.15)}
.k.an{box-shadow:0 0 10px var(--accent);border-color:var(--accent)}
.btn{background:var(--panel-2);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:6px 10px;cursor:pointer;margin:2px}
.btn:hover{border-color:var(--accent)}
.muted{color:var(--muted)} .off{opacity:.4}
input{background:var(--panel-2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:8px}
</style></head><body>
<h1>Hardware-Simulator</h1>
<div class="card"><h2>Leser</h2>
<div class="muted" id="leser"></div>{{CHIPS}}
<form onsubmit="scan(this.k.value);return false" style="margin-top:8px">
<input name="k" placeholder="Kennung (Hex)"> <button class="btn">Vorhalten</button></form></div>
<div id="module"></div>
<script>
async function post(u,b){await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:b?JSON.stringify(b):null});lade()}
function scan(k){post('/api/scan',{kennung:k})}
async function lade(){
 const s=await (await fetch('/api/status')).json();
 document.getElementById('leser').textContent=`${s.leser_clients} Client(s) verbunden · Tür schließt automatisch nach ${s.tuer_zu_nach_s} s`;
 document.getElementById('module').innerHTML=s.module.map((m,mi)=>`
 <div class="card ${m.online?'':'off'}"><h2>Modul ${m.name} <small class="muted">Port ${m.port}</small>
 <button class="btn" onclick="post('/api/modul/${mi+1}/online/${m.online?0:1}')">${m.online?'Ausschalten':'Einschalten'}</button></h2>
 <div class="grid">${m.kanaele.map((k,ki)=>`
  <div class="k ${k.verriegelt?'':'offen'} ${k.ausgang?'an':''}">K${ki+1}<br>
  ${k.verriegelt?'🔒 zu':'🔓 offen'}<br>
  <button class="btn" onclick="post('/api/tuer/${mi+1}/${ki+1}/${k.verriegelt?'auf':'zu'}')">${k.verriegelt?'Nothebel':'Tür zu'}</button></div>`).join('')}
 </div></div>`).join('');
}
lade();setInterval(lade,500);
</script></body></html>"""


async def _ticker() -> None:
    while True:
        anlage.tick()
        await asyncio.sleep(0.05)


async def main() -> None:
    for modul in anlage.module:
        await ModbusSimServer(anlage, modul).starten()
    await leser.starten()
    server = uvicorn.Server(
        uvicorn.Config(web, host="0.0.0.0", port=8080, log_level="warning")
    )
    await asyncio.gather(_ticker(), server.serve())


if __name__ == "__main__":
    asyncio.run(main())
