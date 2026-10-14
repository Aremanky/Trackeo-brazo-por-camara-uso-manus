"""
Guantes MANUS → dedos de la OrcaHand (y vibración de vuelta al guante).

Sustituye a MediaPipe Hands SOLO para los 16 actuadores de los dedos (ctrl[1..16] de
la mano). La flexión de muñeca (ctrl[0]), el giro del antebrazo y el brazo siguen
saliendo de las cámaras: los ángulos "ergonomics" de MANUS no incluyen la muñeca.

Uso desde Skill_Shield_Nivel_6.py (FUENTE_DEDOS = "manus" en config.py):

    guante = GuanteManus()          # una sola vez al arrancar el programa
    guante.iniciar()                # no bloquea: conecta en un hilo propio
    ...
    guante.aplicar = True/False     # ¿manda el guante sobre los dedos? (cámara activa)
    guante.escribir_ctrl(datos, dt) # en el hilo de física, ANTES de cada mj_step
    guante.haptica(modelo, datos)   # en el bucle principal: contactos → vibración
    ...
    guante.cerrar()

Datos del SDK (MANUS Core 3.2.1, Python):
  · callback de ergonomics: por guante, 40 ángulos en GRADOS (0-19 mano izquierda,
    20-39 derecha) en el orden de ErgonomicsDataType:
        pulgar CMCSpread, CMCStretch, MCPStretch, IPStretch,
        índice/corazón/anular/meñique: MCPSpread, MCPStretch, PIPStretch, DIPStretch
  · callback de landscape: qué guante es cada mano (side) y si tiene háptica.
  · lib.CoreSdk_VibrateFingersForGlove(glove_id, float[5])  (pulgar → meñique, 0..1)

═══════════════════════════════════════════════════════════════════════════════
CORRESPONDENCIA GUANTE → ORCAHAND (v2, 8-oct): POR RANGOS, NO POR REGRESIÓN
═══════════════════════════════════════════════════════════════════════════════
Cada actuador k de la mano se calcula así:

    ang  = Σ ángulos de MANUS de sus "fuentes" (grados; p. ej. PIP + DIP)
    u    = (ang - h_min) / (h_max - h_min) · ganancia   ← 0 en TU mínimo, 1 en TU máximo
    ctrl = línea por tramos por los nudos            (rad, recortado a LIMITES_CTRL)
             (m_ini, r_min) · [poses intermedias (u_i, r_i)] · (1 - m_fin, r_max)
           y fuera de ellos, el extremo (v3: márgenes MANUS_MARGEN + ROBOT_INTERMEDIO;
           sin intermedios y sin márgenes es la recta r_min + u · (r_max - r_min) de la v2)

  · h_min / h_max son TUS ángulos medidos en calibrar_manus.py (mano abierta, puño,
    dedos separados, pulgar en sus extremos).
  · r_min / r_max son los ctrl del ROBOT en esas mismas poses (config.MANUS_RANGO_ROBOT).
  · El SIGNO sale solo: si tu ángulo baja cuando el robot debe subir, h_max < h_min y la
    recta ya es decreciente. Ya no hay ganancias ±1 "a ojo" ni mínimos cuadrados.
  · Esto garantiza que tu puño = puño completo del robot y tu abanico = abanico
    completo del robot (problema "no llega al límite"), y arregla los signos de las
    abducciones (problema "anular/pulgar al revés").

PINZAS: los ángulos articulares de una mano humana copiados a la OrcaHand NO juntan las
yemas (proporciones distintas). Igual que hace retargeting.py con la cámara, cuando tu
mano está en una de las pinzas calibradas se mezcla el comando con la pose de contacto
del robot (PINZA_CTRL_CONTACTO, retargeting.py). La pinza se detecta por CERCANÍA en
el espacio de ángulos del guante a las poses de pinza que grabaste al calibrar
(RMS en grados sobre las articulaciones de ese dedo y del pulgar), con histéresis
(MANUS_PINZA_ON_DEG / MANUS_PINZA_OFF_DEG) y mezcla continua: nada de saltos.

Sin manus_calibracion.json (o con uno antiguo, sin "version": 2) se usa un mapeo por
defecto con rangos humanos típicos: funciona, pero calibra en cuanto puedas.

v3 (8-oct, tras probar la mano): RECORRIDO COMPLETO
  · Márgenes (MANUS_MARGEN): antes el robot solo llegaba a su tope si repetías EXACTAMENTE
    la pose extrema de la calibración (puño APRETADO, mano estirada a tope). En uso normal
    el puño se quedaba a 1-2 cm de la palma y la mano abierta, algo doblada. Ahora el
    último 20 % de tu cierre y el primer 10 % de tu apertura ya dan el extremo del robot.
  · Rangos del robot al completo del modelo (_RANGO_ROBOT_DEFECTO): dedo recto de verdad
    (en el MJCF, a 0° los dedos quedan 3-8° doblados), abanico completo, pulgar completo.
  · Abducción del CORAZÓN (ctrl 7): antes fija a 0; ahora sale de MIDDLE_SPREAD.
  · Poses INTERMEDIAS (ROBOT_INTERMEDIO): la recta pasa a ser una línea por tramos que
    además pasa exactamente por la pose del robot en algunas poses de la calibración:
    corazón recto con tu mano abierta, pulgar PERPENDICULAR (lo más lejos de la palma) y
    pulgar CRUZADO con la yema APOYADA en la palma (pide al MCP del robot doblarse 80°:
    el guante apenas mide el MCP del pulgar al cruzarlo y, sin eso, la yema se quedaba
    a 9 cm de la palma).
  · Abducción del pulgar (t-abd) sin calibrar: tu calibración del 8-oct no la pudo medir
    (CMC_SPREAD casi no cambia entre "pulgar en el plano" y "perpendicular") y t-abd se
    quedaba entre −2° y +11°. Ahora, mientras no se calibre, sigue al barrido del pulgar
    (CMC_STRETCH): plano → perpendicular → cruzado. calibrar_manus.py elige el canal.
"""
import json
import math
import os
import sys
import threading
import time

