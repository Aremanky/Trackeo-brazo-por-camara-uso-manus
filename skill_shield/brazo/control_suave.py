"""
Paso 7 — brazo preciso y sin saltos (generador suave, filtros, modo fino).

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)

7-oct — RETRASO: FiltroSaltos ya no congela el brazo durante los movimientos rápidos.
Antes, cualquier movimiento a más de SALTO_VEL_MAX (1 m/s, muy por debajo de lo que
se mueve una mano normal) se tomaba como "error de medida" y el robot se quedaba
quieto hasta que el umbral crecía lo bastante (~1 s en un movimiento amplio). Ahora un
salto solo se descarta si NO se repite: si SALTO_CONFIRMAR fotogramas seguidos siguen
lejos de la última medida buena, es un movimiento real y se acepta.
"""
import numpy as np
import math

import config as _cfg
from config import *

from skill_shield.brazo.ik_codo_muneca import _suavizado_01
from skill_shield.brazo.angulos_humano import _unitario

SALTO_CONFIRMAR = int(getattr(_cfg, "SALTO_CONFIRMAR", 1))   # fotogramas de "pico" que se ignoran


# ══════════════════════════════════════════════════════════════════════════════
# PASO 7 — BRAZO PRECISO Y SIN SALTOS (para maniobrar con herramientas)
# ══════════════════════════════════════════════════════════════════════════════

class GeneradorSuave:
    """
    PASO 7.1 — COMANDO CONTINUO del brazo.

    La cámara da un objetivo nuevo solo 10-30 veces por segundo. Antes ese objetivo
    se escribía TAL CUAL en ctrl: el servo (kp=500) llegaba en ~60 ms y el brazo se
    PARABA hasta el siguiente fotograma → tirón, parada, tirón... ("escalera").

    Ahora el bucle principal solo PUBLICA el objetivo (enviar) y este generador,
    llamado ANTES DE CADA mj_step (500 veces/s, desde HiloFisica), mueve ctrl hacia él:
      1) reparte el salto entre dos fotogramas (interpolación lineal, SUAVE_INTERPOLAR)
      2) con velocidad y ACELERACIÓN limitadas, frenando a tiempo (sin pasarse)
    Es lo mismo que ya hace la demo [5] del taladro (escribe ctrl en cada paso de
    física), y por eso ella se ve suave.

    Solo gestiona los joints de 'indices' (joint1..3 y el del giro de muñeca). Si le
    llega un índice que no es suyo (p.ej. joint4/joint5), lo escribe directo en ctrl.

    OJO: SUAVE_VEL_MAX es un TOPE de velocidad. Si es menor que la velocidad a la que
    te mueves tú, el robot se queda atrás y el retraso crece con la amplitud del gesto
    (90° a 1,2 rad/s = 1,3 s). Debe estar por encima de tu velocidad normal.
    """

    def __init__(self, indices, v_max, a_max):
        self.idx    = [int(i) for i in indices]
        self._local = {i: k for k, i in enumerate(self.idx)}   # índice ctrl → posición
        self.v_max  = np.asarray(v_max, dtype=float)
        self.a_max  = np.asarray(a_max, dtype=float)
        self.factor = 1.0           # < 1 → más lento (modo fino)
        self.activo = False
        self.q = self.v = None

    def activar(self, datos):
        """Arranca desde el ctrl actual (sin saltos)."""
        n = len(self.idx)
        self.q       = np.array([float(datos.ctrl[i]) for i in self.idx])
        self.v       = np.zeros(n)
        self.obj_ini = self.q.copy()             # tramo de interpolación actual:
        self.obj_fin = self.q.copy()             #   de obj_ini a obj_fin en 'dur' s
        self.t_obj   = np.full(n, float(datos.time))
        self.dt_med  = np.full(n, 0.1)           # periodo medio entre objetivos (s)
        self.dur     = self.dt_med.copy()
        self.factor  = 1.0
        self.activo  = True

    def desactivar(self):
        self.activo = False

    def _interpolado(self, t):
        s = np.clip((t - self.t_obj) / self.dur, 0.0, 1.0)
        return self.obj_ini + s * (self.obj_fin - self.obj_ini)

    def enviar(self, datos, indices, valores):
        """Publica objetivos (índices de ctrl). Llamar con el candado de la física."""
        t = float(datos.time)
        interp = self._interpolado(t) if self.activo else None
        for i, v in zip(indices, valores):
            k = self._local.get(int(i)) if self.activo else None
            if k is None:
                datos.ctrl[int(i)] = float(v)          # no es suyo → directo
                continue
            dt = t - self.t_obj[k]
            if dt > 1e-4:                              # periodo real entre fotogramas
                dt = min(max(dt, 0.02), 0.2)
                self.dt_med[k] = 0.7 * self.dt_med[k] + 0.3 * dt
            # el tramo nuevo empieza donde está AHORA la interpolación → continuidad
            self.obj_ini[k] = interp[k]
            self.obj_fin[k] = float(v)
            self.t_obj[k]   = t
            self.dur[k]     = self.dt_med[k] if SUAVE_INTERPOLAR else 1e-6

    def paso(self, modelo, datos, dt):
        """Se llama ANTES de cada mj_step (hilo de física)."""
        if not self.activo:
            return
        obj  = self._interpolado(float(datos.time))
        e    = obj - self.q
        vmax = self.v_max * self.factor
        amax = self.a_max * self.factor
        ae   = np.abs(e)
        # velocidad máxima con la que aún se puede FRENAR a tiempo (perfil trapezoidal)
        v_des = np.sign(e) * np.minimum(np.minimum(vmax, np.sqrt(2.0 * amax * ae)), ae / dt)
        self.v += np.clip(v_des - self.v, -amax * dt, amax * dt)   # aceleración limitada
        self.q += self.v * dt
        for k, i in enumerate(self.idx):
            datos.ctrl[i] = self.q[k]


