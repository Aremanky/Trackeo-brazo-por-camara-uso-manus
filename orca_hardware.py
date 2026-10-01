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

Todos los valores llegan en RADIANES. OrcaHand espera GRADOS → conversión aquí.
Las inversiones de motor (signos negativos en joint_to_motor_map) las gestiona
internamente el SDK de OrcaHand — NO aplicar correcciones de signo manual.

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
atributo .conectado. Los parámetros se leen de config.py (sección FLUIDEZ); si no
están, se usan los valores por defecto de _param(...).
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


class OrcaHardwareWrapper:
    """
    Recibe hardware_target[] (motor-indexado, radianes) y lo manda a OrcaHand desde
    un hilo propio, como comando continuo y suave.
    El SDK gestiona internamente las inversiones de motor del joint_to_motor_map.
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

    def __init__(self, puerto="/dev/ttyUSB0", baudrate=1000000):
        self.puerto       = puerto
        self.baudrate     = baudrate
        self.conectado    = False
        self._hand        = None
        self._sdk_abierto = False

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
            from orca_core import OrcaHand
            self._hand = OrcaHand(config_path=_CONFIG_PATH)
            ok, msg = self._hand.connect()
            if not ok:
                print(f"❌ [ORCA HARDWARE] Fallo al conectar: {msg}")
                return False
            self._sdk_abierto = True
            print("⚙️  [ORCA HARDWARE] Inicializando articulaciones...")
            self._hand.init_joints()

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

    def _leer_postura(self):
        """
        Postura REAL de la mano (rad, orden de motor), para que el primer movimiento
        salga de donde está la mano y no dé un salto. Prueba los nombres habituales
        del SDK; si ninguno funciona devuelve None y se parte del primer objetivo
        (como antes).
        """
        for nombre in ("get_joint_position", "get_joint_positions", "get_joint_pos"):
            f = getattr(self._hand, nombre, None)
            if not callable(f):
                continue
            try:
                r = f()
                if isinstance(r, dict):
                    grados = [r[j] for j in self._joints]
                else:
                    ids = list(getattr(self._hand, "joint_ids", []))
                    r = list(r)
                    if not ids or len(ids) != len(r):
                        continue
                    d = dict(zip(ids, r))
                    grados = [d[j] for j in self._joints]
                if any(g is None for g in grados):
                    continue
                q = np.radians(np.asarray(grados, dtype=float))
                if not np.all(np.isfinite(q)):
                    continue
                print(f"📍 [ORCA HARDWARE] Postura inicial leída con {nombre}() "
                      f"(muñeca {grados[0]:.0f}°, índice MCP {grados[2]:.0f}°): "
                      f"el primer movimiento saldrá de ahí, sin salto.")
                return q
            except Exception:
                continue
        print("ℹ️  [ORCA HARDWARE] No se pudo leer la postura inicial: el primer "
              "objetivo se enviará directamente (como antes).")
        return None

    # ─────────────────────────────────────────────────────────────────────────

    def _interpolado(self, t):
        """Punto del tramo actual (de _obj_ini a _obj_fin) en el instante t."""
        s = min(max((t - self._t_obj) / self._dur, 0.0), 1.0)
        return self._obj_ini + s * (self._obj_fin - self._obj_ini)

    def enviar_posiciones(self, array_radianes):
        """
        PUBLICA el objetivo (hardware_target[], orden de motor, radianes) y vuelve
        enseguida. Quien habla con los servos es el hilo de envío.
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
        """Manda el comando actual al SDK (grados). Devuelve lo que tardó (s)."""
        pose = {j: math.degrees(float(self._q[k])) for k, j in enumerate(self._joints)}
        t0 = time.perf_counter()
        with self.lock_sdk:
            self._hand.set_joint_positions(pose)      # el SDK clipea a ROMs y gestiona signos
        dur = time.perf_counter() - t0

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