import numpy as np

import config as _cfg
from config import LIMITES_CTRL, N_ACT, OFFSET_MANO


def _p(nombre, defecto):
    return getattr(_cfg, nombre, defecto)


# ── Parámetros (config.py, bloque MANUS; si faltan, estos valores) ────────────
MANUS_MODO        = _p("MANUS_MODO", "local")          # "integrado" | "local" | "remoto"
MANUS_LADO        = _p("MANUS_LADO", "derecho")        # mano que se teleopera
MANUS_SDK_RUTA    = _p("MANUS_SDK_RUTA", os.path.join(
    os.path.dirname(os.path.abspath(_cfg.__file__)), "MANUS_Core_3.2.1_SDK_Linux", "Python"))
MANUS_CALIBRACION = _p("MANUS_CALIBRACION", os.path.join(
    os.path.dirname(os.path.abspath(_cfg.__file__)), "manus_calibracion.json"))
MANUS_TIMEOUT_S   = float(_p("MANUS_TIMEOUT_S", 0.3))  # sin datos más tiempo → dedos quietos
MANUS_TAU_S       = float(_p("MANUS_TAU_S", 0.025))    # suavizado (constante de tiempo)
MANUS_HAPTICA     = bool(_p("MANUS_HAPTICA", True))
MANUS_HAPTICA_HZ  = float(_p("MANUS_HAPTICA_HZ", 30.0))
MANUS_FUERZA_MIN  = float(_p("MANUS_FUERZA_MIN", 0.05))  # N: por debajo no vibra
MANUS_FUERZA_MAX  = float(_p("MANUS_FUERZA_MAX", 3.0))   # N: a partir de aquí vibra al 100 %
MANUS_VIBRACION_MAX = float(_p("MANUS_VIBRACION_MAX", 1.0))

# Ganancia extra por actuador sobre la fracción de recorrido (1.0 = tu máximo = máximo del
# robot; 1.15 = llegas al máximo del robot con el 87 % de tu recorrido, útil si no cierras
# el puño del todo con el guante puesto). Claves: nombres de ACTUADORES (ver NOMBRES).
MANUS_GANANCIA    = dict(_p("MANUS_GANANCIA", {}))

# Pinzas (ver cabecera). Grados RMS sobre las articulaciones del dedo + pulgar.
MANUS_PINZA_ACTIVA  = bool(_p("MANUS_PINZA_ACTIVA", True))
MANUS_PINZA_ON_DEG  = float(_p("MANUS_PINZA_ON_DEG", 7.0))   # por debajo: pinza al 100 %
MANUS_PINZA_OFF_DEG = float(_p("MANUS_PINZA_OFF_DEG", 14.0))  # por encima: pinza al 0 %

# Márgenes en los extremos de TU recorrido (v3): (m_ini, m_fin) = fracción de lo medido al
# calibrar que ya cuenta como extremo, en el lado de la pose "mínima" y de la "máxima"
# (flexión: abierta → puño; abducción: juntos → separados; pulgar: según su pose).
# Claves: "flex", "abd", "pulgar" o el nombre de un actuador (p. ej. "indice_pip").
_MARGEN_DEFECTO = {"flex": (0.10, 0.20), "abd": (0.10, 0.15), "pulgar": (0.10, 0.15)}
MANUS_MARGEN = {**_MARGEN_DEFECTO, **dict(_p("MANUS_MARGEN", {}))}

# ── Índices dentro de UNA mano (0..19), orden de ErgonomicsDataType ──────────
ERGO = {
    "THUMB_CMC_SPREAD": 0, "THUMB_CMC_STRETCH": 1, "THUMB_MCP": 2, "THUMB_IP": 3,
    "INDEX_SPREAD": 4,  "INDEX_MCP": 5,  "INDEX_PIP": 6,  "INDEX_DIP": 7,
    "MIDDLE_SPREAD": 8, "MIDDLE_MCP": 9, "MIDDLE_PIP": 10, "MIDDLE_DIP": 11,
    "RING_SPREAD": 12,  "RING_MCP": 13,  "RING_PIP": 14,  "RING_DIP": 15,
    "PINKY_SPREAD": 16, "PINKY_MCP": 17, "PINKY_PIP": 18, "PINKY_DIP": 19,
}

# ctrl de la mano → nombre legible (los mismos que GANANCIA_DEDOS / orca_hardware)
NOMBRES = {1: "menique_abd", 2: "menique_mcp", 3: "menique_pip",
           4: "anular_abd",  5: "anular_mcp",  6: "anular_pip",
           7: "corazon_abd", 8: "corazon_mcp", 9: "corazon_pip",
           10: "indice_abd", 11: "indice_mcp", 12: "indice_pip",
           13: "pulgar_cmc", 14: "pulgar_abd", 15: "pulgar_mcp", 16: "pulgar_ip"}

