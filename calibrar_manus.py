#!/usr/bin/env python3
"""
Calibración guante MANUS → OrcaHand  (genera manus_calibracion.json)
====================================================================
Antes: calibra el guante en el MANUS Core Dashboard (o con sdk_client.py → [C]).

    python calibrar_manus.py          # calibración guiada (~2 min)
    python calibrar_manus.py --ver    # solo ver en vivo los 20 ángulos de tu mano

Te pide unas poses (mano abierta, dedos juntos, dedos separados y las 7 pinzas de
Skill Shield). En cada una mide tus ángulos y ajusta, actuador por actuador, la recta
ctrl = ganancia·ángulo + offset  que mejor lleva TU pose a la pose de la OrcaHand (las
pinzas, a los valores ya calibrados en el visor: PINZA_CTRL_CONTACTO). Así también se
resuelven los SIGNOS (hacia qué lado abre cada dedo).

Con MANUS_FLEXION_DIRECTA = True (config.py) solo se ajustan las ABDUCCIONES y el PULGAR:
la flexión de los 4 dedos sale directa de la calibración de MANUS, así que el puño no
hace falta. Con False se ajusta todo, como antes (y se pide también el puño).
"""
import json
import math
import sys
import time

import numpy as np

from config import LIMITES_CTRL, POSICION_STANDBY
from skill_shield.mano.manus_guante import (
    ERGO, FLEXIONES, GuanteManus, MANUS_CALIBRACION, MANUS_FLEXION_DIRECTA, MAPEO_DEFECTO,
    angulos_a_ctrl, cargar_mapeo,
)

# ── Poses objetivo de la OrcaHand (índices de ctrl de la mano, rad) ───────────
ABIERTA = {i: 0.0 for i in (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12)}
ABIERTA.update({13: POSICION_STANDBY[13], 14: POSICION_STANDBY[14],
                15: POSICION_STANDBY[15], 16: POSICION_STANDBY[16]})
PUNO = {2: 1.5, 3: 1.5, 5: 1.5, 6: 1.5, 8: 1.5, 9: 1.5, 11: 1.5, 12: 1.5}
# Dedos estirados y PEGADOS: la convergencia que usa retargeting.py (CONV_* · FUERZA_ABD)
JUNTOS = {10: -0.27, 4: 0.225, 1: 0.42}
# Dedos estirados y SEPARADOS en abanico (dentro de LIMITES_CTRL)
SEPARADOS = {10: 0.40, 4: -0.20, 1: -0.20}
# Copia de PINZA_CTRL_CONTACTO (retargeting.py): valores medidos en el visor MuJoCo
PINZAS = {
    "indice":         {10: 0.000, 11: 0.491, 12: 1.250, 13: 0.000, 14: 0.469, 15: 0.469, 16: 0.888},
    "corazon":        {8: 0.916, 9: 1.540, 13: 0.426, 14: 0.113, 15: 0.174, 16: 1.720},
    "anular":         {4: -0.0565, 5: 1.230, 6: 0.675, 13: 0.000, 14: -0.282, 15: 0.905, 16: 0.526},
    "menique":        {1: 0.0995, 2: 1.130, 3: 0.366, 13: 0.576, 14: -0.301, 15: 0.207, 16: 0.888},
    "corazon_anular": {4: 0.066, 5: 1.040, 6: 0.867, 8: 1.130, 9: 0.888,
                       13: 0.406, 14: 0.0171, 15: 0.229, 16: 0.217},
    "indice_corazon": {8: 0.916, 9: 0.835, 10: -0.0571, 11: 0.840, 12: 0.643,
                       13: 0.419, 14: 0.291, 15: 0.000, 16: 0.526},
    "anular_menique": {1: 0.194, 2: 0.982, 3: 0.739, 4: -0.0377, 5: 0.916, 6: 0.984,
                       13: 0.236, 14: -0.212, 15: 0.982, 16: 0.292},
}
POSES = [
    ("mano ABIERTA y relajada, dedos estirados", ABIERTA),
] + ([] if MANUS_FLEXION_DIRECTA else [("PUÑO cerrado (pulgar como te salga)", PUNO)]) + [
    ("dedos estirados y JUNTOS (pegados entre sí)", JUNTOS),
    ("dedos estirados y SEPARADOS en abanico", SEPARADOS),
] + [(f"PINZA pulgar ↔ {n.replace('_', ' + ')} (yemas tocándose)", t) for n, t in PINZAS.items()]

# Fuentes de cada actuador para el ajuste (1-2 ángulos de MANUS)
FUENTES = {k: list(f) for k, (f, _, _) in MAPEO_DEFECTO.items()}
FUENTES[13] = ["THUMB_CMC_STRETCH", "THUMB_CMC_SPREAD"]     # oposición: combinación
FUENTES[14] = ["THUMB_CMC_SPREAD", "THUMB_CMC_STRETCH"]
ESPERA_S, MEDIR_S = 2.0, 1.5
RIDGE = 0.02          # regularización de las ganancias (evita ajustes locos con pocas poses)


def medir(guante, segundos):
    muestras, t0 = [], time.perf_counter()
    while time.perf_counter() - t0 < segundos:
        ang, edad = guante.angulos()
        if ang is not None and edad < 0.2:
            muestras.append(ang)
        time.sleep(0.01)
    if len(muestras) < 10:
        return None, None
    m = np.array(muestras)
    return m.mean(axis=0), m.std(axis=0)


