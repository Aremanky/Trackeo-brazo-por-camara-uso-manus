import os
import mujoco, mujoco.viewer, time

_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_XML_ARCTOS = os.path.join(_DIR,"arctos_description-main", "arctos_urdf_description", "urdf", "arctos_mjcf.xml")

modelo = mujoco.MjModel.from_xml_path(RUTA_XML_ARCTOS)
datos  = mujoco.MjData(modelo)
visor  = mujoco.viewer.launch_passive(modelo, datos) 

# (índice de ctrl, nombre del joint, etiqueta anatómica, ángulo objetivo en radianes)
SECUENCIA = [
    (0, "joint1", "Base / giro de hombro", 0.6),
    (1, "joint2", "Hombro (elevación)",     0.5),
    (2, "joint3", "Codo",                   0.6),
    (3, "joint4", "Muñeca 1 (roll)",        0.6),
    (4, "joint5", "Muñeca 2 (pitch)",       0.5),
    (5, "joint6", "Muñeca 3 (yaw)",         0.6),
]

SEGUNDOS_POR_JOINT = 3.0

for idx, nombre, etiqueta, objetivo in SECUENCIA:
    print(f"\n→ Moviendo {nombre}  [{etiqueta}]  a {objetivo} rad")
    datos.ctrl[idx] = objetivo
    t0 = time.time()
    while time.time() - t0 < SEGUNDOS_POR_JOINT and visor.is_running():
        mujoco.mj_step(modelo, datos)
        visor.sync()
        time.sleep(0.002)
    datos.ctrl[idx] = 0.0   # vuelve a cero antes del siguiente
    t0 = time.time()
    while time.time() - t0 < 1.0 and visor.is_running():
        mujoco.mj_step(modelo, datos)
        visor.sync()
        time.sleep(0.002)
    pos = datos.xpos[mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "Link_6_1")]
    print(f"   Posición de la muñeca (Link_6_1): x={pos[0]:.3f}  y={pos[1]:.3f}  z={pos[2]:.3f}")

print("\n✅ Recorrido completo. Cierra la ventana para terminar.")
while visor.is_running():
    mujoco.mj_step(modelo, datos)
    visor.sync()
    time.sleep(0.002)