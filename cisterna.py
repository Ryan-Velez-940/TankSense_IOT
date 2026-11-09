#!/usr/bin/env python3
"""
Nivel de una cisterna con HC-SR04 en Raspberry Pi 4.

El sensor va montado arriba, apuntando hacia abajo, al agua.
Pregunta las medidas de la cisterna y muestra el porcentaje de llenado
(y los litros, si se indica la forma de la cisterna).

Requiere distancia.py en la misma carpeta.
"""
import json
import math
import os
import time

import RPi.GPIO as GPIO
import distancia as sensor

ARCHIVO_CONFIG = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cisterna_config.json"
)
A_CM = {"cm": 1.0, "m": 100.0, "pies": 30.48}
INTERVALO = 2  # segundos entre actualizaciones


# ---------------- Entrada de datos ----------------
def pedir_numero(texto, minimo=None, defecto=None):
    sufijo = f" [{defecto}]" if defecto is not None else ""
    while True:
        s = input(f"{texto}{sufijo}: ").strip().replace(",", ".")
        if s == "" and defecto is not None:
            return float(defecto)
        try:
            v = float(s)
        except ValueError:
            print("  Escribe un número válido.")
            continue
        if minimo is not None and v < minimo:
            print(f"  El valor debe ser al menos {minimo}.")
            continue
        return v


def pedir_opcion(texto, opciones, defecto=None):
    sufijo = f" [{defecto}]" if defecto else ""
    while True:
        s = input(f"{texto} ({' / '.join(opciones)}){sufijo}: ").strip().lower()
        if s == "" and defecto:
            return defecto
        if s in opciones:
            return s
        print("  Opción no válida.")


def pedir_config():
    print("\n=== Configuración de la cisterna ===")
    unidad = pedir_opcion("Unidad de medida", list(A_CM), "cm")
    f = A_CM[unidad]

    while True:
        altura = pedir_numero(
            f"Altura: distancia del sensor al FONDO de la cisterna ({unidad})",
            minimo=0.01,
        ) * f
        margen = pedir_numero(
            f"Distancia del sensor al agua cuando está LLENA ({unidad}; "
            f"recomendado >= 5 cm)",
            minimo=0, defecto=0,
        ) * f
        if margen < altura:
            break
        print("  El margen debe ser menor que la altura. Intenta de nuevo.")

    if altura > sensor.DISTANCIA_MAX_CM:
        print(
            f"  AVISO: el sensor solo lee hasta {sensor.DISTANCIA_MAX_CM} cm. "
            "Con la cisterna casi vacía no habrá lectura."
        )

    forma = pedir_opcion(
        "Forma, para calcular litros", ["rectangular", "cilindrica", "ninguna"],
        "ninguna",
    )
    area_cm2 = None
    if forma == "rectangular":
        largo = pedir_numero(f"Largo ({unidad})", minimo=0.01) * f
        ancho = pedir_numero(f"Ancho ({unidad})", minimo=0.01) * f
        area_cm2 = largo * ancho
    elif forma == "cilindrica":
        diametro = pedir_numero(f"Diámetro ({unidad})", minimo=0.01) * f
        area_cm2 = math.pi * (diametro / 2) ** 2

    cfg = {"altura_cm": altura, "margen_cm": margen, "area_cm2": area_cm2}
    try:
        with open(ARCHIVO_CONFIG, "w") as a:
            json.dump(cfg, a)
    except OSError as e:
        print(f"  No se pudo guardar la configuración: {e}")
    return cfg


def obtener_config():
    if os.path.exists(ARCHIVO_CONFIG):
        try:
            with open(ARCHIVO_CONFIG) as a:
                cfg = json.load(a)
            _ = cfg["altura_cm"], cfg["margen_cm"], cfg["area_cm2"]
            util = cfg["altura_cm"] - cfg["margen_cm"]
            if util <= 0:
                raise ValueError
            lit = ""
            if cfg["area_cm2"]:
                lit = f", capacidad {cfg['area_cm2'] * util / 1000:.0f} L"
            print(
                f"Configuración guardada: altura {cfg['altura_cm']:.1f} cm, "
                f"margen {cfg['margen_cm']:.1f} cm{lit}"
            )
            if pedir_opcion("¿Usar esta configuración?", ["s", "n"], "s") == "s":
                return cfg
        except (OSError, ValueError, KeyError, TypeError):
            print("La configuración guardada no es válida; se pedirá de nuevo.")
    return pedir_config()


# ---------------- Cálculo ----------------
def calcular(cfg, d_cm):
    """Devuelve (porcentaje, litros_actuales, litros_capacidad) para una distancia."""
    util = cfg["altura_cm"] - cfg["margen_cm"]          # profundidad útil
    nivel = min(max(cfg["altura_cm"] - d_cm, 0.0), util)  # profundidad de agua
    porcentaje = nivel / util * 100
    if cfg["area_cm2"]:
        return (
            porcentaje,
            cfg["area_cm2"] * nivel / 1000,
            cfg["area_cm2"] * util / 1000,
        )
    return porcentaje, None, None


def barra(porcentaje, ancho=20):
    llenos = round(porcentaje / 100 * ancho)
    return "[" + "█" * llenos + "░" * (ancho - llenos) + "]"


def main():
    cfg = obtener_config()
    sensor.configurar()
    filtro = sensor.FiltroSaltos()
    print("\nMidiendo... (Ctrl+C para salir)\n")
    try:
        while True:
            d = filtro.procesar(sensor.medir_mediana())
            if d is None:
                print("Sin lectura (revisa el sensor o que haya agua en rango)")
            else:
                pct, litros, cap = calcular(cfg, d)
                texto = f"Nivel: {pct:5.1f} % {barra(pct)}"
                if litros is not None:
                    texto += f"  {litros:.0f} / {cap:.0f} L"
                print(f"{texto}   (sensor a {d:.1f} cm del agua)")
            time.sleep(INTERVALO)
    except KeyboardInterrupt:
        print("\nMedición detenida por el usuario")
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
