"""
HUD: carga y dibujo del logo IDI / Grupo Elecnor (ventana OpenCV y visor MuJoCo).

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import cv2
import numpy as np
import mujoco
import mujoco.viewer


# ══════════════════════════════════════════════════════════════════════════════
# HUD — LOGO IDI / GRUPO ELECNOR
# ══════════════════════════════════════════════════════════════════════════════

def _cargar_logo(ruta: str, alto_px: int = 80):
    """
    Carga el logo (PNG/BGR/BGRA) y lo redimensiona manteniendo la proporción.

    Si la imagen no tiene canal alfa, genera una máscara automática descartando
    los píxeles de fondo oscuro (negros) como transparentes, de modo que solo
    se compone la parte visible del logotipo.

    Devuelve (bgr_uint8, alpha_float32[h,w,1])  ó  (None, None) si falla.
    """
    img = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"⚠  Logo IDI no encontrado en: {ruta}")
        return None, None

    # ── Forzar BGR/BGRA ──────────────────────────────────────────────────────
    if img.ndim == 2:                           # escala de grises
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # ── Redimensionar (mantener aspecto) ─────────────────────────────────────
    h, w = img.shape[:2]
    ancho_px = max(1, int(w * alto_px / h))
    img = cv2.resize(img, (ancho_px, alto_px), interpolation=cv2.INTER_AREA)

    # ── Extraer/generar canal alfa ────────────────────────────────────────────
    if img.shape[2] == 4:                       # BGRA → usar alfa nativo
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        bgr   = img[:, :, :3].copy()
    else:                                        # BGR sin alfa
        bgr = img.copy()
        # Máscara basada en luminosidad: píxeles oscuros (fondo negro) → alfa=0
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY)
        # Suavizado mínimo para bordes antialiasing
        mask  = cv2.GaussianBlur(mask, (3, 3), 0)
        alpha = mask[:, :, np.newaxis].astype(np.float32) / 255.0

    return bgr, alpha


def _superponer_logo(frame: np.ndarray,
                     logo_bgr,
                     logo_alpha,
                     margen: int = 10,
                     posicion: str = "top-left") -> np.ndarray:
    """
    Compone el logo en la esquina indicada de *frame* (operación in-place).

    Parámetros
    ----------
    frame      : imagen BGR uint8 sobre la que se dibuja.
    logo_bgr   : imagen BGR uint8 del logo (resultado de _cargar_logo).
    logo_alpha : máscara float32 [h,w,1] en [0,1] (resultado de _cargar_logo).
    margen     : píxeles de separación respecto al borde.
    posicion   : "top-left" | "top-right" | "bottom-left" | "bottom-right"

    Devuelve el mismo *frame* modificado.
    """
    if logo_bgr is None or frame is None:
        return frame

    fh, fw = frame.shape[:2]
    lh, lw = logo_bgr.shape[:2]

    # Calcular posición de la esquina superior izquierda del logo según posicion
    if posicion == "top-left":
        y0, x0 = margen, margen
    elif posicion == "top-right":
        y0, x0 = margen, fw - lw - margen
    elif posicion == "bottom-left":
        y0, x0 = fh - lh - margen, margen
    else:  # "bottom-right" (comportamiento original)
        y0, x0 = fh - lh - margen, fw - lw - margen

    # Verificar que el logo cabe en el frame
    if y0 < 0 or x0 < 0 or y0 + lh > fh or x0 + lw > fw:
        return frame

    roi   = frame[y0:y0 + lh, x0:x0 + lw].astype(np.float32)
    blend = roi * (1.0 - logo_alpha) + logo_bgr.astype(np.float32) * logo_alpha
    frame[y0:y0 + lh, x0:x0 + lw] = np.clip(blend, 0, 255).astype(np.uint8)
    return frame


def _preparar_logo_mujoco(ruta: str, alto_px: int = 80):
    """
    Prepara el logo en formato RGB aplanado para mjr_drawPixels.

    Genera un panel HUD oscuro (estilo MuJoCo nativo) con el logo centrado
    y padding uniforme.  El resultado se usa en _dibujar_logo_mujoco para
    mostrarlo como banda en el BORDE INFERIOR del visor.

    OpenGL tiene el origen en la esquina INFERIOR-izquierda, por lo que la
    imagen se voltea verticalmente antes de aplanarla.

    Devuelve (pixels_rgb_uint8_flat, panel_w, panel_h)
    o (None, 0, 0) si falla.
    """
    img = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None, 0, 0

    # ── Redimensionar manteniendo proporción ────────────────────────────────
    h, w = img.shape[:2]
    ancho_px = max(1, int(w * alto_px / h))
    img = cv2.resize(img, (ancho_px, alto_px), interpolation=cv2.INTER_AREA)

    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # ── Extraer canal alfa ───────────────────────────────────────────────────
    if img.shape[2] == 4:
        bgr   = img[:, :, :3]
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
    else:
        bgr = img
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 20, 255, cv2.THRESH_BINARY)
        mask  = cv2.GaussianBlur(mask, (3, 3), 0)
        alpha = mask[:, :, np.newaxis].astype(np.float32) / 255.0

    # ── Panel HUD oscuro con padding (misma estética que los HUDs nativos) ──
    pad_x, pad_y = 20, 10
    panel_w = ancho_px + 2 * pad_x
    panel_h = alto_px  + 2 * pad_y

    # Fondo gris muy oscuro con tinte azul IDI: BGR (40, 22, 10) ≈ #0A1628
    panel = np.full((panel_h, panel_w, 3), 0, dtype=np.uint8)
    panel[:] = (40, 22, 10)

    # Línea superior del panel (separador visual, color azul IDI)
    panel[0:2, :] = (139, 90, 10)    # BGR ≈ #0A5A8B

    # Componer logo con alpha-blending sobre el panel
    y0, x0 = pad_y, pad_x
    roi   = panel[y0:y0 + alto_px, x0:x0 + ancho_px].astype(np.float32)
    blend = roi * (1.0 - alpha) + bgr.astype(np.float32) * alpha
    panel[y0:y0 + alto_px, x0:x0 + ancho_px] = np.clip(blend, 0, 255).astype(np.uint8)

    # BGR → RGB + voltear verticalmente (origen OpenGL = abajo-izquierda)
    rgb      = cv2.cvtColor(panel, cv2.COLOR_BGR2RGB)
    rgb_flip = np.flipud(rgb)

    return rgb_flip.flatten().astype(np.uint8), panel_w, panel_h


def _dibujar_logo_mujoco(visor, logo_pixels, logo_w: int, logo_h: int,
                         margen: int = 0):
    """
    Dibuja el panel HUD del logo en el BORDE INFERIOR-CENTRAL del visor MuJoCo
    usando mjr_drawPixels.

    El panel se centra horizontalmente y se ancla al borde inferior de la
    ventana, emulando el comportamiento de los HUDs nativos de MuJoCo
    (ej. panel de controles de escena o panel de posición de rotores).

    Requiere MuJoCo ≥ 3.1 con acceso al contexto interno del visor pasivo.
    Si el contexto no está disponible (versiones antiguas o Wayland), la función
    falla silenciosamente sin interrumpir la simulación.

    Parámetros
    ----------
    visor       : handle del visor pasivo (mujoco.viewer.launch_passive).
    logo_pixels : array uint8 aplanado en RGB (resultado de _preparar_logo_mujoco).
    logo_w/h    : dimensiones del panel (incluyendo padding).
    margen      : separación al borde inferior en píxeles (0 = pegado al borde).
    """
    if logo_pixels is None or logo_w == 0:
        return
    try:
        # Intentar obtener el contexto de renderizado interno del visor.
        # El atributo _renderer existe en MuJoCo ≥ 3.1; en versiones anteriores
        # se lanza AttributeError y la función sale limpiamente.
        renderer = visor._renderer          # mujoco._render.Renderer (interno)
        ctx      = renderer._mjr_context    # mjrContext C-wrapper

        # Tamaño actual del framebuffer
        win_w = renderer.width
        win_h = renderer.height

        # ── Posición: centrado horizontal, anclado al borde inferior ─────────
        # En OpenGL, Y crece hacia ARRIBA → y=0 es el borde INFERIOR.
        # El panel ocupa [margen, margen + logo_h] en Y → borde inferior.
        x_gl = max(0, (win_w - logo_w) // 2)   # centrado horizontal
        y_gl = margen                            # pegado al borde inferior

        # Verificar que el panel cabe en el framebuffer
        if x_gl + logo_w > win_w or y_gl + logo_h > win_h:
            return

        viewport = mujoco.MjrRect(x_gl, y_gl, logo_w, logo_h)
        mujoco.mjr_drawPixels(logo_pixels, None, viewport, ctx)
    except Exception:
        # No hay contexto disponible → degradar silenciosamente
        pass
