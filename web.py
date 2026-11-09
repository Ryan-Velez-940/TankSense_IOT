#!/usr/bin/env python3
"""
Página web del nivel de la cisterna (sin instalar nada extra).

Uso:  python3 web.py
Luego abre  http://IP-DE-LA-PI:8000  desde cualquier celular o PC de la misma red.
Requiere cisterna.py y distancia.py en la misma carpeta.
"""
import json
import math
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import RPi.GPIO as GPIO
import cisterna
import distancia as sensor

PUERTO = 8000
INTERVALO = 3          # segundos entre mediciones
HISTORIAL_CADA = 30    # segundos entre puntos de la gráfica
HISTORIAL_MAX = 2880   # 24 horas de puntos

lock = threading.Lock()
estado = {"ok": False, "pct": None, "litros": None, "cap": None, "d": None}
historial = deque(maxlen=HISTORIAL_MAX)
cfg = None  # medidas de la cisterna; se cambian desde la página


def cargar_config():
    global cfg
    try:
        with open(cisterna.ARCHIVO_CONFIG) as a:
            c = json.load(a)
        if c["altura_cm"] - c["margen_cm"] > 0 and "area_cm2" in c:
            cfg = c
    except (OSError, ValueError, KeyError, TypeError):
        cfg = None


def guardar_config(nueva):
    global cfg
    with lock:
        cfg = nueva
        historial.clear()
        estado.update(ok=False, pct=None, litros=None, cap=None, d=None)
    try:
        with open(cisterna.ARCHIVO_CONFIG, "w") as a:
            json.dump(nueva, a)
    except OSError as e:
        print(f"No se pudo guardar la configuración: {e}")


def validar_config(d):
    """Convierte lo que envía la página en una configuración. ValueError = mensaje para el usuario."""
    if not isinstance(d, dict):
        raise ValueError("Formato inválido.")
    unidad = d.get("unidad")
    if unidad not in cisterna.A_CM:
        raise ValueError("Elige una unidad válida.")
    f = cisterna.A_CM[unidad]

    def num(clave, nombre, positivo=True):
        try:
            v = float(str(d.get(clave, "")).strip().replace(",", "."))
        except ValueError:
            raise ValueError(f"{nombre}: escribe un número.")
        if not math.isfinite(v) or v < 0 or (positivo and v == 0):
            raise ValueError(f"{nombre}: debe ser {'mayor que' if positivo else 'al menos'} 0.")
        return v

    altura = num("altura", "Altura")
    margen = num("margen", "Margen", positivo=False)
    if margen >= altura:
        raise ValueError("El margen debe ser menor que la altura.")

    forma = d.get("forma", "ninguna")
    ui = {"unidad": unidad, "altura": altura, "margen": margen, "forma": forma}
    area = None
    if forma == "rectangular":
        ui["largo"], ui["ancho"] = num("largo", "Largo"), num("ancho", "Ancho")
        area = ui["largo"] * f * ui["ancho"] * f
    elif forma == "cilindrica":
        ui["diametro"] = num("diametro", "Diámetro")
        area = math.pi * (ui["diametro"] * f / 2) ** 2
    elif forma != "ninguna":
        raise ValueError("Elige una forma válida.")
    return {"altura_cm": altura * f, "margen_cm": margen * f, "area_cm2": area, "ui": ui}


def medir_en_segundo_plano():
    filtro = sensor.FiltroSaltos()
    ultimo_punto = 0.0
    while True:
        try:
            with lock:
                c = cfg
            if c is None:
                time.sleep(1)  # esperando que se configure desde la página
                continue
            d = filtro.procesar(sensor.medir_mediana())
            ahora = time.time()
            with lock:
                if c is not cfg:
                    continue  # la configuración cambió mientras se medía
                if d is None:
                    estado["ok"] = False
                else:
                    pct, litros, cap = cisterna.calcular(c, d)
                    estado.update(
                        ok=True,
                        pct=round(pct, 1),
                        litros=None if litros is None else round(litros),
                        cap=None if cap is None else round(cap),
                        d=round(d, 1),
                    )
                    if ahora - ultimo_punto >= HISTORIAL_CADA:
                        historial.append([int(ahora), round(pct, 1)])
                        ultimo_punto = ahora
        except Exception as e:  # que un error puntual no detenga la medición
            print(f"Error al medir: {e}")
        time.sleep(INTERVALO)


