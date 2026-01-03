#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Raspberry Pi web-app: HTTP/MJPEG stream + moottoriohjaus
- Näyttää ESP32:n HTTP/MJPEG-streamin selaimessa
- Intuitiivinen ohjaus (ylös=eteen, alas=taakse)
"""

import os
import sys
import time
import signal
import logging
import threading
import requests
import RPi.GPIO as GPIO
from flask import Flask, Response, jsonify, request, render_template_string

# -------------------- KONFIGURAATIO --------------------

# ESP32:n HTTP/MJPEG stream-osoite
MJPEG_URL = os.environ.get("MJPEG_URL", "http://(ip-osoite)/stream")

# Moottoripinnit (VASEN moottori on nyt ENB, IN3, IN4)
ENB = 18  # Vasen moottori PWM
IN3 = 17  # Vasen moottori pinni
IN4 = 27  # Vasen moottori pinni
ENA = 19  # Oikea moottori PWM
IN1 = 24  # Oikea moottori eteenpäin
IN2 = 23  # Oikea moottori taaksepäin

# Oletusnopeudet
DEFAULT_SPEED = 70       # 0..100 (eteen/taakse)
TURN_SPEED = 40          # 0..100 (käännökset)
PWM_FREQ = 1000          # 1kHz

# -------------------- LOKITUS --------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger("rc-app")

# -------------------- GPIO / MOOTTORIT --------------------

class MotorController:
    def __init__(self):
        # Alusta GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup([ENA, IN1, IN2, ENB, IN3, IN4], GPIO.OUT)
        
        # Alusta PWM
        self.pwm_a = GPIO.PWM(ENA, PWM_FREQ)  # Oikea moottori
        self.pwm_b = GPIO.PWM(ENB, PWM_FREQ)  # Vasen moottori
        self.pwm_a.start(0)
        self.pwm_b.start(0)
        
        self._lock = threading.Lock()
        self.current_action = None
        self.current_speed = DEFAULT_SPEED
        self.turn_speed = TURN_SPEED

    def _set_motors(self, left_speed, right_speed, left_dir, right_dir):
        """Apufunktio moottorien ohjaamiseen"""

        # Vasen moottori (ENB, IN3, IN4) käänteisesti
        with self._lock:
            if left_dir == 'forward':
                GPIO.output(IN3, GPIO.LOW)
                GPIO.output(IN4, GPIO.HIGH)
            elif left_dir == 'backward':
                GPIO.output(IN3, GPIO.HIGH)
                GPIO.output(IN4, GPIO.LOW)
            else:
                GPIO.output(IN3, GPIO.LOW)
                GPIO.output(IN4, GPIO.LOW)
            self.pwm_b.ChangeDutyCycle(left_speed)

            # OIKEA moottori (ENA, IN1, IN2) normaalisti
            GPIO.output(IN1, GPIO.HIGH if right_dir == 'forward' else GPIO.LOW)
            GPIO.output(IN2, GPIO.HIGH if right_dir == 'backward' else GPIO.LOW)
            self.pwm_a.ChangeDutyCycle(right_speed)

    def forward(self):
        log.debug("Moving forward")
        self._set_motors(self.current_speed, self.current_speed, 'forward', 'forward')
        self.current_action = 'forward'

    def backward(self):
        log.debug("Moving backward")
        self._set_motors(self.current_speed, self.current_speed, 'backward', 'backward')
        self.current_action = 'backward'

    def left(self):
        log.debug("Turning left (gentle)")
        self._set_motors(self.turn_speed, self.turn_speed, 'backward', 'forward')
        self.current_action = 'left'

    def right(self):
        log.debug("Turning right (gentle)")
        self._set_motors(self.turn_speed, self.turn_speed, 'forward', 'backward')
        self.current_action = 'right'

    def stop(self):
        log.debug("Stopping motors")
        with self._lock:
            self.pwm_a.ChangeDutyCycle(0)
            self.pwm_b.ChangeDutyCycle(0)
            self.current_action = None

    def set_speed(self, speed):
        """Aseta molempien moottorien nopeus (0-100)"""
        with self._lock:
            self.current_speed = max(0, min(100, speed))
            # Päivitä nopeus jos ollaan liikkeessä
            if self.current_action == 'forward' or self.current_action == 'backward':
                self._set_motors(
                    self.current_speed,
                    self.current_speed,
                    'forward' if self.current_action == 'forward' else 'backward',
                    'forward' if self.current_action == 'forward' else 'backward'
                )
            elif self.current_action == 'left' or self.current_action == 'right':
                self._set_motors(
                    self.turn_speed,
                    self.turn_speed,
                    'backward' if self.current_action == 'left' else 'forward',
                    'forward' if self.current_action == 'left' else 'backward'
                )

    def cleanup(self):
        try:
            self.stop()
            self.pwm_a.stop()
            self.pwm_b.stop()
            GPIO.cleanup()
        except Exception as e:
            log.error(f"Error cleaning up GPIO: {e}")

motor = MotorController()

# -------------------- HTTP/MJPEG LUKU --------------------

def mjpeg_generator():
    """Lukee ESP32:n HTTP/MJPEG-streamiä"""
    boundary = b"--frame"
    headers = {'Connection': 'keep-alive'}
    
    try:
        with requests.get(MJPEG_URL, stream=True, headers=headers) as r:
            r.raise_for_status()
            
            buffer = b""
            for chunk in r.iter_content(chunk_size=1024):
                buffer += chunk
                
                while True:
                    boundary_pos = buffer.find(boundary)
                    if boundary_pos == -1:
                        if len(buffer) > 4096:
                            buffer = buffer[-4096:]
                        break
                    
                    boundary_end = buffer.find(b"\r\n\r\n", boundary_pos)
                    if boundary_end == -1:
                        break
                    
                    jpg_start = boundary_end + 4
                    next_boundary = buffer.find(boundary, jpg_start)
                    if next_boundary == -1:
                        break
                    
                    jpg_data = buffer[jpg_start:next_boundary]
                    
                    yield (boundary + b"\r\n" +
                           b"Content-Type: image/jpeg\r\n" +
                           b"Content-Length: " + str(len(jpg_data)).encode() + b"\r\n\r\n" +
                           jpg_data + b"\r\n")
                    
                    buffer = buffer[next_boundary:]
    except Exception as e:
        log.error(f"Virhe MJPEG-streamissä: {e}")
        yield (boundary + b"\r\n" +
               b"Content-Type: text/plain\r\n\r\n" +
               f"Virhe streamissä: {e}".encode() + b"\r\n")

# -------------------- FLASK APP --------------------

app = Flask("rc-web")

    INDEX_HTML = """