class FiltroSaltos:
    """
    PASO 7.2 — Rechaza PICOS de medida (un fotograma suelto imposible) antes del One Euro.

    Si el objetivo de la palma (o del codo) del robot salta más de
    SALTO_VEL_MAX · Δt + SALTO_MARGEN respecto a la última medida buena, puede ser:
      · un PICO (codo mal colocado, profundidad del fondo, cambio de fuente...): dura
        1 fotograma y al siguiente la medida VUELVE cerca de la buena → se ignora;
      · un MOVIMIENTO RÁPIDO real: al siguiente fotograma SIGUE lejos → se acepta.
    Coste: SALTO_CONFIRMAR fotogramas (~33 ms) de espera al iniciar un gesto rápido.

    Antes (hasta 7-oct) el umbral solo crecía con el tiempo, y como una mano normal
    se mueve a 2-5 m/s (bastante más que SALTO_VEL_MAX), el brazo se quedaba QUIETO
    hasta ~1 s en cada gesto amplio y luego saltaba: era la mitad del retraso.
    Va ANTES del One Euro: si no, el One Euro ve el pico, cree que te mueves rápido y
    deja de filtrar.
    """

    def __init__(self):
        self.reset()

    VEL_TOPE = 6.0                     # m/s: tope de la velocidad estimada (predicción)

    def reset(self):
        self.ref, self.t_ref = None, None
        self.vel = None                # velocidad de cada punto entre las 2 últimas medidas buenas
        self.seguidos = 0              # fotogramas seguidos lejos de lo esperado
        self.rechazados = 0            # total (para el diagnóstico)

    def _guardar(self, puntos, t):
        if self.ref is not None and t - self.t_ref > 1e-3:
            self.vel = []
            for p, r in zip(puntos, self.ref):
                v = (p - r) / (t - self.t_ref)
                n = float(np.linalg.norm(v))
                self.vel.append(v * (self.VEL_TOPE / n) if n > self.VEL_TOPE else v)
        self.ref, self.t_ref, self.seguidos = puntos, t, 0

    def aceptar(self, puntos, t) -> bool:
        puntos = [np.asarray(p, dtype=float) for p in puntos]
        if self.ref is None or SALTO_VEL_MAX <= 0:
            self._guardar(puntos, t)
            return True
        dt = t - self.t_ref
        # se compara con DONDE DEBERÍA ESTAR siguiendo el movimiento que ya llevaba
        # (si no, en un gesto rápido sostenido se tiraría un fotograma de cada dos)
        pred = [r + v * dt for r, v in zip(self.ref, self.vel)] if self.vel else self.ref
        limite = SALTO_VEL_MAX * dt + SALTO_MARGEN
        salto  = max(float(np.linalg.norm(p - q)) for p, q in zip(puntos, pred))
        if salto <= limite:
            self._guardar(puntos, t)
            return True
        self.seguidos += 1
        if self.seguidos > SALTO_CONFIRMAR:      # el "salto" se mantiene → es real
            self._guardar(puntos, t)
            return True
        self.rechazados += 1
        return False


class ZonaMuerta:
    """
    PASO 7.2 — Holgura: la salida solo se mueve cuando la entrada se aleja más de
    'radio', y entonces la ARRASTRA (no salta). Quita el temblor en reposo sin crear
    escalones al empezar a moverse.
    """

    def __init__(self, radio):
        self.radio = float(radio)
        self.y = None

    def reset(self):
        self.y = None

    def __call__(self, x):
        x = np.asarray(x, dtype=float)
        if self.y is None or self.radio <= 0.0:
            self.y = x.copy()
            return x.copy()
        d = x - self.y
        n = float(np.linalg.norm(d))
        if n > self.radio:
            self.y = self.y + d * (1.0 - self.radio / n)
        return self.y.copy()


