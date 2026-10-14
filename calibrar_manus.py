#!/usr/bin/env python3
"""
Calibración guante MANUS → OrcaHand  (genera manus_calibracion.json, versión 3)
=================================================================================
    python calibrar_manus.py            # calibración guiada (~4 min, 16 poses)
    python calibrar_manus.py --ver      # solo ver en vivo los 20 ángulos de tu mano
    python calibrar_manus.py --probar   # ver en vivo el ctrl que saldría + la pinza detectada

QUÉ HACE (por RANGOS — no hay regresión por mínimos cuadrados):
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

NOVEDADES v3 (8-oct, 2ª ronda):
  · Dos poses nuevas para el CORAZÓN (antes estaba fijo): dedos inclinados hacia el
    pulgar y hacia el meñique.
  · Poses INTERMEDIAS: además de los extremos, el robot pasa exactamente por su pose en
    "abierta" (corazón recto), "pulgar_perp" (pulgar lo más lejos de la palma) y
    "pulgar_cruz" (yema del pulgar APOYADA en la palma). Ver ROBOT_INTERMEDIO en
    manus_guante.py.
  · t-abd del pulgar: se usa el canal del guante que más cambie entre "pulgar en el
    plano" y "pulgar perpendicular" (CMC_SPREAD o CMC_STRETCH). En tu calibración del
    8-oct CMC_SPREAD cambió < 4° y t-abd quedó sin calibrar (atascado entre −2° y +11°).
  · Se guardan tus ángulos crudos de todas las poses ("poses_crudas") para poder revisar
    la calibración sin repetirla.

CONSEJOS: mantén cada pose quieta ~3 s; en las poses de "extremo" fuerza de verdad el
extremo (puño apretado, dedos muy separados, pulgar bien cruzado). Las pinzas, con las
yemas tocándose como las harías para coger algo pequeño. En las tres del pulgar
(plano / perpendicular / cruzado) exagera la DIFERENCIA entre ellas.
"""
import json
import sys
import time

import numpy as np

from skill_shield.mano.manus_guante import (
    ERGO, FUENTES, NOMBRES, RANGO_ROBOT, ROBOT_INTERMEDIO, GuanteManus, MANUS_CALIBRACION,
    _RANGO_HUMANO_DEFECTO, angulos_a_ctrl, cargar_calibracion, distancia_pinza,
    mapeo_desde_json,
)

ESPERA_S, MEDIR_S = 2.0, 1.5

# (clave, texto que se muestra)
POSES = [
    ("abierta",    "mano ABIERTA y relajada, dedos estirados y JUNTOS (pegados entre sí), pulgar relajado"),
    ("puno",       "PUÑO cerrado y APRETADO (pulgar por fuera, como te salga)"),
    ("separados",  "dedos estirados y SEPARADOS al máximo (abanico)"),
    ("corazon_indice", "dedos estirados y JUNTOS, inclinados TODOS hacia el lado del PULGAR "
                       "(el CORAZÓN se inclina hacia el ÍNDICE)"),
    ("corazon_anular", "dedos estirados y JUNTOS, inclinados TODOS hacia el lado del MEÑIQUE "
                       "(el CORAZÓN se inclina hacia el ANULAR)"),
    ("pulgar_plano", "PULGAR tumbado en el PLANO de la palma y lo más SEPARADO del índice (una 'L' plana)"),
    ("pulgar_perp",  "PULGAR PERPENDICULAR a la palma (apuntando hacia delante de la palma), dedos estirados"),
    ("pulgar_cruz",  "PULGAR CRUZADO y APOYADO sobre la palma, con la yema en la base del MEÑIQUE, dedos estirados"),
    ("pulgar_flex",  "PULGAR DOBLADO al máximo (nudillo y punta), dedos estirados"),
]
PINZAS = ["indice", "corazon", "anular", "menique", "corazon_anular", "indice_corazon", "anular_menique"]
POSES += [(f"pinza_{n}", f"PINZA pulgar ↔ {n.replace('_', ' + ')} (yemas tocándose)") for n in PINZAS]