<!doctype html>
<html lang="fi">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>RC Web Controller</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; background:#0b0d10; color:#e6ebf0; }
  header { padding: 12px 16px; background:#10141a; border-bottom:1px solid #1d2430; display:flex; align-items:center; gap:12px;}
  .pill { padding:4px 8px; border-radius:999px; background:#1a2332; color:#c9d7e3; font-size:12px;}
  main { display:grid; grid-template-columns: 1fr 320px; gap:16px; padding:16px; }
  .card { background:#10141a; border:1px solid #1d2430; border-radius:16px; overflow:hidden; }
  .card h3 { margin:12px 16px; font-size:16px; font-weight:600; color:#d9e3ec; }
  .video { display:flex; align-items:center; justify-content:center; background:#000; aspect-ratio: 16/9; }
  .video img { width:100%; height:auto; display:block; }
  .controls { padding:16px; display:grid; gap:10px; }
  .grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; }
  button { background:#1a2332; color:#cfe0f1; border:1px solid #273246; border-radius:12px; padding:10px 12px; font-size:14px; cursor:pointer; }
  button:hover { background:#213049; }
  button:active { background:#2a3a5a; }
  .row { display:flex; align-items:center; gap:8px; }
  input[type="range"] { width:100%; }
  small { color:#98a6b5; }
  footer { padding:12px 16px; color:#7c8a99; }
  @media (max-width: 900px) { main { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<header>
  <div style="font-weight:700;">RC Web Controller</div>
  <div class="pill">HTTP/MJPEG</div>
  <div class="pill">{{ mjpeg_url }}</div>
</header>

<main>
  <div class="card">
    <h3>Kamera</h3>
    <div class="video">
      <img src="/video.mjpeg" alt="Live video" />
    </div>
  </div>

  <div class="card">
    <h3>Ohjaus</h3>
    <div class="controls">
      <div class="row">
        <label>Nopeus</label>
        <input id="speed" type="range" min="30" max="100" value="{{ default_speed }}" />
      </div>
      <div class="grid">
        <span></span>
        <button id="forwardBtn" 
                onmousedown="cmd('forward')" 
                ontouchstart="cmd('forward')"
                onmouseup="cmd('stop')" 
                ontouchend="cmd('stop')"
                onmouseleave="cmd('stop')">▲ Eteen</button>
        <span></span>

        <button id="leftBtn" 
                onmousedown="cmd('left')" 
                ontouchstart="cmd('left')"
                onmouseup="cmd('stop')" 
                ontouchend="cmd('stop')"
                onmouseleave="cmd('stop')">◀ Vasen</button>
        <button id="stopBtn" onclick="cmd('stop')">■ Stop</button>
        <button id="rightBtn" 
                onmousedown="cmd('right')" 
                ontouchstart="cmd('right')"
                onmouseup="cmd('stop')" 
                ontouchend="cmd('stop')"
                onmouseleave="cmd('stop')">Oikea ▶</button>

        <span></span>
        <button id="backwardBtn" 
                onmousedown="cmd('backward')" 
                ontouchstart="cmd('backward')"
                onmouseup="cmd('stop')" 
                ontouchend="cmd('stop')"
                onmouseleave="cmd('stop')">▼ Taakse</button>
        <span></span>
      </div>
      <small>Näppäimet: W=eteen, S=taakse, A=vasen, D=oikea, Space=stop</small>
    </div>
  </div>
</main>

<footer>
  <small>Status: <span id="status">—</span></small>
</footer>

<script>
const statusEl = document.getElementById('status');
const speedEl = document.getElementById('speed');

// Päivitä nopeus reaaliajassa
speedEl.addEventListener('input', () => {
  fetch('/api/motor/speed', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({speed: Number(speedEl.value)})
  });
});

// Komentojen lähetys
async function cmd(action) {
  try {
    const r = await fetch('/api/motor', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action})
    });
    const j = await r.json();
    statusEl.textContent = j.ok ? 'OK' : ('Virhe: ' + (j.error||''));
  } catch(e) {
    statusEl.textContent = 'Virhe: ' + e;
  }
}

// Näppäimistöohjaus
document.addEventListener('keydown', (e) => {
  if (e.repeat) return;
  const k = e.key.toLowerCase();
  if (k === 'w') cmd('forward');
  else if (k === 's') cmd('backward');
  else if (k === 'a') cmd('left');
  else if (k === 'd') cmd('right');
  else if (k === ' ') cmd('stop');
});

document.addEventListener('keyup', (e) => {
  const k = e.key.toLowerCase();
  if (['w','a','s','d'].includes(k)) cmd('stop');
});
</script>
</body>
</html>
"""

# -------------------- ROUTET --------------------

@app.route("/")
def index():
    return render_template_string(
        INDEX_HTML,
        mjpeg_url=MJPEG_URL,
        default_speed=DEFAULT_SPEED
    )

@app.route("/health")
def health():
    return jsonify(ok=True, mjpeg=MJPEG_URL)

@app.route("/video.mjpeg")
def video_mjpeg():
    return Response(
        mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/api/motor", methods=["POST"])
def api_motor():
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").lower()

    try:
        if action == "forward":
            motor.forward()
        elif action == "backward":
            motor.backward()
        elif action == "left":
            motor.left()
        elif action == "right":
            motor.right()
        elif action == "stop":
            motor.stop()
        else:
            return jsonify(ok=False, error=f"Tuntematon action '{action}'"), 400
        return jsonify(ok=True, action=action)
    except Exception as e:
        log.exception("Moottorikomento epäonnistui")
        return jsonify(ok=False, error=str(e)), 500

@app.route("/api/motor/speed", methods=["POST"])
def api_motor_speed():
    data = request.get_json(silent=True) or {}
    speed = int(data.get("speed") or DEFAULT_SPEED)
    speed = max(0, min(100, speed))
    
    try:
        motor.set_speed(speed)
        return jsonify(ok=True, speed=speed)
    except Exception as e:
        log.exception("Nopeuden asetus epäonnistui")
        return jsonify(ok=False, error=str(e)), 500

# -------------------- SIIVOUS --------------------

def _graceful_exit(*_):
    log.info("Suljetaan...")
    try:
        motor.cleanup()
    finally:
        os._exit(0)

signal.signal(signal.SIGINT, _graceful_exit)
signal.signal(signal.SIGTERM, _graceful_exit)

# -------------------- MAIN --------------------

if __name__ == "__main__":
    if not MJPEG_URL.startswith("http://"):
        log.warning("MJPEG_URL ei näytä HTTP-osoitteelta: %s", MJPEG_URL)
    log.info("MJPEG lähde: %s", MJPEG_URL)
    log.info("Käynnistyy http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)