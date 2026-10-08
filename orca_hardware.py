#!/usr/bin/env python3
"""
OrcaHardwareWrapper — Skill Shield Nivel 6
============================================
Puente entre el array motor-ordenado de Skill_Shield y la API de OrcaHand v2.

Skill_Shield construye hardware_target[] en ORDEN DE MOTOR (índice = motor_id - 1):
  [0]=Motor1=wrist  [1]=Motor2=index_pip  [2]=Motor3=index_mcp  [3]=Motor4=index_abd
  [4]=Motor5=middle_abd  [5]=Motor6=ring_abd  [6]=Motor7=ring_mcp  [7]=Motor8=ring_pip
  [8]=Motor9=middle_pip  [9]=Motor10=middle_mcp  [10]=Motor11=pinky_pip
  [11]=Motor12=pinky_mcp  [12]=Motor13=pinky_abd  [13]=Motor14=thumb_abd
  [14]=Motor15=thumb_mcp  [15]=Motor16=thumb_dip  [16]=Motor17=thumb_cmc

Todos los valores llegan en RADIANES y en la CONVENCIÓN DEL SIMULADOR (MJCF).
OrcaHand espera GRADOS en SU convención → la traducción se hace aquí (ver abajo).
Las inversiones de MOTOR (signos negativos en joint_to_motor_map) las sigue gestionando
el SDK; lo que se corrige aquí es otra cosa: el SENTIDO DEL ÁNGULO de cada articulación.

TRADUCCIÓN SIM → MANO REAL (8-oct)
----------------------------------
La simulación iba bien pero la mano física no cerraba el puño, no hacía pinzas y no
cerraba el pulgar. Causas en este puente (las dos primeras eran invisibles en el sim):

  1) ABDUCCIONES INVERTIDAS (index/middle/ring/pinky_abd). En el MJCF, ángulo + mueve la
     yema HACIA EL PULGAR; en orca_core, + la mueve HACIA EL MEÑIQUE. Pruebas: el ROM de
     index_abd del config.yaml es [-30, 25], espejo del rango del MJCF [-25, 30]; la
     postura neutral del SDK (índice −14°, anular +10°, meñique +22°) solo es un abanico
     natural con + = hacia el meñique; y el propio orca_core actual lo declara
     (kinematics/v2_kinematics.yaml: sign −1 en las cuatro abducciones). Se mandaba el
     ángulo del sim tal cual → con tus dedos JUNTOS (puño, pinza) la mano real los ABRÍA
     en abanico y el índice se iba hacia el pulgar, cerrándole el paso.
     → ORCA_HW_SIGNOS (por defecto, −1 en las cuatro abducciones).

  2) EL CIERRE DEL SIM NO LLEGABA AL TOPE REAL. El puño del guante es mcp 1.70 rad (97°),
     pip 1.80 (103°), pulgar mcp/ip 1.50 (86°): 97 % del recorrido calibrado en los dedos,
     89 % en el nudillo del pulgar y 83 % en su punta. Además el SDK graba cada tope con
     el par QUITADO (el tendón se relaja), así que hasta el 100 % se queda algo corto.
     → ORCA_HW_CIERRE_COMPLETO: el último tramo del recorrido de cada FLEXIÓN se estira
       para que el "cerrado" del sim sea el tope calibrado de la mano real; por debajo
       de ORCA_HW_CIERRE_RODILLA (60 % del cierre) no cambia nada.
     → ORCA_HW_SOBRECARRERA_DEG: unos grados más allá del tope, SOLO en flexiones. Los
       dedos van en current_based_position: empujan como mucho con max_current (igual que
       al calibrar). Nunca en la muñeca (modo multivuelta, sin límite de corriente).

  3) SEGUIMIENTO: cada ORCA_HW_SEGUIMIENTO_CADA_S se lee la mano (posición + corriente)
     y se avisa de las articulaciones que no llegan a lo pedido, diciendo si es por
     corriente (sube max_current en el config.yaml del SDK) o sin esfuerzo (tendón flojo
     o calibración desfasada → tension.py + calibrate.py del SDK).

  Parámetros opcionales (config.py); si no están, se usan estos valores:
      ORCA_HW_SIGNOS            = {"index_abd": -1, "middle_abd": -1,
                                   "ring_abd": -1, "pinky_abd": -1}   # {} = como antes
      ORCA_HW_CIERRE_COMPLETO   = True
      ORCA_HW_CIERRE_RODILLA    = 0.6     # fracción del cierre donde empieza el estirado
      ORCA_HW_CIERRE_SIM        = {}      # p. ej. {"thumb_dip": 1.50}: "cerrado" del sim (rad)
      ORCA_HW_SOBRECARRERA_DEG  = 4.0     # 0 = sin sobrecarrera (se usa la API pública)
      ORCA_HW_SEGUIMIENTO       = True
      ORCA_HW_SEGUIMIENTO_CADA_S     = 3.0
      ORCA_HW_SEGUIMIENTO_UMBRAL_DEG = 6.0

MANO FÍSICA SIN TROMPICONES (30-sep) — hilo de envío propio
------------------------------------------------------------
Antes, enviar_posiciones() escribía en el puerto serie DESDE el bucle de la cámara,
una vez por fotograma (~10-12 por segundo). Los Dynamixel llegaban a cada objetivo en
pocos ms y se PARABAN hasta el siguiente fotograma: tirón, parada, tirón... Es la misma
"escalera" que el PASO 7.1 (GeneradorSuave) ya quitó al brazo simulado, pero la mano
física seguía recibiéndola. El filtro exponencial que había aquí (ALPHA = 0.35) no lo
arreglaba: también se aplicaba una vez por fotograma, así que seguía habiendo
escalones, y encima añadía ~2 fotogramas de retraso.

Ahora:
  1) enviar_posiciones() NO toca el puerto serie: solo PUBLICA el objetivo y vuelve en
     microsegundos. El bucle de la cámara ya no espera nunca a la mano.
  2) Un hilo propio manda a ORCA_HW_HZ (50/s por defecto) un comando CONTINUO:
     reparte cada salto entre dos fotogramas (interpolación) y limita la velocidad y
     la aceleración de cada articulación, frenando a tiempo (perfil trapezoidal, el
     mismo algoritmo que GeneradorSuave). Los cambios de golpe (pinzas predefinidas,
     puño, bloqueo de muñeca) pasan a ser rampas.
  3) Mide cuánto tarda el SDK en cada envío y avisa si el puerto serie va lento.

La interfaz NO cambia: conectar(), enviar_posiciones(array), desconectar() y el
atributo .conectado. Nuevo: estado_real() para leer la mano (lo usa
diagnostico_mano_real.py).
"""

