"""
Fusión de DOS cámaras OAK-D para medir el brazo humano (hombro, codo, muñeca).

Idea: cada cámara mide muy bien lo que es LATERAL a su eje óptico (posición en la
imagen) y mal lo que es PROFUNDIDAD (el error del estéreo crece con z²). Si las dos
cámaras miran al usuario desde ángulos distintos, la profundidad de una es el lateral
de la otra. Se fusionan los puntos 3D de cada articulación con una media ponderada por
la INCERTIDUMBRE ANISÓTROPA de cada medida (forma de información):

        P = (Σ Wi)⁻¹ · Σ Wi·Pi          Wi = Ri · diag(1/σl², 1/σl², 1/σz²) · Riᵀ

así, con el brazo apuntando a la cámara A (σz grande en A), manda la cámara B en ese
eje, y al revés, sin reglas "si/entonces" que salten de una a otra.

Convención de extrínsecos: p_A = R_ab · p_B + t_ab   (B → A). El marco común es el de A.

Todo lo que viene DESPUÉS (comprobación/reconstrucción del codo con los huesos,
ángulos en el marco del torso, IK, filtros...) no cambia: recibe los mismos puntos 3D
que antes, pero fusionados.
"""
import time
import numpy as np

import config as _cfg
from config import PS_HOMBRO_IZQ, PS_HOMBRO_DER, PS_CODO_IZQ, PS_CODO_DER, \
    PS_MUNECA_IZQ, PS_MUNECA_DER, POSE_VISIBILIDAD_MIN, ANCHO_CAM, ALTO_CAM, PROF_Z_MIN

from skill_shield.brazo.angulos_humano import (
    PuntosCamara, puntos_brazo_estereo, angulos_desde_puntos_3d,
)

# Parámetros (si no están en config.py se usan estos valores por defecto)
SIGMA_PIX    = float(getattr(_cfg, "FUSION_SIGMA_PIX", 4.0))     # error de MediaPipe en la imagen (px)
SIGMA_Z_K    = float(getattr(_cfg, "FUSION_SIGMA_Z_K", 0.006))   # σz = K·z² (m) → 2,4 cm a 2 m
K_FUENTE     = dict(getattr(_cfg, "FUSION_K_FUENTE",
                            {"E": 1.0, "E+": 1.6, "L": 3.0, "M": 6.0}))
GATE_CHI2    = float(getattr(_cfg, "FUSION_GATE_CHI2", 16.0))    # 3 grados de libertad, ≈ 99,9 %
LR_MARGEN_M  = float(getattr(_cfg, "FUSION_LR_MARGEN_M", 0.10))  # chequeo izq/der intercambiados
MEMORIA_S    = float(getattr(_cfg, "FUSION_MEMORIA_S", 0.5))     # cuánto vale el "último punto" para desempatar


def _ids_brazo(brazo: str):
    if brazo == "derecho":
        return PS_HOMBRO_DER, PS_CODO_DER, PS_MUNECA_DER, PS_HOMBRO_IZQ
    return PS_HOMBRO_IZQ, PS_CODO_IZQ, PS_MUNECA_IZQ, PS_HOMBRO_DER


