"""
Comprueba si la profundidad de CADA OAK-D coincide con la realidad (y, de paso, el escalado).

Un sesgo de escala en la profundidad (p.ej. todo ~20 % más cerca de lo que es) explica a la vez
huesos del brazo demasiado cortos y una calibración entre cámaras con error enorme.

Uso:   python comprobar_profundidad.py --mxid-a 1944301001AAFA1700 --mxid-b 1944301081B5FA4800
  1. Pon una superficie plana y con textura (una caja, una pared con carteles, un cuaderno) justo en el
     centro del cuadro de la cámara, a una distancia que MIDES con un metro desde la lente: 1 m, 2 m, 3 m.
  2. Pulsa ESPACIO (con una ventana de cámara seleccionada): se imprime la profundidad que mide cada cámara (mediana de un parche central).
  3. Compara con el metro. Un error > 3-4 % en distancias cortas indica un problema de calibración o de
     alineado; un error que CRECE con la distancia indica sesgo de escala.
Q = salir.
"""
import argparse
import time
from types import SimpleNamespace

import cv2
import numpy as np

from config import ANCHO_CAM, ALTO_CAM


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mxid-a"); ap.add_argument("--mxid-b")
    ap.add_argument("--radio", type=int, default=12, help="mitad del lado del parche central (px)")
    args = ap.parse_args()

    from calibrar_extrinseca import _abrir_las_dos, _ultimo
    cams = _abrir_las_dos(SimpleNamespace(metodo="cuerpo", mxid_a=args.mxid_a, mxid_b=args.mxid_b))
    for c in cams:
        print(f"  [{c['nombre']}] focal reportada por la cámara: {float(c['K'][0][0]):.1f} px")
    ult_c, ult_d = [None, None], [None, None]
    cx, cy, r = ANCHO_CAM // 2, ALTO_CAM // 2, args.radio
    n_fot = [0, 0]
    brillo = [0.0, 0.0]
    t_info = time.time()
    for c in cams:                                   # una ventana por cámara (nombres solo ASCII)
        cv2.namedWindow(f"Camara {c['nombre']}", cv2.WINDOW_AUTOSIZE)
    try:
        while True:
            med = [None, None]
            ok = [False, False]
            for i, c in enumerate(cams):
                nuevo_c = _ultimo(c["qc"], None)
                nuevo_d = _ultimo(c["qd"], None)
                if nuevo_c is not None:
                    ult_c[i] = nuevo_c; n_fot[i] += 1
                if nuevo_d is not None:
                    ult_d[i] = nuevo_d
                if ult_c[i] is None:
                    continue
                img = ult_c[i].getCvFrame()
                brillo[i] = float(img.mean())
                if ult_d[i] is not None:
                    parche = ult_d[i].getFrame()[cy - r:cy + r, cx - r:cx + r]
                    v = parche[parche > 0]
                    if len(v) > 0.3 * parche.size:
                        med[i] = float(np.median(v)) / 1000.0
                    ok[i] = True
                cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), (0, 255, 0), 2)
                cv2.putText(img, f"{c['nombre']}: " + (f"{med[i]:.3f} m" if med[i] else "sin dato"), (10, 28),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.imshow(f"Camara {c['nombre']}", img)
            if time.time() - t_info > 2.0:           # latido: así se ve si llegan fotogramas
                t_info = time.time()
                print(f"  [estado] A: {n_fot[0]} fotogramas, brillo medio {brillo[0]:.0f}"
                      f" | B: {n_fot[1]} fotogramas, brillo medio {brillo[1]:.0f}"
                      f"   (brillo ~0 = imagen negra; tapa/objetivo/exposicion)")
            k = cv2.waitKey(1) & 0xFF
            if k == ord('q'):
                break
            if k == ord(' '):
                print("  ESPACIO -> A: " + (f"{med[0]:.3f} m" if med[0] else "sin dato")
                      + "   B: " + (f"{med[1]:.3f} m" if med[1] else "sin dato")
                      + "   (compara con tu metro)")
    finally:
        cv2.destroyAllWindows()
        for c in cams:
            c["dev"].close()


if __name__ == "__main__":
    main()