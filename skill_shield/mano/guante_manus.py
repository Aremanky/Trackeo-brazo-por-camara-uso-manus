"""
Guante MANUS → ángulos de los dedos (stream de ERGONOMÍA), en GRADOS.

Dos fuentes con la MISMA interfaz, para poder trabajar antes de tener el guante:
  · GuanteSimulado → barras deslizantes en una ventana OpenCV (sin hardware ni licencia).
  · GuanteManus    → SDK de Python de MANUS (modo integrado / local / remoto).

Interfaz común (lo único que usa el resto del proyecto):
  guante.iniciar()         -> True/False
  guante.actualizar()      -> llamar 1 vez por vuelta del bucle (el simulado lee sus barras)
  guante.ultima_lectura()  -> dict {clave: grados}, o None si no hay datos recientes
  guante.lecturas_por_s    -> lecturas recibidas por segundo (diagnóstico)
  guante.cerrar()

Claves de la lectura (20): "<dedo>_<articulación>"
  dedo:         thumb | index | middle | ring | pinky
  articulación: mcp_spread | mcp_stretch | pip_stretch | dip_stretch
  (Convención MANUS para el PULGAR: "mcp" = CMC anatómico, "pip" = MCP anatómico,
   "dip" = IP. Lo confirmaremos el miércoles con el guante puesto.)
"""
import threading
import time

try:
    import config as _cfg
except Exception:
    _cfg = None


def _param(nombre, defecto):
    return getattr(_cfg, nombre, defecto) if _cfg is not None else defecto


DEDOS  = ("thumb", "index", "middle", "ring", "pinky")
ARTICS = ("mcp_spread", "mcp_stretch", "pip_stretch", "dip_stretch")
CLAVES = tuple(f"{d}_{a}" for d in DEDOS for a in ARTICS)


# ══════════════════════════════════════════════════════════════════════════════
# BASE COMÚN — guarda la última lectura de forma segura entre hilos
# ══════════════════════════════════════════════════════════════════════════════
class _GuanteBase:
    def __init__(self):
        self._lock = threading.Lock()
        self._lectura = None
        self._t_lectura = 0.0
        self.lecturas_por_s = 0.0
        self._n_med, self._t_med = 0, time.perf_counter()

    def _publicar(self, lectura: dict):
        """Guarda una lectura nueva. Puede llamarse desde un hilo del SDK."""
        ahora = time.perf_counter()
        with self._lock:
            self._lectura, self._t_lectura = lectura, ahora
            self._n_med += 1
            if ahora - self._t_med >= 1.0:
                self.lecturas_por_s = self._n_med / (ahora - self._t_med)
                self._n_med, self._t_med = 0, ahora

    def ultima_lectura(self, max_edad=None):
        """Copia de la última lectura, o None si es más vieja que MANUS_TIMEOUT_S
        (guante apagado, fuera de alcance...). Con None la mano se queda quieta."""
        if max_edad is None:
            max_edad = _param("MANUS_TIMEOUT_S", 0.3)
        with self._lock:
            if self._lectura is None or time.perf_counter() - self._t_lectura > max_edad:
                return None
            return dict(self._lectura)

    def iniciar(self):    return True
    def actualizar(self): pass
    def cerrar(self):     pass