class CanalFino:
    """
    PASO 7.3 — Modo FINO [F] y CONGELAR [C] para UNA magnitud (la palma 3D o el
    giro de muñeca):
      "normal"    → salida = tu valor (imitación). Al volver de fino/congelado, la
                    diferencia se reparte en FINO_SALIDA_S segundos (sin salto).
      "fino"      → salida = ancla_robot + escala · (tu valor − ancla_tuya)
                    (1 cm tuyo = escala cm del robot, y el temblor igual de reducido)
      "congelado" → salida = la última (el robot no se mueve).
    Los cambios de modo se aplican con el SIGUIENTE valor que llegue: el ancla se
    toma de ese mismo fotograma, así el robot no se mueve al cambiar de modo.
    """

    def __init__(self, escala, angular: bool = False, vel_salida=None):
        self.escala  = float(escala)
        self.angular = angular            # True: ángulo (se desenrolla, cruza ±π sin saltar)
        self.vel_salida = vel_salida      # vel. máx. de la vuelta a normal (unidades/s)
        self.reset()

    def reset(self):
        self.modo = "normal"
        self.ultima = None
        self.ancla_h = self.ancla_r = None
        self.offset, self.t_off, self.dur_off = None, 0.0, FINO_SALIDA_S
        self._pendiente = None
        self._raw = self._cont = None     # desenrollado de ángulos

    def cambiar(self, modo: str):
        self._pendiente = modo

    def _dif(self, a, b):
        d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
        return (d + math.pi) % (2.0 * math.pi) - math.pi if self.angular else d

    def _desenrollar(self, a):
        """Ángulo → señal continua (sin el salto de +π a -π)."""
        if self._raw is None:
            self._raw, self._cont = a.copy(), a.copy()
        else:
            self._cont = self._cont + self._dif(a, self._raw)
            self._raw = a.copy()
        return self._cont.copy()

    def __call__(self, valor, t, limitar=None):
        valor = np.atleast_1d(np.asarray(valor, dtype=float))
        if self.angular:
            valor = self._desenrollar(valor)
        if self.ultima is None:
            self.ultima = valor.copy()
        if self._pendiente is not None:
            nuevo, self._pendiente = self._pendiente, None
            if nuevo == "fino" and self.modo != "fino":
                self.ancla_h, self.ancla_r = valor.copy(), self.ultima.copy()
            elif nuevo == "normal" and self.modo != "normal":
                self.offset, self.t_off = self._dif(self.ultima, valor), t
                dist = float(np.linalg.norm(self.offset))
                self.dur_off = max(FINO_SALIDA_S,
                                   dist / self.vel_salida if self.vel_salida else 0.0)
            if nuevo != "normal":
                self.offset = None
            self.modo = nuevo
        if self.modo == "congelado":
            salida = self.ultima.copy()
        elif self.modo == "fino":
            salida = self.ancla_r + self.escala * (valor - self.ancla_h)
        else:
            salida = valor.copy()
            if self.offset is not None:
                s = _suavizado_01(t - self.t_off, 0.0, self.dur_off)
                if s >= 1.0:
                    self.offset = None
                else:
                    salida = salida + (1.0 - s) * self.offset
        if limitar is not None:
            salida = np.atleast_1d(np.asarray(limitar(salida), dtype=float))
        self.ultima = salida.copy()
        return salida


def aplicar_modo_brazo(fino: bool, congelado: bool, canales, gen) -> str:
    """Pasa el modo (normal / fino / congelado) a los canales y al generador."""
    modo = "congelado" if congelado else ("fino" if fino else "normal")
    for c in canales:
        c.cambiar(modo)
    if gen is not None:
        gen.factor = FINO_FACTOR_VEL if fino else 1.0
    return modo


def fusionar_direccion(d_es, d_mp):
    """
    PASO 7.2 — Fusión estéreo/MediaPipe SIN interruptor. Antes: si las dos
    direcciones diferían más de FUSION_DIR_MAX_DEG se cambiaba de golpe de una a
    otra (salto de hasta ~30°). Ahora, en la franja FUSION_DIR_MAX_DEG ±
    FUSION_DIR_TRANSICION se mezclan poco a poco. Devuelve (dirección, peso estéreo).
    """
    ang = math.degrees(math.acos(float(np.clip(d_es @ d_mp, -1.0, 1.0))))
    lo = FUSION_DIR_MAX_DEG - FUSION_DIR_TRANSICION
    hi = FUSION_DIR_MAX_DEG + FUSION_DIR_TRANSICION
    w = 1.0 - _suavizado_01(ang, lo, hi) if hi > lo else float(ang <= FUSION_DIR_MAX_DEG)
    d = _unitario(w * np.asarray(d_es) + (1.0 - w) * np.asarray(d_mp))
    return (d if d is not None else np.asarray(d_mp)), w


def limitar_alcance_palma(datos, p, hib):
    """Mismo recorte que objetivos_codo_palma (alcance y altura mínima), para los
    objetivos que salen del modo fino."""
    hombro = np.array(datos.xanchor[hib["j_hombro"]])
    v = np.asarray(p, dtype=float) - hombro
    r, r_max = float(np.linalg.norm(v)), HIBRIDO_ALCANCE_MAX * hib["alcance_punta"]
    if r > r_max:
        v *= r_max / r
    out = hombro + v
    out[2] = max(out[2], ARM_Z_MINIMA)
    return out