# Fuentes de MANUS de cada actuador. El "pip" de la OrcaHand mueve la falange media Y la
# distal de una pieza (FingerTipAssembly): se alimenta con PIP + DIP del guante.
FUENTES = {
    1:  ["PINKY_SPREAD"],  2: ["PINKY_MCP"],  3: ["PINKY_PIP", "PINKY_DIP"],
    4:  ["RING_SPREAD"],   5: ["RING_MCP"],   6: ["RING_PIP", "RING_DIP"],
    7:  ["MIDDLE_SPREAD"], 8: ["MIDDLE_MCP"], 9: ["MIDDLE_PIP", "MIDDLE_DIP"],
    10: ["INDEX_SPREAD"], 11: ["INDEX_MCP"], 12: ["INDEX_PIP", "INDEX_DIP"],
    13: ["THUMB_CMC_STRETCH"],   # oposición (barrido del pulgar hacia el meñique)
    14: ["THUMB_CMC_SPREAD"],    # abducción palmar (pulgar fuera del plano de la palma)
    15: ["THUMB_MCP"],
    16: ["THUMB_IP"],
}

# ── Rangos del ROBOT (rad) en las poses de calibración ───────────────────────
# (r_min, r_max) de cada actuador: lo que debe hacer la OrcaHand cuando TÚ estás en el
# mínimo / máximo de esa articulación. Se puede sobrescribir en config.MANUS_RANGO_ROBOT.
# Sentidos de la OrcaHand (comprobados con la cinemática del MJCF orcahand_right_body.xml):
#   · abd de los 4 dedos: + = la yema se desplaza HACIA EL PULGAR (radial). Índice + = se
#     abre; anular/meñique + = se cierran hacia el corazón.
#   · t-abd: + = el pulgar se tumba en el plano de la palma (extensión radial);
#            − = el pulgar sale perpendicular a la palma (abducción palmar).
#   · t-cmc: + = el pulgar barre hacia la base del meñique (oposición); − = hacia fuera.
_RANGO_ROBOT_DEFECTO = {
    # flexión: dedo RECTO → puño con la YEMA TOCANDO LA PALMA. Medido con la cinemática y
    # las mallas del MJCF: con mcp/pip a 0 los dedos quedan 3-8° doblados (rectos con mcp
    # −4°/−3°/−3°/−8°), y con mcp 1.70 + pip 1.80 la yema ya toca la palma (0,1-0,3 mm).
    2: (-0.14, 1.70), 3: (0.0, 1.80),      # meñique mcp, pip
    5: (-0.05, 1.70), 6: (0.0, 1.80),      # anular
    8: (-0.05, 1.70), 9: (0.0, 1.80),      # corazón
    11: (-0.07, 1.70), 12: (0.0, 1.80),    # índice
    # abducción: dedos JUNTOS → SEPARADOS (los "juntos" son la convergencia de retargeting.py)
    10: (-0.27, 0.52),     # índice: pegado al corazón → abierto del todo (máx. del modelo 0.524)
    4:  (0.225, -0.45),    # anular: pegado al corazón → abierto (mín. del modelo −0.471)
    1:  (0.42, -0.50),     # meñique: pegado al anular → abierto (mín. del modelo −0.524)
    7:  (-0.40, 0.40),     # corazón: inclinado hacia el anular → hacia el índice (±0.471)
    # pulgar: rango completo del modelo
    14: (0.96, -0.31),     # CMC_SPREAD: pulgar en el plano de la palma → perpendicular a ella
    13: (-0.785, 0.576),   # CMC_STRETCH: pulgar extendido hacia fuera → cruzado hacia el meñique
    15: (0.0, 1.745),      # MCP: recto → flexionado del todo
    16: (0.0, 1.867),      # IP: recto → flexionado del todo
}
RANGO_ROBOT = {int(k): (float(v[0]), float(v[1]))
               for k, v in {**_RANGO_ROBOT_DEFECTO, **dict(_p("MANUS_RANGO_ROBOT", {}))}.items()}

# Rangos HUMANOS típicos (grados) por si no hay calibración. Orientativos: calibra.
_RANGO_HUMANO_DEFECTO = {
    2: (0.0, 90.0), 3: (0.0, 120.0), 5: (0.0, 90.0), 6: (0.0, 120.0),
    8: (0.0, 90.0), 9: (0.0, 120.0), 11: (0.0, 90.0), 12: (0.0, 120.0),
    10: (-5.0, 20.0), 4: (0.0, -15.0), 1: (-5.0, -25.0), 7: (-20.0, 20.0),
    14: (5.0, 50.0), 13: (0.0, 55.0), 15: (0.0, 55.0), 16: (0.0, 75.0),
}

# Poses INTERMEDIAS (v3): además de en los dos extremos, el actuador pasa EXACTAMENTE por
# este valor del robot (rad) cuando repites esa pose de la calibración (calibrar_manus.py
# guarda tu ángulo en ella). Sobrescribible: config.MANUS_ROBOT_INTERMEDIO = {k: {pose: rad}}.
# Valores medidos con la cinemática y las mallas del MJCF:
#   ·  7 corazón: "abierta" → 0 (recto: ni hacia el índice ni hacia el anular).
#   · 13 t-cmc:   "pulgar_perp" → −0.16 (−9°): con t-abd −18° es lo MÁS LEJOS de la palma
#                 que llega la yema del pulgar (112 mm por delante de la palma).
#   · 14 t-abd:   "pulgar_perp" → −0.31 (perpendicular; solo cuando t-abd sale de
#                 CMC_STRETCH, plano → cruzado: entonces "perp" queda en medio).
#   · 15 t-mcp:   "pulgar_cruz" → 1.40 (80°): con t-cmc +33° y t-abd −18…−6° la YEMA queda
#                 APOYADA en la palma, a la altura del anular. Con el MCP recto se queda a
#                 ~9 cm de ella.
_ROBOT_INTERMEDIO_DEFECTO = {
    7:  {"abierta": 0.0},
    13: {"pulgar_perp": -0.16},
    14: {"pulgar_perp": -0.31},
    15: {"pulgar_cruz": 1.40},
}
ROBOT_INTERMEDIO = {int(k): {str(p): float(r) for p, r in dict(v).items()}
                    for k, v in {**_ROBOT_INTERMEDIO_DEFECTO,
                                 **dict(_p("MANUS_ROBOT_INTERMEDIO", {}))}.items()}
