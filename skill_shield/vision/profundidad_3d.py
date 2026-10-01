"""
Utilidades de percepción 3D (profundidad estéreo → puntos 3D → objetivo del brazo).

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import numpy as np

from config import *


# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE PERCEPCIÓN 3D
# ══════════════════════════════════════════════════════════════════════════════

def profundidad_en_pixel(depth_frame: np.ndarray, px: int, py: int, radio: int = 8):
    """Mediana de profundidad (metros) en un parche alrededor de (px, py)."""
    h, w = depth_frame.shape
    region  = depth_frame[max(0, py-radio):min(h, py+radio),
                          max(0, px-radio):min(w, px+radio)]
    validos = region[region > 0]
    return float(np.median(validos)) / 1000.0 if len(validos) else None


def pixel_a_3d(px: int, py: int, z_m: float,
               ancho: int = ANCHO_CAM, alto: int = ALTO_CAM, f_px: float = F_PX):
    """Proyección inversa: pixel + profundidad → coordenadas 3D métricas.
    El centro óptico se toma en el centro del fotograma (ancho/2, alto/2)."""
    cx = ancho / 2.0
    cy = alto  / 2.0
    return (px - cx) * z_m / f_px, (py - cy) * z_m / f_px, z_m

def mapear_muneca_a_objetivo_brazo(x_m, y_m, z_m, neutro_camara, punto_neutro_brazo=None):
    """
    Convierte la posición 3D de la muñeca (relativa a la cámara, en metros)
    en un punto objetivo 3D para el efector del brazo ARCTOS (frame base
    del robot). 'neutro_camara' es (x0,y0,z0) capturado al calibrar con [A].

    'punto_neutro_brazo' es el punto 3D (frame base del ARCTOS) del que parte
    el movimiento — normalmente la posición REAL del efector en el instante
    de la calibración con [A], para que el brazo empiece a moverse desde
    donde ya estaba en la simulación en vez de saltar a un punto fijo. Si no
    se pasa (None), se usa ARM_OBJETIVO_NEUTRO de config.py como antes.
    """
    delta_cam = {
        "x": x_m - neutro_camara[0],
        "y": y_m - neutro_camara[1],
        "z": z_m - neutro_camara[2],
    }
    origen = punto_neutro_brazo if punto_neutro_brazo is not None else ARM_OBJETIVO_NEUTRO
    objetivo = list(origen)
    for i, eje_robot in enumerate(("robot_x", "robot_y", "robot_z")):
        eje_cam, signo = ARM_MAPEO_EJES[eje_robot]
        objetivo[i] += signo * delta_cam[eje_cam] * ARM_ESCALA_MOVIMIENTO[i]

    # Clip de seguridad: no salirse del radio máximo desde la base
    vec = np.array(objetivo)
    dist = np.linalg.norm(vec)
    if dist > ARM_RADIO_MAX:
        vec *= ARM_RADIO_MAX / dist
    vec[2] = max(vec[2], ARM_Z_MINIMA)
    return tuple(vec)
