#!/usr/bin/env python3
"""
Calibración guante MANUS → OrcaHand  (genera manus_calibracion.json, versión 2)
=================================================================================
    python calibrar_manus.py            # calibración guiada (~3 min, 14 poses)
    python calibrar_manus.py --ver      # solo ver en vivo los 20 ángulos de tu mano
    python calibrar_manus.py --probar   # ver en vivo el ctrl que saldría + la pinza detectada

QUÉ HACE (v2, por RANGOS — ya no hay regresión por mínimos cuadrados):
  Para cada actuador de la OrcaHand mide TU ángulo en dos poses extremas (p. ej. mano
  abierta y puño) y lo hace corresponder con el ctrl del robot en esas poses
  (config.MANUS_RANGO_ROBOT). Así:
    · tu puño cerrado = puño cerrado del robot (llega al límite), tu abanico = abanico
      del robot, tu pulgar en cada extremo = pulgar del robot en su extremo;
    · el SIGNO de cada articulación sale de tus propias medidas (si tu "separados" da un
      ángulo menor que tu "juntos", la recta ya es decreciente): se acabaron los dedos
      que van al revés.
  Además graba tus 7 pinzas: en teleoperación, cuando tu mano se parece a una de ellas,
  la OrcaHand se mezcla con su pose de contacto calibrada (PINZA_CTRL_CONTACTO) para
  que las yemas se toquen de verdad.

CONSEJOS: mantén cada pose quieta ~3 s; en las poses de "extremo" fuerza de verdad el
extremo (puño apretado, dedos muy separados, pulgar bien cruzado). Las pinzas, con las
yemas tocándose como las harías para coger algo pequeño.
"""
import json
import sys
import time

import numpy as np

from skill_shield.mano.manus_guante import (
    ERGO, FUENTES, NOMBRES, PINZA_ERGO, RANGO_ROBOT, GuanteManus, MANUS_CALIBRACION,
    _RANGO_HUMANO_DEFECTO, angulos_a_ctrl, cargar_calibracion, distancia_pinza,
)

ESPERA_S, MEDIR_S = 2.0, 1.5

# (clave, texto que se muestra)
POSES = [
    ("abierta",    "mano ABIERTA y relajada, dedos estirados y JUNTOS (pegados entre sí), pulgar relajado"),
    ("puno",       "PUÑO cerrado y APRETADO (pulgar por fuera, como te salga)"),
    ("separados",  "dedos estirados y SEPARADOS al máximo (abanico)"),
    ("pulgar_plano", "PULGAR tumbado en el PLANO de la palma y lo más SEPARADO del índice (una 'L' plana)"),
    ("pulgar_perp",  "PULGAR PERPENDICULAR a la palma (apuntando hacia delante de la palma), dedos estirados"),
    ("pulgar_cruz",  "PULGAR CRUZADO sobre la palma hasta la base del MEÑIQUE, dedos estirados"),
    ("pulgar_flex",  "PULGAR DOBLADO al máximo (nudillo y punta), dedos estirados"),
]
PINZAS = ["indice", "corazon", "anular", "menique", "corazon_anular", "indice_corazon", "anular_menique"]
POSES += [(f"pinza_{n}", f"PINZA pulgar ↔ {n.replace('_', ' + ')} (yemas tocándose)") for n in PINZAS]

# De qué poses sale el (mínimo, máximo) humano de cada actuador
POSE_MIN_MAX = {
    **{k: ("abierta", "puno") for k in (2, 3, 5, 6, 8, 9, 11, 12)},   # flexión de los 4 dedos
    1: ("abierta", "separados"), 4: ("abierta", "separados"), 10: ("abierta", "separados"),
    14: ("pulgar_plano", "pulgar_perp"),     # CMC_SPREAD  → t-abd
    13: ("pulgar_plano", "pulgar_cruz"),     # CMC_STRETCH → t-cmc
    15: ("abierta", "pulgar_flex"),          # THUMB_MCP   → t-mcp
    16: ("abierta", "pulgar_flex"),          # THUMB_IP    → t-ip
}
MIN_RECORRIDO_DEG = {"abd": 4.0, "flex": 15.0}   # por debajo: pose mal hecha → rango por defecto


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


def suma_fuentes(ang, k):
    return float(sum(ang[ERGO[f]] for f in FUENTES[k]))


def construir_mapeo(medidas):
    """medidas: {clave_pose: array(20) grados} → (mapeo, informe)."""
    mapeo, informe = {}, {}
    for k, fuentes in FUENTES.items():
        r0, r1 = RANGO_ROBOT[k]
        if not fuentes:
            mapeo[k] = ([], (0.0, 1.0), (r0, r1))
            continue
        p_min, p_max = POSE_MIN_MAX[k]
        tipo = "abd" if NOMBRES[k].endswith("abd") else "flex"
        if p_min in medidas and p_max in medidas:
            h0, h1 = suma_fuentes(medidas[p_min], k), suma_fuentes(medidas[p_max], k)
        else:
            h0, h1 = None, None
        if h0 is None or abs(h1 - h0) < MIN_RECORRIDO_DEG[tipo]:
            h0, h1 = _RANGO_HUMANO_DEFECTO[k]
            informe[k] = (f"⚠️  recorrido insuficiente entre '{p_min}' y '{p_max}' → rango "
                          f"humano por defecto [{h0:.0f}°, {h1:.0f}°]")
        else:
            informe[k] = (f"{' + '.join(fuentes)}: tú [{h0:6.1f}° → {h1:6.1f}°]  ⇒  robot "
                          f"[{r0:+.3f} → {r1:+.3f}] rad" + ("   (recta DECRECIENTE)" if h1 < h0 else ""))
        mapeo[k] = (list(fuentes), (float(h0), float(h1)), (r0, r1))
    return mapeo, informe