import math
import os
import sys
import threading
import time
import traceback

import numpy as np

# ── Ruta al SDK de OrcaHand ───────────────────────────────────────────────────
_ORCA_CORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orca_core-main")
if _ORCA_CORE_PATH not in sys.path:
    sys.path.insert(0, _ORCA_CORE_PATH)

_CONFIG_PATH = os.path.join(
    _ORCA_CORE_PATH, "orca_core", "models", "v2", "orcahand_right", "config.yaml"
)

# ── Parámetros de fluidez: se leen de config.py; si no existen, estos valores ──
try:
    import config as _cfg
except Exception:          # p. ej. si se usa este archivo desde otro script/carpeta
    _cfg = None


def _param(nombre, defecto):
    return getattr(_cfg, nombre, defecto) if _cfg is not None else defecto


def _estirar(x, x_rodilla, x_cierre, y_cierre):
    """Tramo final estirado: x_rodilla → x_rodilla, x_cierre → y_cierre (grados)."""
    if x <= x_rodilla:
        return x
    if x >= x_cierre:
        return y_cierre + (x - x_cierre)
    return x_rodilla + (x - x_rodilla) * (y_cierre - x_rodilla) / (x_cierre - x_rodilla)


def _encoger(y, x_rodilla, x_cierre, y_cierre):
    """Inversa de _estirar (para leer la postura real en la convención del sim)."""
    if y <= x_rodilla:
        return y
    if y >= y_cierre:
        return x_cierre + (y - y_cierre)
    return x_rodilla + (y - x_rodilla) * (x_cierre - x_rodilla) / (y_cierre - x_rodilla)