# Sin calibración: tu ángulo (grados) en esas poses (solo el corazón: recto = 0°)
_INTERMEDIO_HUMANO_DEFECTO = {7: {"abierta": 0.0}}

# Qué articulaciones del guante definen cada pinza (índices ERGO): pulgar + dedo(s).
_ERGO_DEDO = {"indice": (4, 5, 6, 7), "corazon": (8, 9, 10, 11),
              "anular": (12, 13, 14, 15), "menique": (16, 17, 18, 19)}
_ERGO_PULGAR = (0, 1, 2, 3)
PINZA_ERGO = {
    "indice":         _ERGO_PULGAR + _ERGO_DEDO["indice"],
    "corazon":        _ERGO_PULGAR + _ERGO_DEDO["corazon"],
    "anular":         _ERGO_PULGAR + _ERGO_DEDO["anular"],
    "menique":        _ERGO_PULGAR + _ERGO_DEDO["menique"],
    "corazon_anular": _ERGO_PULGAR + _ERGO_DEDO["corazon"] + _ERGO_DEDO["anular"],
    "indice_corazon": _ERGO_PULGAR + _ERGO_DEDO["indice"] + _ERGO_DEDO["corazon"],
    "anular_menique": _ERGO_PULGAR + _ERGO_DEDO["anular"] + _ERGO_DEDO["menique"],
}
# Peso de cada canal en la distancia (los spreads son ruidosos y pesan menos)
_PESO_ERGO = np.array([0.7, 1.0, 1.0, 1.0] + [0.5, 1.0, 1.0, 0.7] * 4)


def _margen(k):
    """(m_ini, m_fin) del actuador k: por nombre, si no por tipo (flex / abd / pulgar)."""
    nombre = NOMBRES.get(k, "")
    tipo = "pulgar" if k >= 13 else ("abd" if nombre.endswith("abd") else "flex")
    m = MANUS_MARGEN.get(nombre, MANUS_MARGEN.get(tipo, (0.0, 0.0)))
    return min(max(float(m[0]), 0.0), 0.45), min(max(float(m[1]), 0.0), 0.45)


_CURVAS = {}     # caché de nudos por actuador (se llama cientos de veces por segundo)


def _nudos(k, r0, r1, intermedios=()):
    """Curva del actuador k como nudos ((u, ctrl), ...), con u = fracción de TU recorrido
    (0 = tu mínimo, 1 = tu máximo): los extremos (u = m_ini → r_min, u = 1 − m_fin → r_max)
    se meten hacia dentro con los márgenes, y en medio van las poses intermedias."""
    clave = (k, r0, r1, intermedios)
    c = _CURVAS.get(clave)
    if c is None:
        m0, m1 = _margen(k)
        medio = []
        for u, r in sorted((float(u), float(r)) for u, r in intermedios):
            if 0.02 < u < 0.98 and (not medio or u - medio[-1][0] > 0.01):
                medio.append((u, r))
        if medio:        # el margen nunca se come una pose intermedia
            m0 = min(m0, 0.5 * medio[0][0])
            m1 = min(m1, 0.5 * (1.0 - medio[-1][0]))
        c = ((m0, float(r0)),) + tuple(medio) + ((1.0 - m1, float(r1)),)
        _CURVAS[clave] = c
    return c


def _evaluar(u, nudos):
    """Lineal por tramos por los nudos; fuera de ellos, el valor del extremo (satura)."""
    if u <= nudos[0][0]:
        return nudos[0][1]
    for i in range(1, len(nudos)):
        ub, rb = nudos[i]
        if u <= ub:
            ua, ra = nudos[i - 1]
            return ra + (u - ua) * (rb - ra) / (ub - ua)
    return nudos[-1][1]

# Yemas de la OrcaHand (mismos bodies que retargeting.py), en el orden del SDK:
# pulgar, índice, corazón, anular, meñique
_BODIES_YEMA = ("right_T-DP_b7429e50", "right_I-FingerTipAssembly_ec49c16c",
                "right_M-FingerTipAssembly_34afb748", "right_M-FingerTipAssembly_424a8e75",
                "right_P-FingerTipAssembly_cd219176")


def _importar_sdk():
    """manus_sdk instalado con pip o, si no, desde la carpeta del SDK (MANUS_SDK_RUTA)."""
    try:
        import manus_sdk  # noqa: F401
    except ImportError:
        if MANUS_SDK_RUTA and os.path.isdir(MANUS_SDK_RUTA) and MANUS_SDK_RUTA not in sys.path:
            sys.path.insert(0, MANUS_SDK_RUTA)
    from manus_sdk import lib, ffi, ManusSDK
    from manus_sdk.generated._enums import SDKReturnCode, AxisView, AxisPolarity, Side
    return lib, ffi, ManusSDK, SDKReturnCode, AxisView, AxisPolarity, Side


