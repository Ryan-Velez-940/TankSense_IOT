#!/usr/bin/env python3
"""
Medición de distancia con HC-SR04 en Raspberry Pi 4.
Configurado para aprovechar el alcance máximo del sensor (~4 m / 13 pies).

Conexiones (ECHO con divisor de voltaje 1 kΩ / 2 kΩ):
    VCC  -> 5V   (pin 2)
    GND  -> GND  (pin 6)
    TRIG -> GPIO 23 (pin 16)
    ECHO -> GPIO 24 (pin 18), a través del divisor
"""
import time
import RPi.GPIO as GPIO

# ---------------- Configuración ----------------
GPIO_TRIGGER = 23
GPIO_ECHO = 24

TEMPERATURA_C = 25.0   # Ajusta a la temperatura ambiente real (mejora la precisión)
MUESTRAS = 7           # Lecturas por medición (se usa la mediana)
MIN_VALIDAS = 3        # Mínimo de lecturas válidas para aceptar el resultado

# Rango válido: lo que esté fuera se descarta como ruido.
# 400 cm es el límite oficial del HC-SR04 (más allá son ecos de paredes/techo).
DISTANCIA_MIN_CM = 2
DISTANCIA_MAX_CM = 400

# Filtro anti-saltos: un cambio brusco solo se acepta si se repite
# en varias mediciones seguidas (evita picos falsos de una sola medición).
SALTO_MAX_CM = 30      # cambio mayor a esto se considera "salto"
CONFIRMACIONES = 3     # mediciones seguidas necesarias para aceptar un salto

# ---------------- Constantes derivadas ----------------
# Velocidad del sonido en cm/s según la temperatura
VELOCIDAD_SONIDO = (331.3 + 0.606 * TEMPERATURA_C) * 100

# Sin obstáculo, el HC-SR04 mantiene ECHO en alto ~38 ms y luego lo baja.
# Un pulso de ese largo significa "no hubo eco", no una distancia.
ECHO_SIN_OBJETO = 0.037   # s (con un pequeño margen bajo 38 ms)
TIMEOUT_INICIO = 0.020    # s máx. esperando que ECHO suba tras el trigger
TIMEOUT_ECHO = 0.045      # s máx. esperando que ECHO baje
PAUSA_ENTRE_MEDICIONES = 0.06  # s (recomendado por el fabricante: >= 60 ms)


def configurar():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(GPIO_TRIGGER, GPIO.OUT)
    GPIO.setup(GPIO_ECHO, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.output(GPIO_TRIGGER, False)
    time.sleep(0.1)  # dejar que el sensor se estabilice


def medir_distancia():
    """Una sola medición en cm, o None si no hubo eco válido."""
    time.sleep(PAUSA_ENTRE_MEDICIONES)  # evita ecos de la medición anterior

    # Pulso de ~10 µs en TRIG
    GPIO.output(GPIO_TRIGGER, True)
    time.sleep(0.00001)
    GPIO.output(GPIO_TRIGGER, False)

    # Esperar a que ECHO suba
    limite = time.perf_counter() + TIMEOUT_INICIO
    while GPIO.input(GPIO_ECHO) == 0:
        inicio = time.perf_counter()
        if inicio > limite:
            return None

    # Medir cuánto tiempo permanece ECHO en alto
    inicio = time.perf_counter()
    limite = inicio + TIMEOUT_ECHO
    llegada = inicio
    while GPIO.input(GPIO_ECHO) == 1:
        llegada = time.perf_counter()
        if llegada > limite:
            return None

    duracion = llegada - inicio
    if duracion >= ECHO_SIN_OBJETO:
        return None  # el sensor se rindió: no hay objeto en rango

    d = (duracion * VELOCIDAD_SONIDO) / 2
    if d < DISTANCIA_MIN_CM or d > DISTANCIA_MAX_CM:
        return None  # fuera del rango válido del sensor
    return d


def medir_mediana():
    """Mediana de varias lecturas en cm, o None si no hay suficientes válidas."""
    lecturas = []
    for _ in range(MUESTRAS):
        d = medir_distancia()
        if d is not None:
            lecturas.append(d)

    if len(lecturas) < MIN_VALIDAS:
        return None

    lecturas.sort()
    # Mediana inferior: nunca promedia dos grupos distintos de lecturas
    # (por ejemplo 11 cm y 500 cm) para inventar un valor intermedio.
    return lecturas[(len(lecturas) - 1) // 2]


class FiltroSaltos:
    """Acepta cambios pequeños de inmediato; los grandes, solo si se repiten."""

    def __init__(self):
        self.valor = None      # último valor aceptado
        self.candidato = None  # valor nuevo que aún se está confirmando
        self.cuenta = 0

    def procesar(self, d):
        if d is None:
            return None
        if self.valor is None or abs(d - self.valor) <= SALTO_MAX_CM:
            self.valor = d
            self.candidato, self.cuenta = None, 0
            return self.valor

        # Salto grande: llevar la cuenta de lecturas consistentes
        if self.candidato is not None and abs(d - self.candidato) <= SALTO_MAX_CM:
            self.cuenta += 1
            self.candidato = d
        else:
            self.candidato, self.cuenta = d, 1

        if self.cuenta >= CONFIRMACIONES:
            self.valor = d
            self.candidato, self.cuenta = None, 0
        return self.valor


def main():
    configurar()
    filtro = FiltroSaltos()
    try:
        while True:
            d = filtro.procesar(medir_mediana())
            if d is None:
                print("Sin lectura (fuera de rango, superficie que no refleja o sin eco)")
            else:
                print(f"Distancia = {d:.1f} cm  ({d / 30.48:.2f} pies)")
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\nMedición detenida por el usuario")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
