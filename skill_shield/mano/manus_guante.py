"""
Guantes MANUS → dedos de la OrcaHand (y vibración de vuelta al guante).

Sustituye a MediaPipe Hands SOLO para los 16 actuadores de los dedos (ctrl[1..16] de
la mano). La flexión de muñeca (ctrl[0]), el giro del antebrazo y el brazo siguen
saliendo de las cámaras: los ángulos "ergonomics" de MANUS no incluyen la muñeca.

Uso desde Skill_Shield_Nivel_6.py (FUENTE_DEDOS = "manus" en config.py):

    guante = GuanteManus()          # una sola vez al arrancar el programa
    guante.iniciar()                # no bloquea: conecta en un hilo propio
    ...
    guante.aplicar = True/False     # ¿manda el guante sobre los dedos? (cámara activa)
    guante.escribir_ctrl(datos, dt) # en el hilo de física, ANTES de cada mj_step
    guante.haptica(modelo, datos)   # en el bucle principal: contactos → vibración
    ...
    guante.cerrar()

Datos del SDK (MANUS Core 3.2.1, Python):
  · callback de ergonomics: por guante, 40 ángulos en GRADOS (0-19 mano izquierda,
    20-39 derecha) en el orden de ErgonomicsDataType:
        pulgar CMCSpread, CMCStretch, MCPStretch, IPStretch,
        índice/corazón/anular/meñique: MCPSpread, MCPStretch, PIPStretch, DIPStretch
  · callback de landscape: qué guante es cada mano (side) y si tiene háptica.
  · lib.CoreSdk_VibrateFingersForGlove(glove_id, float[5])  (pulgar → meñique, 0..1)

Correspondencia guante → OrcaHand: lineal por actuador, ctrl = Σ ganancia·ángulo + offset
(ángulos en rad). Los valores por defecto son un punto de partida; los buenos salen
de calibrar_manus.py (mano abierta, puño, dedos juntos/separados y tus 7 pinzas) y se
guardan en MANUS_CALIBRACION (JSON), que este módulo carga solo al arrancar.
"""
import json
import math
import os
import sys
import threading
import time

import numpy as np

import config as _cfg
from config import LIMITES_CTRL, N_ACT, OFFSET_MANO


def _p(nombre, defecto):
    return getattr(_cfg, nombre, defecto)


# ── Parámetros (config.py, bloque MANUS; si faltan, estos valores) ────────────
MANUS_MODO        = _p("MANUS_MODO", "local")          # "integrado" | "local" | "remoto"
MANUS_LADO        = _p("MANUS_LADO", "derecho")        # mano que se teleopera
MANUS_SDK_RUTA    = _p("MANUS_SDK_RUTA", os.path.join(
    os.path.dirname(os.path.abspath(_cfg.__file__)), "MANUS_Core_3.2.1_SDK_Linux", "Python"))
MANUS_CALIBRACION = _p("MANUS_CALIBRACION", os.path.join(
    os.path.dirname(os.path.abspath(_cfg.__file__)), "manus_calibracion.json"))
MANUS_TIMEOUT_S   = float(_p("MANUS_TIMEOUT_S", 0.3))  # sin datos más tiempo → dedos quietos
MANUS_TAU_S       = float(_p("MANUS_TAU_S", 0.025))    # suavizado (constante de tiempo)
MANUS_HAPTICA     = bool(_p("MANUS_HAPTICA", True))
MANUS_HAPTICA_HZ  = float(_p("MANUS_HAPTICA_HZ", 30.0))
MANUS_FUERZA_MIN  = float(_p("MANUS_FUERZA_MIN", 0.05))  # N: por debajo no vibra
MANUS_FUERZA_MAX  = float(_p("MANUS_FUERZA_MAX", 3.0))   # N: a partir de aquí vibra al 100 %
MANUS_VIBRACION_MAX = float(_p("MANUS_VIBRACION_MAX", 1.0))
# Flexión de los 4 dedos (MCP y PIP) DIRECTA desde la calibración de MANUS: el ángulo que
# mide el guante es el que se manda al robot (× la ganancia de cada actuador). La
# calibración propia (manus_calibracion.json) queda solo para abducciones y pulgar.
MANUS_FLEXION_DIRECTA  = bool(_p("MANUS_FLEXION_DIRECTA", True))
MANUS_GANANCIA_FLEXION = dict(_p("MANUS_GANANCIA_FLEXION", {}))