class FusorBrazo:
    """Fusiona los PuntosCamara de la cámara A (principal) y la B (secundaria)."""

    def __init__(self, R_ab, t_ab, brazo: str = "derecho"):
        self.R = np.asarray(R_ab, dtype=float).reshape(3, 3)
        self.t = np.asarray(t_ab, dtype=float).reshape(3)
        self.brazo = brazo
        self.reiniciar()

    def reiniciar(self):
        self._prev = {}                 # {índice: (punto en marco A, instante)}
        self.resumen = "-"              # texto de diagnóstico del último fotograma
        self.n_fotogramas = 0
        self.n_conflictos = 0
        self.n_lr_cambiados = 0

    # ── incertidumbre de una medida ──────────────────────────────────────────
    @staticmethod
    def _covarianza_cam(p, vis, fuente, f_px):
        v  = max(float(vis), 0.2)
        z  = max(float(p[2]), PROF_Z_MIN)
        sz = SIGMA_Z_K * z * z * K_FUENTE.get(fuente, 2.0) / v     # profundidad: crece con z²
        sl = SIGMA_PIX * z / f_px / v                              # lateral: píxeles → metros
        return np.diag([sl * sl, sl * sl, sz * sz])

    def _a_marco_a(self, pc: PuntosCamara, es_b: bool):
        """{índice: (punto en marco A, covarianza en marco A)}"""
        R = self.R if es_b else np.eye(3)
        t = self.t if es_b else np.zeros(3)
        out = {}
        for i, p in pc.pts.items():
            S = self._covarianza_cam(p, pc.vis.get(i, 0.5), pc.fuente.get(i, "E"), pc.f_px)
            out[i] = (R @ p + t, R @ S @ R.T)
        return out

    # ── fusión ───────────────────────────────────────────────────────────────
    @staticmethod
    def _puntuacion_huesos(i, p, pts, longitudes, i_h, i_c, i_m):
        """Cuánto desentona el candidato 'p' con las longitudes de los huesos (m; 0 = encaja).
        Solo para codo y muñeca, y solo si ya hay huesos calibrados y el punto de apoyo fusionado."""
        if longitudes is None:
            return None
        L1, L2 = longitudes
        if i == i_c and i_h in pts:
            return abs(float(np.linalg.norm(p - pts[i_h])) - L1)
        if i == i_m:
            if i_c in pts:
                return abs(float(np.linalg.norm(p - pts[i_c])) - L2)
            if i_h in pts:
                return max(0.0, float(np.linalg.norm(p - pts[i_h])) - (L1 + L2))
        return None

    def fusionar(self, pc_a, pc_b, longitudes=None):
        """
        pc_a, pc_b: PuntosCamara o None. Devuelve (pts, fuente, vis, codo_mp) en el marco
        de A, o None si, tras fusionar, faltan hombro, muñeca u hombro opuesto.
        longitudes: (brazo, antebrazo) en m si ya están calibradas; se usan para decidir
        CUÁL de las dos cámaras tiene razón cuando discrepan en el codo o la muñeca.
        """
        i_h, i_c, i_m, i_h2 = _ids_brazo(self.brazo)
        ea = self._a_marco_a(pc_a, False) if pc_a is not None else {}
        eb = self._a_marco_a(pc_b, True)  if pc_b is not None else {}
        notas = []

        # Chequeo izquierda/derecha: en una vista de perfil MediaPipe puede intercambiar
        # los hombros. Si los de B coinciden mucho mejor con los de A al revés, B se ignora.
        if ea and eb and all(k in ea and k in eb for k in (i_h, i_h2)):
            d_dir = np.linalg.norm(ea[i_h][0] - eb[i_h][0]) + np.linalg.norm(ea[i_h2][0] - eb[i_h2][0])
            d_inv = np.linalg.norm(ea[i_h][0] - eb[i_h2][0]) + np.linalg.norm(ea[i_h2][0] - eb[i_h][0])
            if d_inv + LR_MARGEN_M < d_dir:
                eb = {}
                self.n_lr_cambiados += 1
                notas.append("B:izq/der")

        ahora = time.perf_counter()
        pts, fuente, vis = {}, {}, {}
        conflictos = []
        # Orden: hombros y caderas primero; luego codo y muñeca (sus conflictos se
        # resuelven con los huesos, que necesitan el hombro / el codo ya fusionados)
        orden = sorted(set(ea) | set(eb), key=lambda k: (k == i_c, k == i_m, k))
        for i in orden:
            if i in ea and i in eb:
                (pa, Sa), (pb, Sb) = ea[i], eb[i]
                d = pa - pb
                d2 = float(d @ np.linalg.solve(Sa + Sb, d))
                if d2 <= GATE_CHI2:
                    Wa, Wb = np.linalg.inv(Sa), np.linalg.inv(Sb)
                    pts[i] = np.linalg.solve(Wa + Wb, Wa @ pa + Wb @ pb)
                    fuente[i] = f"{pc_a.fuente[i]}+{pc_b.fuente[i]}"
                else:
                    # Las dos cámaras discrepan más de lo que permite su incertidumbre:
                    # una de las dos mide mal (fondo, oclusión). Se elige UNA, no se promedia.
                    conflictos.append(i)
                    sc_a = self._puntuacion_huesos(i, pa, pts, longitudes, i_h, i_c, i_m)
                    sc_b = self._puntuacion_huesos(i, pb, pts, longitudes, i_h, i_c, i_m)
                    prev = self._prev.get(i)
                    if sc_a is not None and sc_b is not None and abs(sc_a - sc_b) > 0.01:
                        usa_a = sc_a < sc_b            # 1) la que respeta la longitud de los huesos
                    elif prev is not None and ahora - prev[1] <= MEMORIA_S:
                        usa_a = np.linalg.norm(pa - prev[0]) <= np.linalg.norm(pb - prev[0])   # 2) continuidad
                    else:
                        usa_a = np.trace(Sa) <= np.trace(Sb)                                   # 3) menos incertidumbre
                    pts[i] = pa if usa_a else pb
                    fuente[i] = (pc_a.fuente[i] if usa_a else pc_b.fuente[i]) + ("!A" if usa_a else "!B")
                vis[i] = max(pc_a.vis.get(i, 0.0), pc_b.vis.get(i, 0.0))
            elif i in ea:
                pts[i], fuente[i], vis[i] = ea[i][0], pc_a.fuente[i], pc_a.vis.get(i, 0.0)
            else:
                pts[i], fuente[i], vis[i] = eb[i][0], pc_b.fuente[i], pc_b.vis.get(i, 0.0)

        self.n_fotogramas += 1
        if conflictos:
            self.n_conflictos += 1
            notas.append("conflicto:" + ",".join(str(c) for c in sorted(conflictos)))
        usadas = ("A" if ea else "") + ("B" if eb else "")
        self.resumen = "+".join(usadas) + (" " + " ".join(notas) if notas else "")

        if not all(k in pts for k in (i_h, i_m, i_h2)):
            return None
        for i, p in pts.items():
            self._prev[i] = (p, ahora)

        # Respaldo del codo (MediaPipe anclado): el de la cámara con más visibilidad
        codo_mp = None
        cands = []
        if pc_a is not None and pc_a.codo_mp is not None:
            cands.append((pc_a.vis.get(i_c, 0.0), pc_a.codo_mp))
        if pc_b is not None and pc_b.codo_mp is not None and eb:
            cands.append((pc_b.vis.get(i_c, 0.0), self.R @ pc_b.codo_mp + self.t))
        if cands:
            codo_mp = max(cands, key=lambda c: c[0])[1]
        return pts, fuente, vis, codo_mp


