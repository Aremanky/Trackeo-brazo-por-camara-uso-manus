#!/usr/bin/env python3
"""
Calibrador HSV — SKILL-SHIELD
==============================
Ejecuta este script por separado para encontrar los rangos HSV exactos
de tu objeto bajo la iluminación de tu laboratorio.

Uso:
    python3 calibrador_hsv.py

Ajusta los sliders hasta que la máscara muestre SOLO tu objeto en blanco.
Anota los valores H_bajo, H_alto, S_bajo, V_bajo y cópialos en
COLORES_HSV["platano"] dentro de skill_shield_demo.py.

Controles:
    'q' → salir
"""

import cv2
import numpy as np
import depthai as dai


def nada(x):
    pass


# ── Ventana de sliders ─────────────────────────────────────────────────────
cv2.namedWindow("Calibrador HSV")
cv2.resizeWindow("Calibrador HSV", 400, 200)
cv2.createTrackbar("H bajo",  "Calibrador HSV", 20,  179, nada)
cv2.createTrackbar("H alto",  "Calibrador HSV", 35,  179, nada)
cv2.createTrackbar("S bajo",  "Calibrador HSV", 80,  255, nada)
cv2.createTrackbar("S alto",  "Calibrador HSV", 255, 255, nada)
cv2.createTrackbar("V bajo",  "Calibrador HSV", 80,  255, nada)
cv2.createTrackbar("V alto",  "Calibrador HSV", 255, 255, nada)

# ── Configurar cámara Luxonis ──────────────────────────────────────────────
pipeline = dai.Pipeline()
cam = pipeline.create(dai.node.ColorCamera)
cam.setPreviewSize(300, 300)
cam.setInterleaved(False)
xout = pipeline.create(dai.node.XLinkOut)
xout.setStreamName("video")
cam.preview.link(xout.input)

print("🎨 Calibrador HSV iniciado.")
print("   Pon el objeto delante de la cámara y ajusta los sliders.")
print("   Objetivo: máscara completamente blanca sobre el objeto, negra en el resto.")
print("   Pulsa 'q' para salir y copiar los valores.")

with dai.Device(pipeline) as device:
    q = device.getOutputQueue("video", 1, False)

    while True:
        frame = q.get().getCvFrame()
        hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        h1 = cv2.getTrackbarPos("H bajo",  "Calibrador HSV")
        h2 = cv2.getTrackbarPos("H alto",  "Calibrador HSV")
        s1 = cv2.getTrackbarPos("S bajo",  "Calibrador HSV")
        s2 = cv2.getTrackbarPos("S alto",  "Calibrador HSV")
        v1 = cv2.getTrackbarPos("V bajo",  "Calibrador HSV")
        v2 = cv2.getTrackbarPos("V alto",  "Calibrador HSV")

        mascara   = cv2.inRange(hsv, np.array([h1, s1, v1]), np.array([h2, s2, v2]))
        resultado = cv2.bitwise_and(frame, frame, mask=mascara)

        # Mostrar valores actuales en el frame
        texto = f"H({h1}-{h2})  S({s1}-{s2})  V({v1}-{v2})"
        cv2.putText(frame, texto, (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        cv2.imshow("Original",        frame)
        cv2.imshow("Mascara",         mascara)
        cv2.imshow("Resultado",       resultado)
        cv2.imshow("Calibrador HSV",  np.zeros((10, 400, 3), dtype=np.uint8))

        print(f"\r  → COLORES_HSV[\"objeto\"] = (({h1},{s1},{v1}), ({h2},{s2},{v2}))   ",
              end="", flush=True)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            print(f"\n\n✅ Valores finales:")
            print(f'   COLORES_HSV["platano"] = (({h1}, {s1}, {v1}), ({h2}, {s2}, {v2}))')
            break

cv2.destroyAllWindows()