# ── Índices dentro de UNA mano (0..19), orden de ErgonomicsDataType ──────────
ERGO = {
    "THUMB_CMC_SPREAD": 0, "THUMB_CMC_STRETCH": 1, "THUMB_MCP": 2, "THUMB_IP": 3,
    "INDEX_SPREAD": 4,  "INDEX_MCP": 5,  "INDEX_PIP": 6,  "INDEX_DIP": 7,
    "MIDDLE_SPREAD": 8, "MIDDLE_MCP": 9, "MIDDLE_PIP": 10, "MIDDLE_DIP": 11,
    "RING_SPREAD": 12,  "RING_MCP": 13,  "RING_PIP": 14,  "RING_DIP": 15,
    "PINKY_SPREAD": 16, "PINKY_MCP": 17, "PINKY_PIP": 18, "PINKY_DIP": 19,
}

# ── Correspondencia por defecto: ctrl de la mano → (fuentes, ganancias, offset rad) ─
# ctrl[1]=p-abd ctrl[2]=p-mcp ctrl[3]=p-pip · ctrl[4..6] anular · ctrl[7..9] corazón
# ctrl[10..12] índice · ctrl[13]=t-cmc (oposición) ctrl[14]=t-abd ctrl[15]=t-mcp ctrl[16]=t-ip
# Flexiones 1:1. Los SIGNOS de las abducciones y todo el pulgar son una primera
# hipótesis: calibrar_manus.py los ajusta con tus poses (no hace falta tocarlos a mano).
MAPEO_DEFECTO = {
    1:  (["PINKY_SPREAD"],      [-1.0], 0.0),
    2:  (["PINKY_MCP"],         [1.0],  0.0),
    3:  (["PINKY_PIP"],         [1.0],  0.0),
    4:  (["RING_SPREAD"],       [-1.0], 0.0),
    5:  (["RING_MCP"],          [1.0],  0.0),
    6:  (["RING_PIP"],          [1.0],  0.0),
    7:  ([],                    [],     0.0),        # corazón ABD: fijo (como siempre)
    8:  (["MIDDLE_MCP"],        [1.0],  0.0),
    9:  (["MIDDLE_PIP"],        [1.0],  0.0),
    10: (["INDEX_SPREAD"],      [1.0],  0.0),
    11: (["INDEX_MCP"],         [1.0],  0.0),
    12: (["INDEX_PIP"],         [1.0],  0.0),
    13: (["THUMB_CMC_STRETCH"], [1.0], -0.10),
    14: (["THUMB_CMC_SPREAD"],  [1.0],  0.0),
    15: (["THUMB_MCP"],         [1.0],  0.0),
    16: (["THUMB_IP"],          [1.0],  0.0),
}

# Actuadores de FLEXIÓN de los 4 dedos (ctrl de la mano) → nombre en MANUS_GANANCIA_FLEXION
FLEXIONES = {2: "menique_mcp", 3: "menique_pip", 5: "anular_mcp", 6: "anular_pip",
             8: "corazon_mcp", 9: "corazon_pip", 11: "indice_mcp", 12: "indice_pip"}

# Yemas de la OrcaHand (mismos bodies que retargeting.py), en el orden del SDK:
# pulgar, índice, corazón, anular, meñique
_BODIES_YEMA = ("right_T-DP_b7429e50", "right_I-FingerTipAssembly_ec49c16c",
                "right_M-FingerTipAssembly_34afb748", "right_M-FingerTipAssembly_424a8e75",
                "right_P-FingerTipAssembly_cd219176")


def _importar_sdk():
    """manus_sdk instalado con pip o, si no, desde la carpeta del SDK (MANUS_SDK_RUTA)."""
    try:
        import manus_sdk  # noqa: F401
    except ImportError:
        if MANUS_SDK_RUTA and os.path.isdir(MANUS_SDK_RUTA) and MANUS_SDK_RUTA not in sys.path:
            sys.path.insert(0, MANUS_SDK_RUTA)
    from manus_sdk import lib, ffi, ManusSDK
    from manus_sdk.generated._enums import SDKReturnCode, AxisView, AxisPolarity, Side
    return lib, ffi, ManusSDK, SDKReturnCode, AxisView, AxisPolarity, Side


