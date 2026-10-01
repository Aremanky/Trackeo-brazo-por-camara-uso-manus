"""
Paso 2 — modo híbrido: posición de la mano (estéreo) → punto objetivo → IK joint1..3.

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import numpy as np
import mujoco
import math

from config import *

from skill_shield.brazo.ik import OFFSET_LOCAL_MUNON, OFFSET_LOCAL_PALMA, OFFSET_LOCAL_PALMA_CENTRO
from skill_shield.brazo.ik_codo_muneca import _eje_codo_humano_torso
from skill_shield.brazo.angulos_humano import _unitario, angulos_humano_a_q_brazo


# ══════════════════════════════════════════════════════════════════════════════
# PASO 2 — HÍBRIDO: posición de la mano (estéreo) → punto objetivo → IK joint1..3
# ══════════════════════════════════════════════════════════════════════════════

def _punta_brazo_fk(modelo, datos, q3, qpos_idx3, j_hombro, b_mano):
    """Vector hombro (ancla de joint2) → mano_mount, en ejes del mundo, SI joint1..3
    valieran q3. Solo cinemática: la simulación queda exactamente como estaba."""
    guarda = [float(datos.qpos[i]) for i in qpos_idx3]
    for k, i in enumerate(qpos_idx3):
        datos.qpos[i] = q3[k]
    mujoco.mj_kinematics(modelo, datos)
    v = np.array(datos.xpos[b_mano] - datos.xanchor[j_hombro])
    for k, i in enumerate(qpos_idx3):
        datos.qpos[i] = guarda[k]
    mujoco.mj_kinematics(modelo, datos)
    return v


def preparar_hibrido(modelo, datos, qpos_idx_brazo):
    """Alcance del ARCTOS y sus ejes 'fuera / arriba / delante', sacados de TU tabla
    ARM_IMITACION (T-pose y brazo al frente) → mismos signos que la imitación."""
    j2 = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, "joint2")
    bm = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "mano_mount")
    q_fuera   = angulos_humano_a_q_brazo(math.pi / 2, math.pi / 2, 0.0)   # T-pose
    q_delante = angulos_humano_a_q_brazo(0.0,         math.pi / 2, 0.0)   # brazo al frente
    v_fuera   = _punta_brazo_fk(modelo, datos, q_fuera,   qpos_idx_brazo[:3], j2, bm)
    v_delante = _punta_brazo_fk(modelo, datos, q_delante, qpos_idx_brazo[:3], j2, bm)

    arriba  = np.array([0.0, 0.0, 1.0])
    delante = _unitario(v_delante - (v_delante @ arriba) * arriba)
    fuera   = v_fuera - (v_fuera @ arriba) * arriba
    fuera   = _unitario(fuera - (fuera @ delante) * delante)

    # PASO 3 — longitudes del brazo y antebrazo DEL ROBOT, índices y límites
    j3 = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, "joint3")
    mujoco.mj_kinematics(modelo, datos)
    p2, p3, pm = datos.xanchor[j2].copy(), datos.xanchor[j3].copy(), datos.xpos[bm].copy()
    ids = [mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, f"joint{k}") for k in (1, 2, 3)]
    lo = np.array([max(IMITAR_LIMITES[f"joint{k + 1}"][0], LIMITES_CTRL_BRAZO[k][0]) for k in range(3)])
    hi = np.array([min(IMITAR_LIMITES[f"joint{k + 1}"][1], LIMITES_CTRL_BRAZO[k][1]) for k in range(3)])
    # PASO 6 — eje del codo del ROBOT en su T-pose. Sirve para saber después si el
    # robot está en la configuración "girada" (base +180°, hombro hacia atrás):
    # ahí su mano queda volteada 180° y hay que compensar el giro de muñeca.
    _qi3 = qpos_idx_brazo[:3]
    _guarda = [float(datos.qpos[i]) for i in _qi3]
    for k, i in enumerate(_qi3):
        datos.qpos[i] = q_fuera[k]
    mujoco.mj_kinematics(modelo, datos)
    eje_codo_tpose = np.array(datos.xaxis[j3])
    j6 = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, PRONO_JOINT)
    R_mano_tpose = np.array(datos.xmat[bm]).reshape(3, 3)       # orientación de la mano
    # Punto que persigue la IK: la PALMA de la OrcaHand (o el muñón, según config)
    _off_palma = OFFSET_LOCAL_PALMA_CENTRO if PALMA_CENTRO_REAL else OFFSET_LOCAL_PALMA
    off_punta = np.array(_off_palma if HIBRIDO_OBJETIVO == "palma" else OFFSET_LOCAL_MUNON,
                         dtype=float)
    alcance_punta = float(np.linalg.norm(datos.xpos[bm] + R_mano_tpose @ off_punta
                                         - datos.xanchor[j2]))
    # PASO 7.4 — codo → punto final (antebrazo + OrcaHand), fijo con joint4..6 quietos
    L_antebrazo_punta = float(np.linalg.norm(datos.xpos[bm] + R_mano_tpose @ off_punta
                                             - datos.xanchor[j3]))
    eje6_tpose   = np.array(datos.xaxis[j6])                     # eje del giro de muñeca
    for k, i in enumerate(_qi3):
        datos.qpos[i] = _guarda[k]
    mujoco.mj_kinematics(modelo, datos)
    _ejes = np.column_stack([fuera, arriba, delante])
    signo_codo = 1.0 if float((_ejes @ _eje_codo_humano_torso(math.pi / 2)) @ eje_codo_tpose) >= 0 else -1.0

    return {
        "off_punta":     off_punta,       # offset local (mano_mount) del punto final
        "alcance_punta": alcance_punta,   # hombro → punto final con el brazo recto (m)
        "L_antebrazo_punta": L_antebrazo_punta,   # codo → punto final (antebrazo + mano)
        "signo_codo":  signo_codo,
        "j6":          j6,
        "R_mano_tpose": R_mano_tpose,
        "eje6_tpose":  eje6_tpose,
        "j_hombro":    j2,
        "alcance":     float(np.linalg.norm(v_fuera)),
        "ejes":        np.column_stack([fuera, arriba, delante]),  # (fuera,arriba,delante) → mundo
        "j_codo":      j3,
        "b_codo":      int(modelo.jnt_bodyid[j3]),
        "b_mano":      bm,
        "L_brazo":     float(np.linalg.norm(p3 - p2)),
        "L_antebrazo": float(np.linalg.norm(pm - p3)),
        "qpos3":       np.array([modelo.jnt_qposadr[j] for j in ids], dtype=int),
        "dof3":        np.array([modelo.jnt_dofadr[j] for j in ids], dtype=int),
        "lo":          lo,
        "hi":          hi,
    }