def _poses_pinza_robot():
    """PINZA_CTRL_CONTACTO de retargeting.py (poses de contacto medidas en el visor)."""
    try:
        from skill_shield.mano.retargeting import PINZA_CTRL_CONTACTO
        return {n: {int(k): float(v) for k, v in d.items()} for n, d in PINZA_CTRL_CONTACTO.items()}
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# MAPEO
# ══════════════════════════════════════════════════════════════════════════════
def _resolver_intermedios(k, por_pose, h0, h1):
    """{pose: tu ángulo (grados)} → ((u, ctrl del robot), ...) de las poses intermedias
    que el robot conoce (ROBOT_INTERMEDIO). u = fracción de tu recorrido h0 → h1."""
    if abs(h1 - h0) < 1e-6:
        return ()
    out = []
    for pose, h in dict(por_pose or {}).items():
        r = ROBOT_INTERMEDIO.get(k, {}).get(pose)
        if r is not None:
            out.append(((float(h) - h0) / (h1 - h0), float(r)))
    return tuple(sorted(out))


def mapeo_por_defecto():
    """{ctrl: (fuentes, (h_min, h_max) grados, (r_min, r_max) rad, intermedios)} sin
    calibrar. intermedios = ((u, ctrl), ...) (ver ROBOT_INTERMEDIO)."""
    out = {}
    for k in FUENTES:
        h0, h1 = _RANGO_HUMANO_DEFECTO[k]
        out[k] = (list(FUENTES[k]), (h0, h1), RANGO_ROBOT[k],
                  _resolver_intermedios(k, _INTERMEDIO_HUMANO_DEFECTO.get(k), h0, h1))
    return out


def _sin_calibrar(entrada, k):
    """¿Esta entrada del mapeo es la de por defecto (la calibración no pudo medirla)?"""
    h0, h1 = entrada[1]
    d0, d1 = _RANGO_HUMANO_DEFECTO[k]
    return list(entrada[0]) == list(FUENTES[k]) and abs(h0 - d0) < 1e-6 and abs(h1 - d1) < 1e-6


def _t_abd_por_barrido(mapeo, d=None):
    """t-abd (14) sin calibrar pero con el barrido del pulgar (13, CMC_STRETCH) calibrado:
    t-abd sigue a ese barrido — plano (tumbado en la palma) → perpendicular a mitad de
    camino (o donde midió la calibración tu pose "perpendicular") → perpendicular también
    al cruzarlo hacia el meñique (así es como apoya el pulgar en la palma). Es lo que pasa
    con la calibración del 8-oct: CMC_SPREAD no cambió > 4° entre "plano" y
    "perpendicular" y t-abd se quedaba atascado entre −2° y +11°."""
    e13 = mapeo.get(13)
    if e13 is None or list(e13[0]) != ["THUMB_CMC_STRETCH"] or _sin_calibrar(e13, 13):
        return False
    h0, h1 = e13[1]
    u_perp = 0.5
    v13 = (d or {}).get("mapeo", {}).get("13", {})
    h_perp = dict(v13.get("intermedios") or {}).get("pulgar_perp")
    if h_perp is not None and abs(h1 - h0) > 1e-6 and 0.1 < (h_perp - h0) / (h1 - h0) < 0.9:
        u_perp = (h_perp - h0) / (h1 - h0)
    r_perp = ROBOT_INTERMEDIO.get(14, {}).get("pulgar_perp", RANGO_ROBOT[14][1])
    mapeo[14] = (["THUMB_CMC_STRETCH"], (h0, h1), RANGO_ROBOT[14], ((float(u_perp), r_perp),))
    return True


def mapeo_desde_json(d):
    """Contenido de manus_calibracion.json (versión ≥ 2) → mapeo. Lo del ROBOT (extremos y
    poses intermedias) sale SIEMPRE de config (RANGO_ROBOT / ROBOT_INTERMEDIO), así que se
    puede cambiar sin recalibrar; del JSON solo se usan TUS ángulos."""
    mapeo = mapeo_por_defecto()
    for k, v in d.get("mapeo", {}).items():
        k = int(k)
        if k not in FUENTES:
            continue
        if not v.get("fuentes") and FUENTES.get(k):
            continue            # calibración anterior a esa fuente (corazón, v2): por defecto
        h0, h1 = float(v["humano"][0]), float(v["humano"][1])
        robot = RANGO_ROBOT.get(k, (float(v["robot"][0]), float(v["robot"][1])))
        mapeo[k] = (list(v["fuentes"]), (h0, h1), robot,
                    _resolver_intermedios(k, v.get("intermedios"), h0, h1))
    if _sin_calibrar(mapeo[14], 14):
        _t_abd_por_barrido(mapeo, d)
    return mapeo