def cargar_mapeo(ruta=MANUS_CALIBRACION, verbose=True):
    """MAPEO_DEFECTO actualizado con lo calibrado (si existe el JSON)."""
    mapeo = {k: (list(f), list(g), float(o)) for k, (f, g, o) in MAPEO_DEFECTO.items()}
    if ruta and os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as fh:
                d = json.load(fh)
            for k, v in d.get("mapeo", {}).items():
                mapeo[int(k)] = (list(v["fuentes"]), [float(x) for x in v["ganancias"]],
                                 float(v["offset"]))
            if verbose:
                print(f"🧤 [MANUS] Calibración cargada: {os.path.basename(ruta)} "
                      f"({d.get('fecha', '?')})")
        except Exception as e:
            print(f"⚠️  [MANUS] No se pudo leer {ruta} ({e}): uso la correspondencia por defecto.")
    elif verbose:
        print("⚠️  [MANUS] Sin calibración (manus_calibracion.json): abducciones y pulgar con "
              "la correspondencia por defecto. Ejecuta  python calibrar_manus.py.")
    if MANUS_FLEXION_DIRECTA:
        # La flexión de los 4 dedos NO sale del JSON: ángulo de MANUS × ganancia, sin offset
        for k, nombre in FLEXIONES.items():
            fuente = MAPEO_DEFECTO[k][0]
            mapeo[k] = (list(fuente), [float(MANUS_GANANCIA_FLEXION.get(nombre, 1.0))], 0.0)
        if verbose:
            print("🧤 [MANUS] Flexión de los 4 dedos: DIRECTA desde la calibración de MANUS "
                  "(abducciones y pulgar: manus_calibracion.json).")
    return mapeo


def angulos_a_ctrl(ang_rad, mapeo):
    """20 ángulos de UNA mano (rad) → array N_ACT de ctrl de la mano (ctrl[0] = NaN:
    la muñeca no la da el guante). Recortado a LIMITES_CTRL."""
    out = np.full(N_ACT, np.nan)
    for k, (fuentes, ganancias, offset) in mapeo.items():
        v = offset + sum(g * ang_rad[ERGO[f]] for f, g in zip(fuentes, ganancias))
        lo, hi = LIMITES_CTRL[k]
        out[k] = min(max(v, lo), hi)
    return out