def calcular_angulos_brazo_multicamara(fusor: FusorBrazo, ent_a, ent_b,
                                       brazo: str = "derecho",
                                       estimador=None,
                                       vis_min: float = POSE_VISIBILIDAD_MIN,
                                       ancho: int = ANCHO_CAM, alto: int = ALTO_CAM):
    """
    Equivalente multicámara de calcular_angulos_brazo_estereo().

    ent_a / ent_b = (pose_landmarks, pose_world_landmarks, frame_depth, f_px) de cada
    cámara, o None si esa cámara no tiene fotograma o no ve el cuerpo.
    Devuelve el mismo dict de ángulos (con "camaras" = qué cámaras aportaron) o None;
    si es None, 'estimador.motivo_fallo' explica por qué.
    """
    i_h, i_c, i_m, _ = _ids_brazo(brazo)
    fallos_a, fallos_b = [], []
    pc_a = pc_b = None
    if ent_a is not None:
        lm, wlm, depth, f_px = ent_a
        pc_a = puntos_brazo_estereo(lm, depth, f_px, brazo, vis_min, ancho, alto,
                                    estimador, wlm, fallos_a, exigir_hombro_opuesto=True)
    if ent_b is not None:
        lm, wlm, depth, f_px = ent_b
        pc_b = puntos_brazo_estereo(lm, depth, f_px, brazo, vis_min, ancho, alto,
                                    estimador, wlm, fallos_b, exigir_hombro_opuesto=False)

    def motivo(extra=""):
        partes = []
        if ent_a is None:
            partes.append("A: sin fotograma/cuerpo")
        elif fallos_a:
            partes.append("A: " + "; ".join(fallos_a))
        if ent_b is None:
            partes.append("B: sin fotograma/cuerpo")
        elif fallos_b:
            partes.append("B: " + "; ".join(fallos_b))
        if extra:
            partes.append(extra)
        return " | ".join(partes) if partes else "puntos insuficientes"

    if pc_a is None and pc_b is None:
        if estimador is not None:
            estimador.motivo_fallo = motivo()
        return None
    fus = fusor.fusionar(pc_a, pc_b, estimador.longitudes if estimador is not None else None)
    if fus is None:
        if estimador is not None:
            estimador.motivo_fallo = motivo("tras fusionar faltan hombros/muñeca "
                                            "(el hombro opuesto solo lo da la cámara A)")
        return None
    pts, fuente, vis, codo_mp = fus
    fallos = []
    res = angulos_desde_puntos_3d(pts, fuente,
                                  (vis.get(i_h, 0.0), vis.get(i_c, 0.0), vis.get(i_m, 0.0)),
                                  codo_mp, estimador, brazo, vis_min, fallos)
    if res is None:
        if estimador is not None:
            estimador.motivo_fallo = motivo("; ".join(fallos))
        return None
    res["camaras"] = fusor.resumen
    return res