def cargar_calibracion(ruta=MANUS_CALIBRACION, verbose=True):
    """Devuelve (mapeo, pinzas). pinzas = {nombre: array(20) grados} grabadas al calibrar."""
    mapeo, pinzas = mapeo_por_defecto(), {}
    if ruta and os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as fh:
                d = json.load(fh)
            if int(d.get("version", 1)) < 2:
                print(f"⚠️  [MANUS] {os.path.basename(ruta)} es de la calibración ANTIGUA "
                      f"(regresión): se ignora. Ejecuta  python calibrar_manus.py")
            else:
                mapeo = mapeo_desde_json(d)
                for n, ang in d.get("pinzas", {}).items():
                    pinzas[n] = np.asarray(ang, dtype=float)
                if verbose:
                    print(f"🧤 [MANUS] Calibración cargada: {os.path.basename(ruta)} "
                          f"({d.get('fecha', '?')}, {len(pinzas)} pinzas)")
                    viejas = [NOMBRES[int(k)] for k, v in d.get("mapeo", {}).items()
                              if int(k) in FUENTES and FUENTES[int(k)] and not v.get("fuentes")]
                    if viejas or int(d.get("version", 2)) < 3:
                        print("   ℹ️  Calibración anterior a la v3 (corazón fijo, pulgar sin "
                              "poses intermedias): repite  python calibrar_manus.py  para "
                              "aprovechar el recorrido completo.")
                    if list(mapeo[14][0]) == ["THUMB_CMC_STRETCH"] and \
                            not any(list(v.get("fuentes", [])) == ["THUMB_CMC_STRETCH"]
                                    for k, v in d.get("mapeo", {}).items() if int(k) == 14):
                        print("   ℹ️  t-abd (pulgar) no estaba calibrado: sigue al barrido del "
                              "pulgar (plano → perpendicular → cruzado).")
        except Exception as e:
            print(f"⚠️  [MANUS] No se pudo leer {ruta} ({e}): uso la correspondencia por defecto.")
    elif verbose:
        print("⚠️  [MANUS] Sin calibración (manus_calibracion.json): rangos humanos típicos. "
              "Ejecuta  python calibrar_manus.py  para que tu puño/abanico/pulgar lleguen al límite.")
    return mapeo, pinzas


def angulos_a_ctrl(ang_deg, mapeo):
    """20 ángulos de UNA mano (GRADOS) → array N_ACT de ctrl (rad; ctrl[0] = NaN: la muñeca
    no la da el guante). Recortado a LIMITES_CTRL."""
    ang_deg = np.asarray(ang_deg, dtype=float)
    out = np.full(N_ACT, np.nan)
    for k, v in mapeo.items():
        fuentes, (h0, h1), (r0, r1) = v[0], v[1], v[2]
        lo, hi = LIMITES_CTRL[k]
        if not fuentes or abs(h1 - h0) < 1e-6:
            out[k] = min(max(r0, lo), hi)
            continue
        a = float(sum(ang_deg[ERGO[f]] for f in fuentes))
        u = (a - h0) / (h1 - h0)                       # 0 = tu mínimo, 1 = tu máximo
        u *= MANUS_GANANCIA.get(NOMBRES.get(k, ""), 1.0)
        r = _evaluar(u, _nudos(k, r0, r1, tuple(v[3]) if len(v) > 3 else ()))
        out[k] = min(max(r, lo), hi)
    return out


def distancia_pinza(ang_deg, pose_deg, nombre):
    """RMS ponderado (grados) entre tu mano y una pose de pinza grabada, solo sobre las
    articulaciones del pulgar y del dedo (o dedos) de esa pinza."""
    idx = list(PINZA_ERGO[nombre])
    d = (np.asarray(ang_deg, dtype=float)[idx] - np.asarray(pose_deg, dtype=float)[idx]) * _PESO_ERGO[idx]
    return float(np.sqrt(np.mean(d * d)))


