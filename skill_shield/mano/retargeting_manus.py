"""
Retargeting GUANTE → datos.ctrl[] de la OrcaHand.

Mucho más simple que retargeting.py (cámara): el guante ya da ángulos por
articulación, así que cada actuador sale de una fórmula lineal:

    q = offset + signo · escala · radianes(valor_guante)

La tabla MANUS_MAPEO de config.py dice qué valor del guante alimenta cada
actuador. Si un dedo se mueve al revés → cambia su signo. Si se queda corto →
sube su escala. Si en reposo no queda en su sitio → retoca su offset.

NO toca la muñeca (ctrl[0]): el guante no la mide. Se sigue sacando de la cámara.
"""
import math

import numpy as np

from config import *

# Nombres de cada índice de ctrl de la mano (para imprimir)
NOMBRES_CTRL = [
    "muneca", "menique_abd", "menique_mcp", "menique_pip",
    "anular_abd", "anular_mcp", "anular_pip",
    "corazon_abd", "corazon_mcp", "corazon_pip",
    "indice_abd", "indice_mcp", "indice_pip",
    "pulgar_cmc", "pulgar_abd", "pulgar_mcp", "pulgar_ip",
]


def _valor(lectura: dict, clave):
    """Una clave → su valor. Una tupla de claves → la media (p.ej. PIP+DIP)."""
    if isinstance(clave, (tuple, list)):
        return sum(lectura[c] for c in clave) / len(clave)
    return lectura[clave]


def calcular_ctrl_manus(lectura: dict) -> dict:
    """{índice_ctrl: q en rad} ya recortado a LIMITES_CTRL, sin suavizar."""
    objetivo = {}
    for idx, (clave, signo, escala, offset) in MANUS_MAPEO.items():
        q = offset if clave is None else \
            offset + signo * escala * math.radians(_valor(lectura, clave))
        lo, hi = LIMITES_CTRL[idx]
        objetivo[idx] = float(np.clip(q, lo, hi))
    return objetivo


def retarget_manus_a_ctrl(datos, lectura: dict, estado: dict) -> dict:
    """Escribe los dedos de la OrcaHand en datos.ctrl[] a partir del guante.
    Mismo papel que retarget_a_ctrl(), así el resto del programa no cambia."""
    ctrl_mano = datos.ctrl[OFFSET_MANO: OFFSET_MANO + N_ACT]
    objetivo = calcular_ctrl_manus(lectura)

    # Suavizado exponencial ligero (el guante apenas tiembla: valor alto = poco retraso)
    a = float(MANUS_SUAVIZADO)
    previo = estado.get("manus_ctrl_previo")
    for idx, q in objetivo.items():
        if previo is not None and idx in previo:
            q = previo[idx] + a * (q - previo[idx])
        ctrl_mano[idx] = q
        objetivo[idx] = q

    estado["manus_ctrl_previo"] = objetivo
    estado["manus_lectura"] = lectura
    return estado
