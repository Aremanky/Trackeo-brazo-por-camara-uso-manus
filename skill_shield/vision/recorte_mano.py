"""
Detección de la mano sobre un recorte de la imagen guiado por Pose.

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import cv2
import numpy as np

from config import *


# ══════════════════════════════════════════════════════════════════════════════
# DETECCIÓN DE LA MANO SOBRE UN RECORTE GUIADO POR POSE
# ══════════════════════════════════════════════════════════════════════════════

# Puntos de la mano en MediaPipe POSE: (muñeca, meñique, índice, pulgar, codo)
_PS_MANO = {"derecho": (16, 18, 20, 22, 14), "izquierdo": (15, 17, 19, 21, 13)}


def caja_recorte_mano(pose_lm, brazo: str, ancho: int, alto: int,
                      vis_min: float = 0.3):
    """
    Cuadrado (x0, y0, lado) en PÍXELES de una imagen de ancho×alto que contiene la
    mano del lado 'brazo', usando los puntos de mano de MediaPipe Pose.
    Devuelve None si Pose no ve esa muñeca.
    """
    lm = pose_lm.landmark
    i_m, i_me, i_in, _i_pu, i_co = _PS_MANO[brazo]
    if lm[i_m].visibility < vis_min:
        return None

    def px(i):
        return np.array([lm[i].x * ancho, lm[i].y * alto])

    w = px(i_m)
    nudillos = [px(i) for i in (i_me, i_in) if lm[i].visibility >= vis_min]
    if nudillos:
        k = np.mean(nudillos, axis=0)
        d = float(np.linalg.norm(k - w))
        centro = w + 0.6 * (k - w)          # el centro de la mano está pasados los nudillos
    else:
        # Sin nudillos: se prolonga el antebrazo (codo → muñeca)
        e = px(i_co)
        v = w - e
        d = 0.35 * float(np.linalg.norm(v))
        centro = w + 0.25 * v

    lado = max(MANO_RECORTE_FACTOR * d, MANO_RECORTE_MIN * alto)
    lado = int(min(lado, 0.6 * alto))    # tope: una mano nunca ocupa más del 60 % de la altura
    x0 = int(np.clip(centro[0] - lado / 2, 0, ancho - lado))
    y0 = int(np.clip(centro[1] - lado / 2, 0, alto - lado))
    return x0, y0, lado


def detectar_mano_en_recorte(detector, imagen_bgr, caja, tam: int = MANO_RECORTE_PX):
    """
    Ejecuta MediaPipe Hands sobre el recorte 'caja' de 'imagen_bgr' ampliado a tam×tam
    y devuelve el resultado con los landmarks NORMALIZADOS pasados a coordenadas de la
    imagen completa (0..1), como si Hands hubiera procesado la imagen entera.
    Los world landmarks (metros) no dependen del recorte y se dejan tal cual.
    Devuelve None si no encuentra mano en el recorte.
    """
    x0, y0, lado = caja
    alto, ancho = imagen_bgr.shape[:2]
    rec = imagen_bgr[y0:y0 + lado, x0:x0 + lado]
    if rec.shape[0] < 8 or rec.shape[1] < 8:
        return None
    rec = cv2.resize(rec, (tam, tam), interpolation=cv2.INTER_LINEAR)
    rec = cv2.cvtColor(rec, cv2.COLOR_BGR2RGB)
    rec.flags.writeable = False
    res = detector.process(rec)
    if not res.multi_hand_landmarks:
        return None
    for mano in res.multi_hand_landmarks:
        for l in mano.landmark:
            l.x = (x0 + l.x * lado) / ancho
            l.y = (y0 + l.y * lado) / alto
    return res