# ══════════════════════════════════════════════════════════════════════════════
# GUANTE SIMULADO — barras deslizantes (para trabajar hasta que llegue el real)
# ══════════════════════════════════════════════════════════════════════════════
class GuanteSimulado(_GuanteBase):
    VENTANA = "Guante simulado"
    RANGO = {                     # grados (mín, máx) de cada barra
        "mcp_spread":  (-40, 40),
        "mcp_stretch": (-20, 110),
        "pip_stretch": (-20, 110),
        "dip_stretch": (-20, 110),
    }
    POSES = {                     # poses rápidas con las teclas 0 / 1 / 2
        "abierta": {},
        "puno": {**{f"{d}_mcp_stretch": 80 for d in DEDOS[1:]},
                 **{f"{d}_pip_stretch": 95 for d in DEDOS[1:]},
                 **{f"{d}_dip_stretch": 60 for d in DEDOS[1:]},
                 "thumb_mcp_spread": 20, "thumb_mcp_stretch": 40,
                 "thumb_pip_stretch": 40, "thumb_dip_stretch": 40},
        "pinza_indice": {"index_mcp_stretch": 45, "index_pip_stretch": 60,
                         "index_dip_stretch": 30, "thumb_mcp_spread": 25,
                         "thumb_mcp_stretch": 35, "thumb_pip_stretch": 25,
                         "thumb_dip_stretch": 30},
    }

    def _nombre_barra(self, clave):
        dedo, art = clave.split("_", 1)
        return f"{dedo[:2].upper()} {art}"

    def iniciar(self):
        import cv2
        import numpy as np
        self._cv2 = cv2
        cv2.namedWindow(self.VENTANA, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.VENTANA, 520, 760)
        ayuda = np.zeros((60, 520, 3), np.uint8)
        cv2.putText(ayuda, "[0] abierta  [1] puno  [2] pinza indice", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        cv2.putText(ayuda, "Valores en GRADOS (como el stream de ergonomia)", (10, 48),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        cv2.imshow(self.VENTANA, ayuda)
        for clave in CLAVES:
            lo, hi = self.RANGO[clave.split("_", 1)[1]]
            cv2.createTrackbar(self._nombre_barra(clave), self.VENTANA, -lo, hi - lo,
                               lambda _v: None)
        print("[GUANTE] Simulado listo (barras deslizantes).")
        return True

    def poner_pose(self, nombre):
        pose = self.POSES.get(nombre, {})
        for clave in CLAVES:
            lo, _hi = self.RANGO[clave.split("_", 1)[1]]
            self._cv2.setTrackbarPos(self._nombre_barra(clave), self.VENTANA,
                                     int(pose.get(clave, 0)) - lo)

    def actualizar(self):
        lectura = {}
        for clave in CLAVES:
            lo, _hi = self.RANGO[clave.split("_", 1)[1]]
            lectura[clave] = float(self._cv2.getTrackbarPos(
                self._nombre_barra(clave), self.VENTANA) + lo)
        self._publicar(lectura)

    def cerrar(self):
        try:
            self._cv2.destroyWindow(self.VENTANA)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# GUANTE MANUS REAL — SDK de Python
# ══════════════════════════════════════════════════════════════════════════════
# ⚠ VERIFICAR EL MIÉRCOLES (sin guante ni licencia no se puede probar):
#   (1) nombre del método para registrar el callback de ergonomía
#   (2) campos del stream de ergonomía (dataCount / data[i].data[k])
#   (3) nombres del enum ErgonomicsDataType (si no se encuentran, se usa un orden supuesto)
# Con MANUS_DEBUG = True se imprime todo lo necesario para corregirlo en minutos.
# La inicialización y la conexión copian el ejemplo oficial minimal_client.py.
class GuanteManus(_GuanteBase):
    def __init__(self, modo=None, lado=None):
        super().__init__()
        self.modo = (modo or _param("MANUS_MODO", "integrado")).lower()
        self.lado = (lado or _param("MANUS_LADO", "derecha")).lower()
        self.debug = _param("MANUS_DEBUG", True)
        self._indices = None
        self._sdk = None
        self._impreso_stream = False
        self._error_cb = False

    # ── Arranque ──────────────────────────────────────────────────────────────
    def iniciar(self):
        try:
            from manus_sdk import lib, ffi, ManusSDK
            from manus_sdk.generated import _enums as E
        except Exception as e:
            print(f"[MANUS] No se pudo importar manus_sdk ({e}).\n"
                  "        Instálalo en el venv: cd <SDK>/Python && pip install .")
            return False
        self._lib, self._ffi, self._E = lib, ffi, E
        self._indices = self._resolver_indices(E)

        # 1) Inicializar
        r = lib.CoreSdk_InitializeIntegrated() if self.modo == "integrado" \
            else lib.CoreSdk_InitializeCore()
        if r != E.SDKReturnCode.Success:
            print(f"[MANUS] Falló la inicialización ({self.modo}): {self._codigo(r)}")
            return False

        # 2) Callback de ergonomía  ⚠ (1)
        self._sdk = ManusSDK()
        registrar = getattr(self._sdk, "register_ergonomics_callback", None)
        if registrar is None:
            disponibles = [m for m in dir(self._sdk) if m.startswith("register")]
            print(f"[MANUS] No encuentro register_ergonomics_callback. Disponibles: {disponibles}")
            return False
        r = registrar(self._cb_ergonomia)
        if r != E.SDKReturnCode.Success:
            print(f"[MANUS] No se pudo registrar el callback de ergonomía: {self._codigo(r)}")
            return False

        # 3) Sistema de coordenadas (obligatorio antes de conectar)
        cs = ffi.new("CoordinateSystemVUH*")
        cs.view, cs.up = E.AxisView.XFromViewer, E.AxisPolarity.PositiveZ
        cs.handedness, cs.unitScale = E.Side.Right, 1.0
        r = lib.CoreSdk_InitializeCoordinateSystemWithVUH(cs[0], True)
        if r != E.SDKReturnCode.Success:
            print(f"[MANUS] Falló el sistema de coordenadas: {self._codigo(r)}")
            return False

        # 4) Conectar (con reintentos, como el ejemplo oficial)
        for intento in range(int(_param("MANUS_REINTENTOS", 10))):
            if self._conectar():
                print(f"[MANUS] Conectado (modo {self.modo}). Esperando datos del guante...")
                return True
            print(f"[MANUS] No conecta (intento {intento + 1}). Reintento en 1 s...")
            time.sleep(1.0)
        return False

    def _conectar(self):
        lib, ffi, E = self._lib, self._ffi, self._E
        solo_local = (self.modo == "local")
        espera = 3 if self.modo == "remoto" else 1
        if lib.CoreSdk_LookForHosts(espera, solo_local) != E.SDKReturnCode.Success:
            return False
        n = ffi.new("uint32_t*")
        if lib.CoreSdk_GetNumberOfAvailableHostsFound(n) != E.SDKReturnCode.Success or n[0] == 0:
            return False
        hosts = ffi.new("ManusHost[]", n[0])
        if lib.CoreSdk_GetAvailableHostsFound(hosts, n[0]) != E.SDKReturnCode.Success:
            return False
        if self.debug:
            for i in range(n[0]):
                print(f"[MANUS] Host {i}: {ffi.string(hosts[i].hostName).decode()} "
                      f"({ffi.string(hosts[i].ipAddress).decode()})")
        return lib.CoreSdk_ConnectToHost(hosts[0]) == E.SDKReturnCode.Success

    # ── Callback (se ejecuta en un HILO DEL SDK, no en el nuestro) ───────────
    def _cb_ergonomia(self, stream):
        try:
            n = int(stream.dataCount)                       # ⚠ (2)
            if self.debug and not self._impreso_stream:
                self._impreso_stream = True
                print(f"[MANUS] Primer stream de ergonomía: dataCount={n}, "
                      f"campos={[c for c in dir(stream) if not c.startswith('_')]}")
            for i in range(n):
                valores = stream.data[i].data               # ⚠ (2)
                # Se COPIA a floats de Python: la memoria C la reutiliza el SDK.
                lectura = {k: float(valores[idx]) for k, idx in self._indices.items()}
                # Un guante del otro lado deja estos campos a 0 exacto → se salta.
                if any(v != 0.0 for v in lectura.values()):
                    self._publicar(lectura)
                    return
        except Exception as e:
            if not self._error_cb:            # solo se imprime una vez
                self._error_cb = True
                print(f"[MANUS] Error leyendo el stream de ergonomía: {e!r}")

    # ── Qué posición del array corresponde a cada clave ──────────────────────
    def _resolver_indices(self, E):
        lado = "right" if self.lado.startswith("d") else "left"
        art_sdk = {"mcp_spread": "mcpspread", "mcp_stretch": "mcpstretch",
                   "pip_stretch": "pipstretch", "dip_stretch": "dipstretch"}
        tipo = getattr(E, "ErgonomicsDataType", None)       # ⚠ (3)
        if tipo is not None:
            try:
                miembros = {m.name.lower(): int(m.value) for m in tipo}
            except TypeError:
                miembros = {k.lower(): int(v) for k, v in vars(tipo).items()
                            if not k.startswith("_") and isinstance(v, int)}
            indices = {}
            for clave in CLAVES:
                dedo, art = clave.split("_", 1)
                buscado = f"{lado}finger{dedo}{art_sdk[art]}"
                encontrados = [v for nombre, v in miembros.items() if buscado in nombre]
                if len(encontrados) == 1:
                    indices[clave] = encontrados[0]
            if len(indices) == len(CLAVES):
                if self.debug:
                    print(f"[MANUS] Índices de ergonomía leídos del enum ({lado}).")
                return indices
            print(f"[MANUS] ⚠ Solo {len(indices)}/20 claves encontradas en ErgonomicsDataType. "
                  f"Miembros: {list(miembros)[:12]}... → se usa el orden supuesto.")
        # Orden SUPUESTO: por mano 5 dedos × 4 valores; izquierda 0-19, derecha 20-39
        base = 20 if lado == "right" else 0
        return {f"{d}_{a}": base + i * 4 + j
                for i, d in enumerate(DEDOS) for j, a in enumerate(ARTICS)}

    def _codigo(self, r):
        try:
            return self._E.SDKReturnCode(r).name
        except Exception:
            return str(r)

    def cerrar(self):
        apagar = getattr(getattr(self, "_lib", None), "CoreSdk_ShutDown", None)
        if apagar is not None:
            try:
                apagar()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════════
def crear_guante(fuente=None):
    """FUENTE_GUANTE de config.py: "simulado" | "manus"."""
    fuente = (fuente or _param("FUENTE_GUANTE", "simulado")).lower()
    return GuanteManus() if fuente == "manus" else GuanteSimulado()
