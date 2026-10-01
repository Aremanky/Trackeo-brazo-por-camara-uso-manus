"""
IK del brazo ARCTOS (Jacobiana amortiguada) y conversión de landmarks a 3D.

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import numpy as np
import mujoco

from config import *


# ══════════════════════════════════════════════════════════════════════════════
# IK DEL BRAZO ARCTOS — Jacobiana amortiguada, resuelta por fotograma
# ══════════════════════════════════════════════════════════════════════════════
# Trasplantada tal cual de probar_ik_brazo.py (misma lógica, mismos parámetros
# por defecto) para que el brazo se mueva con la IK ya validada por separado.

# PASO 7.4 — centro REAL de la palma de la OrcaHand en el frame de "mano_mount", medido
# en orcahand_right_body.xml: punto medio entre la articulación de la muñeca (0, 0.092,
# 0.010) y el centro de los 4 nudillos (0.001, 0.181, 0.004). El OFFSET_LOCAL_PALMA de
# abajo caía ~3 cm más fuera, casi en los nudillos. Solo lo usa la IK de imitación
# (PALMA_CENTRO_REAL); el escenario del taladro sigue con el antiguo para no mover el techo.
OFFSET_LOCAL_PALMA_CENTRO = (0.0, 0.137, 0.007)
OFFSET_LOCAL_PALMA = (0.0, 0.165, 0.015)  # offset (frame local de "mano_mount")
                                           # hasta el centro aproximado de la palma —
                                           # se deja definido por si se quiere volver
                                           # a usar, pero el seguimiento por cámara
                                           # usa ahora OFFSET_LOCAL_MUNON (ver abajo).
OFFSET_LOCAL_MUNON = (0.0, 0.0, 0.0)      # sin offset: el propio origen de
                                           # "mano_mount" — la punta/muñón del
                                           # brazo, justo donde se atornilla la
                                           # mano. Es el punto que se calibra con
                                           # [A] y el que persigue la IK en el
                                           # seguimiento por cámara.


def resolver_ik_brazo(modelo, datos, objetivo_xyz, dof_idx, qpos_idx,
                       nombre_body_efector="mano_mount",
                       offset_local_efector=OFFSET_LOCAL_PALMA,
                       n_iter=8, lambda_amort=0.2, paso_max=0.08,
                       postura_referencia=None, ganancia_null=0.3,
                       q_inicial=None):
    """
    Varias mini-iteraciones de IK POR FOTOGRAMA (en vez de un único paso
    grande). Cada iteración recalcula la Jacobiana en la postura hipotética
    actual usando mj_kinematics (solo cinemática, sin física), así que
    converge de forma suave incluso cerca de singularidades.

    'offset_local_efector' es un desplazamiento (metros, frame LOCAL de
    'nombre_body_efector') desde el origen de ese body hasta el punto que
    realmente queremos llevar al objetivo — en este robot, el origen de
    "mano_mount" es solo la brida de montaje brazo↔mano; la palma real está
    desplazada hacia adelante.
    """
    body_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body_efector)
    offset_local = np.array(offset_local_efector)
    n  = len(qpos_idx)
    lo = np.array([l for l, _ in LIMITES_CTRL_BRAZO[:n]])
    hi = np.array([h for _, h in LIMITES_CTRL_BRAZO[:n]])

    q = (np.array(q_inicial, dtype=float) if q_inicial is not None
         else np.array([datos.qpos[qi] for qi in qpos_idx]))
    qpos_original = {qi: datos.qpos[qi] for qi in qpos_idx}   # para restaurar al final

    for _ in range(n_iter):
        for k, qi in enumerate(qpos_idx):
            datos.qpos[qi] = q[k]
        mujoco.mj_kinematics(modelo, datos)          # recoloca el esqueleto, sin simular física

        R_mano = datos.xmat[body_id].reshape(3, 3)
        punto_efector = datos.xpos[body_id] + R_mano @ offset_local

        error = np.array(objetivo_xyz) - punto_efector

        jacp = np.zeros((3, modelo.nv))
        mujoco.mj_jac(modelo, datos, jacp, None, punto_efector, body_id)
        J = jacp[:, dof_idx]

        JJt = J @ J.T
        J_pinv_amort = J.T @ np.linalg.inv(JJt + (lambda_amort ** 2) * np.eye(3))
        delta_q = J_pinv_amort @ error

        if postura_referencia is not None:
            N = np.eye(len(dof_idx)) - J_pinv_amort @ J
            delta_q = delta_q + N @ (ganancia_null * (postura_referencia - q))

        norma = np.linalg.norm(delta_q)
        if norma > paso_max:
            delta_q *= paso_max / norma

        q = np.clip(q + delta_q, lo, hi)

    # IMPORTANTE: restauramos el estado real de la simulación — solo hemos
    # usado qpos como "borrador" para calcular Jacobianas, no debe quedar el
    # brazo teletransportado a la solución antes de que el motor de física lo
    # mueva de verdad (vía datos.ctrl[]).
    for qi in qpos_idx:
        datos.qpos[qi] = qpos_original[qi]
    mujoco.mj_kinematics(modelo, datos)

    return q


def landmarks_a_3d(world_lm, es_mano_izq: bool = False):
    """
    Convierte world_landmarks de MediaPipe al frame de referencia de la mano
    (palma = plano XY, dedos apuntan en +Y) en metros.

    Usa sistema ortogonal definido por los MCP centrales (Gram-Schmidt),
    igual que en orca_retargeter/orca_teleop.
    """
    pts = [np.array([lm.x, lm.y, lm.z]) for lm in world_lm.landmark]
    rel = [p - pts[LM_MUNECA] for p in pts]

    adelante = rel[LM_CORAZON_MCP]
    lateral  = rel[LM_MENIQUE_MCP] - rel[LM_INDICE_MCP]

    n_ad, n_lat = np.linalg.norm(adelante), np.linalg.norm(lateral)
    if n_ad < 1e-6 or n_lat < 1e-6:
        return [(0.0, 0.0, 0.0)] * 21

    adelante = adelante / n_ad
    lateral  = lateral / n_lat
    lateral  = lateral - np.dot(lateral, adelante) * adelante  # Gram-Schmidt
    n_lat2   = np.linalg.norm(lateral)
    if n_lat2 < 1e-6:
        return [(0.0, 0.0, 0.0)] * 21
    lateral = lateral / n_lat2
    arriba  = np.cross(lateral, adelante)
    arriba  = arriba / np.linalg.norm(arriba)

    OFFSET_ADAPTADOR = 0.12  # metros — offset del adaptador físico en el robot
    result = []
    for p in rel:
        sign_lat = -1.0 if es_mano_izq else 1.0
        result.append((
            sign_lat * np.dot(p, lateral),
            np.dot(p, adelante) + OFFSET_ADAPTADOR,
            np.dot(p, arriba),
        ))
    return result
