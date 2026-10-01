"""
Helpers de escena: pelota, soporte, destornillador y rotación de la mano.

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import mujoco
import math

from config import *


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UNIFICADOS (Pelota, Soporte, Destornillador y Rotación de Mano)
# ══════════════════════════════════════════════════════════════════════════════
OBJ_OCULTO = (0.0, 0.0, -10.0)

def euler_a_quat(euler):
    """Convierte ángulos (roll, pitch, yaw) a un cuaternión [w, x, y, z]"""
    cx = math.cos(euler[0] * 0.5); sx = math.sin(euler[0] * 0.5)
    cy = math.cos(euler[1] * 0.5); sy = math.sin(euler[1] * 0.5)
    cz = math.cos(euler[2] * 0.5); sz = math.sin(euler[2] * 0.5)
    return [cx*cy*cz + sx*sy*sz, sx*cy*cz - cx*sy*sz, cx*sy*cz + sx*cy*sz, cx*cy*sz - sx*sy*cz]

def _mover_mano(modelo, datos, pos, euler):
    """OBSOLETA desde la fusión con el brazo ARCTOS: teletransportaba un body
    mocap "right_mount" que ya no existe suelto (la mano cuelga ahora del
    extremo del brazo vía joint4/5/6, y su orientación la decide la IK de
    posición). Se deja definida por compatibilidad, pero ya no se llama desde
    las teclas de flecha — ver el bloque "FLECHAS DE DIRECCIÓN" más abajo. Si
    se necesita volver a controlar la orientación manualmente, rehacer como
    3 posturas fijas de joint4/5/6 en vez de un mocap."""
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "right_mount")
        mid = modelo.body_mocapid[bid]
        datos.mocap_pos[mid] = pos
        datos.mocap_quat[mid] = euler_a_quat(euler)
        mujoco.mj_forward(modelo, datos)
        print("✋ Orientación de la mano actualizada.")
    except Exception as exc:
        print(f"⚠ _mover_mano: {exc}")

def _spawn_objeto_dinamico(modelo, datos, nombre_joint, conf_dict):
    """Hace caer un objeto aplicando un offset y rotación específicos sobre la mano."""
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "right_mount")
        pos_mano = datos.xpos[bid]
        
        jnt_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, nombre_joint)
        qa = modelo.jnt_qposadr[jnt_id]
        da = modelo.jnt_dofadr[jnt_id]
        
        # Extraemos la posición y la orientación del diccionario
        offset = conf_dict.get("pos", (0.0, 0.0, 0.30))
        euler  = conf_dict.get("euler", (0.0, 0.0, 0.0))
        
        # Aplicamos el offset personalizado en X, Y, Z
        datos.qpos[qa]       = pos_mano[0] + offset[0]
        datos.qpos[qa + 1]   = pos_mano[1] + offset[1]
        datos.qpos[qa + 2]   = pos_mano[2] + offset[2]
        
        # Aplicamos la rotación (convirtiendo Euler a Cuaternión)
        datos.qpos[qa+3:qa+7] = euler_a_quat(euler)
        
        datos.qvel[da:da+6]   = 0.0
        mujoco.mj_forward(modelo, datos)
        return True
    except Exception as exc:
        return False

# Wrappers limpios: ahora solo reciben el bloque de configuración del objeto
def _spawn_pelota(modelo, datos, conf): return _spawn_objeto_dinamico(modelo, datos, "pelota_freejoint", conf)
def _ocultar_pelota(modelo, datos): return _ocultar_objeto(modelo, datos, "pelota_freejoint")
def _spawn_destornillador(modelo, datos, conf): return _spawn_objeto_dinamico(modelo, datos, "phillips_screwdriver_joint", conf)
def _ocultar_destornillador(modelo, datos): return _ocultar_objeto(modelo, datos, "phillips_screwdriver_joint")

def _ocultar_objeto(modelo, datos, nombre_joint):
    try:
        jnt_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, nombre_joint)
        qa = modelo.jnt_qposadr[jnt_id]
        da = modelo.jnt_dofadr[jnt_id]
        datos.qpos[qa:qa+3] = OBJ_OCULTO
        datos.qpos[qa+3:qa+7] = [1.0, 0.0, 0.0, 0.0]
        datos.qvel[da:da+6] = 0.0
        mujoco.mj_forward(modelo, datos)
        return True
    except Exception as exc:
        return False

# El soporte es mocap, así que se mueve diferente (lo fijamos cerca del centro global)
def _spawn_soporte(modelo, datos, conf, nombre_body="soporte_pelota"):
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body)
        mid = modelo.body_mocapid[bid]
        
        datos.mocap_pos[mid] = conf.get("pos", (0.09, -0.07, 0.10))
        datos.mocap_quat[mid] = euler_a_quat(conf.get("euler", (0.0, 0.0, 0.0)))
        
        mujoco.mj_forward(modelo, datos)
        return True
    except: return False

def _ocultar_soporte(modelo, datos, nombre_body="soporte_pelota"):
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body)
        mid = modelo.body_mocapid[bid]
        datos.mocap_pos[mid] = OBJ_OCULTO
        mujoco.mj_forward(modelo, datos)
        return True
    except: return False