class GuanteManus:
    """Conexión con MANUS (hilo propio), últimos ángulos de la mano y vibración."""

    def __init__(self, modo=MANUS_MODO, lado=MANUS_LADO):
        self.modo = modo
        self.lado = lado
        self.aplicar = False             # el bucle principal decide si el guante manda
        self.conectado = False
        self.mapeo, self.pinzas = cargar_calibracion()
        if tuple(LIMITES_CTRL[7]) == (0.0, 0.0) or tuple(RANGO_ROBOT[7]) == (0.0, 0.0) or \
                tuple(LIMITES_CTRL[11])[0] >= 0.0:
            print("⚠️  [MANUS] config.py aún tiene los límites antiguos (corazón fijo, dedos sin "
                  "estirar del todo): pega el bloque de config_rango_completo.py al FINAL de config.py.")
        self.pinzas_robot = _poses_pinza_robot()
        # solo las pinzas que tienen pose del guante Y pose de contacto del robot
        self.pinzas = {n: p for n, p in self.pinzas.items() if n in self.pinzas_robot}
        self.pinza = None                # nombre de la pinza activa (o None) — para el HUD
        self.pinza_peso = 0.0            # 0..1 cuánto manda la pose de contacto
        self._lock = threading.Lock()
        self._ang = None                 # 20 ángulos (grados) de nuestra mano
        self._t_ang = 0.0
        self._n_paquetes, self._t_hz, self.hz = 0, time.perf_counter(), 0.0
        self._guantes = {}               # glove_id → (side, isHaptics)
        self._id_guante = None           # glove_id de nuestra mano (para vibrar)
        self._ctrl_suave = None          # comando que se escribe en el hilo de física
        self._t_haptica = 0.0
        self._vibrando = False
        self._hilo = None
        self._activo = False
        self._sdk = None
        self.error = ""

    # ── ciclo de vida ────────────────────────────────────────────────────────
    def iniciar(self):
        """Inicializa el SDK y conecta en segundo plano. Devuelve False si el SDK no
        se puede cargar (el programa sigue con los dedos de la cámara)."""
        try:
            (self.lib, self.ffi, ManusSDK, self.RC,
             AxisView, AxisPolarity, Side) = _importar_sdk()
        except Exception as e:
            self.error = f"SDK de MANUS no disponible: {e}"
            print(f"❌ [MANUS] {self.error}")
            return False
        self._Side = Side
        lib, ffi = self.lib, self.ffi
        r = lib.CoreSdk_InitializeIntegrated() if self.modo == "integrado" \
            else lib.CoreSdk_InitializeCore()
        if r != self.RC.Success:
            self.error = f"no se pudo inicializar el SDK ({self.RC(r).name})"
            print(f"❌ [MANUS] {self.error}")
            return False
        cs = ffi.new("CoordinateSystemVUH*")
        cs.view, cs.up = AxisView.XFromViewer, AxisPolarity.PositiveZ
        cs.handedness, cs.unitScale = Side.Right, 1.0
        lib.CoreSdk_InitializeCoordinateSystemWithVUH(cs[0], True)
        self._sdk = ManusSDK()
        self._sdk.register_landscape_callback(self._cb_landscape)
        self._sdk.register_ergonomics_callback(self._cb_ergonomics)
        self._activo = True
        self._hilo = threading.Thread(target=self._conectar, name="MANUS-conexion", daemon=True)
        self._hilo.start()
        print(f"🧤 [MANUS] SDK listo (modo {self.modo}); conectando en segundo plano...")
        return True

    def _conectar(self):
        lib, ffi = self.lib, self.ffi
        loopback = self.modo == "local"
        espera = 1 if loopback else 3
        avisado = False
        while self._activo and not self.conectado:
            try:
                if lib.CoreSdk_LookForHosts(espera, loopback) == self.RC.Success:
                    n = ffi.new("uint32_t*")
                    if lib.CoreSdk_GetNumberOfAvailableHostsFound(n) == self.RC.Success and n[0] > 0:
                        hosts = ffi.new("ManusHost[]", n[0])
                        if lib.CoreSdk_GetAvailableHostsFound(hosts, n[0]) == self.RC.Success \
                                and lib.CoreSdk_ConnectToHost(hosts[0]) == self.RC.Success:
                            self.conectado = True
                            print("✅ [MANUS] Conectado: esperando datos del guante...")
                            return
            except Exception as e:
                self.error = str(e)
            if not avisado:
                print("⏳ [MANUS] Sin conexión todavía"
                      + (" (¿está abierto el MANUS Core Dashboard?)" if self.modo != "integrado"
                         else " (¿dongle enchufado y guante encendido?)") + ". Reintentando...")
                avisado = True
            time.sleep(1.0)

    def cerrar(self):
        self._activo = False
        if self._sdk is None:
            return
        try:
            self.vibrar([0.0] * 5)
            self.lib.CoreSdk_ShutDown()
        except Exception:
            pass
        self._sdk = None
        print("🧤 [MANUS] SDK cerrado.")

    # ── callbacks del SDK (hilo del SDK: copiar y salir, nada pesado) ─────────
    def _cb_landscape(self, landscape):
        try:
            g = landscape.gloveDevices
            guantes = {int(g.gloves[i].id): (int(g.gloves[i].side), bool(g.gloves[i].isHaptics))
                       for i in range(g.gloveCount)}
            lado = self._Side.Right if self.lado == "derecho" else self._Side.Left
            with self._lock:
                self._guantes = guantes
                self._id_guante = next((gid for gid, (s, _) in guantes.items() if s == lado), None)
        except Exception as e:
            self.error = f"landscape: {e}"

    def _cb_ergonomics(self, stream):
        try:
            base = 20 if self.lado == "derecho" else 0
            elegido = None
            with self._lock:
                id_nuestro = self._id_guante
            for i in range(stream.dataCount):
                d = stream.data[i]
                vals = [float(d.data[base + k]) for k in range(20)]
                if id_nuestro is not None and int(d.id) == id_nuestro:
                    elegido = vals
                    break
                if elegido is None and any(abs(v) > 1e-6 for v in vals):
                    elegido = vals                 # sin landscape aún: el que tenga datos
            if elegido is None:
                return
            ahora = time.perf_counter()
            with self._lock:
                self._ang, self._t_ang = elegido, ahora
                self._n_paquetes += 1
                if ahora - self._t_hz >= 1.0:
                    self.hz = self._n_paquetes / (ahora - self._t_hz)
                    self._n_paquetes, self._t_hz = 0, ahora
        except Exception as e:
            self.error = f"ergonomics: {e}"

    # ── lectura ──────────────────────────────────────────────────────────────
    def angulos(self):
        """(20 ángulos en GRADOS, antigüedad en s) de tu mano, o (None, inf)."""
        with self._lock:
            if self._ang is None:
                return None, float("inf")
            return list(self._ang), time.perf_counter() - self._t_ang

    def datos_frescos(self):
        _, edad = self.angulos()
        return edad <= MANUS_TIMEOUT_S

    def _actualizar_pinza(self, ang):
        """Pinza más cercana a tu mano (en grados RMS) con histéresis. Devuelve
        (nombre | None, peso 0..1)."""
        if not (MANUS_PINZA_ACTIVA and self.pinzas):
            return None, 0.0
        dist = {n: distancia_pinza(ang, p, n) for n, p in self.pinzas.items()}
        on, off = MANUS_PINZA_ON_DEG, MANUS_PINZA_OFF_DEG
        if self.pinza is not None and dist[self.pinza] <= off:
            nombre = self.pinza                            # la activa se mantiene hasta OFF
        else:
            nombre = min(dist, key=dist.get)
            if dist[nombre] > off:
                return None, 0.0
        peso = min(max((off - dist[nombre]) / max(off - on, 1e-6), 0.0), 1.0)
        return nombre, peso

    def ctrl_objetivo(self):
        """ctrl de la mano (N_ACT, NaN en la muñeca) según el guante, o None.
        Incluye la mezcla con la pose de contacto si estás en una pinza calibrada."""
        ang, edad = self.angulos()
        if ang is None or edad > MANUS_TIMEOUT_S:
            return None
        obj = angulos_a_ctrl(ang, self.mapeo)
        nombre, peso = self._actualizar_pinza(ang)
        self.pinza, self.pinza_peso = nombre, peso
        if nombre is not None and peso > 0.0:
            for k, v in self.pinzas_robot[nombre].items():
                lo, hi = LIMITES_CTRL[k]
                obj[k] = (1.0 - peso) * obj[k] + peso * min(max(v, lo), hi)
        return obj

    def estado_txt(self):
        if self._sdk is None:
            return "MANUS: sin SDK"
        if not self.conectado:
            return "MANUS: conectando..."
        if not self.datos_frescos():
            return "MANUS: SIN DATOS (¿guante encendido?)"
        txt = f"MANUS: OK {self.hz:3.0f} Hz" + ("" if self.aplicar else " (standby)")
        if self.pinza is not None:
            txt += f"  PINZA {self.pinza.replace('_', '+')} {100 * self.pinza_peso:3.0f} %"
        return txt

    # ── escritura en la simulación (hilo de física, antes de cada mj_step) ────
    def escribir_ctrl(self, datos, dt):
        """Lleva ctrl[1..16] de la mano hacia el guante con un filtro de primer orden
        (MANUS_TAU_S). Sin datos frescos o con aplicar=False no toca nada."""
        if not self.aplicar:
            self._ctrl_suave = None
            return
        obj = self.ctrl_objetivo()
        if obj is None:
            return                                     # dedos quietos donde estén
        i0 = OFFSET_MANO
        if self._ctrl_suave is None:                   # arranque: desde donde está la mano
            self._ctrl_suave = np.array(datos.ctrl[i0:i0 + N_ACT], dtype=float)
        a = 1.0 - math.exp(-dt / MANUS_TAU_S) if MANUS_TAU_S > 0 else 1.0
        m = ~np.isnan(obj)                             # todo menos la muñeca
        self._ctrl_suave[m] += a * (obj[m] - self._ctrl_suave[m])
        datos.ctrl[i0 + 1:i0 + N_ACT] = self._ctrl_suave[1:]

    def restaurar_dedos(self, datos):
        """Vuelve a poner en ctrl[1..16] los dedos del guante. Se llama justo después
        de retarget_a_ctrl (cámara), que también los escribe: así la mano FÍSICA
        (construir_hardware_target) y la grabación de episodios leen los del guante."""
        if self.aplicar and self._ctrl_suave is not None:
            datos.ctrl[OFFSET_MANO + 1:OFFSET_MANO + N_ACT] = self._ctrl_suave[1:]

    # ── vibración ────────────────────────────────────────────────────────────
    def es_haptico(self):
        with self._lock:
            return self._id_guante is not None and self._guantes.get(self._id_guante, (0, False))[1]

    def vibrar(self, potencias):
        """potencias: 5 valores 0..1 (pulgar, índice, corazón, anular, meñique)."""
        with self._lock:
            gid = self._id_guante
        if self._sdk is None or not self.conectado or gid is None:
            return False
        p = self.ffi.new("float[5]")
        for i in range(5):
            p[i] = float(min(max(potencias[i], 0.0), 1.0))
        return self.lib.CoreSdk_VibrateFingersForGlove(gid, p) == self.RC.Success

    def haptica(self, modelo, datos):
        """Fuerza de contacto en cada yema de la OrcaHand (simulación) → vibración del
        dedo correspondiente. Llamar con el candado de la física (bucle principal)."""
        if not (MANUS_HAPTICA and self.aplicar and self.conectado and self.es_haptico()):
            if self._vibrando:
                self.vibrar([0.0] * 5)
                self._vibrando = False
            return
        ahora = time.perf_counter()
        if ahora - self._t_haptica < 1.0 / MANUS_HAPTICA_HZ:
            return
        self._t_haptica = ahora
        fuerzas = fuerzas_yemas(modelo, datos)
        rango = max(MANUS_FUERZA_MAX - MANUS_FUERZA_MIN, 1e-6)
        pot = [MANUS_VIBRACION_MAX * min(max((f - MANUS_FUERZA_MIN) / rango, 0.0), 1.0)
               for f in fuerzas]
        if any(pot) or self._vibrando:
            self.vibrar(pot)
            self._vibrando = any(pot)


_ids_yema = None


def fuerzas_yemas(modelo, datos):
    """Fuerza normal (N) de contacto sobre cada yema (pulgar → meñique)."""
    import mujoco
    global _ids_yema
    if _ids_yema is None:
        _ids_yema = [mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, n) for n in _BODIES_YEMA]
    f = [0.0] * 5
    f6 = np.zeros(6)
    for i in range(datos.ncon):
        c = datos.contact[i]
        b1, b2 = modelo.geom_bodyid[c.geom1], modelo.geom_bodyid[c.geom2]
        for k, b in enumerate(_ids_yema):
            if b >= 0 and (b1 == b or b2 == b) and b1 != b2:
                mujoco.mj_contactForce(modelo, datos, i, f6)
                f[k] += abs(float(f6[0]))
    return f