def analizar_seguimiento(wrapper, estado, umbral_deg, solo=None):
    """
    estado = wrapper.estado_real() → líneas de texto con las articulaciones que no
    llegan a lo pedido (más de umbral_deg) y el motivo probable. [] si todo llega.
    La sobrecarrera no cuenta como error: por diseño el dedo no puede pasar del tope.
    """
    filas = []
    for j, (pedido, real, frac) in estado.items():
        if (solo is not None and j not in solo) or pedido is None or real is None:
            continue
        lo, hi = wrapper._rom.get(j, (-1e9, 1e9))
        objetivo = min(max(pedido, lo), hi)
        err = real - objetivo
        if abs(err) <= umbral_deg:
            continue
        base = f"{j:11s} pide {objetivo:6.1f}°  está en {real:6.1f}°  ({err:+5.1f}°)"
        if j == "wrist":
            motivo = "muñeca (modo multivuelta, sin límite de corriente): revisa su calibración"
        elif frac != frac:          # NaN
            motivo = "sin lectura de corriente"
        elif frac >= 0.85:
            motivo = (f"corriente {100 * frac:3.0f} % de max_current → LIMITADA POR CORRIENTE: "
                      f"algo la frena (piel, otro dedo, rozamiento) o max_current es bajo")
        else:
            motivo = (f"corriente {100 * frac:3.0f} % → no llega SIN apretar: tendón flojo, "
                      f"calibración desfasada o tope mecánico antes de lo esperado")
        filas.append(f"{base}  ·  {motivo}")
    return filas


