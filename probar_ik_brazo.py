import os, time
import numpy as np
import mujoco, mujoco.viewer

_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_XML = os.path.join(_DIR, "arctos_description-main",
                         "arctos_urdf_description", "urdf", "arctos_mjcf.xml")

ARM_JOINTS = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6"]
LIMITES_CTRL_BRAZO = [
    (-3.14, 3.14),   # joint1 (base)
    (-2.5,  2.5),    # joint2 (hombro)
    (-2.5,  2.5),    # joint3 (codo)
    (-3.14, 3.14),   # joint4 (muñeca 1)
    (-3.14, 3.14),   # joint5 (muñeca 2)
    (-3.14, 3.14),   # joint6 (muñeca 3)
]


def resolver_ik_brazo(modelo, datos, objetivo_xyz, dof_idx, qpos_idx,
                       nombre_body_efector="mano_mount",
                       offset_local_efector=(0.0, 0.165, 0.015),
                       n_iter=8, lambda_amort=0.2, paso_max=0.08,
                       postura_referencia=None, ganancia_null=0.3):
    """
    Resuelve varias mini-iteraciones de IK POR FOTOGRAMA (en vez de un único
    paso grande). Cada iteración recalcula la Jacobiana en la postura
    hipotética actual usando mj_kinematics (solo cinemática, sin física),
    así que converge de forma suave incluso cerca de singularidades, sin
    necesitar saltos bruscos entre fotogramas.

    'offset_local_efector' es un desplazamiento (en metros, en el frame LOCAL
    de 'nombre_body_efector') desde el origen de ese body hasta el punto que
    realmente queremos llevar al objetivo. En este robot, el origen de
    "mano_mount" es solo la brida de montaje entre el brazo y la mano; la
    palma real está desplazada hacia adelante. El valor por defecto
    (0, 0.165, 0.015) es una aproximación al centro de la palma, calculada a
    partir de la cinemática fija de la OrcaHand (mano_mount -> ... ->
    right_R-Carpals). Ajusta estos números si ves que el punto no cae justo
    en el centro de la palma.
    """
    body_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body_efector)
    offset_local = np.array(offset_local_efector)
    lo = np.array([l for l, _ in LIMITES_CTRL_BRAZO])
    hi = np.array([h for _, h in LIMITES_CTRL_BRAZO])

    q = np.array([datos.qpos[qi] for qi in qpos_idx])
    qpos_original = {qi: datos.qpos[qi] for qi in qpos_idx}   # para restaurar al final

    for _ in range(n_iter):
        for k, qi in enumerate(qpos_idx):
            datos.qpos[qi] = q[k]
        mujoco.mj_kinematics(modelo, datos)          # recoloca el esqueleto, sin simular física

        # Punto real del efector = origen de mano_mount + offset local
        # rotado a coordenadas de mundo con la orientación actual del body.
        R_mano = datos.xmat[body_id].reshape(3, 3)
        punto_efector = datos.xpos[body_id] + R_mano @ offset_local

        error = np.array(objetivo_xyz) - punto_efector

        jacp = np.zeros((3, modelo.nv))
        # mj_jac (a diferencia de mj_jacBody) calcula la Jacobiana en un
        # punto arbitrario rígidamente unido al body, no solo en su origen.
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
    # usado qpos como "borrador" para calcular Jacobianas, no debe quedar
    # el brazo teletransportado a la solución antes de que el motor de
    # física lo mueva de verdad.
    for qi in qpos_idx:
        datos.qpos[qi] = qpos_original[qi]
    mujoco.mj_kinematics(modelo, datos)

    return q


def main():
    modelo = mujoco.MjModel.from_xml_path(RUTA_XML)
    datos  = mujoco.MjData(modelo)
    visor  = mujoco.viewer.launch_passive(modelo, datos)

    dof_idx  = [modelo.jnt_dofadr[mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, j)]
                for j in ARM_JOINTS]
    qpos_idx = [modelo.jnt_qposadr[mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, j)]
                for j in ARM_JOINTS]
    postura_referencia = np.array([datos.qpos[qi] for qi in qpos_idx])

    print("🎯 Moviendo el objetivo en un círculo de 5cm frente al robot, para probar la IK...")

    def dibujar_esfera(idx, pos, radio=0.015, color=(1.0, 0.0, 0.0, 1.0)):
        """Dibuja (o actualiza) una esfera en la posición 'pos' dentro de la
        escena de usuario del visor, en el slot 'idx'. No afecta a la
        física: es solo un marcador visual."""
        mujoco.mjv_initGeom(
            visor.user_scn.geoms[idx],
            type=mujoco.mjtGeom.mjGEOM_SPHERE,
            size=[radio, 0, 0],
            pos=np.array(pos, dtype=np.float64),
            mat=np.eye(3).flatten(),
            rgba=np.array(color, dtype=np.float32),
        )

    mano_mount_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "mano_mount")
    offset_local_palma = np.array([0.0, 0.165, 0.015])
    t0 = time.time()
    while visor.is_running():
        t = time.time() - t0
        objetivo = (0.30 + 0.1 * np.cos(t * 0.3), 0.1 * np.sin(t * 0.3), 0.30)

        q_deseado = resolver_ik_brazo(modelo, datos, objetivo, dof_idx, qpos_idx,
                               offset_local_efector=offset_local_palma,
                               n_iter=30,
                               postura_referencia=None,
                               ganancia_null=0.05)

        # Punto real de la palma con la pose ACTUAL (para dibujar y medir error)
        R_mano_actual = datos.xmat[mano_mount_id].reshape(3, 3)
        punto_palma_actual = datos.xpos[mano_mount_id] + R_mano_actual @ offset_local_palma

        visor.user_scn.ngeom = 2
        dibujar_esfera(0, objetivo, color=(1.0, 0.0, 0.0, 1.0))          # rojo = objetivo
        dibujar_esfera(1, punto_palma_actual, color=(0.0, 1.0, 0.0, 1.0))  # verde = palma real

        error_actual = np.linalg.norm(np.array(objetivo) - punto_palma_actual)
        if int(time.time() * 4) % 4 == 0:
            print(f"error={error_actual:.4f} m   q={np.round(q_deseado, 2)}")
        for k in range(6):
            datos.ctrl[k] = float(q_deseado[k])

        mujoco.mj_step(modelo, datos)
        visor.sync()
        time.sleep(0.002)

if __name__ == "__main__":
    main()