# De qué poses sale el (mínimo, máximo) humano de cada actuador
POSE_MIN_MAX = {
    **{k: ("abierta", "puno") for k in (2, 3, 5, 6, 8, 9, 11, 12)},   # flexión de los 4 dedos
    1: ("abierta", "separados"), 4: ("abierta", "separados"), 10: ("abierta", "separados"),
    7: ("corazon_anular", "corazon_indice"),  # MIDDLE_SPREAD → abducción del corazón
    14: ("pulgar_plano", "pulgar_perp"),      # CMC_SPREAD (o CMC_STRETCH, ver elegir_canal_t_abd)
    13: ("pulgar_plano", "pulgar_cruz"),      # CMC_STRETCH → t-cmc
    15: ("abierta", "pulgar_flex"),           # THUMB_MCP   → t-mcp
    16: ("abierta", "pulgar_flex"),           # THUMB_IP    → t-ip
}
# Poses INTERMEDIAS que se guardan para cada actuador, con la parte de tu recorrido (u, de
# 0 a 1) en la que tienen que caer para usarse (si no, la pose está mal hecha y se ignora).
# Lo que hace el ROBOT en ellas está en manus_guante.ROBOT_INTERMEDIO.
INTERMEDIAS = {
    7:  {"abierta": (0.15, 0.85)},
    13: {"pulgar_perp": (0.10, 0.90)},
    15: {"pulgar_cruz": (0.25, 0.90)},
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


def suma(ang, fuentes):
    return float(sum(ang[ERGO[f]] for f in fuentes))


def elegir_canal_t_abd(medidas):
    """Canal del guante para t-abd (14) → (fuentes, (pose_min, pose_max), intermedias, nota).
    El que más cambie entre 'pulgar_plano' y 'pulgar_perp':
      · CMC_SPREAD:  plano → perp (lo previsto: t-abd y t-cmc salen de canales distintos);
      · CMC_STRETCH: plano → cruz pasando por perp (t-abd baja de 'en el plano' a
        'perpendicular' en la primera parte del barrido del pulgar y se queda ahí al
        cruzarlo). Solo vale si 'perp' cae entre 'plano' y 'cruz'."""
    pl, pe, cr = (medidas.get(p) for p in ("pulgar_plano", "pulgar_perp", "pulgar_cruz"))
    spread = (["THUMB_CMC_SPREAD"], ("pulgar_plano", "pulgar_perp"), {}, "")
    if pl is None or pe is None:
        return spread
    i_sp, i_st = ERGO["THUMB_CMC_SPREAD"], ERGO["THUMB_CMC_STRETCH"]
    d_sp = abs(pe[i_sp] - pl[i_sp])
    d_st, u_perp = 0.0, None
    if cr is not None and abs(cr[i_st] - pl[i_st]) > 1e-6:
        u_perp = (pe[i_st] - pl[i_st]) / (cr[i_st] - pl[i_st])
        if 0.10 <= u_perp <= 0.90:
            d_st = abs(pe[i_st] - pl[i_st])
    nota = (f"CMC_SPREAD cambia {d_sp:.1f}° de 'plano' a 'perp'; CMC_STRETCH {abs(pe[i_st] - pl[i_st]):.1f}°"
            + (f" (perp en el {100 * u_perp:.0f} % del barrido plano → cruz)" if u_perp is not None else ""))
    if d_sp >= MIN_RECORRIDO_DEG["abd"] and d_sp >= d_st:
        return spread[0], spread[1], {}, nota + " → uso CMC_SPREAD"
    if d_st >= MIN_RECORRIDO_DEG["abd"]:
        return (["THUMB_CMC_STRETCH"], ("pulgar_plano", "pulgar_cruz"),
                {"pulgar_perp": (0.10, 0.90)}, nota + " → uso CMC_STRETCH")
    return spread[0], spread[1], {}, nota


def construir_mapeo(medidas):
    """medidas: {clave_pose: array(20) grados} → (mapeo para el JSON, informe)."""
    mapeo, informe = {}, {}
    for k, fuentes in FUENTES.items():
        r0, r1 = RANGO_ROBOT[k]
        if not fuentes:
            mapeo[k] = {"fuentes": [], "humano": [0.0, 1.0], "robot": [r0, r1]}
            continue
        p_min, p_max = POSE_MIN_MAX[k]
        intermedias = dict(INTERMEDIAS.get(k, {}))
        nota = ""
        if k == 14:
            fuentes, (p_min, p_max), intermedias, nota = elegir_canal_t_abd(medidas)
        fuentes = list(fuentes)
        tipo = "abd" if NOMBRES[k].endswith("abd") else "flex"
        h0 = h1 = None
        if p_min in medidas and p_max in medidas:
            h0, h1 = suma(medidas[p_min], fuentes), suma(medidas[p_max], fuentes)
        inter = {}
        if h0 is None or abs(h1 - h0) < MIN_RECORRIDO_DEG[tipo]:
            h0, h1 = _RANGO_HUMANO_DEFECTO[k]
            if k == 7:       # corazón por defecto: ±20° alrededor de tu mano abierta = recto
                c = suma(medidas["abierta"], fuentes) if "abierta" in medidas else 0.0
                h0, h1 = c - 20.0, c + 20.0
                inter["abierta"] = c
            informe[k] = (f"⚠️  recorrido insuficiente entre '{p_min}' y '{p_max}' → rango "
                          f"humano por defecto [{h0:.0f}°, {h1:.0f}°]")
            if k == 14:
                informe[k] += ("\n{:20s}· en teleoperación seguirá al barrido del pulgar (t-cmc): "
                               "plano → perpendicular → cruzado. Repite las 3 poses del pulgar "
                               "exagerando la diferencia si quieres moverlo por separado.".format(""))
        else:
            informe[k] = (f"{' + '.join(fuentes)}: tú [{h0:6.1f}° → {h1:6.1f}°]  ⇒  robot "
                          f"[{r0:+.3f} → {r1:+.3f}] rad" + ("   (recta DECRECIENTE)" if h1 < h0 else ""))
            for pose, (u_min, u_max) in intermedias.items():
                r = ROBOT_INTERMEDIO.get(k, {}).get(pose)
                if r is None or pose not in medidas:
                    continue
                h = suma(medidas[pose], fuentes)
                u = (h - h0) / (h1 - h0)
                if u_min <= u <= u_max:
                    inter[pose] = h
                    informe[k] += f"\n{'':20s}· '{pose}' en el {100 * u:3.0f} % de tu recorrido → robot {r:+.2f} rad"
                else:
                    informe[k] += (f"\n{'':20s}· '{pose}' cae en el {100 * u:3.0f} % de tu recorrido "
                                   f"(fuera de {100 * u_min:.0f}-{100 * u_max:.0f} %): no se usa")
        if nota:
            informe[k] += f"\n{'':20s}· {nota}"
        mapeo[k] = {"fuentes": fuentes, "humano": [float(h0), float(h1)], "robot": [r0, r1],
                    "intermedios": {p: float(h) for p, h in inter.items()}}
    return mapeo, informe


def comprobar(medidas, mapeo_json):
    """Lo que hará el robot en tus poses de calibración (rad), con el mapeo nuevo."""
    m = mapeo_desde_json({"version": 3, "mapeo": {str(k): v for k, v in mapeo_json.items()}})
    print("\nComprobación con el mapeo nuevo (rad):")
    def fila(pose, ks):
        if pose in medidas:
            c = angulos_a_ctrl(medidas[pose], m)
            print(f"  {pose:15s} " + "  ".join(f"{NOMBRES[k]}={c[k]:+.2f}" for k in ks))
    for pose in ("abierta", "puno"):
        fila(pose, (2, 3, 5, 6, 8, 9, 11, 12))
    for pose in ("abierta", "separados"):
        fila(pose, (1, 4, 7, 10))
    for pose in ("corazon_indice", "abierta", "corazon_anular"):
        fila(pose, (7,))
    for pose in ("pulgar_plano", "pulgar_perp", "pulgar_cruz", "pulgar_flex"):
        fila(pose, (13, 14, 15, 16))
    print("  (pulgar: plano ≈ cmc −0.79 abd +0.96 · perp ≈ cmc −0.16 abd −0.31 · "
          "cruz ≈ cmc +0.58 abd −0.31 mcp +1.40 = yema apoyada en la palma)")


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
    print("\nResultado (tu recorrido → recorrido del robot; los extremos ya tienen márgenes, "
          "ver MANUS_MARGEN):")
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
    comprobar(medidas, mapeo)
    with open(MANUS_CALIBRACION, "w", encoding="utf-8") as fh:
        json.dump({"version": 3, "fecha": time.strftime("%Y-%m-%d %H:%M"),
                   "mapeo": {str(k): v for k, v in mapeo.items()},
                   "pinzas": pinzas,
                   "poses": len(medidas),
                   "poses_crudas": {p: [float(x) for x in a] for p, a in medidas.items()}},
                  fh, indent=2, ensure_ascii=False)
    print(f"\n💾 Guardado en {MANUS_CALIBRACION}. Skill Shield lo carga al arrancar.")
    cargar_calibracion(verbose=True)
    print("Si algún dedo va al revés en la simulación, cambia SOLO su par (r_min, r_max) "
          "en config.MANUS_RANGO_ROBOT (no hace falta recalibrar).")
    return 0


if __name__ == "__main__":
    sys.exit(main())