class OrcaHardwareWrapper:
    """
    Recibe hardware_target[] (motor-indexado, radianes, convención del SIM) y lo manda
    a OrcaHand desde un hilo propio, como comando continuo y suave, traducido a la
    convención de orca_core (ver cabecera).
    """

    # Índice del array (= motor_id - 1) → nombre de joint OrcaHand
    # Derivado directamente de cómo Skill_Shield_Nivel_6.py construye hardware_target[]
    MOTOR_A_JOINT = {
        0:  "wrist",       # Motor 1  ← mu_pos["wrist"]
        1:  "index_pip",   # Motor 2  ← mu_pos["index_pip"]
        2:  "index_mcp",   # Motor 3  ← mu_pos["index_mcp"]
        3:  "index_abd",   # Motor 4  ← mu_pos["index_abd"]
        4:  "middle_abd",  # Motor 5  ← mu_pos["middle_abd"]
        5:  "ring_abd",    # Motor 6  ← mu_pos["ring_abd"]
        6:  "ring_mcp",    # Motor 7  ← mu_pos["ring_mcp"]
        7:  "ring_pip",    # Motor 8  ← mu_pos["ring_pip"]
        8:  "middle_pip",  # Motor 9  ← mu_pos["middle_pip"]
        9:  "middle_mcp",  # Motor 10 ← mu_pos["middle_mcp"]
        10: "pinky_pip",   # Motor 11 ← mu_pos["pinky_pip"]
        11: "pinky_mcp",   # Motor 12 ← mu_pos["pinky_mcp"]
        12: "pinky_abd",   # Motor 13 ← mu_pos["pinky_abd"]
        13: "thumb_abd",   # Motor 14 ← mu_pos["thumb_abd"]
        14: "thumb_mcp",   # Motor 15 ← mu_pos["thumb_mcp"]
        15: "thumb_dip",   # Motor 16 ← mu_pos["thumb_dip"]
        16: "thumb_cmc",   # Motor 17 ← mu_pos["thumb_cmc"]
    }

    # Índice de ctrl de la mano (los de config.LIMITES_CTRL) de cada joint
    JOINT_A_CTRL = {
        "wrist": 0, "pinky_abd": 1, "pinky_mcp": 2, "pinky_pip": 3,
        "ring_abd": 4, "ring_mcp": 5, "ring_pip": 6,
        "middle_abd": 7, "middle_mcp": 8, "middle_pip": 9,
        "index_abd": 10, "index_mcp": 11, "index_pip": 12,
        "thumb_cmc": 13, "thumb_abd": 14, "thumb_mcp": 15, "thumb_dip": 16,
    }

    # Flexiones (cierre de dedos y pulgar): las ÚNICAS con cierre completo y sobrecarrera.
    # Nunca la muñeca (multi_turn_position, sin límite de corriente), ni las abducciones,
    # ni thumb_cmc / thumb_abd.
    FLEXION = ("index_mcp", "index_pip", "middle_mcp", "middle_pip", "ring_mcp",
               "ring_pip", "pinky_mcp", "pinky_pip", "thumb_mcp", "thumb_dip")

    # Sentido del ángulo sim (MJCF) → orca_core. Ver cabecera, punto 1.
    SIGNOS_DEFECTO = {"index_abd": -1, "middle_abd": -1, "ring_abd": -1, "pinky_abd": -1}

    # Debug de pulgar: True para imprimir valores cada DEBUG_CADA_N envíos
    # (a 50 envíos/s, 30 envíos ≈ 0.6 s)
    DEBUG_PULGAR = False
    DEBUG_CADA_N = 30

    # Cada tramo de interpolación dura un 20 % más que el periodo medio entre
    # fotogramas: si el siguiente llega un poco tarde (el bucle de la cámara no va a
    # ritmo fijo), la mano sigue moviéndose en vez de pararse a esperarlo (~20 ms más
    # de retraso a cambio). 1.0 = igual que GeneradorSuave.
    MARGEN_TRAMO = 1.2

    # Errores seguidos del SDK tras los que se da la mano por desconectada
    # (a 50 envíos/s, 100 ≈ 2 s: p. ej. cable USB sacado)
    MAX_ERRORES_SEGUIDOS = 100

    def __init__(self, puerto="/dev/ttyUSB0", baudrate=1000000, config_path=None,
                 clase_mano=None):
        self.puerto       = puerto
        self.baudrate     = baudrate
        self.conectado    = False
        self._hand        = None
        self._sdk_abierto = False
        self._config_path = config_path or _CONFIG_PATH
        self._clase_mano  = clase_mano        # None = orca_core.OrcaHand (p. ej. MockOrcaHand para ensayar)

        self._n      = len(self.MOTOR_A_JOINT)
        self._joints = [self.MOTOR_A_JOINT[i] for i in range(self._n)]

        # ── Parámetros (config.py → sección FLUIDEZ) ──
        self.hz         = max(1.0, float(_param("ORCA_HW_HZ", 50)))
        self.interpolar = bool(_param("ORCA_HW_INTERPOLAR", True))
        self._vmax = np.full(self._n, float(_param("ORCA_HW_VEL_MAX", 6.0)))
        self._amax = np.full(self._n, float(_param("ORCA_HW_ACEL_MAX", 60.0)))
        for joint, (v, a) in dict(_param("ORCA_HW_LIMITES_JOINT", {})).items():
            if joint in self._joints:
                k = self._joints.index(joint)
                self._vmax[k], self._amax[k] = float(v), float(a)
            else:
                print(f"⚠️  [ORCA HARDWARE] ORCA_HW_LIMITES_JOINT: joint desconocido '{joint}'")
        self.debug_tiempos = bool(_param("ORCA_HW_DEBUG_TIEMPOS", True))
        self.cada_s_debug  = float(_param("ORCA_HW_DEBUG_CADA_S", 5.0))

        # ── Traducción sim → mano real (config.py → ORCA_HW_*; ver cabecera) ──
        signos = dict(_param("ORCA_HW_SIGNOS", self.SIGNOS_DEFECTO))
        for joint in signos:
            if joint not in self._joints:
                print(f"⚠️  [ORCA HARDWARE] ORCA_HW_SIGNOS: joint desconocido '{joint}'")
        self._signo = np.array([-1.0 if float(signos.get(j, 1)) < 0 else 1.0
                                for j in self._joints])
        self.cierre_completo = bool(_param("ORCA_HW_CIERRE_COMPLETO", True))
        self.rodilla         = min(max(float(_param("ORCA_HW_CIERRE_RODILLA", 0.6)), 0.0), 0.95)
        self.sobrecarrera    = max(0.0, float(_param("ORCA_HW_SOBRECARRERA_DEG", 4.0)))
        self.seguimiento     = bool(_param("ORCA_HW_SEGUIMIENTO", True))
        self.cada_s_seg      = float(_param("ORCA_HW_SEGUIMIENTO_CADA_S", 3.0))
        self.umbral_seg      = float(_param("ORCA_HW_SEGUIMIENTO_UMBRAL_DEG", 6.0))
        self._rom           = {}     # joint → (lo, hi) del config.yaml del SDK (grados)
        self._rango_sdk     = {}     # joint → (lo, hi) que se puede mandar (con sobrecarrera)
        self._cierre        = {}     # joint → (x_rodilla, x_cierre, y_cierre) en grados
        self._motor_directo = False  # True = sobrecarrera activa (sin el recorte del SDK)
        self._ult_pose      = None   # última pose mandada (grados, convención orca_core)

        # Candado del SDK / puerto serie. Solo el hilo de envío habla con los servos;
        # si algún día lees algo del SDK desde otro hilo (p. ej. los sensores
        # táctiles), hazlo dentro de `with mano_real.lock_sdk:`.
        self.lock_sdk  = threading.RLock()
        self._lock_obj = threading.Lock()      # protege el objetivo publicado
        self._hilo     = None
        self._activo   = False
        self._reiniciar_generador()

    # ─────────────────────────────────────────────────────────────────────────

    def _reiniciar_generador(self):
        self._q       = None                   # comando que se está enviando (rad)
        self._v       = np.zeros(self._n)      # su velocidad (rad/s)
        self._obj_ini = None                   # tramo de interpolación actual:
        self._obj_fin = None                   #   de _obj_ini a _obj_fin en _dur s
        self._t_obj   = 0.0
        self._dt_med  = 0.1                    # periodo medio entre objetivos (s)
        self._dur     = 0.1
        self._q_leida = None                   # postura real leída al conectar (rad)
        self._n_env   = 0

    # ─────────────────────────────────────────────────────────────────────────

    def conectar(self):
        print(f"🔌 [ORCA HARDWARE] Conectando en {self.puerto} @ {self.baudrate} bps...")
        try:
            clase = self._clase_mano
            if clase is None:
                from orca_core import OrcaHand
                clase = OrcaHand
            self._hand = clase(config_path=self._config_path)
            ok, msg = self._hand.connect()
            if not ok:
                print(f"❌ [ORCA HARDWARE] Fallo al conectar: {msg}")
                return False
            self._sdk_abierto = True
            print("⚙️  [ORCA HARDWARE] Inicializando articulaciones...")
            self._hand.init_joints()
            self._preparar_traduccion()

            self._reiniciar_generador()
            self._q_leida = self._leer_postura()
            self.conectado = True
            self._activo   = True
            self._hilo = threading.Thread(target=self._bucle_envio,
                                          name="OrcaHW-envio", daemon=True)
            self._hilo.start()
            print(f"✅ [ORCA HARDWARE] Mano física lista — envío continuo a {self.hz:.0f} Hz "
                  f"(vel. máx {self._vmax.max():.1f} rad/s, acel. máx {self._amax.max():.0f} rad/s²).")
            return True
        except ImportError as e:
            print(f"❌ [ORCA HARDWARE] orca_core no instalado: {e}")
            return False
        except Exception as e:
            print(f"❌ [ORCA HARDWARE] Error: {e}")
            traceback.print_exc()
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # TRADUCCIÓN SIM (MJCF, rad) ↔ ORCA_CORE (grados)
    # ─────────────────────────────────────────────────────────────────────────

    def _cierre_sim_grados(self, joint):
        """Valor del sim (grados, ya con el signo aplicado) que significa 'cerrado del todo'."""
        a_mano = dict(_param("ORCA_HW_CIERRE_SIM", {}))
        if joint in a_mano:
            rad = float(a_mano[joint])
        else:
            k = self.JOINT_A_CTRL[joint]
            rango = dict(_param("MANUS_RANGO_ROBOT", {})).get(k)
            if str(_param("FUENTE_DEDOS", "camara")) == "manus" and rango is not None:
                rad = max(float(rango[0]), float(rango[1]))     # puño del guante
            else:
                lim = _param("LIMITES_CTRL", None)
                if lim is None:
                    return None
                rad = float(lim[k][1])                          # puño de la cámara
        return float(self._signo[self._joints.index(joint)]) * math.degrees(rad)

    def _preparar_traduccion(self):
        """ROMs del config.yaml del SDK → rangos y tramos de cierre. Tras init_joints()."""
        cfg = self._hand.config
        self._rom = {j: (float(cfg.joint_roms_dict[j][0]), float(cfg.joint_roms_dict[j][1]))
                     for j in self._joints}
        # Sobrecarrera = mandar más allá del ROM, que set_joint_positions() recorta: se
        # usa el mismo cálculo del SDK (_joint_to_motor_pos) sin ese recorte.
        self._motor_directo = (self.sobrecarrera > 0.0
                               and callable(getattr(self._hand, "_joint_to_motor_pos", None))
                               and callable(getattr(self._hand, "_set_motor_pos", None)))
        extra = self.sobrecarrera if self._motor_directo else 0.0
        self._rango_sdk, self._cierre = {}, {}
        for j in self._joints:
            lo, hi = self._rom[j]
            if j not in self.FLEXION:
                self._rango_sdk[j] = (lo, hi)
                continue
            self._rango_sdk[j] = (lo, hi + extra)
            x_c = self._cierre_sim_grados(j) if self.cierre_completo else None
            y_c = hi + extra
            if x_c is not None and x_c > 0.0:
                x_k = self.rodilla * x_c
                if x_c > x_k + 1.0 and y_c > x_k + 1.0:
                    self._cierre[j] = (x_k, x_c, y_c)

        invertidas = [j for k, j in enumerate(self._joints) if self._signo[k] < 0]
        print("🔁 [ORCA HARDWARE] Traducción sim → mano real:")
        print("   · sentido invertido: " + (", ".join(invertidas) if invertidas else "ninguna")
              + ("  (sim + = hacia el pulgar; orca_core + = hacia el meñique)" if invertidas else ""))
        if self._cierre:
            print("   · cierre completo (sim → real): " + "  ".join(
                f"{j.replace('_', ' ')} {c[1]:.0f}°→{c[2]:.0f}°" for j, c in self._cierre.items()))
        print(f"   · sobrecarrera de flexión: {extra:.0f}°"
              + ("" if self._motor_directo or self.sobrecarrera == 0 else
                 "  (desactivada: este SDK no expone _joint_to_motor_pos/_set_motor_pos)"))
        print(f"   · modo {getattr(cfg, 'control_mode', '?')}, max_current = "
              f"{getattr(cfg, 'max_current', '?')} (config.yaml del SDK)")
        if invertidas:
            print("   Comprobación: en la postura neutral del arranque el índice queda abierto "
                  "hacia el pulgar y el meñique hacia fuera (index_abd −14°, pinky_abd +22°).")

    def _a_sdk(self, q):
        """q (orden de motor, rad, convención sim) → {joint: grados orca_core}, recortado."""
        pose = {}
        for k, j in enumerate(self._joints):
            g = self._signo[k] * math.degrees(float(q[k]))
            c = self._cierre.get(j)
            if c is not None:
                g = _estirar(g, *c)
            lo, hi = self._rango_sdk.get(j, (-1e9, 1e9))
            pose[j] = min(max(g, lo), hi)
        return pose

    def _desde_sdk(self, grados):
        """{joint: grados orca_core} → q (orden de motor, rad, convención sim) o None."""
        q = np.empty(self._n)
        for k, j in enumerate(self._joints):
            g = grados.get(j)
            if g is None:
                return None
            c = self._cierre.get(j)
            if c is not None:
                g = _encoger(float(g), *c)
            q[k] = math.radians(self._signo[k] * float(g))
        return q

    # ─────────────────────────────────────────────────────────────────────────

    def _leer_postura(self):
        """
        Postura REAL de la mano (rad, orden de motor, convención del sim), para que el
        primer movimiento salga de donde está la mano y no dé un salto. Si no se puede
        leer, devuelve None y se parte del primer objetivo (como antes).
        (Antes no funcionaba: get_joint_position() devuelve un OrcaJointPositions, no un
        dict ni una lista, y siempre se caía al "no se pudo leer".)
        """
        try:
            with self.lock_sdk:
                r = self._hand.get_joint_position()
            grados = r.as_dict() if hasattr(r, "as_dict") else dict(r)
            q = self._desde_sdk(grados)
            if q is None or not np.all(np.isfinite(q)):
                raise ValueError("faltan articulaciones sin calibrar")
            print(f"📍 [ORCA HARDWARE] Postura inicial leída (muñeca {grados['wrist']:.0f}°, "
                  f"índice MCP {grados['index_mcp']:.0f}°): el primer movimiento saldrá de "
                  f"ahí, sin salto.")
            return q
        except Exception as e:
            print(f"ℹ️  [ORCA HARDWARE] No se pudo leer la postura inicial ({e}): el primer "
                  "objetivo se enviará directamente (como antes).")
            return None

    def estado_real(self):
        """
        Lee la mano: {joint: (pedido°, real°, fracción de max_current)}, en grados de
        orca_core. 'pedido' es lo último que se mandó (None si aún nada). ~2-4 ms.
        """
        if self._hand is None:
            return {}
        with self.lock_sdk:
            pos, _vel, cur = self._hand._motor_client.read_pos_vel_cur()
            reales = self._hand._motor_to_joint_pos(pos)
        cfg = self._hand.config
        lector = getattr(self._hand._motor_client, "_pos_vel_cur_reader", None)
        escala = float(getattr(lector, "cur_scale", 1.0) or 1.0)   # misma unidad que Goal Current
        i_max = max(float(cfg.max_current), 1.0)
        idx = {mid: i for i, mid in enumerate(cfg.motor_ids)}
        pedida = self._ult_pose or {}
        out = {}
        for j in self._joints:
            mid = cfg.joint_to_motor_map.get(j)
            frac = abs(float(cur[idx[mid]])) / escala / i_max if mid in idx else float("nan")
            out[j] = (pedida.get(j), reales.get(j), frac)
        return out

    def _informe_seguimiento(self):
        """Avisa de lo que no llega (solo articulaciones cuyo comando ya está quieto)."""
        quietas = {j for k, j in enumerate(self._joints) if abs(self._v[k]) < 0.3}
        filas = analizar_seguimiento(self, self.estado_real(), self.umbral_seg, quietas)
        if filas:
            print("\n🔎 [ORCA HARDWARE] No llegan a lo pedido:")
            for f in filas:
                print("   " + f)

    # ─────────────────────────────────────────────────────────────────────────

    def _interpolado(self, t):
        """Punto del tramo actual (de _obj_ini a _obj_fin) en el instante t."""
        s = min(max((t - self._t_obj) / self._dur, 0.0), 1.0)
        return self._obj_ini + s * (self._obj_fin - self._obj_ini)

    def enviar_posiciones(self, array_radianes):
        """
        PUBLICA el objetivo (hardware_target[], orden de motor, radianes, convención del
        sim) y vuelve enseguida. Quien habla con los servos es el hilo de envío.
        Se puede llamar a cualquier ritmo (en teleoperación, una vez por fotograma).
        """
        if not self.conectado:
            return False
        try:
            obj = np.array([float(array_radianes[i]) for i in range(self._n)])
        except (IndexError, TypeError, ValueError) as e:
            print(f"⚠️  [ORCA HARDWARE] Objetivo no válido: {e}")
            return False
        if not np.all(np.isfinite(obj)):
            return False

        ahora = time.perf_counter()
        with self._lock_obj:
            if self._obj_fin is None:                        # primer objetivo
                inicio = self._q_leida if self._q_leida is not None else obj
                self._obj_ini = inicio.copy()
            else:
                dt = ahora - self._t_obj
                if dt > 1e-4:                                # periodo real entre objetivos
                    dt = min(max(dt, 0.02), 0.25)
                    self._dt_med = 0.7 * self._dt_med + 0.3 * dt
                # el tramo nuevo empieza donde va AHORA la interpolación → continuidad
                self._obj_ini = self._interpolado(ahora)
            self._obj_fin = obj
            self._t_obj   = ahora
            self._dur     = self.MARGEN_TRAMO * self._dt_med if self.interpolar else 1e-6
        return True

    # ─────────────────────────────────────────────────────────────────────────

    def _paso_generador(self, ref, dt):
        """Lleva el comando hacia 'ref' con velocidad y aceleración limitadas."""
        e  = ref - self._q
        ae = np.abs(e)
        # velocidad máxima con la que aún se puede FRENAR a tiempo (perfil trapezoidal)
        v_des = np.sign(e) * np.minimum(np.minimum(self._vmax, np.sqrt(2.0 * self._amax * ae)),
                                        ae / dt)
        self._v += np.clip(v_des - self._v, -self._amax * dt, self._amax * dt)
        self._q += self._v * dt

    def _enviar_sdk(self):
        """Manda el comando actual al SDK (grados, convención orca_core). Devuelve lo que tardó (s)."""
        pose = self._a_sdk(self._q)
        t0 = time.perf_counter()
        with self.lock_sdk:
            if self._motor_directo:
                # Lo mismo que hace set_joint_positions() del SDK (signos de motor, wraps,
                # calibración) pero SIN su recorte al ROM, para dejar pasar la sobrecarrera
                # de las flexiones (ya recortada en _a_sdk a ROM + ORCA_HW_SOBRECARRERA_DEG).
                self._hand._set_motor_pos(self._hand._joint_to_motor_pos(pose))
            else:
                self._hand.set_joint_positions(pose)  # el SDK recorta a los ROMs
        dur = time.perf_counter() - t0
        self._ult_pose = pose

        self._n_env += 1
        if self.DEBUG_PULGAR and self._n_env % self.DEBUG_CADA_N == 0:
            print(
                f"[PULGAR] cmc={pose['thumb_cmc']:6.1f}°  abd={pose['thumb_abd']:6.1f}°  "
                f"mcp={pose['thumb_mcp']:6.1f}°  dip={pose['thumb_dip']:6.1f}°"
            )
        return dur

    def _bucle_envio(self):
        """Hilo de envío: comando continuo a ORCA_HW_HZ."""
        periodo = 1.0 / self.hz
        t_sig   = time.perf_counter()
        t_prev  = None
        # estadística de tiempos
        t_rep, n_rep, sdk_sum, sdk_max = time.perf_counter(), 0, 0.0, 0.0
        aviso_lento = False
        errores, t_ult_error = 0, 0.0
        t_seg = time.perf_counter()

        while self._activo:
            ahora = time.perf_counter()
            with self._lock_obj:
                ref = None if self._obj_fin is None else self._interpolado(ahora)

            if ref is not None:                       # hasta el primer objetivo, no se envía nada
                if self._q is None:                   # arranque: desde la postura real
                    self._q = (self._q_leida if self._q_leida is not None else ref).copy()
                    self._v[:] = 0.0
                    t_prev = ahora
                dt = min(max(ahora - t_prev, 1e-3), 0.1)
                t_prev = ahora
                self._paso_generador(ref, dt)

                try:
                    dur = self._enviar_sdk()
                    errores = 0
                    n_rep  += 1
                    sdk_sum += dur
                    sdk_max  = max(sdk_max, dur)
                except Exception as e:
                    errores += 1
                    if ahora - t_ult_error > 1.0:      # como mucho un aviso por segundo
                        print(f"⚠️  [ORCA HARDWARE] Error enviando posiciones: {e}")
                        t_ult_error = ahora
                    if errores >= self.MAX_ERRORES_SEGUIDOS:
                        print("❌ [ORCA HARDWARE] Demasiados errores seguidos: se deja de "
                              "enviar (¿cable USB o alimentación de la mano?).")
                        self.conectado = False
                        self._activo   = False
                        break

            # ── Seguimiento: ¿llega la mano real a lo que se le pide? ──
            if self.seguimiento and self._ult_pose is not None and ahora - t_seg >= self.cada_s_seg:
                t_seg = ahora
                try:
                    self._informe_seguimiento()
                except Exception as e:
                    self.seguimiento = False
                    print(f"⚠️  [ORCA HARDWARE] Seguimiento desactivado (no se pudo leer la mano: {e})")

            # ── Informe periódico: envíos/s reales y lo que tarda el SDK ──
            if ahora - t_rep >= self.cada_s_debug and n_rep > 0:
                media = sdk_sum / n_rep
                if self.debug_tiempos:
                    print(f"\n📶 [ORCA HARDWARE] {n_rep / (ahora - t_rep):4.1f} envíos/s · "
                          f"SDK: media {1000 * media:.1f} ms, máx {1000 * sdk_max:.1f} ms")
                if media > 0.5 * periodo and not aviso_lento:
                    aviso_lento = True
                    print(f"⚠️  [ORCA HARDWARE] Cada envío tarda {1000 * media:.1f} ms (más de medio "
                          f"periodo de {1000 * periodo:.0f} ms). Si el adaptador es FTDI (U2D2), "
                          f"pon su latency_timer a 1 ms; si no mejora, baja ORCA_HW_HZ.")
                t_rep, n_rep, sdk_sum, sdk_max = ahora, 0, 0.0, 0.0

            # ── Ritmo fijo ──
            t_sig += periodo
            espera = t_sig - time.perf_counter()
            if espera > 0:
                time.sleep(espera)
            else:
                t_sig = time.perf_counter()           # vamos tarde: no se intenta "recuperar"

    # ─────────────────────────────────────────────────────────────────────────

    def _parar_hilo(self):
        self._activo = False
        h = self._hilo
        if h is not None and h.is_alive() and h is not threading.current_thread():
            h.join(timeout=1.0)
        self._hilo = None

    def desconectar(self):
        self._parar_hilo()                            # primero se calla el hilo de envío
        self.conectado = False
        if self._hand is None or not self._sdk_abierto:
            return
        try:
            with self.lock_sdk:
                print("🔌 [ORCA HARDWARE] Volviendo a posición neutral...")
                self._hand.set_neutral_position(num_steps=6, step_size=0.02)
                self._hand.stop_task()
                self._hand.disconnect()
            print("✅ [ORCA HARDWARE] Mano desconectada.")
        except Exception as e:
            print(f"⚠️  [ORCA HARDWARE] Error al desconectar: {e}")
        finally:
            self._sdk_abierto = False