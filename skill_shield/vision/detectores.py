"""
Detectores de MediaPipe (manos y cuerpo), creados UNA sola vez al importar.

Todos los módulos que los usan importan estas mismas instancias.

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import mediapipe as mp

from config import *


mp_hands  = mp.solutions.hands
mp_draw   = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

detector_mano = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.6,
)

# Detector de manos SOLO para el recorte alrededor de tu mano (ver MANO_RECORTE).
# Es una instancia aparte porque su "seguimiento" interno trabaja en coordenadas del
# recorte, que no son las de la imagen completa.
detector_mano_recorte = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# ── Detector de CUERPO (33 puntos: hombros, codos, muñecas, caderas, cara...) ──
# Se ejecuta EN PARALELO al de manos: Hands sigue encargándose de los dedos y
# Pose de esqueleto del cuerpo. De momento solo se dibuja (paso 1); en el paso
# siguiente se usarán sus puntos para calcular los ángulos del brazo.
mp_pose = mp.solutions.pose
detector_pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=POSE_COMPLEJIDAD,
    smooth_landmarks=True,
    min_detection_confidence=POSE_CONF_DETECCION,
    min_tracking_confidence=POSE_CONF_SEGUIMIENTO,
)
