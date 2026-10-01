"""
Paquete Skill Shield Nivel 6 — teleoperación OrcaHand + brazo ARCTOS.

El punto de entrada sigue siendo Skill_Shield_Nivel_6.py (raíz del proyecto).
"""
import os

# Igual que en el script original: debe fijarse ANTES de importar cv2. Aquí se
# garantiza aunque algún script importe directamente un módulo del paquete.
os.environ["QT_QPA_PLATFORM"] = "xcb"