class GuanteManus:
    """Conexión con MANUS (hilo propio), últimos ángulos de la mano y vibración."""

    def __init__(self, modo=MANUS_MODO, lado=MANUS_LADO):
        self.modo = modo
        self.lado = lado
        self.aplicar = False             # el bucle principal decide si el guante manda
        self.conectado = False
        self.mapeo = cargar_mapeo()
        self._lock = threading.Lock()
        self._ang = None                 # 20 ángulos (grados) de nuestra mano
        self._t_ang = 0.0
        self._n_paquetes, self._t_hz, self.hz = 0, time.perf_counter(), 0.0
        self._guantes = {}               # glove_id → (side, isHaptics)
        self._id_guante = None           # glove_id de nuestra mano (para vibrar)
        self._ctrl_suave = None          # comando que se escribe en el hilo de física
        self._t_haptica = 0.0
        self._vibrando = False
        self._hilo = None
        self._activo = False
        self._sdk = None
        self.error = ""

    # ── ciclo de vida ────────────────────────────────────────────────────────
    def iniciar(self):
        """Inicializa el SDK y conecta en segundo plano. Devuelve False si el SDK no
        se puede cargar (el programa sigue con los dedos de la cámara)."""
        try:
            (self.lib, self.ffi, ManusSDK, self.RC,
             AxisView, AxisPolarity, Side) = _importar_sdk()
        except Exception as e:
            self.error = f"SDK de MANUS no disponible: {e}"
            print(f"❌ [MANUS] {self.error}")
            return False
        self._Side = Side
        lib, ffi = self.lib, self.ffi
        r = lib.CoreSdk_InitializeIntegrated() if self.modo == "integrado" \
            else lib.CoreSdk_InitializeCore()
        if r != self.RC.Success:
            self.error = f"no se pudo inicializar el SDK ({self.RC(r).name})"
            print(f"❌ [MANUS] {self.error}")
            return False
        cs = ffi.new("CoordinateSystemVUH*")
        cs.view, cs.up = AxisView.XFromViewer, AxisPolarity.PositiveZ
        cs.handedness, cs.unitScale = Side.Right, 1.0
        lib.CoreSdk_InitializeCoordinateSystemWithVUH(cs[0], True)
        self._sdk = ManusSDK()
        self._sdk.register_landscape_callback(self._cb_landscape)
        self._sdk.register_ergonomics_callback(self._cb_ergonomics)
        self._activo = True
        self._hilo = threading.Thread(target=self._conectar, name="MANUS-conexion", daemon=True)
        self._hilo.start()
        print(f"🧤 [MANUS] SDK listo (modo {self.modo}); conectando en segundo plano...")
        return True

    def _conectar(self):
        lib, ffi = self.lib, self.ffi
        loopback = self.modo == "local"
        espera = 1 if loopback else 3
        avisado = False
        while self._activo and not self.conectado:
            try:
                if lib.CoreSdk_LookForHosts(espera, loopback) == self.RC.Success:
                    n = ffi.new("uint32_t*")
                    if lib.CoreSdk_GetNumberOfAvailableHostsFound(n) == self.RC.Success and n[0] > 0:
                        hosts = ffi.new("ManusHost[]", n[0])
                        if lib.CoreSdk_GetAvailableHostsFound(hosts, n[0]) == self.RC.Success \
                                and lib.CoreSdk_ConnectToHost(hosts[0]) == self.RC.Success:
                            self.conectado = True
                            print("✅ [MANUS] Conectado: esperando datos del guante...")
                            return
            except Exception as e:
                self.error = str(e)
            if not avisado:
                print("⏳ [MANUS] Sin conexión todavía"
                      + (" (¿está abierto el MANUS Core Dashboard?)" if self.modo != "integrado"
                         else " (¿dongle enchufado y guante encendido?)") + ". Reintentando...")
                avisado = True
            time.sleep(1.0)

    def cerrar(self):
        self._activo = False
        if self._sdk is None:
            return
        try:
            self.vibrar([0.0] * 5)
            self.lib.CoreSdk_ShutDown()
        except Exception:
            pass
        self._sdk = None
        print("🧤 [MANUS] SDK cerrado.")

    # ── callbacks del SDK (hilo del SDK: copiar y salir, nada pesado) ─────────
    def _cb_landscape(self, landscape):
        try:
            g = landscape.gloveDevices
            guantes = {int(g.gloves[i].id): (int(g.gloves[i].side), bool(g.gloves[i].isHaptics))
                       for i in range(g.gloveCount)}
            lado = self._Side.Right if self.lado == "derecho" else self._Side.Left
            with self._lock:
                self._guantes = guantes
                self._id_guante = next((gid for gid, (s, _) in guantes.items() if s == lado), None)
        except Exception as e:
            self.error = f"landscape: {e}"

    def _cb_ergonomics(self, stream):
        try:
            base = 20 if self.lado == "derecho" else 0
            elegido = None
            with self._lock:
                id_nuestro = self._id_guante
            for i in range(stream.dataCount):
                d = stream.data[i]
                vals = [float(d.data[base + k]) for k in range(20)]
                if id_nuestro is not None and int(d.id) == id_nuestro:
                    elegido = vals
                    break
                if elegido is None and any(abs(v) > 1e-6 for v in vals):
                    elegido = vals                 # sin landscape aún: el que tenga datos
            if elegido is None:
                return
            ahora = time.perf_counter()
            with self._lock:
                self._ang, self._t_ang = elegido, ahora
                self._n_paquetes += 1
                if ahora - self._t_hz >= 1.0:
                    self.hz = self._n_paquetes / (ahora - self._t_hz)
                    self._n_paquetes, self._t_hz = 0, ahora
        except Exception as e:
            self.error = f"ergonomics: {e}"

    # ── lectura ──────────────────────────────────────────────────────────────
    def angulos(self):
        """(20 ángulos en GRADOS, antigüedad en s) de tu mano, o (None, inf)."""
        with self._lock:
            if self._ang is None:
                return None, float("inf")
            return list(self._ang), time.perf_counter() - self._t_ang

    def datos_frescos(self):
        _, edad = self.angulos()
        return edad <= MANUS_TIMEOUT_S

    def ctrl_objetivo(self):
        """ctrl de la mano (N_ACT, NaN en la muñeca) según el guante, o None."""
        ang, edad = self.angulos()
        if ang is None or edad > MANUS_TIMEOUT_S:
            return None
        return angulos_a_ctrl(np.radians(ang), self.mapeo)

    def estado_txt(self):
        if self._sdk is None:
            return "MANUS: sin SDK"
        if not self.conectado:
            return "MANUS: conectando..."
        if not self.datos_frescos():
            return "MANUS: SIN DATOS (¿guante encendido?)"
        return f"MANUS: OK {self.hz:3.0f} Hz" + ("" if self.aplicar else " (standby)")

    # ── escritura en la simulación (hilo de física, antes de cada mj_step) ────
    def escribir_ctrl(self, datos, dt):
        """Lleva ctrl[1..16] de la mano hacia el guante con un filtro de primer orden
        (MANUS_TAU_S). Sin datos frescos o con aplicar=False no toca nada."""
        if not self.aplicar:
            self._ctrl_suave = None
            return
        obj = self.ctrl_objetivo()
        if obj is None:
            return                                     # dedos quietos donde estén
        i0 = OFFSET_MANO
        if self._ctrl_suave is None:                   # arranque: desde donde está la mano
            self._ctrl_suave = np.array(datos.ctrl[i0:i0 + N_ACT], dtype=float)
        a = 1.0 - math.exp(-dt / MANUS_TAU_S) if MANUS_TAU_S > 0 else 1.0
        m = ~np.isnan(obj)                             # todo menos la muñeca
        self._ctrl_suave[m] += a * (obj[m] - self._ctrl_suave[m])
        datos.ctrl[i0 + 1:i0 + N_ACT] = self._ctrl_suave[1:]

    def restaurar_dedos(self, datos):
        """Vuelve a poner en ctrl[1..16] los dedos del guante. Se llama justo después
        de retarget_a_ctrl (cámara), que también los escribe: así la mano FÍSICA
        (construir_hardware_target) y la grabación de episodios leen los del guante."""
        if self.aplicar and self._ctrl_suave is not None:
            datos.ctrl[OFFSET_MANO + 1:OFFSET_MANO + N_ACT] = self._ctrl_suave[1:]

    # ── vibración ────────────────────────────────────────────────────────────
    def es_haptico(self):
        with self._lock:
            return self._id_guante is not None and self._guantes.get(self._id_guante, (0, False))[1]

    def vibrar(self, potencias):
        """potencias: 5 valores 0..1 (pulgar, índice, corazón, anular, meñique)."""
        with self._lock:
            gid = self._id_guante
        if self._sdk is None or not self.conectado or gid is None:
            return False
        p = self.ffi.new("float[5]")
        for i in range(5):
            p[i] = float(min(max(potencias[i], 0.0), 1.0))
        return self.lib.CoreSdk_VibrateFingersForGlove(gid, p) == self.RC.Success

    def haptica(self, modelo, datos):
        """Fuerza de contacto en cada yema de la OrcaHand (simulación) → vibración del
        dedo correspondiente. Llamar con el candado de la física (bucle principal)."""
        if not (MANUS_HAPTICA and self.aplicar and self.conectado and self.es_haptico()):
            if self._vibrando:
                self.vibrar([0.0] * 5)
                self._vibrando = False
            return
        ahora = time.perf_counter()
        if ahora - self._t_haptica < 1.0 / MANUS_HAPTICA_HZ:
            return
        self._t_haptica = ahora
        fuerzas = fuerzas_yemas(modelo, datos)
        rango = max(MANUS_FUERZA_MAX - MANUS_FUERZA_MIN, 1e-6)
        pot = [MANUS_VIBRACION_MAX * min(max((f - MANUS_FUERZA_MIN) / rango, 0.0), 1.0)
               for f in fuerzas]
        if any(pot) or self._vibrando:
            self.vibrar(pot)
            self._vibrando = any(pot)


_ids_yema = None


def fuerzas_yemas(modelo, datos):
    """Fuerza normal (N) de contacto sobre cada yema (pulgar → meñique)."""
    import mujoco
    global _ids_yema
    if _ids_yema is None:
        _ids_yema = [mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, n) for n in _BODIES_YEMA]
    f = [0.0] * 5
    f6 = np.zeros(6)
    for i in range(datos.ncon):
        c = datos.contact[i]
        b1, b2 = modelo.geom_bodyid[c.geom1], modelo.geom_bodyid[c.geom2]
        for k, b in enumerate(_ids_yema):
            if b >= 0 and (b1 == b or b2 == b) and b1 != b2:
                mujoco.mj_contactForce(modelo, datos, i, f6)
                f[k] += abs(float(f6[0]))
    return f