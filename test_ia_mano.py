import cv2
import mediapipe as mp
import depthai as dai
import numpy as np

# 1. Configurar MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# 2. Configurar Cámara Luxonis (Pipeline sencillo)
pipeline = dai.Pipeline()
cam = pipeline.create(dai.node.ColorCamera)
cam.setPreviewSize(640, 480) 
cam.setInterleaved(False)
xout = pipeline.create(dai.node.XLinkOut)
xout.setStreamName("video")
cam.preview.link(xout.input)

print("🖐️ Iniciando Detección de Mano IA (Nivel 4)...")

with dai.Device(pipeline) as device:
    q_video = device.getOutputQueue(name="video", maxSize=1, blocking=False)

    while True:
        frame_data = q_video.get()
        if frame_data is None: continue
        
        img = frame_data.getCvFrame()
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # 3. PROCESAR CON IA
        resultado = hands.process(img_rgb)

        if resultado.multi_hand_landmarks:
            for hand_landmarks in resultado.multi_hand_landmarks:
                # Dibujar esqueleto
                mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS)
                
                # Marcar la punta del índice (Punto 8)
                punto_8 = hand_landmarks.landmark[8]
                h, w, c = img.shape
                cx, cy = int(punto_8.x * w), int(punto_8.y * h)
                cv2.circle(img, (cx, cy), 10, (0, 255, 0), cv2.FILLED)

        cv2.imshow("Prueba Nivel 4: IA Hands", img)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cv2.destroyAllWindows()
