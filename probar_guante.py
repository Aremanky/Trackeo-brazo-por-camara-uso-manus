#!/usr/bin/env python3
"""
Prueba del guante (simulado o MANUS) moviendo SOLO los dedos de la OrcaHand en MuJoCo.
No toca Skill_Shield_Nivel_6.py: sirve para ajustar MANUS_MAPEO con calma.

  python probar_guante.py              → usa FUENTE_GUANTE de config.py
  python probar_guante.py simulado
  python probar_guante.py manus

Teclas (con la ventana "Estado guante" o "Guante simulado" seleccionada):
  [0] abierta  [1] puño  [2] pinza índice   (solo guante simulado)
  [P] imprimir lectura del guante y ctrl de cada actuador
  [Q] salir
"""
import sys
import time

import cv2
import mujoco
import mujoco.viewer
import numpy as np

from config import *
from skill_shield.mano.guante_manus import CLAVES, GuanteSimulado, crear_guante
from skill_shield.mano.retargeting_manus import NOMBRES_CTRL, retarget_manus_a_ctrl


def imprimir(lectura, datos):
    print("\n── Lectura del guante (grados) ──")
    for i in range(0, len(CLAVES), 4):
        print("  " + "  ".join(f"{c:18s}{lectura[c]:7.1f}" for c in CLAVES[i:i + 4]))
    print("── ctrl de la mano (rad) ──")
    ctrl = datos.ctrl[OFFSET_MANO: OFFSET_MANO + N_ACT]
    for idx, (clave, signo, escala, offset) in MANUS_MAPEO.items():
        print(f"  [{idx:2d}] {NOMBRES_CTRL[idx]:12s} = {ctrl[idx]:6.3f}   ← {clave} "
              f"(signo {signo:+.0f}, escala {escala}, offset {offset})")


def main():
    fuente = sys.argv[1] if len(sys.argv) > 1 else None
    guante = crear_guante(fuente)
    if not guante.iniciar():
        print("❌ No se pudo iniciar el guante.")
        return

    modelo = mujoco.MjModel.from_xml_path(RUTA_XML)
    datos = mujoco.MjData(modelo)

    # Brazo en su postura de reposo (también en qpos, para que no "caiga" al arrancar)
    for i, nombre in enumerate(ARM_JOINTS):
        jid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, nombre)
        datos.qpos[modelo.jnt_qposadr[jid]] = POSICION_STANDBY_BRAZO[i]
        datos.ctrl[i] = POSICION_STANDBY_BRAZO[i]
    datos.ctrl[OFFSET_MANO: OFFSET_MANO + N_ACT] = POSICION_STANDBY
    mujoco.mj_forward(modelo, datos)

    estado = {}
    ts = float(modelo.opt.timestep)
    panel = np.zeros((90, 420, 3), np.uint8)

    with mujoco.viewer.launch_passive(modelo, datos) as visor:
        t_ant, deuda = time.perf_counter(), 0.0
        while visor.is_running():
            t0 = time.perf_counter()

            guante.actualizar()
            lectura = guante.ultima_lectura()
            if lectura is not None:
                estado = retarget_manus_a_ctrl(datos, lectura, estado)

            # Física al ritmo del reloj real
            ahora = time.perf_counter()
            deuda = min(deuda + (ahora - t_ant), 0.1)
            t_ant = ahora
            n = int(deuda / ts)
            for _ in range(n):
                mujoco.mj_step(modelo, datos)
            deuda -= n * ts
            visor.sync()

            # Panel de estado
            panel[:] = 0
            txt_estado = "RECIBIENDO" if lectura is not None else "SIN DATOS"
            color = (0, 255, 0) if lectura is not None else (0, 0, 255)
            cv2.putText(panel, f"{type(guante).__name__}: {txt_estado}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.putText(panel, f"{guante.lecturas_por_s:5.1f} lecturas/s   [P] imprimir  [Q] salir",
                        (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
            cv2.imshow("Estado guante", panel)

            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            elif k == ord("p") and lectura is not None:
                imprimir(lectura, datos)
            elif isinstance(guante, GuanteSimulado) and k in (ord("0"), ord("1"), ord("2")):
                guante.poner_pose({ord("0"): "abierta", ord("1"): "puno",
                                   ord("2"): "pinza_indice"}[k])

            espera = 1 / 60 - (time.perf_counter() - t0)
            if espera > 0:
                time.sleep(espera)

    guante.cerrar()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