class Manejador(BaseHTTPRequestHandler):
    def responder(self, cuerpo, tipo="application/json", codigo=200):
        if not isinstance(cuerpo, bytes):
            cuerpo = json.dumps(cuerpo).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.responder(PAGINA.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path.startswith("/api/nivel"):
            with lock:
                datos = dict(estado, hist=list(historial), configurado=cfg is not None)
            self.responder(datos)
        elif self.path.startswith("/api/config"):
            with lock:
                c = cfg or {}
            ui = c.get("ui") or (
                {"unidad": "cm", "altura": round(c["altura_cm"], 1),
                 "margen": round(c["margen_cm"], 1), "forma": "ninguna"}
                if c else {}
            )
            self.responder({"ui": ui})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/api/config":
            self.send_error(404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 10000:
                raise ValueError("Datos demasiado grandes.")
            nueva = validar_config(json.loads(self.rfile.read(n) or b"{}"))
        except (ValueError, TypeError) as e:
            self.responder({"ok": False, "error": str(e)}, codigo=400)
            return
        guardar_config(nueva)
        aviso = None
        if nueva["altura_cm"] > sensor.DISTANCIA_MAX_CM:
            aviso = (f"El sensor solo lee hasta {sensor.DISTANCIA_MAX_CM} cm: "
                     "con la cisterna casi vacía no habrá lectura.")
        self.responder({"ok": True, "aviso": aviso})

    def log_message(self, *args):
        pass  # sin ruido en la terminal


def ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "IP-DE-LA-PI"


def main():
    cargar_config()
    sensor.configurar()
    threading.Thread(target=medir_en_segundo_plano, daemon=True).start()

    servidor = ThreadingHTTPServer(("0.0.0.0", PUERTO), Manejador)
    print(f"\nPágina lista en  http://{ip_local()}:{PUERTO}   (Ctrl+C para salir)")
    if cfg is None:
        print("Aún no hay medidas guardadas: configúralas desde la página.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido")
    finally:
        servidor.server_close()
        GPIO.cleanup()


PAGINA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nivel de la cisterna</title>
<style>
:root{
  --fondo:#eef3f4; --tinta:#12313a; --suave:#5c7780; --linea:#cfdde1;
  --agua:#1f8fb5; --agua-suave:rgba(31,143,181,.18); --vaso:#9db4bb; --bajo:#d9822b;
}
@media (prefers-color-scheme: dark){
  :root{
    --fondo:#0f1d22; --tinta:#e4eef0; --suave:#8fa8b0; --linea:#24383f;
    --agua:#38b0d6; --agua-suave:rgba(56,176,214,.2); --vaso:#4a6670; --bajo:#f0a04b;
  }
}
body.bajo{ --agua:var(--bajo); --agua-suave:rgba(217,130,43,.2); }
*{ box-sizing:border-box; }
body{
  margin:0; min-height:100vh; background:var(--fondo); color:var(--tinta);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  display:grid; place-items:center; padding:24px;
}
main{ width:min(920px,100%); display:grid; gap:40px; grid-template-columns:auto 1fr; align-items:center; }
.vaso{
  position:relative; width:min(200px,38vw); aspect-ratio:5/8; justify-self:center;
  border:3px solid var(--vaso); border-top-width:0; border-radius:0 0 26px 26px; overflow:hidden;
}
.agua{ position:absolute; left:0; right:0; bottom:0; height:0; background:var(--agua); transition:height 1.2s ease, background .4s; }
.marca{ position:absolute; left:0; right:0; border-top:1px dashed var(--vaso); font-size:11px; color:var(--suave); padding:1px 6px; }
.marca.sobre-agua{ color:#fff; }
h1{ margin:0; font-size:clamp(64px,12vw,112px); font-weight:300; line-height:1; font-variant-numeric:tabular-nums; }
h1 small{ font-size:.4em; margin-left:4px; color:var(--suave); }
h2{ font-size:14px; font-weight:600; margin:28px 0 8px; color:var(--suave); }
.estado{ margin:8px 0 0; font-size:18px; }
body.bajo .estado{ color:var(--bajo); font-weight:600; }
body.off .estado{ color:var(--bajo); }
dl{ display:flex; flex-wrap:wrap; gap:12px 40px; margin:22px 0 0; }
dt{ font-size:13px; color:var(--suave); }
dd{ margin:2px 0 0; font-size:20px; font-variant-numeric:tabular-nums; }
canvas{ width:100%; height:180px; display:block; }
.act{ margin:6px 0 0; font-size:12px; color:var(--suave); }
@media (max-width:640px){
  main{ grid-template-columns:1fr; gap:24px; }
  .vaso{ width:150px; }
}
@media (prefers-reduced-motion: reduce){ .agua{ transition:none; } }
[hidden]{ display:none !important; }
.cfg-btn{ margin-top:18px; background:none; border:1px solid var(--vaso); color:var(--tinta); border-radius:8px; padding:8px 14px; font:inherit; font-size:14px; cursor:pointer; }
.cfg-btn:hover{ border-color:var(--agua); }
dialog{ border:1px solid var(--vaso); border-radius:14px; background:var(--fondo); color:var(--tinta); padding:24px; width:min(420px,92vw); }
dialog::backdrop{ background:rgba(0,0,0,.45); }
dialog h3{ margin:0 0 4px; font-size:20px; font-weight:600; }
dialog .ayuda{ margin:0; font-size:13px; color:var(--suave); }
label{ display:block; margin-top:14px; font-size:13px; color:var(--suave); }
input,select{ width:100%; margin-top:4px; padding:9px 10px; font:inherit; font-size:16px; color:var(--tinta); background:transparent; border:1px solid var(--vaso); border-radius:8px; }
input:focus-visible,select:focus-visible,button:focus-visible{ outline:2px solid var(--agua); outline-offset:2px; }
.fila{ display:flex; gap:12px; }
.fila > label{ flex:1; }
.acciones{ display:flex; gap:10px; justify-content:flex-end; margin-top:22px; }
.acciones button{ font:inherit; font-size:15px; padding:9px 16px; border-radius:8px; border:1px solid var(--vaso); background:transparent; color:var(--tinta); cursor:pointer; }
.acciones button.principal{ background:var(--agua); border-color:var(--agua); color:#fff; }
#err{ color:var(--bajo); font-size:14px; min-height:1.2em; margin:12px 0 0; }
</style>
</head>
<body>
<main>
  <div class="vaso" role="img" aria-label="Nivel de agua de la cisterna">
    <div class="agua" id="agua"></div>
    <span class="marca" style="bottom:75%">75 %</span>
    <span class="marca" style="bottom:50%">50 %</span>
    <span class="marca" style="bottom:25%">25 %</span>
  </div>
  <section>
    <h1><span id="pct">--</span><small>%</small></h1>
    <p class="estado" id="estado">Conectando con la Raspberry Pi…</p>
    <dl>
      <div><dt>Volumen</dt><dd id="litros">--</dd></div>
      <div><dt>Distancia del sensor al agua</dt><dd id="dist">--</dd></div>
    </dl>
    <h2>Últimas 24 horas</h2>
    <canvas id="g"></canvas>
    <p class="act" id="act"></p>
    <button class="cfg-btn" id="abrir" type="button">Configurar cisterna</button>
  </section>
</main>
<dialog id="dlg">
  <form id="frm">
    <h3>Medidas de la cisterna</h3>
    <p class="ayuda">El sensor va arriba, apuntando al agua.</p>
    <label>Unidad
      <select id="unidad"><option value="cm">Centímetros (cm)</option><option value="m">Metros (m)</option><option value="pies">Pies</option></select>
    </label>
    <label>Altura: del sensor al fondo (<span class="u">cm</span>)
      <input id="altura" type="number" step="any" min="0" inputmode="decimal">
    </label>
    <label>Del sensor al agua cuando está llena (<span class="u">cm</span>)
      <input id="margen" type="number" step="any" min="0" inputmode="decimal" value="0">
    </label>
    <label>Forma, para calcular litros
      <select id="forma"><option value="ninguna">Solo porcentaje</option><option value="rectangular">Rectangular</option><option value="cilindrica">Cilíndrica</option></select>
    </label>
    <div class="fila" id="rect" hidden>
      <label>Largo (<span class="u">cm</span>)<input id="largo" type="number" step="any" min="0" inputmode="decimal"></label>
      <label>Ancho (<span class="u">cm</span>)<input id="ancho" type="number" step="any" min="0" inputmode="decimal"></label>
    </div>
    <div id="cil" hidden>
      <label>Diámetro (<span class="u">cm</span>)<input id="diametro" type="number" step="any" min="0" inputmode="decimal"></label>
    </div>
    <p id="err" role="alert"></p>
    <div class="acciones">
      <button type="button" id="cancelar">Cancelar</button>
      <button type="submit" class="principal">Guardar medidas</button>
    </div>
  </form>
</dialog>
<script>
const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.body).getPropertyValue(n).trim();
let ultimo = null;

async function leer(){
  try{
    const r = await fetch('/api/nivel', {cache:'no-store'});
    ultimo = await r.json();
    pintar(ultimo);
  }catch(e){
    document.body.classList.add('off');
    $('estado').textContent = 'Sin conexión con la Raspberry Pi';
  }
}

let yaAbierto = false;
function pintar(d){
  document.body.classList.remove('off');
  if(d.configurado === false){
    $('estado').textContent = 'Configura las medidas de la cisterna para empezar';
    $('pct').textContent = '--'; $('agua').style.height = '0%';
    if(!yaAbierto){ yaAbierto = true; abrir(); }
    return;
  }
  if(d.pct === null){
    $('estado').textContent = 'Esperando la primera lectura del sensor…';
    return;
  }
  const bajo = d.pct <= 15;
  document.body.classList.toggle('bajo', bajo);
  $('agua').style.height = d.pct + '%';
  document.querySelectorAll('.marca').forEach(m => {
    m.classList.toggle('sobre-agua', parseFloat(m.style.bottom) < d.pct);
  });
  $('pct').textContent = d.pct.toFixed(0);
  $('estado').textContent = !d.ok ? 'Sin lectura del sensor: se muestra el último nivel'
    : d.pct >= 95 ? 'Cisterna llena' : bajo ? 'Nivel bajo' : 'Nivel normal';
  $('litros').textContent = d.litros === null ? 'Sin forma configurada' : d.litros + ' de ' + d.cap + ' L';
  $('dist').textContent = d.d + ' cm';
  $('act').textContent = 'Actualizado a las ' + new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  grafica(d.hist);
}

function grafica(h){
  const c = $('g'), dpr = window.devicePixelRatio || 1, w = c.clientWidth, hh = c.clientHeight;
  c.width = w * dpr; c.height = hh * dpr;
  const x = c.getContext('2d'); x.scale(dpr, dpr); x.clearRect(0, 0, w, hh);
  const L = 36, B = 20, T = 6, R = 6, aw = w - L - R, ah = hh - T - B;
  x.font = '11px system-ui'; x.lineWidth = 1;
  [0, 50, 100].forEach(v => {
    const y = T + ah * (1 - v / 100);
    x.strokeStyle = css('--linea'); x.beginPath(); x.moveTo(L, y); x.lineTo(w - R, y); x.stroke();
    x.fillStyle = css('--suave'); x.textAlign = 'right'; x.fillText(v + '%', L - 6, y + 4);
  });
  if(!h || h.length < 2){
    x.textAlign = 'center'; x.fillText('Reuniendo datos…', L + aw / 2, T + ah / 2);
    return;
  }
  const t0 = h[0][0], t1 = h[h.length - 1][0], sp = Math.max(t1 - t0, 1);
  const px = t => L + aw * (t - t0) / sp, py = v => T + ah * (1 - v / 100);
  x.beginPath();
  h.forEach((p, i) => i ? x.lineTo(px(p[0]), py(p[1])) : x.moveTo(px(p[0]), py(p[1])));
  x.strokeStyle = css('--agua'); x.lineWidth = 2; x.stroke();
  x.lineTo(px(t1), py(0)); x.lineTo(px(t0), py(0)); x.closePath();
  x.fillStyle = css('--agua-suave'); x.fill();
  const hm = t => new Date(t * 1000).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
  x.fillStyle = css('--suave');
  x.textAlign = 'left'; x.fillText(hm(t0), L, hh - 4);
  x.textAlign = 'right'; x.fillText(hm(t1), w - R, hh - 4);
}

const CAMPOS = ['unidad', 'altura', 'margen', 'forma', 'largo', 'ancho', 'diametro'];
function actualizarForma(){
  const f = $('forma').value;
  $('rect').hidden = f !== 'rectangular';
  $('cil').hidden = f !== 'cilindrica';
}
$('forma').addEventListener('change', actualizarForma);
$('unidad').addEventListener('change', () => {
  document.querySelectorAll('.u').forEach(e => e.textContent = $('unidad').value);
});

async function abrir(){
  try{
    const r = await fetch('/api/config', {cache:'no-store'});
    const u = (await r.json()).ui || {};
    CAMPOS.forEach(k => { if(u[k] !== undefined) $(k).value = u[k]; });
  }catch(e){}
  actualizarForma();
  $('unidad').dispatchEvent(new Event('change'));
  $('err').textContent = '';
  $('dlg').showModal();
}

$('abrir').addEventListener('click', abrir);
$('cancelar').addEventListener('click', () => $('dlg').close());
$('frm').addEventListener('submit', async ev => {
  ev.preventDefault();
  const d = {};
  CAMPOS.forEach(k => d[k] = $(k).value);
  try{
    const r = await fetch('/api/config', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(d)});
    const j = await r.json();
    if(!j.ok){ $('err').textContent = j.error; return; }
    $('dlg').close();
    if(j.aviso) alert(j.aviso);
    leer();
  }catch(e){
    $('err').textContent = 'No se pudo guardar: sin conexión con la Raspberry Pi.';
  }
});

window.addEventListener('resize', () => { if(ultimo && ultimo.pct !== null) grafica(ultimo.hist); });
leer();
setInterval(leer, 3000);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