def ajustar(medidas):
    """medidas: [(ángulos rad (20,), {ctrl: objetivo})] → (mapeo, informe)."""
    mapeo, informe = {}, {}
    for k, (f_def, g_def, o_def) in MAPEO_DEFECTO.items():
        if not f_def:                                           # corazón ABD: fijo
            mapeo[k] = ([], [], 0.0)
            continue
        if MANUS_FLEXION_DIRECTA and k in FLEXIONES:            # directa de MANUS: no se ajusta
            continue
        fuentes = FUENTES[k]
        filas = [(np.array([a[ERGO[f]] for f in fuentes]), t[k]) for a, t in medidas if k in t]
        if len(filas) < len(fuentes) + 1:
            fuentes, filas = fuentes[:1], [(x[:1], y) for x, y in filas]
        if len(filas) < 2 or np.std([x[0] for x, _ in filas]) < math.radians(3):
            mapeo[k] = (list(f_def), list(g_def), o_def)
            informe[k] = "sin datos suficientes → valor por defecto"
            continue
        X = np.array([x for x, _ in filas])
        y = np.array([v for _, v in filas])
        Xm, ym = X.mean(axis=0), y.mean()
        Xc = X - Xm
        g = np.linalg.solve(Xc.T @ Xc + RIDGE * np.eye(X.shape[1]), Xc.T @ (y - ym))
        o = float(ym - Xm @ g)
        lo, hi = LIMITES_CTRL[k]
        pred = np.clip(X @ g + o, lo, hi)
        mapeo[k] = (fuentes, [float(v) for v in g], o)
        informe[k] = (f"{' + '.join(f'{v:+.2f}·{f}' for f, v in zip(fuentes, g))} {o:+.2f}   "
                      f"error medio {math.degrees(np.sqrt(np.mean((pred - y) ** 2))):4.1f}° "
                      f"({len(filas)} poses)")
    return mapeo, informe


def main():
    guante = GuanteManus()
    if not guante.iniciar():
        return 1
    print("Esperando datos del guante...")
    t0 = time.perf_counter()
    while not guante.datos_frescos():
        if time.perf_counter() - t0 > 20:
            print("❌ No llegan datos del guante en 20 s (¿Dashboard abierto, guante encendido?).")
            guante.cerrar()
            return 1
        time.sleep(0.2)

    if "--ver" in sys.argv:
        print("Ángulos de tu mano en vivo (Ctrl+C para salir)")
        nombres = sorted(ERGO, key=ERGO.get)
        try:
            while True:
                ang, _ = guante.angulos()
                print("\r" + "  ".join(f"{n.split('_', 1)[1][:9]}={a:6.1f}" for n, a in zip(nombres, ang))
                      if ang else "\rsin datos", end="", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print()
        guante.cerrar()
        return 0

    print(f"\n🧤 Calibración guante → OrcaHand: {len(POSES)} poses. En cada una: colócate, "
          f"pulsa ENTER y mantén la pose ~{ESPERA_S + MEDIR_S:.0f} s.\n")
    medidas = []
    for i, (texto, objetivo) in enumerate(POSES, 1):
        input(f"[{i}/{len(POSES)}] {texto}  → ENTER (o escribe 's' + ENTER para saltarla) ")
        time.sleep(ESPERA_S)
        media, dispersion = medir(guante, MEDIR_S)
        if media is None:
            print("   ⚠️  sin datos, pose descartada")
            continue
        if dispersion.max() > 8.0:
            print(f"   ⚠️  te has movido bastante (hasta {dispersion.max():.0f}°): la uso igualmente")
        medidas.append((np.radians(media), objetivo))
        print("   ✓ medida")
    guante.cerrar()
    if len(medidas) < 4:
        print("❌ Muy pocas poses: no se guarda nada.")
        return 1

    mapeo, informe = ajustar(medidas)
    print("\nResultado (ctrl = Σ ganancia·ángulo[rad] + offset):")
    if MANUS_FLEXION_DIRECTA:
        print("  (flexión de los 4 dedos: directa de MANUS × MANUS_GANANCIA_FLEXION, no se guarda aquí)")
    nombres = {1: "meñique abd", 2: "meñique mcp", 3: "meñique pip", 4: "anular abd",
               5: "anular mcp", 6: "anular pip", 8: "corazón mcp", 9: "corazón pip",
               10: "índice abd", 11: "índice mcp", 12: "índice pip", 13: "pulgar cmc",
               14: "pulgar abd", 15: "pulgar mcp", 16: "pulgar ip"}
    for k in sorted(informe):
        print(f"  ctrl[{k:2d}] {nombres.get(k, ''):12s} {informe[k]}")
    with open(MANUS_CALIBRACION, "w", encoding="utf-8") as fh:
        json.dump({"fecha": time.strftime("%Y-%m-%d %H:%M"),
                   "mapeo": {str(k): {"fuentes": f, "ganancias": g, "offset": o}
                             for k, (f, g, o) in mapeo.items()},
                   "poses": len(medidas)}, fh, indent=2, ensure_ascii=False)
    print(f"\n💾 Guardado en {MANUS_CALIBRACION}. Skill Shield lo carga al arrancar.")
    # Comprobación rápida: la mano abierta medida → ctrl
    print("Mano abierta → ctrl:",
          np.round(angulos_a_ctrl(medidas[0][0], cargar_mapeo(verbose=False))[1:], 2))
    return 0


if __name__ == "__main__":
    sys.exit(main())