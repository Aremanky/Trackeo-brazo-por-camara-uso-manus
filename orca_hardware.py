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
"""

import math
import os
import sys
import traceback

# ── Ruta al SDK de OrcaHand ───────────────────────────────────────────────────
_ORCA_CORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "orca_core-main")
if _ORCA_CORE_PATH not in sys.path:
    sys.path.insert(0, _ORCA_CORE_PATH)

_CONFIG_PATH = os.path.join(
    _ORCA_CORE_PATH, "orca_core", "models", "v2", "orcahand_right", "config.yaml"
)


class OrcaHardwareWrapper:
    """
    Recibe hardware_target[] (motor-indexado, radianes) y lo envía a OrcaHand.
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

    # Filtro exponencial de suavizado
    # El Skill_Shield ya aplica SuavizadorND, así que mantenemos alpha moderado
    ALPHA = 0.35

    # Debug de pulgar: True para imprimir valores cada DEBUG_CADA_N frames
    DEBUG_PULGAR = False
    DEBUG_CADA_N = 30

    def __init__(self, puerto="/dev/ttyUSB0", baudrate=1000000):
        self.puerto     = puerto
        self.baudrate   = baudrate
        self.conectado  = False
        self._hand      = None
        self._pose_prev = {}
        self._frame_n   = 0

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
            print("⚙️  [ORCA HARDWARE] Inicializando articulaciones...")
            self._hand.init_joints()
            self.conectado  = True
            self._pose_prev = {}
            self._frame_n   = 0
            print("✅ [ORCA HARDWARE] Mano física lista.")
            return True
        except ImportError as e:
            print(f"❌ [ORCA HARDWARE] orca_core no instalado: {e}")
            return False
        except Exception as e:
            print(f"❌ [ORCA HARDWARE] Error: {e}")
            traceback.print_exc()
            return False

    # ─────────────────────────────────────────────────────────────────────────

    def enviar_posiciones(self, array_radianes):
        """
        Recibe hardware_target[] (motor-indexed, radianes).
        1. Convierte cada valor de radianes a grados.
        2. Aplica filtro exponencial para suavizar.
        3. Envía a OrcaHand por nombre de joint.
        El SDK clipea a los ROMs y gestiona inversiones de motor.
        """
        if not self.conectado or self._hand is None:
            return False
        try:
            # 1. Radianes → grados, usando el mapeo motor-indexed correcto
            pose_raw = {
                joint: math.degrees(float(array_radianes[idx]))
                for idx, joint in self.MOTOR_A_JOINT.items()
                if idx < len(array_radianes)
            }

            # 2. Filtro exponencial (amortigua temblor residual)
            pose_suave = {}
            for joint, val in pose_raw.items():
                prev = self._pose_prev.get(joint, val)
                pose_suave[joint] = self.ALPHA * val + (1.0 - self.ALPHA) * prev
            self._pose_prev = pose_suave

            # 3. Debug del pulgar (activar con DEBUG_PULGAR = True)
            if self.DEBUG_PULGAR:
                self._frame_n += 1
                if self._frame_n % self.DEBUG_CADA_N == 0:
                    print(
                        f"[PULGAR] cmc={pose_suave.get('thumb_cmc', 0):6.1f}°  "
                        f"abd={pose_suave.get('thumb_abd', 0):6.1f}°  "
                        f"mcp={pose_suave.get('thumb_mcp', 0):6.1f}°  "
                        f"dip={pose_suave.get('thumb_dip', 0):6.1f}°"
                    )

            # 4. Enviar (SDK clipea a ROMs y gestiona signos de motor)
            self._hand.set_joint_positions(pose_suave)
            return True

        except Exception as e:
            print(f"⚠️  [ORCA HARDWARE] Error enviando posiciones: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────

    def desconectar(self):
        if self.conectado and self._hand is not None:
            try:
                print("🔌 [ORCA HARDWARE] Volviendo a posición neutral...")
                self._hand.set_neutral_position(num_steps=6, step_size=0.02)
                self._hand.stop_task()
                self._hand.disconnect()
                print("✅ [ORCA HARDWARE] Mano desconectada.")
            except Exception as e:
                print(f"⚠️  [ORCA HARDWARE] Error al desconectar: {e}")
            finally:
                self.conectado = False