def main():
    guante = GuanteManus()
    if not guante.iniciar():
        return 1
    print("Esperando datos del guante...")
    t0 = time.perf_counter()
    while not guante.datos_frescos():
        if time.perf_counter() - t0 > 20:
            print("❌ No llegan datos del guante en 20 s (¿Dashboard abierto / dongle, guante encendido?).")
            guante.cerrar()
            return 1
        time.sleep(0.2)

    if "--ver" in sys.argv:
        print("Ángulos de tu mano en vivo, grados (Ctrl+C para salir)")
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

    if "--probar" in sys.argv:
        print("ctrl de la OrcaHand que saldría del guante (rad) y pinza detectada (Ctrl+C para salir)")
        try:
            while True:
                obj = guante.ctrl_objetivo()
                if obj is None:
                    print("\rsin datos", end="", flush=True)
                else:
                    txt = " ".join(f"{NOMBRES[k][:6]}={obj[k]:+.2f}" for k in range(1, 17))
                    pz = f"  PINZA {guante.pinza} {100 * guante.pinza_peso:3.0f}%" if guante.pinza else "  (sin pinza)"
                    print("\r" + txt + pz + "   ", end="", flush=True)
                time.sleep(0.1)
        except KeyboardInterrupt:
            print()
        guante.cerrar()
        return 0

    print(f"\n🧤 Calibración guante → OrcaHand: {len(POSES)} poses. En cada una: colócate, "
          f"pulsa ENTER y mantén la pose ~{ESPERA_S + MEDIR_S:.0f} s.\n")
    medidas = {}
    for i, (clave, texto) in enumerate(POSES, 1):
        r = input(f"[{i}/{len(POSES)}] {texto}  → ENTER (o 's' + ENTER para saltarla) ").strip().lower()
        if r == "s":
            print("   (saltada)")
            continue
        time.sleep(ESPERA_S)
        media, dispersion = medir(guante, MEDIR_S)
        if media is None:
            print("   ⚠️  sin datos, pose descartada")
            continue
        if dispersion.max() > 8.0:
            print(f"   ⚠️  te has movido bastante (hasta {dispersion.max():.0f}°): la uso igualmente")
        medidas[clave] = media
        print("   ✓ medida")
    guante.cerrar()
    if "abierta" not in medidas or "puno" not in medidas:
        print("❌ Faltan las poses básicas (abierta y puño): no se guarda nada.")
        return 1

    mapeo, informe = construir_mapeo(medidas)
    print("\nResultado (ctrl = r_min + fracción de TU recorrido · (r_max - r_min)):")
    for k in sorted(informe):
        print(f"  ctrl[{k:2d}] {NOMBRES[k]:12s} {informe[k]}")
    pinzas = {n: [float(v) for v in medidas[f"pinza_{n}"]] for n in PINZAS if f"pinza_{n}" in medidas}
    if pinzas:
        print(f"\nPinzas grabadas: {', '.join(pinzas)}")
        # Aviso si dos pinzas son casi iguales para el guante (se confundirían)
        for a in pinzas:
            for b in pinzas:
                if a < b:
                    d = distancia_pinza(pinzas[a], pinzas[b], a)
                    if d < 8.0:
                        print(f"  ⚠️  '{a}' y '{b}' se parecen mucho para el guante ({d:.1f}° RMS): "
                              f"podrían confundirse. Repite la calibración exagerando la diferencia.")
    with open(MANUS_CALIBRACION, "w", encoding="utf-8") as fh:
        json.dump({"version": 2, "fecha": time.strftime("%Y-%m-%d %H:%M"),
                   "mapeo": {str(k): {"fuentes": f, "humano": list(h), "robot": list(r)}
                             for k, (f, h, r) in mapeo.items()},
                   "pinzas": pinzas,
                   "poses": len(medidas)}, fh, indent=2, ensure_ascii=False)
    print(f"\n💾 Guardado en {MANUS_CALIBRACION}. Skill Shield lo carga al arrancar.")
    m2, _ = cargar_calibracion(verbose=False)
    print("Comprobación → ctrl[1..16] con tu mano ABIERTA:",
          np.round(angulos_a_ctrl(medidas["abierta"], m2)[1:], 2))
    print("Comprobación → ctrl[1..16] con tu PUÑO:      ",
          np.round(angulos_a_ctrl(medidas["puno"], m2)[1:], 2))
    print("Si algún dedo va al revés en la simulación, cambia SOLO su par (r_min, r_max) "
          "en config.MANUS_RANGO_ROBOT (no hace falta recalibrar).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
