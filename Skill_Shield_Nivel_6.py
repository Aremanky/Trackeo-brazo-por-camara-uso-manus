#!/usr/bin/env python3
"""
Teleoperación OrcaHand v2 (mano derecha) con OAK-D + MediaPipe → MuJoCo
=========================================================================
Sin dependencias de ROS 2. Todo el pipeline es Python puro.

Arquitectura:
  OAK-D (DepthAI) → MediaPipe (21 landmarks) → Retargeting → MuJoCo ctrl[]

Controles de teclado:
  [A]  Activar control por cámara
  [S]  Standby (devuelve todos los actuadores a 0)
  [G]  Toggle grabación — pide nombre de TAREA y guarda episodios en episodios/<tarea>/
  [E]  Entrenar SOLO la última tarea grabada (modelos/<tarea>.pth) — rápido
  [Shift+E]  Reentrenar TODAS las tareas grabadas (más lento, tras cambios grandes)
  [P]  Spawnear / ocultar pelota de gomaespuma en MuJoCo
  [I]  Modo IA real — muestra un menú para elegir qué TAREA reproducir
  [M]  Demo de maniobra autónoma con pinzas fijas + ruido (no usa la red)
  [3]  Mostrar / ocultar el ENTORNO DE TRABAJO (mesa con alicates, destornillador,
       bombilla y fusible — definido en mesa_trabajo.xml)
  [F]  Modo FINO del brazo: el robot se mueve FINO_ESCALA veces lo que te mueves tú
       (para maniobrar con herramientas). Otra vez [F] → vuelve a imitarte suavemente
  [C]  CONGELAR / descongelar el brazo (se queda quieto; la mano sigue funcionando)
  [Q]  Salir

Dependencias:
  pip install mujoco depthai mediapipe opencv-python numpy torch

Uso:
  Actualiza RUTA_XML con la ruta a tu scene_right.xml de orcahand_description.
  python teleop_orca_mujoco.py
"""
import os
import multiprocessing
os.environ["QT_QPA_PLATFORM"] = "xcb"
import cv2
import mediapipe as mp
import depthai as dai
import numpy as np
import mujoco
import mujoco.viewer
import csv
import math
import time
import threading
from contextlib import contextmanager, nullcontext
import torch
import torch.nn as nn
import torch.optim as optim
from collections import deque

# ══════════════════════════════════════════════════════════════════════════════
# IMPORTACIÓN DEL PANEL DE CONFIGURACIÓN GLOBAL (NIVEL 6)
# ══════════════════════════════════════════════════════════════════════════════
from config import *
from config import _UMBRAL_COMBO_ON, _UMBRAL_COMBO_OFF, _UMBRAL_COMBO2_ON, _UMBRAL_COMBO2_OFF, _UMBRAL_COMBO3_ON, _UMBRAL_COMBO3_OFF
from orca_hardware import OrcaHardwareWrapper

mp_hands  = mp.solutions.hands
mp_draw   = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

detector_mano = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.7,
    min_tracking_confidence=0.6,
)

# Detector de manos SOLO para el recorte alrededor de tu mano (ver MANO_RECORTE).
# Es una instancia aparte porque su "seguimiento" interno trabaja en coordenadas del
# recorte, que no son las de la imagen completa.
detector_mano_recorte = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
)

# ── Detector de CUERPO (33 puntos: hombros, codos, muñecas, caderas, cara...) ──
# Se ejecuta EN PARALELO al de manos: Hands sigue encargándose de los dedos y
# Pose de esqueleto del cuerpo. De momento solo se dibuja (paso 1); en el paso
# siguiente se usarán sus puntos para calcular los ángulos del brazo.
mp_pose = mp.solutions.pose
detector_pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=POSE_COMPLEJIDAD,
    smooth_landmarks=True,
    min_detection_confidence=POSE_CONF_DETECCION,
    min_tracking_confidence=POSE_CONF_SEGUIMIENTO,
)

# ══════════════════════════════════════════════════════════════════════════════
# CEREBRO IA  —  ACT (Action Chunking Transformer) simplificado, sin imágenes
# ══════════════════════════════════════════════════════════════════════════════
# Basado en la arquitectura de ACT (Zhao et al., "Learning Fine-Grained Bimanual
# Manipulation with Low-Cost Hardware") — la misma familia de algoritmo que usan
# proyectos como ALOHA. Dos piezas nuevas respecto a nuestro MLP anterior:
#
# 1. CVAE con variable latente de "estilo" (z): un pequeño Transformer codificador,
#    que SOLO se usa durante el entrenamiento, resume la secuencia de acciones real
#    de cada episodio en un vector z. El decodificador aprende a partir de z, así
#    que nunca tiene que "promediar" entre gestos distintos — cada uno se explica
#    por su propio z. En inferencia no hay demostración real disponible, así que
#    se usa z=0 (la media del prior).
# 2. Transformer en vez de MLP: el decodificador usa "action queries" aprendidas
#    (una por cada paso futuro del bloque) que atienden, vía cross-attention, al
#    historial de postura + z, y producen el bloque de acciones futuras de golpe.
#
# Entradas : historial de VENTANA_IA fotogramas de qpos (+ z durante entrenamiento)
# Salidas  : bloque de CHUNK_IA fotogramas futuros de ctrl

VENTANA_IA     = 8    # nº de fotogramas de historial que ve la red en cada predicción
CHUNK_IA       = 30   # nº de fotogramas futuros que la red predice de una vez (ACT
                       # suele usar bloques más largos que un MLP simple, ya que el
                       # "temporal ensembling" en inferencia se encarga de suavizar)
DIM_LATENTE    = 32    # tamaño del vector de estilo z
DIM_MODELO     = 128   # dimensión interna del Transformer
N_CABEZAS      = 4     # nº de cabezas de atención
N_CAPAS_ENC    = 4     # capas del Transformer codificador de estilo
N_CAPAS_CTX    = 4     # capas del Transformer que codifica el contexto (historial+z)
N_CAPAS_DEC    = 1     # capas del decoder de acciones — LeRobot (implementación de
                       # referencia de ACT) usa 1 aquí a propósito: la implementación
                       # original tenía un bug que hacía que solo la 1ª capa de un
                       # decoder de 7 se usara realmente, y así es como se validó y
                       # funcionó en la práctica — lo replicamos en vez de "arreglarlo"
BETA_KL        = 10.0  # peso del término KL en la pérdida (estándar en ACT: 10-20)

EPISODIOS_DIR  = "episodios"  # cada TAREA tiene su propia subcarpeta: episodios/<tarea>/
                               # y dentro, cada grabación [G]...[G] es un episodio_XXXX.csv
MODELOS_DIR    = "modelos"    # un modelo .pth entrenado por cada tarea: modelos/<tarea>.pth


def _nombre_seguro(texto: str) -> str:
    """Convierte un nombre de tarea escrito por el usuario en un nombre de carpeta/
    archivo seguro (sin espacios ni caracteres raros)."""
    limpio = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in texto.strip())
    return limpio.lower() or "tarea_sin_nombre"


def _listar_tareas_grabadas(episodios_dir: str = EPISODIOS_DIR):
    """Devuelve los nombres de las subcarpetas de tareas que tengan al menos 1 episodio."""
    if not os.path.isdir(episodios_dir):
        return []
    tareas = []
    for nombre in sorted(os.listdir(episodios_dir)):
        ruta = os.path.join(episodios_dir, nombre)
        if os.path.isdir(ruta) and _listar_episodios(ruta):
            tareas.append(nombre)
    return tareas


def _listar_modelos_entrenados(modelos_dir: str = MODELOS_DIR):
    """Devuelve los nombres de tarea (sin '.pth') que ya tienen un modelo entrenado."""
    if not os.path.isdir(modelos_dir):
        return []
    return sorted(f[:-4] for f in os.listdir(modelos_dir) if f.endswith(".pth"))

def calcular_pronosupinacion(hand_world_lm, antebrazo, eje_ref):
    """Giro del antebrazo (rad) alrededor de su eje, medido desde el EJE DEL CODO
    DEL ROBOT (horizontal, perpendicular al plano del brazo según el azimut).
    A diferencia de la versión anterior, funciona con el antebrazo vertical.
    None si no es fiable."""
    a = _unitario(antebrazo)
    if a is None or eje_ref is None:
        return None
    h = eje_ref - (eje_ref @ a) * a                    # eje del codo, ⟂ antebrazo
    if np.linalg.norm(h) < 0.4 * np.linalg.norm(eje_ref):
        return None                                    # antebrazo casi paralelo al eje del codo
    h = _unitario(h)
    lat = _lm_hand(hand_world_lm, LM_MENIQUE_MCP) - _lm_hand(hand_world_lm, LM_INDICE_MCP)
    lat_p = lat - (lat @ a) * a                        # proyección ⟂ antebrazo
    if np.linalg.norm(lat_p) < 0.5 * np.linalg.norm(lat):
        return None                                    # nudillos casi alineados con el antebrazo
    lat_p = _unitario(lat_p)
    return math.atan2(float(np.cross(h, lat_p) @ a), float(h @ lat_p))

class ACTModel(nn.Module):
    """CVAE + Transformer para clonación de conducta con variable latente de estilo."""

    def __init__(self, n_joints: int = N_ACT, ventana: int = VENTANA_IA,
                 chunk: int = CHUNK_IA, dim: int = DIM_MODELO,
                 n_heads: int = N_CABEZAS, n_capas_enc: int = N_CAPAS_ENC,
                 n_capas_ctx: int = N_CAPAS_CTX, n_capas_dec: int = N_CAPAS_DEC,
                 dim_z: int = DIM_LATENTE):
        super().__init__()
        self.ventana, self.chunk, self.dim_z = ventana, chunk, dim_z

        # — Embeddings de entrada —
        self.embed_qpos   = nn.Linear(n_joints, dim)
        self.embed_action = nn.Linear(n_joints, dim)
        self.cls_token     = nn.Parameter(torch.zeros(1, 1, dim))
        self.pos_embed_enc = nn.Parameter(torch.zeros(1, 2 + chunk, dim))  # CLS + qpos + chunk

        # — Codificador de estilo (solo se usa con demostración real, en training) —
        capa_enc = nn.TransformerEncoderLayer(
            d_model=dim, nhead=n_heads, dim_feedforward=dim * 4, batch_first=True)
        self.style_encoder = nn.TransformerEncoder(capa_enc, num_layers=n_capas_enc)
        self.to_mu_logvar  = nn.Linear(dim, dim_z * 2)

        # — Política: Transformer encoder (contexto) + decoder (action queries) —
        self.latent_proj    = nn.Linear(dim_z, dim)
        self.pos_embed_pol  = nn.Parameter(torch.zeros(1, ventana + 1, dim))
        capa_pol_enc = nn.TransformerEncoderLayer(
            d_model=dim, nhead=n_heads, dim_feedforward=dim * 4, batch_first=True)
        self.policy_encoder = nn.TransformerEncoder(capa_pol_enc, num_layers=n_capas_ctx)

        self.action_queries = nn.Parameter(torch.zeros(1, chunk, dim))
        capa_pol_dec = nn.TransformerDecoderLayer(
            d_model=dim, nhead=n_heads, dim_feedforward=dim * 4, batch_first=True)
        self.policy_decoder = nn.TransformerDecoder(capa_pol_dec, num_layers=n_capas_dec)

        self.cabeza_salida = nn.Linear(dim, n_joints)

    def _codificar_estilo(self, qpos_actual: torch.Tensor, action_chunk: torch.Tensor):
        b = action_chunk.shape[0]
        act_emb  = self.embed_action(action_chunk)                    # (B, chunk, dim)
        qpos_emb = self.embed_qpos(qpos_actual).unsqueeze(1)           # (B, 1, dim)
        cls = self.cls_token.expand(b, -1, -1)                        # (B, 1, dim)
        seq = torch.cat([cls, qpos_emb, act_emb], dim=1) + self.pos_embed_enc
        salida_enc = self.style_encoder(seq)
        mu, logvar = self.to_mu_logvar(salida_enc[:, 0]).chunk(2, dim=-1)
        return mu, logvar

    def _decodificar(self, qpos_hist: torch.Tensor, z: torch.Tensor):
        b = qpos_hist.shape[0]
        hist_emb = self.embed_qpos(qpos_hist)                         # (B, ventana, dim)
        z_emb    = self.latent_proj(z).unsqueeze(1)                   # (B, 1, dim)
        contexto = torch.cat([hist_emb, z_emb], dim=1) + self.pos_embed_pol
        memoria  = self.policy_encoder(contexto)
        queries  = self.action_queries.expand(b, -1, -1)
        salida_dec = self.policy_decoder(queries, memoria)
        return self.cabeza_salida(salida_dec)                         # (B, chunk, n_joints)

    def forward(self, qpos_hist: torch.Tensor, action_chunk: torch.Tensor = None):
        """Si se pasa action_chunk (entrenamiento): usa el codificador de estilo real.
        Si no (inferencia): usa z=0 (media del prior), sin necesitar demostración."""
        b = qpos_hist.shape[0]
        if action_chunk is not None:
            qpos_actual = qpos_hist[:, -1, :]   # postura más reciente del historial
            mu, logvar = self._codificar_estilo(qpos_actual, action_chunk)
            std = torch.exp(0.5 * logvar)
            z = mu + std * torch.randn_like(std)
        else:
            mu = logvar = None
            z = torch.zeros(b, self.dim_z, device=qpos_hist.device)
        prediccion = self._decodificar(qpos_hist, z)
        return prediccion, mu, logvar


def _listar_episodios(episodios_dir: str = EPISODIOS_DIR):
    if not os.path.isdir(episodios_dir):
        return []
    return sorted(
        os.path.join(episodios_dir, f)
        for f in os.listdir(episodios_dir)
        if f.startswith("episodio_") and f.endswith(".csv")
    )


def _siguiente_numero_episodio(episodios_dir: str = EPISODIOS_DIR) -> int:
    existentes = _listar_episodios(episodios_dir)
    if not existentes:
        return 1
    numeros = []
    for ruta in existentes:
        nombre = os.path.basename(ruta)
        try:
            numeros.append(int(nombre.replace("episodio_", "").replace(".csv", "")))
        except ValueError:
            continue
    return (max(numeros) + 1) if numeros else 1


def guardar_episodio(buffer_filas, episodios_dir: str = EPISODIOS_DIR) -> str | None:
    """Guarda un episodio grabado (lista de filas qpos+ctrl) como un CSV independiente.
    Devuelve la ruta guardada, o None si el buffer estaba vacío."""
    if not buffer_filas:
        return None
    os.makedirs(episodios_dir, exist_ok=True)
    numero = _siguiente_numero_episodio(episodios_dir)
    ruta = os.path.join(episodios_dir, f"episodio_{numero:04d}.csv")
    with open(ruta, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(buffer_filas)
    return ruta


def entrenar_ia(episodios_dir: str = EPISODIOS_DIR, archivo_pesos: str = ARCHIVO_PESOS) -> bool:
    """Entrena el modelo ACT (CVAE+Transformer) a partir de los episodios grabados."""
    rutas = _listar_episodios(episodios_dir)
    if not rutas:
        print(f"❌ No hay episodios grabados en '{episodios_dir}/'. Pulsa [G] primero.")
        return False

    print(f"\n🧠 ENTRENANDO ACT (CVAE + Transformer) con {len(rutas)} episodio(s)... "
          f"Por favor, espera.")

    minimo_filas = VENTANA_IA + CHUNK_IA
    x_data, y_data, episodio_id_data = [], [], []
    episodios_usados, episodios_cortos = 0, 0
    deltas_tiempo = []   # diferencias reales entre fotogramas consecutivos (s)

    for ruta in rutas:
        qpos_seq, ctrl_seq, tiempos = [], [], []
        with open(ruta, "r") as f:
            for row in csv.reader(f):
                # Formato nuevo: 17 qpos + 17 ctrl + 1 timestamp = 35
                # Formato viejo (episodios grabados antes de este cambio): 34
                if len(row) == 2 * N_ACT + 1:
                    vals = [float(v) for v in row]
                    qpos_seq.append(vals[:N_ACT])
                    ctrl_seq.append(vals[N_ACT:2 * N_ACT])
                    tiempos.append(vals[-1])
                elif len(row) == 2 * N_ACT:
                    vals = [float(v) for v in row]
                    qpos_seq.append(vals[:N_ACT])
                    ctrl_seq.append(vals[N_ACT:])
                else:
                    continue

        if len(qpos_seq) <= minimo_filas:
            episodios_cortos += 1
            continue
        episodios_usados += 1

        # — Ritmo real de grabación: diferencias entre timestamps consecutivos —
        if len(tiempos) >= 2:
            deltas_tiempo.extend(t2 - t1 for t1, t2 in zip(tiempos, tiempos[1:]))

        # Ventanas SOLO dentro de este episodio — nunca cruzan a otro episodio
                # Ventanas SOLO dentro de este episodio — nunca cruzan a otro episodio
        for i in range(VENTANA_IA, len(qpos_seq) - CHUNK_IA + 1):
            ventana = qpos_seq[i - VENTANA_IA:i]
            bloque  = ctrl_seq[i:i + CHUNK_IA]
            x_data.append(ventana)
            y_data.append(bloque)
            episodio_id_data.append(episodios_usados)  # id = nº de episodio válido, no de fila

    # Mediana en vez de media: robusta frente a algún salto puntual de la cámara
    DT_POR_DEFECTO = 1.0 / 15.0   # ~15 fps, si no hay timestamps (episodios viejos)
    if deltas_tiempo:
        dt_objetivo = float(np.median(deltas_tiempo))
        # Descartamos valores absurdos (p.ej. si hubo una pausa real en medio)
        if not (0.01 <= dt_objetivo <= 0.5):
            dt_objetivo = DT_POR_DEFECTO
    else:
        dt_objetivo = DT_POR_DEFECTO
    print(f"⏱  Ritmo real de grabación detectado: {dt_objetivo*1000:.1f} ms/fotograma "
          f"(~{1/dt_objetivo:.1f} fps)")

    if episodios_cortos:
        print(f"⚠️  {episodios_cortos} episodio(s) descartado(s) por ser más cortos "
              f"que el mínimo ({minimo_filas + 1} filas).")

    if not x_data:
        print("❌ Ningún episodio tiene suficientes fotogramas. Graba más datos.")
        return False

    x_arr = np.array(x_data, dtype=np.float32)                 # (N, ventana, n_joints)
    y_arr = np.array(y_data, dtype=np.float32)                 # (N, chunk, n_joints)

    UMBRAL_MUESTRAS_MINIMO = 300
    if len(x_arr) < UMBRAL_MUESTRAS_MINIMO:
        print(f"⚠️  AVISO: solo {len(x_arr)} muestras de entrenamiento de "
              f"{episodios_usados} episodio(s). Recomendado: más episodios / más "
              f"repeticiones por gesto. Continuando de todas formas...")

    # — Normalización por articulación (compartida en qpos y en ctrl) —
    mu_x, sigma_x = x_arr.mean(axis=(0, 1)), x_arr.std(axis=(0, 1)) + 1e-6
    mu_y, sigma_y = y_arr.mean(axis=(0, 1)), y_arr.std(axis=(0, 1)) + 1e-6
    x_norm = (x_arr - mu_x) / sigma_x
    y_norm = (y_arr - mu_y) / sigma_y

    n = len(x_norm)
    episodio_arr = np.array(episodio_id_data)
    ids_episodios = np.unique(episodio_arr)
    n_ep = len(ids_episodios)

    if n_ep > 1:
        ids_perm  = np.random.permutation(ids_episodios)
        n_val_ep  = max(1, int(n_ep * 0.2))
        ids_val   = set(ids_perm[:n_val_ep].tolist())
        idx_val   = np.where(np.isin(episodio_arr, list(ids_val)))[0]
        idx_train = np.where(~np.isin(episodio_arr, list(ids_val)))[0]
        print(f"📊 Split por episodio: {n_ep - n_val_ep} episodio(s) train, "
              f"{n_val_ep} episodio(s) val (de {n_ep} totales).")
    else:
        # Solo hay 1 episodio válido: no existe forma honesta de aislar la validación.
        print("⚠️  Solo hay 1 episodio con datos suficientes: la validación no es "
              "independiente (ventanas del mismo episodio en train y val). "
              "Grabad más episodios para una validación fiable.")
        idx = np.random.permutation(n)
        n_val = max(1, int(n * 0.2))
        idx_val, idx_train = idx[:n_val], idx[n_val:]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    modelo_ia   = ACTModel().to(device)
    optimizador = optim.Adam(modelo_ia.parameters(), lr=1e-4)

    x_train = torch.tensor(x_norm[idx_train], dtype=torch.float32, device=device)
    y_train = torch.tensor(y_norm[idx_train], dtype=torch.float32, device=device)
    x_val   = torch.tensor(x_norm[idx_val],   dtype=torch.float32, device=device)
    y_val   = torch.tensor(y_norm[idx_val],   dtype=torch.float32, device=device)

    MAX_EPOCAS    = 8000  # los Transformers necesitan bastantes más iteraciones que
                          # un MLP para converger — LeRobot recomienda del orden de
                          # ~100.000 pasos de entrenamiento para ACT en su casos de uso
    TAM_LOTE      = 64
    PACIENCIA     = 200   # mucho más margen que antes — un Transformer puede tardar
                          # bastante en "arrancar" antes de que la validación mejore
                          # de forma consistente
    RUIDO_ENTRADA = 0.08
    mejor_val, mejor_estado, sin_mejora = float("inf"), None, 0
    n_train = x_train.shape[0]

    def _perdida(pred, mu, logvar, objetivo):
        recon = nn.functional.mse_loss(pred, objetivo)
        kl = -0.5 * torch.mean(1 + logvar - mu.pow(2) - logvar.exp())
        return recon + BETA_KL * kl, recon, kl

    for epoch in range(MAX_EPOCAS):
        modelo_ia.train()
        perm = torch.randperm(n_train, device=device)
        for ini in range(0, n_train, TAM_LOTE):
            lote = perm[ini:ini + TAM_LOTE]
            x_ruidoso = x_train[lote] + RUIDO_ENTRADA * torch.randn_like(x_train[lote])
            optimizador.zero_grad()
            pred, mu, logvar = modelo_ia(x_ruidoso, y_train[lote])
            loss, _, _ = _perdida(pred, mu, logvar, y_train[lote])
            loss.backward()
            optimizador.step()

        modelo_ia.eval()
        with torch.no_grad():
            pred_val, mu_val, logvar_val = modelo_ia(x_val, y_val)
            val_loss, val_recon, val_kl = _perdida(pred_val, mu_val, logvar_val, y_val)
            val_loss = val_loss.item()

        if (epoch + 1) % 50 == 0:
            print(f"   Epoch [{epoch+1}/{MAX_EPOCAS}]  Val total={val_loss:.5f}  "
                  f"(recon={val_recon.item():.5f}  kl={val_kl.item():.5f})")

        if val_loss < mejor_val - 1e-5:
            mejor_val = val_loss
            mejor_estado = {k: v.clone() for k, v in modelo_ia.state_dict().items()}
            sin_mejora = 0
        else:
            sin_mejora += 1
            if sin_mejora >= PACIENCIA:
                print(f"   ⏹  Sin mejora en validación durante {PACIENCIA} epochs. "
                      f"Paramos en epoch {epoch+1}.")
                break

    if mejor_estado is not None:
        modelo_ia.load_state_dict(mejor_estado)

    torch.save({
        "state_dict": modelo_ia.state_dict(),
        "mu_x": mu_x, "sigma_x": sigma_x,
        "mu_y": mu_y, "sigma_y": sigma_y,
        "ventana": VENTANA_IA,
        "chunk": CHUNK_IA,
        "dt_objetivo": dt_objetivo,
    }, archivo_pesos)

    print(f"✅ ENTRENAMIENTO COMPLETADO (mejor Val={mejor_val:.5f}, "
          f"{episodios_usados} episodios, {len(x_arr)} muestras). "
          f"Pesos guardados en '{archivo_pesos}'.\n")
    return True


def entrenar_todas_las_tareas(episodios_dir: str = EPISODIOS_DIR,
                               modelos_dir: str = MODELOS_DIR):
    """Recorre cada subcarpeta de episodios/ (una por tarea) y entrena un modelo
    independiente para cada una, guardado en modelos/<tarea>.pth."""
    tareas = _listar_tareas_grabadas(episodios_dir)
    if not tareas:
        print(f"❌ No hay ninguna tarea grabada en '{episodios_dir}/'. Pulsa [G] primero.")
        return

    os.makedirs(modelos_dir, exist_ok=True)
    print(f"\n📋 Se van a entrenar {len(tareas)} tarea(s): {', '.join(tareas)}\n")

    for tarea in tareas:
        print(f"\n{'='*70}\n▶ Entrenando tarea: '{tarea}'\n{'='*70}")
        ruta_episodios = os.path.join(episodios_dir, tarea)
        ruta_pesos = os.path.join(modelos_dir, f"{tarea}.pth")
        entrenar_ia(ruta_episodios, ruta_pesos)

    print(f"\n🏁 Entrenamiento de todas las tareas completado. "
          f"Modelos disponibles en '{modelos_dir}/'.\n")


def cargar_ia(archivo_pesos: str = ARCHIVO_PESOS):
    """Carga pesos + estadísticas de normalización del modelo ACT. Devuelve un dict
    listo para inferencia, o None."""
    if not os.path.exists(archivo_pesos):
        print("❌ No hay IA entrenada.")
        return None
    try:
        chk = torch.load(archivo_pesos, map_location="cpu", weights_only=False)
        ventana = int(chk.get("ventana", VENTANA_IA))
        chunk   = int(chk.get("chunk", CHUNK_IA))
        dt_objetivo = float(chk.get("dt_objetivo", 1.0 / 15.0))
        modelo_ia = ACTModel(ventana=ventana, chunk=chunk)
        modelo_ia.load_state_dict(chk["state_dict"])
        modelo_ia.eval()
        print(f"✅ IA (ACT) cargada desde '{archivo_pesos}' "
              f"(ventana={ventana}, bloque={chunk}, ritmo={dt_objetivo*1000:.0f} ms/fotograma).")
        return {
            "modelo":  modelo_ia,
            "mu_x":    torch.as_tensor(chk["mu_x"],    dtype=torch.float32),
            "sigma_x": torch.as_tensor(chk["sigma_x"], dtype=torch.float32),
            "mu_y":    torch.as_tensor(chk["mu_y"],    dtype=torch.float32),
            "sigma_y": torch.as_tensor(chk["sigma_y"], dtype=torch.float32),
            "ventana": ventana,
            "chunk":   chunk,
            "dt_objetivo": dt_objetivo,
        }
    except Exception as e:
        print(f"❌ Error al cargar la IA: {e}")
        return None




# ══════════════════════════════════════════════════════════════════════════════
# SUAVIZADOR N-DoF  (filtro de media móvil)
# ══════════════════════════════════════════════════════════════════════════════

class SuavizadorND:
    """Filtro de media móvil (rolling average) para vectores de N dimensiones.
    
    Soporta cambio dinámico de ventana: en zona de puño se reduce a 1
    (sin suavizado) para que el cierre llegue al máximo sin dilución.
    """

    def __init__(self, n_dim: int, ventana: int = 4):
        self._ventana_base = ventana
        self._buf = deque(maxlen=ventana)
        self.n_dim = n_dim

    def set_ventana(self, nueva_ventana: int):
        """Cambia el tamaño de ventana en caliente sin perder el buffer."""
        nueva_ventana = max(1, nueva_ventana)
        if nueva_ventana != self._buf.maxlen:
            datos_actuales = list(self._buf)
            self._buf = deque(datos_actuales[-nueva_ventana:], maxlen=nueva_ventana)

    def actualizar(self, valores) -> np.ndarray:
        self._buf.append(np.asarray(valores, dtype=float))
        return np.mean(self._buf, axis=0)

    def reset(self):
        self._buf.clear()
        self._buf = deque(maxlen=self._ventana_base)


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


# ══════════════════════════════════════════════════════════════════════════════
# HARDWARE REAL — construcción del array de motores + límite de seguridad
# ══════════════════════════════════════════════════════════════════════════════

def construir_hardware_target(datos) -> list:
    """Convierte datos.ctrl[] (orden de actuadores MuJoCo) al orden ESTRICTO
    que espera OrcaHand (Motor 1 a 17). Misma lógica que ya usaba la
    teleoperación, factorizada aquí para reutilizarla también en Modo IA Real."""
    # ctrl_mano: vista sobre la porción de mano de datos.ctrl[], desplazada
    # OFFSET_MANO posiciones porque ahora el brazo ocupa los primeros índices.
    ctrl_mano = datos.ctrl[OFFSET_MANO: OFFSET_MANO + N_ACT]
    mu_pos = {
        "wrist":      float(ctrl_mano[0]),
        "pinky_abd":  float(ctrl_mano[1]),
        "pinky_mcp":  float(ctrl_mano[2]),
        "pinky_pip":  float(ctrl_mano[3]),
        "ring_abd":   float(ctrl_mano[4]),
        "ring_mcp":   float(ctrl_mano[5]),
        "ring_pip":   float(ctrl_mano[6]),
        "middle_abd": float(ctrl_mano[7]),
        "middle_mcp": float(ctrl_mano[8]),
        "middle_pip": float(ctrl_mano[9]),
        "index_abd":  float(ctrl_mano[10]),
        "index_mcp":  float(ctrl_mano[11]),
        "index_pip":  float(ctrl_mano[12]),
        "thumb_cmc":  float(ctrl_mano[13]),
        "thumb_abd":  float(ctrl_mano[14]),
        "thumb_mcp":  float(ctrl_mano[15]),
        "thumb_dip":  float(ctrl_mano[16]),
    }
    return [
        mu_pos["wrist"], mu_pos["index_pip"], mu_pos["index_mcp"], mu_pos["index_abd"],
        mu_pos["middle_abd"], mu_pos["ring_abd"], mu_pos["ring_mcp"], mu_pos["ring_pip"],
        mu_pos["middle_pip"], mu_pos["middle_mcp"], mu_pos["pinky_pip"], mu_pos["pinky_mcp"],
        mu_pos["pinky_abd"], mu_pos["thumb_abd"], mu_pos["thumb_mcp"], mu_pos["thumb_dip"],
        mu_pos["thumb_cmc"],
    ]


# Máximo cambio permitido por motor entre un envío y el siguiente al hardware
# REAL, en radianes. Pensado para el Modo IA Real: como la IA puede predecir
# saltos más bruscos que una teleoperación humana (que ya viene naturalmente
# suavizada por tu propio movimiento), esto evita tirones mecánicos si la red
# predice algo poco fiable. NO se aplica a la teleoperación manual (ya es segura
# por venir de un humano moviéndose a ritmo natural).
MAX_DELTA_HARDWARE_POR_PASO = 0.12  # rad (~7°) por paso de envío


def limitar_salto_hardware(objetivo: list, anterior: list,
                            max_delta: float = MAX_DELTA_HARDWARE_POR_PASO) -> list:
    """Recorta cada componente de 'objetivo' para que no se aleje de 'anterior'
    más de 'max_delta' radianes. Devuelve una nueva lista, ya limitada."""
    limitado = []
    for obj, ant in zip(objetivo, anterior):
        delta = obj - ant
        if delta > max_delta:
            obj = ant + max_delta
        elif delta < -max_delta:
            obj = ant - max_delta
        limitado.append(obj)
    return limitado


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UNIFICADOS (Pelota, Soporte, Destornillador y Rotación de Mano)
# ══════════════════════════════════════════════════════════════════════════════
OBJ_OCULTO = (0.0, 0.0, -10.0)

def euler_a_quat(euler):
    """Convierte ángulos (roll, pitch, yaw) a un cuaternión [w, x, y, z]"""
    cx = math.cos(euler[0] * 0.5); sx = math.sin(euler[0] * 0.5)
    cy = math.cos(euler[1] * 0.5); sy = math.sin(euler[1] * 0.5)
    cz = math.cos(euler[2] * 0.5); sz = math.sin(euler[2] * 0.5)
    return [cx*cy*cz + sx*sy*sz, sx*cy*cz - cx*sy*sz, cx*sy*cz + sx*cy*sz, cx*cy*sz - sx*sy*cz]

def _mover_mano(modelo, datos, pos, euler):
    """OBSOLETA desde la fusión con el brazo ARCTOS: teletransportaba un body
    mocap "right_mount" que ya no existe suelto (la mano cuelga ahora del
    extremo del brazo vía joint4/5/6, y su orientación la decide la IK de
    posición). Se deja definida por compatibilidad, pero ya no se llama desde
    las teclas de flecha — ver el bloque "FLECHAS DE DIRECCIÓN" más abajo. Si
    se necesita volver a controlar la orientación manualmente, rehacer como
    3 posturas fijas de joint4/5/6 en vez de un mocap."""
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "right_mount")
        mid = modelo.body_mocapid[bid]
        datos.mocap_pos[mid] = pos
        datos.mocap_quat[mid] = euler_a_quat(euler)
        mujoco.mj_forward(modelo, datos)
        print("✋ Orientación de la mano actualizada.")
    except Exception as exc:
        print(f"⚠ _mover_mano: {exc}")

def _spawn_objeto_dinamico(modelo, datos, nombre_joint, conf_dict):
    """Hace caer un objeto aplicando un offset y rotación específicos sobre la mano."""
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "right_mount")
        pos_mano = datos.xpos[bid]
        
        jnt_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, nombre_joint)
        qa = modelo.jnt_qposadr[jnt_id]
        da = modelo.jnt_dofadr[jnt_id]
        
        # Extraemos la posición y la orientación del diccionario
        offset = conf_dict.get("pos", (0.0, 0.0, 0.30))
        euler  = conf_dict.get("euler", (0.0, 0.0, 0.0))
        
        # Aplicamos el offset personalizado en X, Y, Z
        datos.qpos[qa]       = pos_mano[0] + offset[0]
        datos.qpos[qa + 1]   = pos_mano[1] + offset[1]
        datos.qpos[qa + 2]   = pos_mano[2] + offset[2]
        
        # Aplicamos la rotación (convirtiendo Euler a Cuaternión)
        datos.qpos[qa+3:qa+7] = euler_a_quat(euler)
        
        datos.qvel[da:da+6]   = 0.0
        mujoco.mj_forward(modelo, datos)
        return True
    except Exception as exc:
        return False

# Wrappers limpios: ahora solo reciben el bloque de configuración del objeto
def _spawn_pelota(modelo, datos, conf): return _spawn_objeto_dinamico(modelo, datos, "pelota_freejoint", conf)
def _ocultar_pelota(modelo, datos): return _ocultar_objeto(modelo, datos, "pelota_freejoint")
def _spawn_destornillador(modelo, datos, conf): return _spawn_objeto_dinamico(modelo, datos, "phillips_screwdriver_joint", conf)
def _ocultar_destornillador(modelo, datos): return _ocultar_objeto(modelo, datos, "phillips_screwdriver_joint")

def _ocultar_objeto(modelo, datos, nombre_joint):
    try:
        jnt_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, nombre_joint)
        qa = modelo.jnt_qposadr[jnt_id]
        da = modelo.jnt_dofadr[jnt_id]
        datos.qpos[qa:qa+3] = OBJ_OCULTO
        datos.qpos[qa+3:qa+7] = [1.0, 0.0, 0.0, 0.0]
        datos.qvel[da:da+6] = 0.0
        mujoco.mj_forward(modelo, datos)
        return True
    except Exception as exc:
        return False

# El soporte es mocap, así que se mueve diferente (lo fijamos cerca del centro global)
def _spawn_soporte(modelo, datos, conf, nombre_body="soporte_pelota"):
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body)
        mid = modelo.body_mocapid[bid]
        
        datos.mocap_pos[mid] = conf.get("pos", (0.09, -0.07, 0.10))
        datos.mocap_quat[mid] = euler_a_quat(conf.get("euler", (0.0, 0.0, 0.0)))
        
        mujoco.mj_forward(modelo, datos)
        return True
    except: return False

def _ocultar_soporte(modelo, datos, nombre_body="soporte_pelota"):
    try:
        bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body)
        mid = modelo.body_mocapid[bid]
        datos.mocap_pos[mid] = OBJ_OCULTO
        mujoco.mj_forward(modelo, datos)
        return True
    except: return False


# ══════════════════════════════════════════════════════════════════════════════
# ENTORNO DE TRABAJO — TECLA [3]
# ══════════════════════════════════════════════════════════════════════════════
# Mini mesa de taller con alicates, destornillador, bombilla y fusible (más una
# bandeja de piezas, un portalámparas y un portafusibles fijos). Todo está
# definido en mesa_trabajo.xml, que se incluye desde arctos_mjcf.xml con:
#     <include file="mesa_trabajo.xml"/>
# Al arrancar queda escondido y sin colisiones; [3] lo coloca delante del brazo
# (con los objetos recolocados en su sitio) y [3] otra vez lo esconde.

# Centro de la SUPERFICIE de la mesa en el mundo (m): (x, y, z).
#   x → distancia delante del brazo (MÁS GRANDE = MÁS LEJOS del brazo)
#   y → desplazamiento lateral
#   z → altura de la superficie de trabajo
# Los objetos y la cámara se mueven solos con la mesa.
TALLER_POS_MESA = (-0.8, 0.0, 0.10)

TALLER_MESA = "taller_mesa"

# Pose de cada objeto RELATIVA al centro de la superficie de la mesa:
#   ((x, y, z) en metros, cuaternión de reposo (w, x, y, z))
# La z es la altura a la que se suelta (unos mm por encima de donde apoya).
TALLER_OBJETOS = {
    "taller_alicates":       ((-0.070,  0.100, 0.0085), (0.7071068, 0.0, 0.0, 0.7071068)),  # girados 90°
    "taller_destornillador": ((-0.030, -0.050, 0.0133), (0.9848078, 0.0, 0.0, 0.1736482)),  # girado 20°
    "taller_bombilla":       (( 0.062,  0.175, 0.0350), (1.0, 0.0, 0.0, 0.0)),              # en la bandeja
    "taller_fusible":        (( 0.060,  0.115, 0.0122), (1.0, 0.0, 0.0, 0.0)),              # en la bandeja
}

# Al mostrar el entorno, reencuadrar la cámara del visor para verlo entero
TALLER_ENCUADRAR_CAMARA = True

# Física de contacto "para agarrar" que se activa SOLO mientras la mesa está
# visible (al ocultarla se restauran los valores originales del modelo, así
# que el resto del comportamiento — pelota, destornillador [2], modo [M]... —
# no cambia):
#   · cono de fricción elíptico + impratio alto → el rozamiento se modela de
#     forma más realista y los objetos no "patinan" entre los dedos.
#   · noslip → elimina el deslizamiento lento de un objeto sujeto en pinza.
TALLER_FISICA_AGARRE = True
TALLER_IMPRATIO      = 10.0
TALLER_NOSLIP_ITER   = 3
TALLER_CAMARA = {
    # La cámara mira a un punto entre la base del brazo y la mesa; se calcula
    # a partir de TALLER_POS_MESA para que siga a la mesa si la mueves.
    "lookat":    (0.72 * TALLER_POS_MESA[0], TALLER_POS_MESA[1], TALLER_POS_MESA[2] + 0.08),
    "distancia": 0.95,
    "azimut":    225,
    "elevacion": -30,
}


class EntornoTaller:
    """Muestra / esconde la mesa de trabajo y sus objetos en MuJoCo."""

    def __init__(self, modelo, datos):
        self.disponible = False
        self.visible    = False

        faltan = []
        mesa = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, TALLER_MESA)
        if mesa < 0 or modelo.body_mocapid[mesa] < 0:
            faltan.append(TALLER_MESA)

        # nombre → (body id, índice en qpos, índice en qvel) de su freejoint
        self.objetos = {}
        for nombre in TALLER_OBJETOS:
            bid = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre)
            if bid < 0 or modelo.body_jntnum[bid] != 1 or \
               int(modelo.jnt_type[modelo.body_jntadr[bid]]) != int(mujoco.mjtJoint.mjJNT_FREE):
                faltan.append(nombre)
                continue
            j = modelo.body_jntadr[bid]
            self.objetos[nombre] = (bid, modelo.jnt_qposadr[j], modelo.jnt_dofadr[j])

        if faltan:
            print(f"⚠ Entorno de trabajo [3] NO disponible, faltan en el modelo: {faltan}. "
                  f"¿Está <include file=\"mesa_trabajo.xml\"/> en arctos_mjcf.xml?")
            return

        self.mocap_id = modelo.body_mocapid[mesa]

        # Geoms que chocan (group 0) de la mesa y los objetos, con sus valores
        # originales del XML, para poder apagar/encender sus colisiones.
        cuerpos = {mesa} | {bid for bid, _, _ in self.objetos.values()}
        self.colision_original = {
            g: (int(modelo.geom_contype[g]), int(modelo.geom_conaffinity[g]))
            for g in range(modelo.ngeom)
            if modelo.geom_bodyid[g] in cuerpos and modelo.geom_group[g] == 0
        }
        self.gravcomp_original = {bid: float(modelo.body_gravcomp[bid])
                                  for bid, _, _ in self.objetos.values()}

        # Opciones de física originales, para restaurarlas al ocultar la mesa
        self.opt_original = (int(modelo.opt.cone), float(modelo.opt.impratio),
                             int(modelo.opt.noslip_iterations))

        self.disponible = True
        self.ocultar(modelo, datos)
        print("🧰 Entorno de trabajo cargado (pulsa [3] para mostrarlo).")

    def _colisiones(self, modelo, activas: bool):
        for g, (ct, ca) in self.colision_original.items():
            modelo.geom_contype[g]     = ct if activas else 0
            modelo.geom_conaffinity[g] = ca if activas else 0

    def mostrar(self, modelo, datos):
        base = np.array(TALLER_POS_MESA, dtype=float)
        datos.mocap_pos[self.mocap_id]  = base
        datos.mocap_quat[self.mocap_id] = [1.0, 0.0, 0.0, 0.0]
        for nombre, (bid, qa, da) in self.objetos.items():
            rel, quat = TALLER_OBJETOS[nombre]
            q = np.array(quat, dtype=float)
            datos.qpos[qa:qa + 3]     = base + np.array(rel, dtype=float)
            datos.qpos[qa + 3:qa + 7] = q / np.linalg.norm(q)
            datos.qvel[da:da + 6]     = 0.0
            modelo.body_gravcomp[bid] = self.gravcomp_original[bid]
        self._colisiones(modelo, True)
        if TALLER_FISICA_AGARRE:
            modelo.opt.cone              = int(mujoco.mjtCone.mjCONE_ELLIPTIC)
            modelo.opt.impratio          = TALLER_IMPRATIO
            modelo.opt.noslip_iterations = TALLER_NOSLIP_ITER
        mujoco.mj_forward(modelo, datos)
        self.visible = True

    def ocultar(self, modelo, datos):
        # Escondido bajo el suelo, sin colisiones y "flotando" (gravcomp) para
        # que no se quede cayendo indefinidamente mientras no se usa.
        datos.mocap_pos[self.mocap_id] = OBJ_OCULTO
        self._colisiones(modelo, False)
        (modelo.opt.cone, modelo.opt.impratio,
         modelo.opt.noslip_iterations) = self.opt_original
        for k, (bid, qa, da) in enumerate(self.objetos.values()):
            datos.qpos[qa:qa + 3]     = (OBJ_OCULTO[0] + 0.5 * (k + 1), OBJ_OCULTO[1], OBJ_OCULTO[2])
            datos.qpos[qa + 3:qa + 7] = [1.0, 0.0, 0.0, 0.0]
            datos.qvel[da:da + 6]     = 0.0
            modelo.body_gravcomp[bid] = 1.0
        mujoco.mj_forward(modelo, datos)
        self.visible = False

    def alternar(self, modelo, datos) -> bool:
        if self.visible:
            self.ocultar(modelo, datos)
        else:
            self.mostrar(modelo, datos)
        return self.visible


# ══════════════════════════════════════════════════════════════════════════════
# ESCENARIO TALADRO — TECLA [4]
# ══════════════════════════════════════════════════════════════════════════════
# Un taladro de pie sobre una peana y un techo encima del robot. Está definido
# en escena_taladro.xml (lo GENERA taladro/preparar_taladro.py a partir de
# taladro/drill.obj) y se incluye desde arctos_mjcf.xml con:
#     <include file="escena_taladro.xml"/>
# Paso 1: aparecer / desaparecer con [4], poder coger el taladro y llevarlo al
# techo. (Paso 2: que la broca gire y deje el agujero al tocar el techo.)

class EntornoTaladro:
    """Muestra / esconde el techo, la peana y el taladro, y ayuda a sujetarlo."""

    def __init__(self, modelo, datos):
        self.disponible = False
        self.visible    = False
        self.sujeto     = False

        _id = lambda tipo, n: mujoco.mj_name2id(modelo, tipo, n)
        B, G, J = mujoco.mjtObj.mjOBJ_BODY, mujoco.mjtObj.mjOBJ_GEOM, mujoco.mjtObj.mjOBJ_JOINT
        self.b_techo, self.b_soporte = _id(B, "taladro_techo"), _id(B, "taladro_soporte")
        self.b_taladro = _id(B, "taladro")
        self.j_libre   = _id(J, "taladro_libre")
        self.j_giro    = _id(J, "taladro_giro")
        self.g_bateria = _id(G, "taladro_col_bateria")
        if min(self.b_techo, self.b_soporte, self.b_taladro, self.j_libre, self.j_giro,
               self.g_bateria) < 0:
            print("⚠ Escenario taladro [4] NO disponible: ejecuta taladro/preparar_taladro.py "
                  "y añade <include file=\"escena_taladro.xml\"/> en arctos_mjcf.xml.")
            return

        self.m_techo   = modelo.body_mocapid[self.b_techo]
        self.m_soporte = modelo.body_mocapid[self.b_soporte]
        self.qa = modelo.jnt_qposadr[self.j_libre]
        self.da = modelo.jnt_dofadr[self.j_libre]
        self.da_giro = modelo.jnt_dofadr[self.j_giro]

        # Cuerpos del taladro (el propio + el rotor) y de la MANO (todo lo que
        # cuelga de mano_mount), para contar contactos mano ↔ taladro.
        def desciende_de(b, raiz):
            while b > 0:
                if b == raiz:
                    return True
                b = modelo.body_parentid[b]
            return False
        b_mano = _id(B, "mano_mount")
        self.cuerpos_taladro = {b for b in range(modelo.nbody) if desciende_de(b, self.b_taladro)}
        self.cuerpos_mano    = {b for b in range(modelo.nbody) if b_mano >= 0 and desciende_de(b, b_mano)}

        # Geoms que CHOCAN de techo, peana y taladro, por nombre (los visuales no).
        # Se les pone la misma "máscara" de colisión que usan la mano y el suelo:
        # si el modelo del robot usa otros bits (o un <default> con contype=0),
        # con contype=1 a secas el taladro atravesaría todo y caería al infinito.
        nombres_col = ("taladro_col_", "taladro_punta", "taladro_techo_geom", "taladro_soporte_geom")
        self.geoms_col = [g for g in range(modelo.ngeom)
                          if (mujoco.mj_id2name(modelo, mujoco.mjtObj.mjOBJ_GEOM, g) or "")
                          .startswith(nombres_col)]
        mascara = 0
        for g in range(modelo.ngeom):
            b = modelo.geom_bodyid[g]
            es_suelo = (b == 0 and modelo.geom_type[g] == int(mujoco.mjtGeom.mjGEOM_PLANE))
            if b in self.cuerpos_mano or es_suelo:
                mascara |= int(modelo.geom_contype[g]) | int(modelo.geom_conaffinity[g])
        mascara = mascara or 1
        for g in self.geoms_col:
            modelo.geom_contype[g] = modelo.geom_conaffinity[g] = mascara
        self.colision_original = {g: (mascara, mascara) for g in self.geoms_col}
        print(f"🔩 Taladro: {len(self.geoms_col)} geoms de colisión (máscara {mascara}), "
              f"{len(self.cuerpos_mano)} cuerpos de mano")
        self.opt_original = (int(modelo.opt.cone), float(modelo.opt.impratio),
                             int(modelo.opt.noslip_iterations))
        # Altura de la base de la batería por debajo del origen del taladro
        self.alto_base = float(modelo.geom_size[self.g_bateria][2] - modelo.geom_pos[self.g_bateria][2])
        # Techo (su geom) y marcas de agujeros (mocap) — las usa la demo [5]
        self.g_techo = _id(G, "taladro_techo_geom")
        self.b_agujeros = [b for b in (_id(B, f"taladro_agujero_{k}") for k in range(32)) if b >= 0]
        self.m_agujeros = [int(modelo.body_mocapid[b]) for b in self.b_agujeros]

        self.disponible = True
        self.ocultar(modelo, datos)
        print("🔩 Escenario taladro cargado (pulsa [4] para mostrarlo).")

    # ── utilidades ────────────────────────────────────────────────────────────
    def _colisiones(self, modelo, activas: bool):
        for g, (ct, ca) in self.colision_original.items():
            modelo.geom_contype[g]     = ct if activas else 0
            modelo.geom_conaffinity[g] = ca if activas else 0

    @staticmethod
    def _altura_palma_vertical(modelo, datos):
        """Altura de la palma con el brazo totalmente vertical (para colocar el techo)."""
        ids = [mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, f"joint{k}") for k in (1, 2, 3)]
        qa  = [modelo.jnt_qposadr[j] for j in ids]
        bm  = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "mano_mount")
        guarda = [float(datos.qpos[i]) for i in qa]
        for i, v in zip(qa, (0.0, 0.0, 1.52)):          # joint3 = 1.52 → antebrazo recto
            datos.qpos[i] = v
        mujoco.mj_kinematics(modelo, datos)
        z = float((datos.xpos[bm] + datos.xmat[bm].reshape(3, 3) @ np.array(OFFSET_LOCAL_PALMA))[2])
        for i, v in zip(qa, guarda):
            datos.qpos[i] = v
        mujoco.mj_kinematics(modelo, datos)
        return z

    # ── mostrar / ocultar ─────────────────────────────────────────────────────
    def mostrar(self, modelo, datos):
        # Techo: por encima de la palma con el brazo vertical, lo justo para
        # llegar con la broca (o a la altura fija de config si se indica).
        z_techo = TALADRO_TECHO_Z if TALADRO_TECHO_Z is not None else \
            self._altura_palma_vertical(modelo, datos) + TALADRO_TECHO_HOLGURA
        datos.mocap_pos[self.m_techo]  = (TALADRO_TECHO_XY[0], TALADRO_TECHO_XY[1], z_techo + 0.015)
        datos.mocap_quat[self.m_techo] = [1.0, 0.0, 0.0, 0.0]

        # Peana y taladro de pie encima, con la broca mirando HACIA FUERA del robot
        # (así la empuñadura queda del lado del brazo).
        sop = np.array(TALADRO_POS_SOPORTE, dtype=float)
        self.recolocar_taladro(modelo, datos, forward=False)

        self._colisiones(modelo, True)
        modelo.opt.cone              = int(mujoco.mjtCone.mjCONE_ELLIPTIC)
        modelo.opt.impratio          = TALLER_IMPRATIO
        modelo.opt.noslip_iterations = TALLER_NOSLIP_ITER
        mujoco.mj_forward(modelo, datos)
        self.visible, self.sujeto = True, False
        print(f"🔩 Techo a z = {z_techo:.2f} m · taladro en la peana ({sop[0]:.2f}, {sop[1]:.2f}, {sop[2]:.2f})")

    def recolocar_taladro(self, modelo, datos, forward=True):
        """Peana en su sitio y taladro DE PIE encima, quieto (broca hacia fuera)."""
        sop = np.array(TALADRO_POS_SOPORTE, dtype=float)
        datos.mocap_pos[self.m_soporte]  = sop - [0.0, 0.0, 0.01]
        datos.mocap_quat[self.m_soporte] = [1.0, 0.0, 0.0, 0.0]
        yaw = math.atan2(sop[1], sop[0])
        datos.qpos[self.qa:self.qa + 3]     = sop + [0.0, 0.0, self.alto_base + 0.003]
        datos.qpos[self.qa + 3:self.qa + 7] = [math.cos(yaw / 2), 0.0, 0.0, math.sin(yaw / 2)]
        datos.qvel[self.da:self.da + 6]     = 0.0
        datos.qvel[self.da_giro]            = 0.0
        modelo.body_gravcomp[self.b_taladro] = 0.0
        if forward:
            mujoco.mj_forward(modelo, datos)

    def ocultar(self, modelo, datos):
        for k, m in enumerate(self.m_agujeros):          # los agujeros hechos por la demo [5]
            datos.mocap_pos[m] = (OBJ_OCULTO[0] + 3.0 + 0.1 * k, OBJ_OCULTO[1], OBJ_OCULTO[2])
        datos.mocap_pos[self.m_techo]   = OBJ_OCULTO
        datos.mocap_pos[self.m_soporte] = (OBJ_OCULTO[0] + 1.0, OBJ_OCULTO[1], OBJ_OCULTO[2])
        datos.qpos[self.qa:self.qa + 3]     = (OBJ_OCULTO[0] + 2.0, OBJ_OCULTO[1], OBJ_OCULTO[2])
        datos.qpos[self.qa + 3:self.qa + 7] = [1.0, 0.0, 0.0, 0.0]
        datos.qvel[self.da:self.da + 6]     = 0.0
        modelo.body_gravcomp[self.b_taladro] = 1.0       # flotando, quieto, sin caer
        self._colisiones(modelo, False)
        (modelo.opt.cone, modelo.opt.impratio, modelo.opt.noslip_iterations) = self.opt_original
        mujoco.mj_forward(modelo, datos)
        self.visible, self.sujeto = False, False

    def alternar(self, modelo, datos) -> bool:
        if self.visible:
            self.ocultar(modelo, datos)
        else:
            self.mostrar(modelo, datos)
        return self.visible

    # ── cada fotograma ────────────────────────────────────────────────────────
    def contactos_mano(self, modelo, datos) -> int:
        n = 0
        for i in range(datos.ncon):
            c = datos.contact[i]
            b1, b2 = modelo.geom_bodyid[c.geom1], modelo.geom_bodyid[c.geom2]
            if (b1 in self.cuerpos_mano and b2 in self.cuerpos_taladro) or \
               (b2 in self.cuerpos_mano and b1 in self.cuerpos_taladro):
                n += 1
        return n

    def actualizar(self, modelo, datos):
        """AGARRE ASISTIDO: mientras la mano lo toca con suficientes contactos,
        el taladro no pesa (gravcomp). Los dedos solo tienen que sujetarlo, no
        levantar 0.6 kg, que con la mano simulada acaba resbalando."""
        if not self.visible:
            return
        # Red de seguridad: si se ha caído muy abajo, vuelve a la peana
        if datos.qpos[self.qa + 2] < -0.5:
            print("⚠ El taladro se ha caído del escenario → vuelve a la peana")
            self.mostrar(modelo, datos)
            return
        if not TALADRO_ASISTENCIA_AGARRE:
            return
        sujeto = self.contactos_mano(modelo, datos) >= TALADRO_CONTACTOS_AGARRE
        if sujeto != self.sujeto:
            modelo.body_gravcomp[self.b_taladro] = 1.0 if sujeto else 0.0
            print("✊ Taladro SUJETO (agarre asistido)" if sujeto else "🖐️ Taladro SOLTADO")
            self.sujeto = sujeto


# ══════════════════════════════════════════════════════════════════════════════
# DEMO AUTOMÁTICA DEL TALADRO — TECLA [5]
# ══════════════════════════════════════════════════════════════════════════════
# El brazo ARCTOS + OrcaHand DERECHA, sin cámara:
#   1) se acerca al taladro por su lado DERECHO (palma contra el lado derecho de
#      la empuñadura, pulgar arriba, dedos rodeándola: agarre de pistola),
#   2) lo agarra y lo levanta de la peana,
#   3) lo lleva bajo el techo con la broca mirando hacia ARRIBA,
#   4) aprieta el gatillo MÁS FUERTE con el índice → el motor arranca,
#   5) empuja la broca contra el techo y deja el agujero,
#   6) suelta el gatillo, devuelve el taladro a la peana y vuelve a reposo.
#
# Todo se calcula con la cinemática REAL del modelo (brazo + OrcaHand + taladro):
# la mano alarga el brazo, así que el alcance y la altura del techo se miden
# con la mano incluida, no con el brazo solo.
#
# Agarre: al cerrar la mano el taladro se "suelda" a la mano (weld de MuJoCo,
# <equality> en arctos_mjcf.xml). Con la mano simulada y 0.6 kg el taladro acaba
# resbalando; así la demo sale siempre igual. Mientras espera en la peana va
# soldado a la peana, para que la mano no lo tumbe al acercarse.

def _unit(v):
    v = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def _minjerk(s):
    """0→1 con velocidad y aceleración nulas al principio y al final (movimiento suave)."""
    s = min(max(float(s), 0.0), 1.0)
    return s * s * s * (10.0 - 15.0 * s + 6.0 * s * s)


def _vector_giro(R):
    """Matriz de rotación → vector de giro (eje * ángulo, rad)."""
    q = np.zeros(4)
    mujoco.mju_mat2Quat(q, np.ascontiguousarray(R, dtype=float).reshape(9))
    if q[0] < 0:
        q = -q
    s = float(np.linalg.norm(q[1:]))
    if s < 1e-12:
        return np.zeros(3)
    return q[1:] / s * (2.0 * math.atan2(s, q[0]))


def _eq_activa(modelo, datos, eq, activa: bool):
    """Activa/desactiva una restricción (MuJoCo 3.x: datos.eq_active; 2.x: modelo.eq_active)."""
    arr = getattr(datos, "eq_active", None)
    if arr is None:
        arr = modelo.eq_active
    arr[eq] = 1 if activa else 0


def _eq_esta_activa(modelo, datos, eq) -> bool:
    arr = getattr(datos, "eq_active", None)
    if arr is None:
        arr = modelo.eq_active
    return bool(arr[eq])


class DemoTaladro:
    NOMBRES_DEDOS = ("i", "m", "r", "p")

    def __init__(self, modelo, entorno_taladro):
        self.ok = False
        self.env = entorno_taladro
        self.terminada = True
        self.segmentos, self.seg, self.t_seg = [], None, 0.0
        self.fase = "-"
        self.z_techo = None
        self.n_agujero = 0
        if not entorno_taladro.disponible:
            print("⚠ Demo taladro [5] NO disponible: falta el escenario del taladro [4].")
            return

        _id = lambda tipo, n: mujoco.mj_name2id(modelo, tipo, n)
        B, G, J, E = (mujoco.mjtObj.mjOBJ_BODY, mujoco.mjtObj.mjOBJ_GEOM,
                      mujoco.mjtObj.mjOBJ_JOINT, mujoco.mjtObj.mjOBJ_EQUALITY)
        self.eq_mano  = _id(E, "taladro_en_mano")
        self.eq_peana = _id(E, "taladro_en_peana")
        if self.eq_mano < 0 or self.eq_peana < 0:
            print("⚠ Demo taladro [5] NO disponible: añade en arctos_mjcf.xml el bloque\n"
                  "    <equality>\n"
                  "      <weld name=\"taladro_en_mano\"  body1=\"mano_mount\"      body2=\"taladro\" active=\"false\" solref=\"0.01 1\"/>\n"
                  "      <weld name=\"taladro_en_peana\" body1=\"taladro_soporte\" body2=\"taladro\" active=\"false\" solref=\"0.01 1\"/>\n"
                  "    </equality>")
            return

        self.bm      = _id(B, "mano_mount")
        self.b_tal   = entorno_taladro.b_taladro
        self.b_sop   = entorno_taladro.b_soporte
        self.g_punta = _id(G, "taladro_punta")
        self.g_mango = _id(G, "taladro_col_empunadura")
        self.g_sop   = _id(G, "taladro_soporte_geom")
        j_mcp = {d: _id(J, f"right_{d}-mcp") for d in self.NOMBRES_DEDOS}
        j_pip_m = _id(J, "right_m-pip")
        if min(self.bm, self.g_punta, self.g_mango, self.g_sop, j_pip_m, *j_mcp.values()) < 0:
            print("⚠ Demo taladro [5] NO disponible: no encuentro mano_mount, los dedos "
                  "de la OrcaHand o las piezas del taladro en el modelo.")
            return

        self.qidx = np.array([modelo.jnt_qposadr[_id(J, j)] for j in ARM_JOINTS], dtype=int)
        self.didx = np.array([modelo.jnt_dofadr[_id(J, j)] for j in ARM_JOINTS], dtype=int)
        self.lo = np.array([l for l, _ in LIMITES_CTRL_BRAZO], dtype=float)
        self.hi = np.array([h for _, h in LIMITES_CTRL_BRAZO], dtype=float)
        self.dk = mujoco.MjData(modelo)          # datos "borrador" solo para cinemática / IK

        # ── 1) Marco de agarre de la MANO (en ejes locales de mano_mount) ──────
        # f = hacia donde apuntan los dedos · n = hacia donde se cierran (normal de
        # la palma) · l = hacia el índice/pulgar. Se miden en el propio modelo.
        d = self.dk
        mujoco.mj_kinematics(modelo, d)
        Rm, pm = d.xmat[self.bm].reshape(3, 3).copy(), d.xpos[self.bm].copy()
        anc = lambda j: d.xanchor[j].copy()
        f = _unit(anc(j_pip_m) - anc(j_mcp["m"]))
        pip_antes = anc(j_pip_m)
        qa_mcp = modelo.jnt_qposadr[j_mcp["m"]]
        d.qpos[qa_mcp] = 0.8                                   # flexionar el corazón...
        mujoco.mj_kinematics(modelo, d)
        mov = anc(j_pip_m) - pip_antes                          # ...¿hacia dónde se cierra?
        d.qpos[qa_mcp] = modelo.qpos0[qa_mcp]
        mujoco.mj_kinematics(modelo, d)
        n = _unit(mov - (mov @ f) * f)
        lat = anc(j_mcp["i"]) - anc(j_mcp["p"])                 # meñique → índice
        l = _unit(lat - (lat @ f) * f - (lat @ n) * n)
        if float(np.cross(f, n) @ l) < 0:
            print("⚠ Demo taladro: la mano no parece DERECHA (índice y meñique cambiados); "
                  "el taladro quedaría al revés en la mano.")
            l = np.cross(f, n)
        nudillos = np.mean([anc(j_mcp[k]) for k in self.NOMBRES_DEDOS], axis=0)
        self.H_loc = Rm.T @ np.column_stack([f, n, l])           # columnas f, n, l

        # ── 2) Geometría del TALADRO (en ejes del propio taladro) ─────────────
        d.qpos[entorno_taladro.qa:entorno_taladro.qa + 7] = [0, 0, 0, 1, 0, 0, 0]
        mujoco.mj_kinematics(modelo, d)
        Rg = d.geom_xmat[self.g_mango].reshape(3, 3).copy()          # cápsula de la empuñadura
        self.c_mango = d.geom_xpos[self.g_mango].copy()
        self.r_mango = float(modelo.geom_size[self.g_mango][0])
        eje_mango = Rg[:, 2] if Rg[2, 2] >= 0 else -Rg[:, 2]      # batería → cabeza
        self.bit_d = _unit(d.xaxis[entorno_taladro.j_giro].copy())   # eje de la broca
        self.tip_d = (d.geom_xpos[self.g_punta].copy()
                      + self.bit_d * float(modelo.geom_size[self.g_punta][0]))
        ex = _unit(self.bit_d - (self.bit_d @ eje_mango) * eje_mango)
        self.E = np.column_stack([ex, np.cross(eje_mango, ex), eje_mango])
        d.qpos[:] = modelo.qpos0
        mujoco.mj_kinematics(modelo, d)

        # Punto de la mano que debe coincidir con el eje de la empuñadura: delante
        # de la palma (media mano + radio del mango), a la altura de los nudillos.
        o_f, o_n, o_l = TALADRO_DEMO_AGARRE_OFFSET
        agarre = nudillos + f * o_f + n * (o_n + self.r_mango) + l * o_l
        self.G_loc = Rm.T @ (agarre - pm)

        # Agarre "de diseño": pose del taladro en ejes de mano_mount
        self.R_md_dis = self.H_loc @ self.E.T
        self.p_md_dis = self.G_loc - self.R_md_dis @ self.c_mango

        # Semillas para la IK (varias posturas de partida del brazo)
        self.semillas = [np.array([j1, j2, j3, 0.0, j5, 0.0])
                         for j1 in np.linspace(-2.4, 2.4, 7)
                         for (j2, j3) in ((0.5, 1.0), (1.0, 0.2), (-0.5, 1.2))
                         for j5 in (0.6, -0.6)]

        # Manos (17 valores de ctrl)
        self.mano_abierta = self._mano(TALADRO_DEMO_MANO_ABIERTA)
        self.mano_agarre  = self._mano(TALADRO_DEMO_MANO_AGARRE)
        self.mano_gatillo = self._mano({**TALADRO_DEMO_MANO_AGARRE, **TALADRO_DEMO_MANO_GATILLO})
        g0, g1 = self.mano_agarre[11], self.mano_gatillo[11]
        self.umbral_gatillo = g0 + 0.7 * (g1 - g0)

        # Autocolisiones: eslabones del ARCTOS (sus propios geoms) y mano. Los pares que
        # ya se tocan en posturas normales (mallas que solapan en las uniones) no cuentan.
        self.cuerpos_brazo = {b for b in (_id(B, f"Link_{k}_1") for k in range(1, 7)) if b >= 0}
        self.cuerpos_mano = set(entorno_taladro.cuerpos_mano)
        self.geoms_brazo = [g for g in range(modelo.ngeom) if modelo.geom_bodyid[g] in self.cuerpos_brazo]
        self.col_brazo_orig = {g: (int(modelo.geom_contype[g]), int(modelo.geom_conaffinity[g]))
                               for g in self.geoms_brazo}
        self.pares_base = set()
        for q_b in (np.zeros(6), np.array(POSICION_STANDBY_BRAZO, dtype=float)):
            self.pares_base |= set(self._pares_en_contacto(modelo, q_b, umbral=0.0))
        self.integral = np.zeros(len(ARM_JOINTS))
        self._q_cmd_prev = None
        self._t_fin = None

        # Estado dinámico
        self.sujeto, self.omega, self.motor = False, 0.0, False
        self.agujero_colocado, self.progreso = False, 0.0
        self.error = None
        self.ok = True
        fmt = lambda v: "(" + ", ".join(f"{x:+.2f}" for x in v) + ")"
        print(f"🛠️  Demo taladro [5] lista (mango r = {self.r_mango * 1000:.0f} mm, "
              f"broca a {np.linalg.norm(self.tip_d - self.c_mango) * 100:.1f} cm del mango).\n"
              f"    Mano en ejes de mano_mount: dedos {fmt(self.H_loc[:, 0])} · palma "
              f"{fmt(self.H_loc[:, 1])} · índice {fmt(self.H_loc[:, 2])} · "
              f"agarre {fmt(self.G_loc * 100)} cm")

    # ── utilidades ────────────────────────────────────────────────────────────
    @staticmethod
    def _mano(valores: dict):
        m = np.zeros(N_ACT)
        m[13:17] = POSICION_STANDBY[13:17]
        for i, v in valores.items():
            lo, hi = LIMITES_CTRL[i]
            m[i] = float(np.clip(v, lo, hi))
        return m

    def _nombre_cuerpo(self, modelo, b):
        return mujoco.mj_id2name(modelo, mujoco.mjtObj.mjOBJ_BODY, int(b)) or f"cuerpo {b}"

    def _es_par_vigilado(self, b1, b2):
        """Brazo↔brazo o brazo↔mano (lo de dentro de la mano no cuenta)."""
        br1, br2 = b1 in self.cuerpos_brazo, b2 in self.cuerpos_brazo
        return (br1 and (br2 or b2 in self.cuerpos_mano)) or (br2 and b1 in self.cuerpos_mano)

    def _pares_en_contacto(self, modelo, q, umbral=0.003):
        """{(b1, b2): penetración} de autocolisiones si el brazo estuviera en q.
        Se mira con las colisiones ORIGINALES del brazo aunque la demo las tenga apagadas."""
        d = self.dk
        guarda = {g: (int(modelo.geom_contype[g]), int(modelo.geom_conaffinity[g]))
                  for g in self.geoms_brazo}
        for g, (ct, ca) in self.col_brazo_orig.items():
            modelo.geom_contype[g], modelo.geom_conaffinity[g] = ct, ca
        d.qpos[self.qidx] = q
        mujoco.mj_kinematics(modelo, d)
        mujoco.mj_collision(modelo, d)
        pares = {}
        for i in range(d.ncon):
            c = d.contact[i]
            b1, b2 = int(modelo.geom_bodyid[c.geom1]), int(modelo.geom_bodyid[c.geom2])
            if self._es_par_vigilado(b1, b2) and -float(c.dist) > umbral:
                par = (min(b1, b2), max(b1, b2))
                pares[par] = max(pares.get(par, 0.0), -float(c.dist))
        for g, (ct, ca) in guarda.items():
            modelo.geom_contype[g], modelo.geom_conaffinity[g] = ct, ca
        return pares

    def _autocolision(self, modelo, q):
        """(penetración máx. en m, texto) de autocolisiones NUEVAS en la postura q."""
        pares = {k: v for k, v in self._pares_en_contacto(modelo, q).items()
                 if k not in self.pares_base}
        if not pares:
            return 0.0, ""
        (b1, b2), pen = max(pares.items(), key=lambda kv: kv[1])
        return pen, f"{self._nombre_cuerpo(modelo, b1)} ↔ {self._nombre_cuerpo(modelo, b2)}"

    def _fk(self, modelo, q):
        d = self.dk
        d.qpos[self.qidx] = q
        mujoco.mj_kinematics(modelo, d)
        mujoco.mj_comPos(modelo, d)
        return d.xmat[self.bm].reshape(3, 3).copy(), d.xpos[self.bm].copy()

    def _ik(self, modelo, q_ini, p_loc, p_obj, ejes, iters=100, w_rot=0.3, lam=0.02, paso=0.2):
        """IK del brazo completo (6 joints): lleva el punto p_loc (ejes de mano_mount)
        a p_obj y alinea los ejes. ejes = [(eje_local, eje_mundo_objetivo), ...];
        con UN solo eje, el giro alrededor de él queda libre."""
        d = self.dk
        q = np.clip(np.asarray(q_ini, dtype=float), self.lo, self.hi)
        p_loc, p_obj = np.asarray(p_loc, dtype=float), np.asarray(p_obj, dtype=float)
        A_loc = np.column_stack([a for a, _ in ejes])
        T = np.column_stack([_unit(t) for _, t in ejes])
        jacp, jacr = np.zeros((3, modelo.nv)), np.zeros((3, modelo.nv))

        def errores(R, p0):
            e_p = p_obj - (p0 + R @ p_loc)
            A = R @ A_loc
            if len(ejes) == 1:
                a, t = A[:, 0], T[:, 0]
                c = np.cross(a, t)
                ang = math.atan2(float(np.linalg.norm(c)), float(a @ t))
                e_r = _unit(c) * ang if np.linalg.norm(c) > 1e-9 else np.zeros(3)
            else:
                e_r = _vector_giro(T @ A.T)
            return e_p, e_r, A

        for _ in range(iters):
            R, p0 = self._fk(modelo, q)
            e_p, e_r, A = errores(R, p0)
            if np.linalg.norm(e_p) < 3e-4 and np.linalg.norm(e_r) < 2e-3:
                break
            mujoco.mj_jac(modelo, d, jacp, jacr, p0 + R @ p_loc, self.bm)
            Jp, Jr = jacp[:, self.didx], jacr[:, self.didx]
            if len(ejes) == 1:                                # el giro sobre el eje no importa
                a = A[:, 0]
                Jr = (np.eye(3) - np.outer(a, a)) @ Jr
            Jt = np.vstack([Jp, w_rot * Jr])
            e = np.concatenate([e_p, w_rot * e_r])
            dq = Jt.T @ np.linalg.solve(Jt @ Jt.T + lam ** 2 * np.eye(6), e)
            m = float(np.abs(dq).max())
            if m > paso:
                dq *= paso / m
            q = np.clip(q + dq, self.lo, self.hi)
        R, p0 = self._fk(modelo, q)
        e_p, _, A = errores(R, p0)
        ang = max(math.acos(float(np.clip(A[:, k] @ T[:, k], -1.0, 1.0))) for k in range(len(ejes)))
        return q, float(np.linalg.norm(e_p)), ang

    def _ik_multi(self, modelo, q_pref, p_loc, p_obj, ejes, extra=()):
        """IK desde muchas posturas de partida; se queda con la que llega (≤3 mm, ≤3°)
        moviendo menos el brazo respecto a q_pref."""
        q_pref = np.asarray(q_pref, dtype=float)
        mejor, clave_mejor = None, None
        for k, s in enumerate([q_pref, *extra, *self.semillas]):
            q, ep, ea = self._ik(modelo, s, p_loc, p_obj, ejes, iters=150 if k == 0 else 100)
            bueno = ep < 0.003 and ea < math.radians(3.0)
            if bueno and self._autocolision(modelo, q)[0] > 0.0:
                coste = 5.0 + ep                      # llega, pero la mano choca con el brazo
            else:
                coste = float(np.abs(q - q_pref).sum()) if bueno else ep + 0.05 * ea + 10.0
            if clave_mejor is None or coste < clave_mejor:
                mejor, clave_mejor = (q, ep, ea), coste
            # Si desde la postura actual ya llega sin retorcerse, no hace falta buscar más
            if k == 0 and bueno and coste < 2.5:
                break
        return mejor

    def _camino(self, modelo, q0, p_loc, pA, pB, ejes, n=10):
        """Línea recta de pA a pB (mismo agarre), resuelta en n puntos con IK encadenada."""
        qs, peor = [np.asarray(q0, dtype=float)], 0.0
        pA, pB = np.asarray(pA, dtype=float), np.asarray(pB, dtype=float)
        for k in range(1, n + 1):
            q, ep, _ = self._ik(modelo, qs[-1], p_loc, pA + (k / n) * (pB - pA), ejes, iters=50)
            qs.append(q)
            peor = max(peor, ep)
        return qs, peor

    @staticmethod
    def _avisar(nombre, ep, ea):
        if ep > 0.01 or ea > math.radians(8):
            print(f"   ⚠ {nombre}: la IK no llega bien (error {ep * 100:.1f} cm, "
                  f"{math.degrees(ea):.0f}°). Revisa TALADRO_POS_SOPORTE / TALADRO_DEMO_AGUJERO_XY.")
        else:
            print(f"   ✓ {nombre}: error {ep * 1000:.1f} mm, {math.degrees(ea):.1f}°")

    def _soldar(self, modelo, datos, eq, b1, b2):
        """Activa el weld eq con la pose relativa ACTUAL de b2 respecto a b1 (sin saltos)."""
        mujoco.mj_kinematics(modelo, datos)
        R1, p1 = datos.xmat[b1].reshape(3, 3), datos.xpos[b1]
        q1inv, qrel = np.zeros(4), np.zeros(4)
        mujoco.mju_negQuat(q1inv, datos.xquat[b1])
        mujoco.mju_mulQuat(qrel, q1inv, datos.xquat[b2])
        modelo.eq_data[eq, 0:3]  = 0.0                               # ancla en el origen de b2
        modelo.eq_data[eq, 3:6]  = R1.T @ (datos.xpos[b2] - p1)      # b2 visto desde b1
        modelo.eq_data[eq, 6:10] = qrel
        _eq_activa(modelo, datos, eq, True)

    def _pose(self, datos, b):
        return datos.xmat[b].reshape(3, 3).copy(), datos.xpos[b].copy()

    # ── planificación ─────────────────────────────────────────────────────────
    def _agujero_xy(self):
        k = self.n_agujero
        pasos = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        dx, dy = pasos[k % len(pasos)]
        s = TALADRO_DEMO_SEP_AGUJEROS
        return np.array([TALADRO_DEMO_AGUJERO_XY[0] + dx * s, TALADRO_DEMO_AGUJERO_XY[1] + dy * s])

    def _calcular_techo(self, modelo, q_ini, xy):
        """Altura del techo = lo más alto que llega la PUNTA DE LA BROCA (brazo + mano +
        taladro, broca vertical) sobre el punto del agujero, menos un margen."""
        tip_m = self.p_md_dis + self.R_md_dis @ self.tip_d
        bit_m = self.R_md_dis @ self.bit_d
        eje = [(bit_m, np.array([0.0, 0.0, 1.0]))]
        llega = lambda r: r[1] < 0.003 and r[2] < math.radians(3.0)
        q, z_ok, z_mal = np.asarray(q_ini, dtype=float), None, None
        for z in np.arange(0.60, 2.01, 0.05):                # búsqueda gruesa (5 cm)
            r = self._ik_multi(modelo, q, tip_m, (xy[0], xy[1], z), eje)
            if llega(r):
                q, z_ok = r[0], float(z)
            else:
                z_mal = float(z)
                break
        if z_ok is None:
            print("   ⚠ La broca no llega en vertical sobre el punto del agujero: "
                  "acerca TALADRO_DEMO_AGUJERO_XY a la base del brazo.")
            return 0.9
        if z_mal is not None:                                 # afinar (1 cm)
            for z in np.arange(z_ok + 0.01, z_mal, 0.01):
                r = self._ik(modelo, q, tip_m, (xy[0], xy[1], z), eje, iters=80)
                if not llega(r):
                    break
                q, z_ok = r[0], float(z)
        print(f"   ✓ Alcance máx. de la broca (brazo + OrcaHand + taladro): z = {z_ok:.2f} m")
        return z_ok - TALADRO_DEMO_MARGEN_TECHO

    # ── trayectorias cartesianas: la mano va en LÍNEA RECTA, sin barridos ────
    # (con interpolación ARTICULAR entre dos posturas lejanas la mano puede dar
    #  un rodeo por abajo y quedarse enganchada bajo la peana: es lo que pasaba)
    @staticmethod
    def _slerp_R(RA, RB, u):
        qa, qb = np.zeros(4), np.zeros(4)
        mujoco.mju_mat2Quat(qa, np.ascontiguousarray(RA, dtype=float).reshape(9))
        mujoco.mju_mat2Quat(qb, np.ascontiguousarray(RB, dtype=float).reshape(9))
        c = float(qa @ qb)
        if c < 0.0:
            qb, c = -qb, -c
        if c > 0.9995:
            q = qa + u * (qb - qa)
        else:
            th = math.acos(c)
            q = (math.sin((1.0 - u) * th) * qa + math.sin(u * th) * qb) / math.sin(th)
        q = q / np.linalg.norm(q)
        R = np.zeros(9)
        mujoco.mju_quat2Mat(R, q)
        return R.reshape(3, 3)

    def _pose_q(self, modelo, q):
        """(rotación de mano_mount, punto de agarre) si el brazo estuviera en q."""
        R, p = self._fk(modelo, q)
        return R, p + R @ self.G_loc

    def _recta(self, modelo, q0, R_B, P_B, paso_m=0.015, paso_rad=0.06):
        """Desde la pose de q0, la mano va en línea recta hasta P_B girando poco a poco
        hasta R_B. IK encadenada (cada punto parte del anterior) → sin saltos.
        Devuelve (qs, error_final_m, error_final_rad, mayor_salto_rad)."""
        R_A, P_A = self._pose_q(modelo, q0)
        ang = float(np.linalg.norm(_vector_giro(R_B @ R_A.T)))
        n = max(2, int(math.ceil(max(np.linalg.norm(P_B - P_A) / paso_m, ang / paso_rad))))
        qs, I, salto = [np.asarray(q0, dtype=float)], np.eye(3), 0.0
        ep = ea = 0.0
        for k in range(1, n + 1):
            u = k / n
            R = self._slerp_R(R_A, R_B, u)
            q, ep, ea = self._ik(modelo, qs[-1], self.G_loc, P_A + u * (P_B - P_A),
                                 [(I[:, j], R[:, j]) for j in range(3)], iters=60 if k < n else 150)
            salto = max(salto, float(np.abs(q - qs[-1]).max()))
            qs.append(q)
        return qs, ep, ea, salto

    def _punto_bajo_cerca_del_taladro(self, modelo, qs, n=40):
        """Recorre un movimiento ARTICULAR y devuelve cuánto baja la mano (m) por
        debajo de la altura segura cuando está cerca del taladro (0 = nunca)."""
        cx, cy = self.pose_peana[1][:2]
        peor = 0.0
        for a, b in zip(qs[:-1], qs[1:]):
            for u in np.linspace(0.0, 1.0, n):
                _, P = self._pose_q(modelo, a + u * (b - a))
                if math.hypot(P[0] - cx, P[1] - cy) < 0.25:
                    peor = max(peor, self.z_segura - P[2])
        return peor

    def _tramo(self, modelo, nombre, q0, R_B, P_B, q_alt=None, q_fin=None):
        """Tramo en línea recta; si es imposible (límites, singularidad), movimiento
        articular hasta una postura alternativa (q_alt o la mejor IK), pasando por
        arriba si ese movimiento bajara la mano junto al taladro.
        q_fin: postura EXACTA en la que debe acabar (enlaza con el tramo siguiente)."""
        qs, ep, ea, salto = self._recta(modelo, q0, R_B, P_B)
        pen, par = max((self._autocolision(modelo, q) for q in qs[::3] + [qs[-1]]),
                       key=lambda r: r[0])
        if pen > 0.0:
            print(f"   ⚠ {nombre}: en línea recta la mano chocaría con el brazo ({par}, "
                  f"{pen * 1000:.0f} mm)")
            ep = max(ep, 1.0)
        if ep < 0.005 and ea < math.radians(4) and salto < 1.2:
            if q_fin is None:
                return qs
            if float(np.abs(qs[-1] - q_fin).max()) < 0.15:
                return qs[:-1] + [np.asarray(q_fin, dtype=float)]
            ep = ea = 0.0                     # llega, pero con otra postura del brazo
        if q_fin is not None:
            q_alt = q_fin
        I = np.eye(3)
        if q_alt is None:
            q_alt, ep2, ea2 = self._ik_multi(modelo, q0, self.G_loc, P_B,
                                             [(I[:, j], R_B[:, j]) for j in range(3)])
            self._avisar(f"{nombre} (postura alternativa)", ep2, ea2)
        print(f"   ⚠ {nombre}: no se puede en línea recta (error {ep * 100:.1f} cm, "
              f"{math.degrees(ea):.0f}°) → movimiento articular")
        camino = [np.asarray(q0, dtype=float), np.asarray(q_alt, dtype=float)]
        if self._punto_bajo_cerca_del_taladro(modelo, camino) > 0.02:
            R_A, P_A = self._pose_q(modelo, q0)
            P_m = 0.5 * (P_A + P_B)
            P_m[2] = max(P_A[2], P_B[2], self.z_segura) + 0.10
            R_m = self._slerp_R(R_A, R_B, 0.5)
            q_via, ep3, ea3 = self._ik_multi(modelo, q0, self.G_loc, P_m,
                                             [(I[:, j], R_m[:, j]) for j in range(3)])
            camino = [camino[0], q_via, camino[1]]
            baja = self._punto_bajo_cerca_del_taladro(modelo, camino)
            print(f"     ↳ con un punto de paso por arriba (la mano baja {baja * 100:.0f} cm "
                  f"de la altura segura junto al taladro)")
        return camino

    # ── planificación ─────────────────────────────────────────────────────────
    def _plan_recogida(self, modelo, datos, q_act):
        print("🧮 Demo taladro: planificando la recogida...")
        R_wd, p_wd = self._pose(datos, self.b_tal)
        self.pose_peana = (R_wd, p_wd)
        H = R_wd @ self.E                           # f, n, l que debe tener la mano
        R_g = H @ self.H_loc.T                      # rotación de mano_mount al agarrar
        P_g = p_wd + R_wd @ self.c_mango            # centro del mango
        arriba = np.array([0.0, 0.0, 1.0])
        P_pre = P_g - H[:, 1] * TALADRO_DEMO_APROX  # al lado DERECHO del mango
        R_0, P_0 = self._pose_q(modelo, q_act)
        # Altura segura: el punto de agarre por encima de la cabeza del taladro
        z_seg = P_g[2] + TALADRO_DEMO_ALTURA_SEGURA
        self.z_segura = z_seg
        P_sobre = np.array([P_pre[0], P_pre[1], z_seg])

        I = np.eye(3)
        ejes_g = [(I[:, j], R_g[:, j]) for j in range(3)]
        # El final del acercamiento se planifica HACIA ATRÁS desde el agarre, con una
        # postura de brazo natural (cercana a la de reposo), para que la mano entre
        # siempre igual venga de donde venga:
        #   agarre ← entrar ← punto de entrada ← bajar ← sobre el taladro
        q_ref = np.array(POSICION_STANDBY_BRAZO, dtype=float)
        q_agarre, ep, ea = self._ik_multi(modelo, q_ref, self.G_loc, P_g, ejes_g, extra=(q_act,))
        self._avisar("agarre de la empuñadura", ep, ea)
        pen, par = self._autocolision(modelo, q_agarre)
        if pen > 0.0:
            print(f"   ⚠ En la postura de agarre la mano toca el brazo ({par}, {pen * 1000:.0f} mm). "
                  f"Prueba a mover TALADRO_POS_SOPORTE.")
        salir, ep1, _, _ = self._recta(modelo, q_agarre, R_g, P_pre)
        alzar, ep2, _, _ = self._recta(modelo, salir[-1], R_g, P_sobre)
        if max(ep1, ep2) > 0.005:
            print(f"   ⚠ La entrada lateral al mango no sale recta (error {max(ep1, ep2) * 100:.1f} cm)")
        entrar, bajar = salir[::-1], alzar[::-1]
        # Desde donde esté el brazo: subir en vertical e ir por arriba
        subir = self._tramo(modelo, "subir la mano", q_act, R_0,
                            np.array([P_0[0], P_0[1], max(z_seg, P_0[2])]))
        ir = self._tramo(modelo, "ir sobre el taladro", subir[-1], R_g, P_sobre, q_fin=bajar[0])
        levantar = self._tramo(modelo, "levantar", q_agarre, R_g,
                               P_g + np.array([0.0, 0.0, TALADRO_DEMO_ALTURA_PASO]))
        return dict(subir=subir, ir=ir, bajar=bajar, entrar=entrar, levantar=levantar)

    def _plan_techo_y_vuelta(self, modelo, datos):
        """Tras agarrar: pose REAL del taladro en la mano → perforar y devolverlo."""
        print("🧮 Demo taladro: planificando el taladrado...")
        R_wm, p_wm = self._pose(datos, self.bm)
        R_wd, p_wd = self._pose(datos, self.b_tal)
        R_md, p_md = R_wm.T @ R_wd, R_wm.T @ (p_wd - p_wm)
        tip_m, bit_m = p_md + R_md @ self.tip_d, R_md @ self.bit_d
        arriba = np.array([0.0, 0.0, 1.0])
        eje = [(bit_m, arriba)]
        x, y = self.xy
        zt = self.z_techo
        q_lev = self.plan1["levantar"][-1]

        # Pose bajo el techo con la broca vertical (el giro alrededor de ella, libre)
        q_bajo, ep, ea = self._ik_multi(modelo, q_lev, tip_m, (x, y, zt - TALADRO_DEMO_BAJO_TECHO), eje)
        self._avisar("broca bajo el techo", ep, ea)
        R_b, P_b = self._pose_q(modelo, q_bajo)
        al_techo = self._tramo(modelo, "llevar al techo", q_lev, R_b, P_b, q_alt=q_bajo)
        q0 = al_techo[-1]
        acercar, ep1 = self._camino(modelo, q0, tip_m, (x, y, zt - TALADRO_DEMO_BAJO_TECHO),
                                    (x, y, zt - 0.001), eje)
        perforar, ep2 = self._camino(modelo, acercar[-1], tip_m, (x, y, zt - 0.001),
                                     (x, y, zt + TALADRO_DEMO_PROFUNDIDAD), eje, n=8)
        self._avisar("perforación", max(ep1, ep2), 0.0)
        atras = perforar[::-1] + acercar[::-1][1:]            # termina en q0

        # Devolver el taladro EXACTAMENTE a donde estaba en la peana
        R_wd0, p_wd0 = self.pose_peana
        R_obj = R_wd0 @ R_md.T                                # mano_mount al dejarlo
        P_obj = (p_wd0 - R_obj @ p_md) + R_obj @ self.G_loc   # su punto de agarre
        n_w = R_obj @ self.H_loc[:, 1]
        P_arriba = P_obj + arriba * TALADRO_DEMO_ALTURA_PASO
        volver  = self._tramo(modelo, "volver sobre la peana", q0, R_obj, P_arriba)
        dejar   = self._tramo(modelo, "dejar en la peana", volver[-1], R_obj, P_obj)
        R_f, P_f = self._pose_q(modelo, dejar[-1])
        self._avisar("taladro en la peana", float(np.linalg.norm(P_f - P_obj)),
                     float(np.linalg.norm(_vector_giro(R_obj @ R_f.T))))
        retirar = self._tramo(modelo, "retirar la mano", dejar[-1], R_obj, P_obj - n_w * TALADRO_DEMO_APROX)
        alejar  = self._tramo(modelo, "subir la mano", retirar[-1], R_obj,
                              P_obj - n_w * TALADRO_DEMO_APROX + arriba * TALADRO_DEMO_ALTURA_PASO)
        q_rep = np.array(POSICION_STANDBY_BRAZO, dtype=float)
        R_s, P_s = self._pose_q(modelo, q_rep)
        # A reposo: la mano va en línea recta hasta su sitio de reposo (lejos del
        # taladro) y, si el brazo llega con otra postura, se recoloca ya allí.
        reposo, ep, ea, salto = self._recta(modelo, alejar[-1], R_s, P_s)
        if ep < 0.005 and ea < math.radians(4) and salto < 1.2:
            reposo = reposo + [q_rep]
        else:
            reposo = self._tramo(modelo, "volver a reposo", alejar[-1], R_s, P_s, q_fin=q_rep)
        return dict(al_techo=al_techo, acercar=acercar, perforar=perforar, atras=atras,
                    volver=volver, dejar=dejar, retirar=retirar, alejar=alejar, reposo=reposo)

    # ── segmentos (trayectorias por tramos) ───────────────────────────────────
    def _seg(self, nombre, dur, qs, mano=None, al_terminar=None, vibrar=False):
        qs = [np.asarray(q, dtype=float) for q in qs]
        if len(qs) == 1:
            qs = qs * 2
        dur = dur / max(TALADRO_DEMO_VELOCIDAD, 0.05)
        # Nunca más deprisa que TALADRO_DEMO_VEL_MAX (rad/s) en ninguna articulación:
        # el perfil suave tiene un pico de 1.875 × la velocidad media.
        recorrido = float(sum(np.abs(b - a).max() for a, b in zip(qs[:-1], qs[1:])))
        dur = max(dur, 1.875 * recorrido / TALADRO_DEMO_VEL_MAX, 0.05)
        return dict(nombre=nombre, dur=dur, qs=qs, mano=mano, al_terminar=al_terminar, vibrar=vibrar)

    def iniciar(self, modelo, datos, visor=None) -> bool:
        if not self.ok:
            print("⚠ Demo taladro [5] no disponible (mira los avisos del arranque).")
            return False
        env = self.env
        if not env.visible:
            env.mostrar(modelo, datos)
        # Estado limpio: sin soldaduras, taladro de pie en la peana
        _eq_activa(modelo, datos, self.eq_mano, False)
        _eq_activa(modelo, datos, self.eq_peana, False)
        env.recolocar_taladro(modelo, datos)
        env._colisiones(modelo, True)
        self._fisica_demo(modelo, True)
        self._soldar(modelo, datos, self.eq_peana, self.b_sop, self.b_tal)
        modelo.body_gravcomp[self.b_tal] = 1.0
        self.sujeto, self.omega, self.agujero_colocado, self.progreso = False, 0.0, False, 0.0
        self.error = None
        self.integral[:] = 0.0
        self._q_cmd_prev = None
        # Los ESLABONES del brazo dejan de chocar con la mano y el taladro durante la
        # demo (bit de colisión 2): un roce de mallas en la muñeca ya no puede dejar
        # el brazo atascado. El plan igualmente evita posturas con autocolisión.
        if TALADRO_DEMO_SIN_AUTOCOLISION:
            for g in self.geoms_brazo:
                modelo.geom_contype[g] = modelo.geom_conaffinity[g] = 2

        # La peana y el techo no chocan en la demo: el taladro va sujeto por los welds
        # y así la mano nunca puede quedarse enganchada bajo la peana.
        modelo.geom_contype[self.g_sop] = modelo.geom_conaffinity[self.g_sop] = 0
        modelo.geom_contype[env.g_techo] = modelo.geom_conaffinity[env.g_techo] = 0

        q_act = datos.qpos[self.qidx].copy()
        self.plan1 = self._plan_recogida(modelo, datos, q_act)

        # Techo a la altura que alcanza DE VERDAD la broca (una sola vez)
        self.xy = self._agujero_xy()
        if TALADRO_DEMO_TECHO_Z is not None:
            self.z_techo = float(TALADRO_DEMO_TECHO_Z)
        elif self.z_techo is None:
            self.z_techo = self._calcular_techo(modelo, self.plan1["levantar"][-1], self.xy)
        datos.mocap_pos[env.m_techo] = (TALADRO_TECHO_XY[0], TALADRO_TECHO_XY[1], self.z_techo + 0.015)
        datos.mocap_quat[env.m_techo] = [1.0, 0.0, 0.0, 0.0]
        mujoco.mj_forward(modelo, datos)
        print(f"🔩 Techo a z = {self.z_techo:.2f} m · agujero nº {self.n_agujero + 1} en "
              f"({self.xy[0]:+.2f}, {self.xy[1]:+.2f})")

        p1 = self.plan1
        T = TALADRO_DEMO_TIEMPOS
        self.segmentos = [
            self._seg("Subiendo la mano", T["subir"], p1["subir"], self.mano_abierta),
            self._seg("Yendo sobre el taladro", T["acercar"], p1["ir"]),
            self._seg("Bajando junto al mango", T["bajar"], p1["bajar"]),
            self._seg("Metiendo la mano (lado derecho)", T["entrar"], p1["entrar"]),
            self._seg("Cerrando la mano", T["cerrar"], [p1["entrar"][-1]], self.mano_agarre,
                      al_terminar=self._al_agarrar),
        ]
        self.seg, self.t_seg, self.terminada = None, 0.0, False
        self._mano_ini = datos.ctrl[OFFSET_MANO:OFFSET_MANO + N_ACT].copy()
        if visor is not None:
            with visor.lock():
                sp = np.array(TALADRO_POS_SOPORTE, dtype=float)
                cam = TALADRO_DEMO_CAMARA
                visor.cam.lookat[:] = (0.5 * (sp[0] + self.xy[0]), 0.5 * (sp[1] + self.xy[1]),
                                       0.5 * (sp[2] + self.z_techo))
                visor.cam.distance  = cam["distancia"]
                visor.cam.azimuth   = cam["azimut"]
                visor.cam.elevation = cam["elevacion"]
        return True

    def _comprobar_agarre(self, datos):
        """¿Está de verdad el mango dentro de la mano? Devuelve (ok, texto)."""
        R_m, p_m = self._pose(datos, self.bm)
        R_d, p_d = self._pose(datos, self.b_tal)
        P = p_m + R_m @ self.G_loc                    # donde la mano espera el mango
        c = p_d + R_d @ self.c_mango                  # donde está el mango
        v = R_d.T @ (P - c)                           # en ejes del taladro
        a = self.E[:, 2]                              # eje del mango (ejes del taladro)
        perp = float(np.linalg.norm(v - (v @ a) * a))
        eje_mano = R_d.T @ (R_m @ self.H_loc[:, 2])
        ang = math.degrees(math.acos(float(np.clip(eje_mano @ a, -1.0, 1.0))))
        txt = (f"mano a {perp * 100:.1f} cm del eje del mango, {v @ a * 100:+.1f} cm a lo largo, "
               f"{ang:.0f}° de giro (x broca {v[0] * 100:+.1f} · y izq {v[1] * 100:+.1f} · "
               f"z arriba {v[2] * 100:+.1f} cm)")
        ok = perp <= TALADRO_DEMO_TOL_AGARRE and abs(v @ a) <= 0.04 and ang <= 35.0
        return ok, txt

    def _contactos_dedos(self, modelo, datos):
        """Contactos REALES mano↔taladro (comprobación física, independiente del plan)."""
        return self.env.contactos_mano(modelo, datos)

    def _al_agarrar(self, modelo, datos):
        ok, txt = self._comprobar_agarre(datos)
        p1, T = self.plan1, TALADRO_DEMO_TIEMPOS
        if not ok:
            # NO se suelda un taladro que no está en la mano: se aborta con calma
            self.error = "Agarre fallido: la mano no esta en el mango"
            print(f"❌ Agarre FALLIDO: {txt}\n   → la mano se retira. Envía esta línea para afinarlo.")
            salida = p1["entrar"][::-1] + p1["bajar"][::-1][1:] + p1["ir"][::-1][1:]
            self.segmentos = [
                self._seg("Abriendo la mano", T["abrir"], [p1["entrar"][-1]], self.mano_abierta),
                self._seg("Retirando la mano", T["retirar"], salida),
                self._seg("Volviendo a reposo", T["reposo"], [salida[-1], POSICION_STANDBY_BRAZO],
                          np.array(POSICION_STANDBY, dtype=float), al_terminar=self._al_acabar),
            ]
            return
        # Taladro: de la peana a la mano
        _eq_activa(modelo, datos, self.eq_peana, False)
        self._soldar(modelo, datos, self.eq_mano, self.bm, self.b_tal)
        modelo.body_gravcomp[self.b_tal] = 1.0
        self.sujeto = True
        n_c = self._contactos_dedos(modelo, datos)
        print(f"✊ Taladro AGARRADO ({txt}; {n_c} contactos dedos↔taladro)")
        if n_c < TALADRO_DEMO_CONTACTOS_MIN:
            print("   ⚠ La mano está donde manda el plan pero apenas toca el mango: el taladro "
                  "se sujeta igual (soldadura), pero ajusta TALADRO_DEMO_AGARRE_OFFSET o "
                  "TALADRO_DEMO_MANO_AGARRE para que los dedos lo rodeen de verdad.")
        p2 = self._plan_techo_y_vuelta(modelo, datos)
        q_top = p2["acercar"][-1]
        self.segmentos += [
            self._seg("Levantando el taladro", T["levantar"], p1["levantar"]),
            self._seg("Llevandolo al techo", T["al_techo"], p2["al_techo"]),
            self._seg("Acercando la broca al techo", T["acercar_broca"], p2["acercar"]),
            self._seg("Apretando el gatillo", T["gatillo"], [q_top], self.mano_gatillo),
            self._seg("Motor en marcha", T["arrancar"], [q_top]),
            self._seg("PERFORANDO el techo", T["perforar"], p2["perforar"], vibrar=True),
            self._seg("Sacando la broca", T["sacar"], p2["atras"]),
            self._seg("Soltando el gatillo", T["soltar_gatillo"], [p2["atras"][-1]], self.mano_agarre),
            self._seg("Devolviendo el taladro", T["volver"], p2["volver"]),
            self._seg("Dejandolo en la peana", T["dejar"], p2["dejar"], al_terminar=self._al_dejar),
            self._seg("Abriendo la mano", T["abrir"], [p2["dejar"][-1]], self.mano_abierta),
            self._seg("Retirando la mano", T["retirar"], p2["retirar"]),
            self._seg("Subiendo la mano", T["levantar"], p2["alejar"]),
            self._seg("Volviendo a reposo", T["reposo"], p2["reposo"],
                      np.array(POSICION_STANDBY, dtype=float), al_terminar=self._al_acabar),
        ]

    def _al_dejar(self, modelo, datos):
        _eq_activa(modelo, datos, self.eq_mano, False)
        self._soldar(modelo, datos, self.eq_peana, self.b_sop, self.b_tal)
        self.sujeto = False
        print("🖐️  Taladro devuelto a la peana")

    def _al_acabar(self, modelo, datos):
        if self.error is None:
            self.n_agujero += 1
            print("✅ Demo del taladro TERMINADA — [5] repetir (nuevo agujero) · [S] volver al teleop")
        else:
            print("⚠ Demo del taladro interrumpida — [5] reintentar · [S] volver al teleop")

    # ── cada paso de física ───────────────────────────────────────────────────
    def paso(self, modelo, datos, dt):
        """Se llama ANTES de cada mj_step: escribe ctrl del brazo y la mano."""
        if self.terminada:
            self._motor(modelo, datos, dt)
            # Diagnóstico: con la demo acabada el brazo vuelve a los SERVOS. Si al
            # segundo no sostienen la postura de reposo, el problema está en el modelo
            # (peso sin compensar, servos flojos o roces) y afecta también al teleop.
            if self._t_fin is not None:
                self._t_fin += dt
                if self._t_fin >= 1.0:
                    self._t_fin = None
                    dq = np.degrees(datos.qpos[self.qidx] - datos.ctrl[:len(ARM_JOINTS)])
                    if float(np.abs(dq).max()) > 1.0:
                        print("   ⚠ Con los servos, el brazo no sostiene el reposo: real−mando (°) "
                              + "  ".join(f"j{k + 1} {v:+.1f}" for k, v in enumerate(dq)))
                        choques = self._choques_vivos(modelo, datos)
                        print("      contactos del brazo/mano: "
                              + (", ".join(choques) if choques else "ninguno"))
                    else:
                        print("   ✓ Con los servos, el brazo sostiene bien el reposo.")
            return
        if self.seg is None:
            if not self.segmentos:
                self.terminada, self.fase = True, "Terminada"
                self._t_fin = 0.0
                return
            self.seg = self.segmentos.pop(0)
            self.t_seg = 0.0
            self.fase = self.seg["nombre"]
            self._mano_ini = datos.ctrl[OFFSET_MANO:OFFSET_MANO + N_ACT].copy()
        seg = self.seg
        self.t_seg += dt
        s = _minjerk(self.t_seg / seg["dur"])

        qs = seg["qs"]
        u = s * (len(qs) - 1)
        i = min(int(u), len(qs) - 2)
        q = qs[i] + (u - i) * (qs[i + 1] - qs[i])
        if seg["vibrar"] and self.omega > 1.0:            # vibración del taladro
            a = TALADRO_DEMO_VIBRACION
            q = q + np.array([0, 0, 0, a * math.sin(2 * math.pi * 23 * self.t_seg),
                              a * math.cos(2 * math.pi * 31 * self.t_seg), 0])
        if TALADRO_DEMO_BRAZO_CINEMATICO:
            # Brazo CINEMÁTICO: sus articulaciones se colocan EXACTAMENTE en el plan en
            # cada paso de física (como en una animación). Ni el peso de la mano, ni un
            # roce, ni una soldadura pueden desviarlo. Los dedos siguen siendo físicos.
            q_prev = self._q_cmd_prev if self._q_cmd_prev is not None else datos.qpos[self.qidx].copy()
            datos.qpos[self.qidx] = q
            datos.qvel[self.didx] = (q - q_prev) / max(dt, 1e-6)
            datos.ctrl[:len(ARM_JOINTS)] = q
            self._q_cmd_prev = q.copy()
            if seg["mano"] is not None:
                datos.ctrl[OFFSET_MANO:OFFSET_MANO + N_ACT] = (
                    self._mano_ini + s * (np.asarray(seg["mano"]) - self._mano_ini))
            self._motor(modelo, datos, dt)
            self._fin_de_segmento(modelo, datos, seg)
            return
        # Corrección integral: si el brazo se queda corto de forma sostenida (peso, un
        # roce...), el mando se adelanta un poco hasta que las articulaciones llegan.
        # Solo con el plan casi quieto: el retraso normal del servo al moverse no cuenta.
        err = q - datos.qpos[self.qidx]
        q_prev = getattr(self, "_q_plan_prev", q)
        quieto = float(np.abs(q - q_prev).max()) < 0.05 * dt
        self._q_plan_prev = q
        if TALADRO_DEMO_KI > 0.0 and quieto and float(np.abs(err).max()) < 0.3:
            self.integral = np.clip(self.integral + TALADRO_DEMO_KI * err * dt, -0.25, 0.25)
        datos.ctrl[:len(ARM_JOINTS)] = q + self.integral
        if seg["mano"] is not None:
            datos.ctrl[OFFSET_MANO:OFFSET_MANO + N_ACT] = (
                self._mano_ini + s * (np.asarray(seg["mano"]) - self._mano_ini))

        self._motor(modelo, datos, dt)
        self._fin_de_segmento(modelo, datos, seg)

    def _fin_de_segmento(self, modelo, datos, seg):
        if self.t_seg >= seg["dur"]:
            self.seg = None
            # ¿Ha llegado el brazo de verdad? (si no, algo lo frena: un choque)
            _, p_plan = self._fk(modelo, seg["qs"][-1])
            desvio = float(np.linalg.norm(datos.xpos[self.bm] - p_plan))
            if desvio > 0.02:
                dq = np.degrees(datos.qpos[self.qidx] - seg["qs"][-1])
                print(f"   ⚠ Al acabar '{seg['nombre']}' la mano estaba a {desvio * 100:.1f} cm "
                      f"de donde debía.\n      joints real−plan (°): "
                      + "  ".join(f"j{k + 1} {v:+.1f}" for k, v in enumerate(dq))
                      + "\n      corrección integral (°): "
                      + "  ".join(f"{v:+.1f}" for v in np.degrees(self.integral)))
                choques = self._choques_vivos(modelo, datos)
                print("      contactos del brazo/mano: " + (", ".join(choques) if choques else "ninguno"))
            if seg["al_terminar"] is not None:
                seg["al_terminar"](modelo, datos)

    def _choques_vivos(self, modelo, datos):
        """Contactos REALES ahora mismo del brazo o la mano con cualquier cosa
        (salvo los de dentro de la propia mano y mano↔taladro)."""
        vistos = {}
        for i in range(datos.ncon):
            c = datos.contact[i]
            b1, b2 = int(modelo.geom_bodyid[c.geom1]), int(modelo.geom_bodyid[c.geom2])
            implicados = self.cuerpos_brazo | self.cuerpos_mano
            if b1 not in implicados and b2 not in implicados:
                continue
            if b1 in self.cuerpos_mano and b2 in self.cuerpos_mano:
                continue
            if {b1, b2} & self.env.cuerpos_taladro and {b1, b2} & self.cuerpos_mano:
                continue
            k = f"{self._nombre_cuerpo(modelo, b1)} ↔ {self._nombre_cuerpo(modelo, b2)}"
            vistos[k] = max(vistos.get(k, 0.0), -float(c.dist))
        return [f"{k} ({v * 1000:.0f} mm)" for k, v in sorted(vistos.items(), key=lambda kv: -kv[1])[:4]]

    def _motor(self, modelo, datos, dt):
        """Gatillo: el motor gira si el índice aprieta MÁS que en el agarre normal.
        La broca que gira y está dentro del techo va haciendo el agujero."""
        env = self.env
        encendido = self.sujeto and datos.ctrl[OFFSET_MANO + 11] >= self.umbral_gatillo
        w_obj = TALADRO_DEMO_RPM * 2 * math.pi / 60 if encendido else 0.0
        self.omega += float(np.clip(w_obj - self.omega, -120 * dt, 120 * dt))   # rampa
        if self.omega > 0.0 or encendido:
            datos.qvel[env.da_giro] = self.omega
        self.motor = encendido
        if not (encendido and env.m_agujeros):
            return
        # ¿La punta ya está en el techo?
        r = float(modelo.geom_size[self.g_punta][0])
        bit_w = _unit(datos.xaxis[env.j_giro])
        tip = datos.geom_xpos[self.g_punta] + bit_w * r
        zt = self.z_techo
        if tip[2] < zt - 0.002:
            return
        k = self.n_agujero % len(env.m_agujeros)
        b, m = env.b_agujeros[k], env.m_agujeros[k]
        g = modelo.body_geomadr[b]
        if not self.agujero_colocado:
            if not hasattr(self, "_r_agujero"):
                self._r_agujero = float(modelo.geom_size[g][0])
            datos.mocap_pos[m] = (tip[0], tip[1], zt - 0.0012)
            datos.mocap_quat[m] = [1.0, 0.0, 0.0, 0.0]
            self.agujero_colocado = True
            print("🌀 La broca toca el techo: perforando...")
        self.progreso = max(self.progreso, float(np.clip((tip[2] - zt) / TALADRO_DEMO_PROFUNDIDAD, 0, 1)))
        modelo.geom_size[g][0] = 0.0015 + self.progreso * (self._r_agujero - 0.0015)

    def _fisica_demo(self, modelo, activar: bool):
        """Ajustes de física SOLO durante la demo (al salir se restauran):
          · El taladro hereda del <default> del brazo damping=3 y armature=0.02 en su
            freejoint (pensados para las articulaciones del ARCTOS): frenan su giro y
            la soldadura con la mano cede poco a poco → al bajar a la peana el taladro
            acababa girado dentro de la mano y luego la mano lo atravesaba al soltarlo.
          · noslip (del escenario [4]) hace el rozamiento de los dedos "rígido" y
            también empuja al taladro contra la soldadura.
          · Soldaduras más rígidas: el taladro no se mueve en la mano ni en la peana."""
        da = self.env.da
        if activar:
            if getattr(self, "_fisica_orig", None) is None:
                self._fisica_orig = dict(
                    damping=modelo.dof_damping[da:da + 6].copy(),
                    armature=modelo.dof_armature[da:da + 6].copy(),
                    friccion=modelo.dof_frictionloss[da:da + 6].copy(),
                    noslip=int(modelo.opt.noslip_iterations),
                    solref={eq: modelo.eq_solref[eq].copy() for eq in (self.eq_mano, self.eq_peana)},
                    solimp={eq: modelo.eq_solimp[eq].copy() for eq in (self.eq_mano, self.eq_peana)})
            modelo.dof_damping[da:da + 6] = 0.0
            modelo.dof_armature[da:da + 6] = 0.0
            modelo.dof_frictionloss[da:da + 6] = 0.0
            modelo.opt.noslip_iterations = 0
            for eq in (self.eq_mano, self.eq_peana):
                modelo.eq_solref[eq][:2] = (TALADRO_DEMO_SOLDADURA_RIGIDEZ, 1.0)
                modelo.eq_solimp[eq][:3] = (0.95, 0.99, 0.001)
        elif getattr(self, "_fisica_orig", None) is not None:
            o = self._fisica_orig
            modelo.dof_damping[da:da + 6] = o["damping"]
            modelo.dof_armature[da:da + 6] = o["armature"]
            modelo.dof_frictionloss[da:da + 6] = o["friccion"]
            modelo.opt.noslip_iterations = o["noslip"]
            for eq in (self.eq_mano, self.eq_peana):
                modelo.eq_solref[eq] = o["solref"][eq]
                modelo.eq_solimp[eq] = o["solimp"][eq]
            self._fisica_orig = None

    def terminar(self, modelo, datos):
        """Al salir de la demo: todo como estaba (el techo y los agujeros se quedan)."""
        if not self.ok:
            return
        _eq_activa(modelo, datos, self.eq_mano, False)
        _eq_activa(modelo, datos, self.eq_peana, False)
        self.sujeto, self.omega, self.motor = False, 0.0, False
        self.env._colisiones(modelo, True)       # el techo vuelve a ser sólido
        self._fisica_demo(modelo, False)
        for g, (ct, ca) in self.col_brazo_orig.items():
            modelo.geom_contype[g], modelo.geom_conaffinity[g] = ct, ca
        self.integral[:] = 0.0
        datos.ctrl[:len(ARM_JOINTS)] = datos.qpos[self.qidx]   # sin tirón al salir
        if self.env.visible:
            self.env.recolocar_taladro(modelo, datos)
        for i, v in enumerate(POSICION_STANDBY):
            datos.ctrl[OFFSET_MANO + i] = float(v)
        self.segmentos, self.seg, self.terminada = [], None, True
        mujoco.mj_forward(modelo, datos)


# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE PERCEPCIÓN 3D
# ══════════════════════════════════════════════════════════════════════════════

def profundidad_en_pixel(depth_frame: np.ndarray, px: int, py: int, radio: int = 8):
    """Mediana de profundidad (metros) en un parche alrededor de (px, py)."""
    h, w = depth_frame.shape
    region  = depth_frame[max(0, py-radio):min(h, py+radio),
                          max(0, px-radio):min(w, px+radio)]
    validos = region[region > 0]
    return float(np.median(validos)) / 1000.0 if len(validos) else None


def pixel_a_3d(px: int, py: int, z_m: float,
               ancho: int = ANCHO_CAM, alto: int = ALTO_CAM, f_px: float = F_PX):
    """Proyección inversa: pixel + profundidad → coordenadas 3D métricas.
    El centro óptico se toma en el centro del fotograma (ancho/2, alto/2)."""
    cx = ancho / 2.0
    cy = alto  / 2.0
    return (px - cx) * z_m / f_px, (py - cy) * z_m / f_px, z_m

def mapear_muneca_a_objetivo_brazo(x_m, y_m, z_m, neutro_camara, punto_neutro_brazo=None):
    """
    Convierte la posición 3D de la muñeca (relativa a la cámara, en metros)
    en un punto objetivo 3D para el efector del brazo ARCTOS (frame base
    del robot). 'neutro_camara' es (x0,y0,z0) capturado al calibrar con [A].

    'punto_neutro_brazo' es el punto 3D (frame base del ARCTOS) del que parte
    el movimiento — normalmente la posición REAL del efector en el instante
    de la calibración con [A], para que el brazo empiece a moverse desde
    donde ya estaba en la simulación en vez de saltar a un punto fijo. Si no
    se pasa (None), se usa ARM_OBJETIVO_NEUTRO de config.py como antes.
    """
    delta_cam = {
        "x": x_m - neutro_camara[0],
        "y": y_m - neutro_camara[1],
        "z": z_m - neutro_camara[2],
    }
    origen = punto_neutro_brazo if punto_neutro_brazo is not None else ARM_OBJETIVO_NEUTRO
    objetivo = list(origen)
    for i, eje_robot in enumerate(("robot_x", "robot_y", "robot_z")):
        eje_cam, signo = ARM_MAPEO_EJES[eje_robot]
        objetivo[i] += signo * delta_cam[eje_cam] * ARM_ESCALA_MOVIMIENTO[i]

    # Clip de seguridad: no salirse del radio máximo desde la base
    vec = np.array(objetivo)
    dist = np.linalg.norm(vec)
    if dist > ARM_RADIO_MAX:
        vec *= ARM_RADIO_MAX / dist
    vec[2] = max(vec[2], ARM_Z_MINIMA)
    return tuple(vec)


# ══════════════════════════════════════════════════════════════════════════════
# IK DEL BRAZO ARCTOS — Jacobiana amortiguada, resuelta por fotograma
# ══════════════════════════════════════════════════════════════════════════════
# Trasplantada tal cual de probar_ik_brazo.py (misma lógica, mismos parámetros
# por defecto) para que el brazo se mueva con la IK ya validada por separado.

# PASO 7.4 — centro REAL de la palma de la OrcaHand en el frame de "mano_mount", medido
# en orcahand_right_body.xml: punto medio entre la articulación de la muñeca (0, 0.092,
# 0.010) y el centro de los 4 nudillos (0.001, 0.181, 0.004). El OFFSET_LOCAL_PALMA de
# abajo caía ~3 cm más fuera, casi en los nudillos. Solo lo usa la IK de imitación
# (PALMA_CENTRO_REAL); el escenario del taladro sigue con el antiguo para no mover el techo.
OFFSET_LOCAL_PALMA_CENTRO = (0.0, 0.137, 0.007)
OFFSET_LOCAL_PALMA = (0.0, 0.165, 0.015)  # offset (frame local de "mano_mount")
                                           # hasta el centro aproximado de la palma —
                                           # se deja definido por si se quiere volver
                                           # a usar, pero el seguimiento por cámara
                                           # usa ahora OFFSET_LOCAL_MUNON (ver abajo).
OFFSET_LOCAL_MUNON = (0.0, 0.0, 0.0)      # sin offset: el propio origen de
                                           # "mano_mount" — la punta/muñón del
                                           # brazo, justo donde se atornilla la
                                           # mano. Es el punto que se calibra con
                                           # [A] y el que persigue la IK en el
                                           # seguimiento por cámara.


def resolver_ik_brazo(modelo, datos, objetivo_xyz, dof_idx, qpos_idx,
                       nombre_body_efector="mano_mount",
                       offset_local_efector=OFFSET_LOCAL_PALMA,
                       n_iter=8, lambda_amort=0.2, paso_max=0.08,
                       postura_referencia=None, ganancia_null=0.3,
                       q_inicial=None):
    """
    Varias mini-iteraciones de IK POR FOTOGRAMA (en vez de un único paso
    grande). Cada iteración recalcula la Jacobiana en la postura hipotética
    actual usando mj_kinematics (solo cinemática, sin física), así que
    converge de forma suave incluso cerca de singularidades.

    'offset_local_efector' es un desplazamiento (metros, frame LOCAL de
    'nombre_body_efector') desde el origen de ese body hasta el punto que
    realmente queremos llevar al objetivo — en este robot, el origen de
    "mano_mount" es solo la brida de montaje brazo↔mano; la palma real está
    desplazada hacia adelante.
    """
    body_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, nombre_body_efector)
    offset_local = np.array(offset_local_efector)
    n  = len(qpos_idx)
    lo = np.array([l for l, _ in LIMITES_CTRL_BRAZO[:n]])
    hi = np.array([h for _, h in LIMITES_CTRL_BRAZO[:n]])

    q = (np.array(q_inicial, dtype=float) if q_inicial is not None
         else np.array([datos.qpos[qi] for qi in qpos_idx]))
    qpos_original = {qi: datos.qpos[qi] for qi in qpos_idx}   # para restaurar al final

    for _ in range(n_iter):
        for k, qi in enumerate(qpos_idx):
            datos.qpos[qi] = q[k]
        mujoco.mj_kinematics(modelo, datos)          # recoloca el esqueleto, sin simular física

        R_mano = datos.xmat[body_id].reshape(3, 3)
        punto_efector = datos.xpos[body_id] + R_mano @ offset_local

        error = np.array(objetivo_xyz) - punto_efector

        jacp = np.zeros((3, modelo.nv))
        mujoco.mj_jac(modelo, datos, jacp, None, punto_efector, body_id)
        J = jacp[:, dof_idx]

        JJt = J @ J.T
        J_pinv_amort = J.T @ np.linalg.inv(JJt + (lambda_amort ** 2) * np.eye(3))
        delta_q = J_pinv_amort @ error

        if postura_referencia is not None:
            N = np.eye(len(dof_idx)) - J_pinv_amort @ J
            delta_q = delta_q + N @ (ganancia_null * (postura_referencia - q))

        norma = np.linalg.norm(delta_q)
        if norma > paso_max:
            delta_q *= paso_max / norma

        q = np.clip(q + delta_q, lo, hi)

    # IMPORTANTE: restauramos el estado real de la simulación — solo hemos
    # usado qpos como "borrador" para calcular Jacobianas, no debe quedar el
    # brazo teletransportado a la solución antes de que el motor de física lo
    # mueva de verdad (vía datos.ctrl[]).
    for qi in qpos_idx:
        datos.qpos[qi] = qpos_original[qi]
    mujoco.mj_kinematics(modelo, datos)

    return q


def landmarks_a_3d(world_lm, es_mano_izq: bool = False):
    """
    Convierte world_landmarks de MediaPipe al frame de referencia de la mano
    (palma = plano XY, dedos apuntan en +Y) en metros.

    Usa sistema ortogonal definido por los MCP centrales (Gram-Schmidt),
    igual que en orca_retargeter/orca_teleop.
    """
    pts = [np.array([lm.x, lm.y, lm.z]) for lm in world_lm.landmark]
    rel = [p - pts[LM_MUNECA] for p in pts]

    adelante = rel[LM_CORAZON_MCP]
    lateral  = rel[LM_MENIQUE_MCP] - rel[LM_INDICE_MCP]

    n_ad, n_lat = np.linalg.norm(adelante), np.linalg.norm(lateral)
    if n_ad < 1e-6 or n_lat < 1e-6:
        return [(0.0, 0.0, 0.0)] * 21

    adelante = adelante / n_ad
    lateral  = lateral / n_lat
    lateral  = lateral - np.dot(lateral, adelante) * adelante  # Gram-Schmidt
    n_lat2   = np.linalg.norm(lateral)
    if n_lat2 < 1e-6:
        return [(0.0, 0.0, 0.0)] * 21
    lateral = lateral / n_lat2
    arriba  = np.cross(lateral, adelante)
    arriba  = arriba / np.linalg.norm(arriba)

    OFFSET_ADAPTADOR = 0.12  # metros — offset del adaptador físico en el robot
    result = []
    for p in rel:
        sign_lat = -1.0 if es_mano_izq else 1.0
        result.append((
            sign_lat * np.dot(p, lateral),
            np.dot(p, adelante) + OFFSET_ADAPTADOR,
            np.dot(p, arriba),
        ))
    return result

# ══════════════════════════════════════════════════════════════════════════════
# PASO 2 — HÍBRIDO: posición de la mano (estéreo) → punto objetivo → IK joint1..3
# ══════════════════════════════════════════════════════════════════════════════

def _punta_brazo_fk(modelo, datos, q3, qpos_idx3, j_hombro, b_mano):
    """Vector hombro (ancla de joint2) → mano_mount, en ejes del mundo, SI joint1..3
    valieran q3. Solo cinemática: la simulación queda exactamente como estaba."""
    guarda = [float(datos.qpos[i]) for i in qpos_idx3]
    for k, i in enumerate(qpos_idx3):
        datos.qpos[i] = q3[k]
    mujoco.mj_kinematics(modelo, datos)
    v = np.array(datos.xpos[b_mano] - datos.xanchor[j_hombro])
    for k, i in enumerate(qpos_idx3):
        datos.qpos[i] = guarda[k]
    mujoco.mj_kinematics(modelo, datos)
    return v


def preparar_hibrido(modelo, datos, qpos_idx_brazo):
    """Alcance del ARCTOS y sus ejes 'fuera / arriba / delante', sacados de TU tabla
    ARM_IMITACION (T-pose y brazo al frente) → mismos signos que la imitación."""
    j2 = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, "joint2")
    bm = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "mano_mount")
    q_fuera   = angulos_humano_a_q_brazo(math.pi / 2, math.pi / 2, 0.0)   # T-pose
    q_delante = angulos_humano_a_q_brazo(0.0,         math.pi / 2, 0.0)   # brazo al frente
    v_fuera   = _punta_brazo_fk(modelo, datos, q_fuera,   qpos_idx_brazo[:3], j2, bm)
    v_delante = _punta_brazo_fk(modelo, datos, q_delante, qpos_idx_brazo[:3], j2, bm)

    arriba  = np.array([0.0, 0.0, 1.0])
    delante = _unitario(v_delante - (v_delante @ arriba) * arriba)
    fuera   = v_fuera - (v_fuera @ arriba) * arriba
    fuera   = _unitario(fuera - (fuera @ delante) * delante)

    # PASO 3 — longitudes del brazo y antebrazo DEL ROBOT, índices y límites
    j3 = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, "joint3")
    mujoco.mj_kinematics(modelo, datos)
    p2, p3, pm = datos.xanchor[j2].copy(), datos.xanchor[j3].copy(), datos.xpos[bm].copy()
    ids = [mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, f"joint{k}") for k in (1, 2, 3)]
    lo = np.array([max(IMITAR_LIMITES[f"joint{k + 1}"][0], LIMITES_CTRL_BRAZO[k][0]) for k in range(3)])
    hi = np.array([min(IMITAR_LIMITES[f"joint{k + 1}"][1], LIMITES_CTRL_BRAZO[k][1]) for k in range(3)])
    # PASO 6 — eje del codo del ROBOT en su T-pose. Sirve para saber después si el
    # robot está en la configuración "girada" (base +180°, hombro hacia atrás):
    # ahí su mano queda volteada 180° y hay que compensar el giro de muñeca.
    _qi3 = qpos_idx_brazo[:3]
    _guarda = [float(datos.qpos[i]) for i in _qi3]
    for k, i in enumerate(_qi3):
        datos.qpos[i] = q_fuera[k]
    mujoco.mj_kinematics(modelo, datos)
    eje_codo_tpose = np.array(datos.xaxis[j3])
    j6 = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, PRONO_JOINT)
    R_mano_tpose = np.array(datos.xmat[bm]).reshape(3, 3)       # orientación de la mano
    # Punto que persigue la IK: la PALMA de la OrcaHand (o el muñón, según config)
    _off_palma = OFFSET_LOCAL_PALMA_CENTRO if PALMA_CENTRO_REAL else OFFSET_LOCAL_PALMA
    off_punta = np.array(_off_palma if HIBRIDO_OBJETIVO == "palma" else OFFSET_LOCAL_MUNON,
                         dtype=float)
    alcance_punta = float(np.linalg.norm(datos.xpos[bm] + R_mano_tpose @ off_punta
                                         - datos.xanchor[j2]))
    # PASO 7.4 — codo → punto final (antebrazo + OrcaHand), fijo con joint4..6 quietos
    L_antebrazo_punta = float(np.linalg.norm(datos.xpos[bm] + R_mano_tpose @ off_punta
                                             - datos.xanchor[j3]))
    eje6_tpose   = np.array(datos.xaxis[j6])                     # eje del giro de muñeca
    for k, i in enumerate(_qi3):
        datos.qpos[i] = _guarda[k]
    mujoco.mj_kinematics(modelo, datos)
    _ejes = np.column_stack([fuera, arriba, delante])
    signo_codo = 1.0 if float((_ejes @ _eje_codo_humano_torso(math.pi / 2)) @ eje_codo_tpose) >= 0 else -1.0

    return {
        "off_punta":     off_punta,       # offset local (mano_mount) del punto final
        "alcance_punta": alcance_punta,   # hombro → punto final con el brazo recto (m)
        "L_antebrazo_punta": L_antebrazo_punta,   # codo → punto final (antebrazo + mano)
        "signo_codo":  signo_codo,
        "j6":          j6,
        "R_mano_tpose": R_mano_tpose,
        "eje6_tpose":  eje6_tpose,
        "j_hombro":    j2,
        "alcance":     float(np.linalg.norm(v_fuera)),
        "ejes":        np.column_stack([fuera, arriba, delante]),  # (fuera,arriba,delante) → mundo
        "j_codo":      j3,
        "b_codo":      int(modelo.jnt_bodyid[j3]),
        "b_mano":      bm,
        "L_brazo":     float(np.linalg.norm(p3 - p2)),
        "L_antebrazo": float(np.linalg.norm(pm - p3)),
        "qpos3":       np.array([modelo.jnt_qposadr[j] for j in ids], dtype=int),
        "dof3":        np.array([modelo.jnt_dofadr[j] for j in ids], dtype=int),
        "lo":          lo,
        "hi":          hi,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PASO 3 — DIRECCIONES + IK CON CODO Y MUÑECA (ideas del proyecto TRON 2)
# ══════════════════════════════════════════════════════════════════════════════

class FiltroOneEuro:
    """
    PASO 5 — Filtro One Euro (Casiez et al., 2012), el mismo del TRON 2.
    Se adapta a la velocidad: en REPOSO filtra mucho (no tiembla) y cuando te
    mueves RÁPIDO filtra poco (casi sin retraso). Una media móvil, en cambio,
    retrasa siempre lo mismo. Funciona con vectores (np.array).
    """

    def __init__(self, min_cutoff=None, beta=None, d_cutoff=1.0):
        self.min_cutoff = FILTRO_MIN_CUTOFF if min_cutoff is None else min_cutoff
        self.beta       = FILTRO_BETA if beta is None else beta
        self.d_cutoff   = d_cutoff
        self.reset()

    def reset(self):
        self.x = self.dx = self.t = None

    @staticmethod
    def _alfa(corte, dt):
        tau = 1.0 / (2.0 * math.pi * corte)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t):
        x = np.asarray(x, dtype=float)
        if self.x is None:
            self.x, self.dx, self.t = x.copy(), np.zeros_like(x), t
            return x.copy()
        dt = max(t - self.t, 1e-3)
        a_d = self._alfa(self.d_cutoff, dt)
        self.dx = a_d * (x - self.x) / dt + (1.0 - a_d) * self.dx
        a = self._alfa(self.min_cutoff + self.beta * float(np.linalg.norm(self.dx)), dt)
        self.x = a * x + (1.0 - a) * self.x
        self.t = t
        return self.x.copy()


def _eje_codo_humano_torso(az_rad):
    """Eje del codo del humano (horizontal, ⟂ al plano vertical de su brazo según
    el azimut) en componentes (fuera, arriba, delante). Solo importa su SIGNO
    relativo: se compara con el eje del codo del robot."""
    return np.array([math.cos(az_rad), 0.0, -math.sin(az_rad)])


def semilla_girada(q):
    """Misma q con la base girada 180° y el hombro inclinado hacia el otro lado:
    lleva a la solución con el codo doblado al OTRO lado ("codo arriba")."""
    q = np.asarray(q, dtype=float).copy()
    q[0] = _wrap(q[0] + math.pi)
    q[1] = -q[1]
    return q


def es_girada(q, q1_ref):
    """¿Está la base apuntando al lado contrario de tu brazo (configuración girada)?
    q1_ref = joint1 que pide el modo ángulos según tu azimut."""
    return abs(_wrap(float(q[0]) - float(q1_ref))) > math.pi / 2


def coste_ik(q, err, q_actual, q1_ref):
    """Error + penalizaciones. Evita que el rescate elija soluciones que exigen
    girar mucho la base (vueltas) o la configuración girada si no compensa."""
    c = err + IK_PENALIZA_BASE * abs(float(q[0]) - float(q_actual[0]))
    if es_girada(q, q1_ref):
        c += IK_PENALIZA_GIRADA
    return c


def rescatar_ik(modelo, datos, obj_c, obj_m, w_codo, hib, semillas, q_actual, q1_ref):
    """PASO 6 — resuelve desde varias posturas de partida y devuelve la de MENOR
    COSTE (error + penalizaciones): (q, error, coste, nombre)."""
    mejor = (None, float("inf"), float("inf"), "")
    for nombre, q0 in semillas:
        q, ec, em = resolver_ik_codo_muneca(modelo, datos, obj_c, obj_m, w_codo, hib, q0,
                                            n_iter=IK_RESCATE_ITER)
        e = math.hypot(w_codo * ec, em)
        c = coste_ik(q, e, q_actual, q1_ref)
        if c < mejor[2]:
            mejor = (q, e, c, nombre)
    return mejor


def _equivalente_en_rango(q, q_actual, lo, hi):
    """De q, q±2π, el que cae dentro de [lo, hi] más cerca de q_actual."""
    cands = [q + k * 2.0 * math.pi for k in (-1, 0, 1)]
    cands = [c for c in cands if lo <= c <= hi]
    if not cands:
        return float(np.clip(q, lo, hi))
    return float(min(cands, key=lambda c: abs(c - q_actual)))


def _perp(v, eje):
    """Componente de v perpendicular a eje (unitario), normalizada. None si no hay."""
    w = np.asarray(v, dtype=float) - float(np.dot(v, eje)) * np.asarray(eje)
    return _unitario(w) if np.linalg.norm(w) > 0.3 * max(np.linalg.norm(v), 1e-9) else None


def lateral_mano_humana_mundo(hand_wlm, torso, hib):
    """Dirección índice→meñique de TU mano, llevada a ejes del mundo del robot.
    La profundidad de MediaPipe Hands sale 'aplastada': se estira con PRONO_Z_ESCALA."""
    lat = _lm_hand(hand_wlm, LM_MENIQUE_MCP) - _lm_hand(hand_wlm, LM_INDICE_MCP)
    lat = np.array([lat[0], lat[1], lat[2] * PRONO_Z_ESCALA])
    derecha, arriba, delante, lado = torso
    t = np.array([lado * float(lat @ derecha), float(lat @ arriba), float(lat @ delante)])
    return _unitario(hib["ejes"] @ t)


def q6_para_orientacion(datos, hib, lat_local, lat_objetivo, q6_actual):
    """ORIENTACIÓN EN EL MUNDO (28-sep): qué joint6 deja la mano del robot con su
    índice→meñique apuntando igual que el tuyo, sea cual sea la postura del brazo
    que haya elegido la IK (normal, girada...). Devuelve None si no es fiable."""
    eje = _unitario(np.array(datos.xaxis[hib["j6"]]))
    if eje is None:
        return None
    lat_robot = np.array(datos.xmat[hib["b_mano"]]).reshape(3, 3) @ lat_local
    u, v = _perp(lat_robot, eje), _perp(lat_objetivo, eje)
    if u is None or v is None:
        return None
    delta = math.atan2(float(np.cross(u, v) @ eje), float(u @ v))
    return q6_actual + delta


def _suavizado_01(x, lo, hi):
    """0 por debajo de lo, 1 por encima de hi, curva suave (smoothstep) en medio."""
    t = float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))
    return t * t * (3.0 - 2.0 * t)


def enderezar(d_b, d_a):
    """Zona muerta en la flexión del codo. Con el brazo casi estirado, el ruido del
    seguimiento se convierte en pequeñas flexiones en direcciones aleatorias
    (en tus T-pose el codo mide 17-25° estando recto). Por debajo de
    ZONA_MUERTA_CODO[0] el antebrazo se alinea con el brazo; hasta [1] se atenúa."""
    theta = float(np.arccos(np.clip(np.dot(d_b, d_a), -1.0, 1.0)))
    s = math.sin(theta)
    if s < 1e-6:
        return np.asarray(d_a, dtype=float)
    lo, hi = np.radians(ZONA_MUERTA_CODO)
    theta_n = theta * _suavizado_01(theta, lo, hi)
    return (math.sin(theta - theta_n) * np.asarray(d_b) + math.sin(theta_n) * np.asarray(d_a)) / s


def peso_codo_humano(d_b, d_a):
    """Con el brazo casi recto la posición del codo no aporta (y es ruido):
    su peso en la IK baja a 0. Doblado, vale HIBRIDO_PESO_CODO."""
    ang = math.degrees(math.acos(float(np.clip(np.dot(d_b, d_a), -1.0, 1.0))))
    return HIBRIDO_PESO_CODO * _suavizado_01(ang, *HIBRIDO_CODO_RECTO)


def objetivos_codo_muneca(datos, d_b, d_a, hib):
    """Tus direcciones (fuera, arriba, delante) → dónde deben estar el codo y la
    muñeca del ARCTOS: SU hombro + SUS longitudes en TUS direcciones."""
    codo   = np.array(datos.xanchor[hib["j_hombro"]]) + hib["L_brazo"] * (hib["ejes"] @ d_b)
    muneca = codo + hib["L_antebrazo"] * (hib["ejes"] @ d_a)
    muneca[2] = max(muneca[2], ARM_Z_MINIMA)
    return codo, muneca


def codo_compatible(hombro, palma, codo_humano, L1, L2):
    """
    PASO 7.4 — Dónde PUEDE estar el codo del ARCTOS si su palma va a 'palma':
    a L1 del hombro y a L2 de la palma (L2 = antebrazo + OrcaHand). Esos puntos forman
    una circunferencia; se elige el más cercano a 'codo_humano' (tu dirección de
    brazo). Así el codo solo decide la POSTURA y ya no tira de la palma: antes el
    objetivo del codo estaba en tu dirección con las longitudes del robot, y con el
    codo doblado era imposible cumplir los dos → la palma se pasaba hasta 3-4 cm.
    Si no hay solución (palma demasiado lejos o cerca), devuelve codo_humano.
    """
    v = np.asarray(palma, dtype=float) - hombro
    d = float(np.linalg.norm(v))
    if d < 1e-6 or d <= abs(L1 - L2) + 1e-4:
        return np.asarray(codo_humano, dtype=float)
    u = v / d
    if d >= L1 + L2:                                   # brazo estirado: codo en la línea
        return hombro + u * L1
    a = (L1 * L1 - L2 * L2 + d * d) / (2.0 * d)        # distancia del hombro al centro
    h = math.sqrt(max(L1 * L1 - a * a, 0.0))           # radio de la circunferencia
    w = np.asarray(codo_humano, dtype=float) - hombro
    n = w - float(w @ u) * u                           # hacia TU codo, ⟂ a hombro→palma
    nn = float(np.linalg.norm(n))
    if nn < 1e-6:
        return np.asarray(codo_humano, dtype=float)
    return hombro + a * u + (n / nn) * h


def objetivos_codo_palma(datos, d_b, d_a, hib, longitudes_humano):
    """
    La mano del robot va donde va TU PALMA, teniendo en cuenta que el ARCTOS
    con la OrcaHand no tiene tus proporciones:
      · tu palma respecto a tu hombro = L1·dir_brazo + (L2 + muñeca→palma)·dir_antebrazo
        (con TUS huesos calibrados)
      · se divide por tu alcance total (brazo + antebrazo + mano) → fracción ≤ 1
      · se multiplica por el alcance del ARCTOS hasta SU palma
    El codo sigue la dirección de tu brazo (postura), con peso en la IK.
    La mano se considera alineada con el antebrazo: la flexión de muñeca ya la
    hace la propia OrcaHand, y contarla aquí también la duplicaría.
    """
    L1, L2 = longitudes_humano
    L3 = HUMANO_MUNECA_PALMA
    palma_h = L1 * np.asarray(d_b) + (L2 + L3) * np.asarray(d_a)
    frac = palma_h / (L1 + L2 + L3)                      # |frac| ≤ 1 siempre
    hombro = np.array(datos.xanchor[hib["j_hombro"]])
    v = (hib["ejes"] @ frac) * hib["alcance_punta"] * HIBRIDO_ESCALA
    r, r_max = float(np.linalg.norm(v)), HIBRIDO_ALCANCE_MAX * hib["alcance_punta"]
    if r > r_max:
        v *= r_max / r
    palma = hombro + v
    palma[2] = max(palma[2], ARM_Z_MINIMA)
    codo = hombro + hib["L_brazo"] * (hib["ejes"] @ np.asarray(d_b))
    if CODO_COMPATIBLE and "L_antebrazo_punta" in hib:      # PASO 7.4
        codo = codo_compatible(hombro, palma, codo, hib["L_brazo"], hib["L_antebrazo_punta"])
    return codo, palma


def resolver_ik_codo_muneca(modelo, datos, obj_c, obj_m, w_codo, hib, q_inicial,
                            n_iter=None, lam=0.05, paso_max=None, q_ref=None, w_cont=0.0):
    """
    IK de joint1..3 que persigue A LA VEZ el codo (con peso w_codo) y la muñeca
    del ARCTOS, por mínimos cuadrados amortiguados. Como el ARCTOS no puede
    reproducir cualquier postura humana (hombro de 2 ejes), busca el mejor
    compromiso. Tomado del TRON 2:
      · si una articulación se saldría de su límite, se BLOQUEA y las demás
        compensan (en vez de recortar y quedarse con error)
      · búsqueda lineal: solo se aceptan pasos que NO empeoran el error
    Solo usa cinemática (sin física) y deja la simulación como estaba.
    PASO 7.2 — con q_ref y w_cont > 0 (m/rad) también penaliza alejarse de q_ref
    (la solución anterior): cerca de una singularidad no gira la base media vuelta
    para ganar 1 cm. Donde el brazo está bien condicionado apenas influye y, con el
    objetivo quieto, converge igual al punto exacto (no deja error permanente).
    Devuelve (q, error_codo_m, error_muneca_m) — errores geométricos, sin la penalización.
    """
    n_iter   = HIBRIDO_IK_ITER if n_iter is None else n_iter
    paso_max = HIBRIDO_IK_PASO if paso_max is None else paso_max
    qidx, didx, lo, hi = hib["qpos3"], hib["dof3"], hib["lo"], hib["hi"]
    jc, bc, bm = hib["j_codo"], hib["b_codo"], hib["b_mano"]
    guarda = datos.qpos[qidx].copy()
    jac = np.zeros((3, modelo.nv))
    off = hib.get("off_punta", np.zeros(3))

    def fijar(q):
        datos.qpos[qidx] = q
        mujoco.mj_kinematics(modelo, datos)
        mujoco.mj_comPos(modelo, datos)          # necesario para mj_jac

    def punta():
        """Punto final que se persigue: palma de la OrcaHand (o muñón)."""
        return datos.xpos[bm] + datos.xmat[bm].reshape(3, 3) @ off

    cont = q_ref is not None and w_cont > 0.0
    q_ref = np.asarray(q_ref, dtype=float) if cont else None
    n_filas = 9 if cont else 6

    def errores(qq):
        ec = float(np.linalg.norm(obj_c - datos.xanchor[jc]))
        em = float(np.linalg.norm(obj_m - punta()))
        tot = float(np.hypot(w_codo * ec, em))
        if cont:
            tot = float(np.hypot(tot, w_cont * np.linalg.norm(qq - q_ref)))
        return tot, ec, em

    q = np.clip(np.asarray(q_inicial, dtype=float), lo, hi)
    fijar(q)
    err = errores(q)[0]
    for _ in range(n_iter):
        p_c, p_m = datos.xanchor[jc].copy(), punta().copy()
        mujoco.mj_jac(modelo, datos, jac, None, p_c, bc)
        J_c = jac[:, didx].copy()
        mujoco.mj_jac(modelo, datos, jac, None, p_m, bm)
        J_m = jac[:, didx].copy()
        J = np.vstack([w_codo * J_c, J_m])
        e = np.concatenate([w_codo * (obj_c - p_c), obj_m - p_m])
        if cont:                                             # PASO 7.2: continuidad
            J = np.vstack([J, w_cont * np.eye(3)])
            e = np.concatenate([e, w_cont * (q_ref - q)])

        libres = np.ones(3, dtype=bool)
        for _ in range(3):                                   # bloqueo de límites
            Jl = J * libres
            dq = Jl.T @ np.linalg.solve(Jl @ Jl.T + lam ** 2 * np.eye(n_filas), e)
            dq[~libres] = 0.0
            fuera = libres & (((q + dq) < lo) | ((q + dq) > hi))
            if not fuera.any():
                break
            libres &= ~fuera
        mayor = float(np.abs(dq).max())
        if mayor > paso_max:
            dq *= paso_max / mayor

        aceptado, alfa = False, 1.0                          # búsqueda lineal
        for _ in range(4):
            q_n = np.clip(q + alfa * dq, lo, hi)
            fijar(q_n)
            err_n = errores(q_n)[0]
            if err_n <= err + 1e-4:
                q, err, aceptado = q_n, err_n, True
                break
            alfa *= 0.5
        if not aceptado:
            fijar(q)
            break
        if err < 1e-3 or alfa * min(mayor, paso_max) < 1e-5:   # llegó / ya no avanza
            break

    fijar(q)
    _, ec, em = errores(q)
    fijar(guarda)                                            # la simulación, como estaba
    return q, ec, em


def objetivo_mano_hibrido(datos, v_humano, long_brazo, hib):
    """Tu vector hombro→muñeca (m) → punto (mundo) donde debe estar mano_mount."""
    frac = np.asarray(v_humano, dtype=float) / max(long_brazo, 1e-3)
    n = float(np.linalg.norm(frac))
    if n > 1.0:                       # ruido del estéreo: nunca "más que estirado"
        frac /= n
    v = hib["ejes"] @ frac * hib["alcance"] * HIBRIDO_ESCALA
    r, r_max = float(np.linalg.norm(v)), HIBRIDO_ALCANCE_MAX * hib["alcance"]
    if r > r_max:
        v *= r_max / r
    obj = np.array(datos.xanchor[hib["j_hombro"]]) + v
    obj[2] = max(obj[2], ARM_Z_MINIMA)
    return obj

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
    PASO 7.2 — Rechaza medidas IMPOSIBLES antes de filtrarlas.

    Una mano humana no se teletransporta. Si el objetivo de la palma (o del codo)
    del robot salta más de  SALTO_VEL_MAX · Δt + SALTO_MARGEN  respecto a la última
    medida buena, es un error de medida (codo mal colocado, profundidad del fondo,
    cambio de fuente estéreo↔MediaPipe...) y ese fotograma se ignora.
    Importante: va ANTES del One Euro, porque el One Euro, al ver un cambio brusco,
    cree que te mueves rápido y deja de filtrar → el error pasaba casi entero.
    Si el 'salto' se mantiene, el umbral crece con el tiempo (Δt) y acaba
    aceptándose: era un movimiento real.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.ref, self.t_ref = None, None
        self.rechazados = 0            # total (para el diagnóstico)

    def aceptar(self, puntos, t) -> bool:
        puntos = [np.asarray(p, dtype=float) for p in puntos]
        if self.ref is None or SALTO_VEL_MAX <= 0:
            self.ref, self.t_ref = puntos, t
            return True
        limite = SALTO_VEL_MAX * (t - self.t_ref) + SALTO_MARGEN
        salto  = max(float(np.linalg.norm(p - r)) for p, r in zip(puntos, self.ref))
        if salto <= limite:
            self.ref, self.t_ref = puntos, t
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

# ══════════════════════════════════════════════════════════════════════════════
# ÁNGULOS DEL BRAZO HUMANO (MediaPipe Pose → marco del torso)
# ══════════════════════════════════════════════════════════════════════════════

def _unitario(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-6 else None


def _angulos_desde_puntos(P, vis, brazo: str = "derecho",
                          vis_min: float = POSE_VISIBILIDAD_MIN):
    """
    Devuelve los ángulos del brazo humano, medidos respecto al TORSO (no a la
    cámara), o None si los puntos necesarios no se ven con confianza.

    Marco del torso (se construye con hombros y caderas):
        derecha : de tu hombro izquierdo al derecho
        arriba  : de la cadera al hombro
        delante : hacia donde miras
    Así los ángulos no cambian si te giras o te mueves delante de la cámara.

    Devuelve un dict con (todo en GRADOS):
        "azimut"       giro del brazo (hombro→codo) alrededor de la vertical.
                       0 = apunta al frente | +90 = hacia fuera (lado del brazo)
                       | -90 = cruzado hacia el otro lado | ±180 = hacia atrás
        "elevacion"    0 = brazo colgando | 90 = horizontal | 180 = hacia arriba
        "codo"         flexión del codo. 0 = brazo estirado | ~150 = muy doblado
        "azimut_muneca" igual que "azimut" pero para la línea hombro→MUÑECA
        "azimut_fiable" False si el brazo está casi vertical (el azimut es ruido)
        "ref"          "caderas" o "vertical" (cómo se obtuvo el eje 'arriba')
    """
    # P(i)   → punto 3D (np.array, metros) del landmark i, en ejes de cámara
    #          (x = derecha de la imagen, y = ABAJO, z = alejándose de la cámara)
    # vis(i) → confianza 0..1 de ese punto (0 = no disponible)

    if brazo == "derecho":
        i_h, i_c, i_m, lado = PS_HOMBRO_DER, PS_CODO_DER, PS_MUNECA_DER, 1.0
    else:
        i_h, i_c, i_m, lado = PS_HOMBRO_IZQ, PS_CODO_IZQ, PS_MUNECA_IZQ, -1.0

    # Puntos imprescindibles: hombro, codo y muñeca del brazo + ambos hombros
    for i in (i_h, i_c, i_m, PS_HOMBRO_IZQ, PS_HOMBRO_DER):
        if vis(i) < vis_min:
            return None

    # Eje "arriba": con las caderas si se ven; si no (torso cortado por el
    # encuadre), con la vertical de la cámara (y de imagen crece hacia ABAJO).
    if ARRIBA_REF == "caderas" and vis(PS_CADERA_IZQ) >= vis_min and vis(PS_CADERA_DER) >= vis_min:
        arriba = _unitario((P(PS_HOMBRO_IZQ) + P(PS_HOMBRO_DER)) / 2.0
                           - (P(PS_CADERA_IZQ) + P(PS_CADERA_DER)) / 2.0)
        ref = "caderas"
    else:
        arriba, ref = np.array([0.0, -1.0, 0.0]), "vertical"
    derecha = _unitario(P(PS_HOMBRO_DER) - P(PS_HOMBRO_IZQ))
    if arriba is None or derecha is None:
        return None
    derecha = _unitario(derecha - np.dot(derecha, arriba) * arriba)   # ortogonalizar
    if derecha is None:
        return None
    delante = np.cross(arriba, derecha)       # ya es unitario (ortogonales)

    def a_torso(v):
        return np.array([np.dot(v, derecha), np.dot(v, arriba), np.dot(v, delante)])

    u = _unitario(P(i_c) - P(i_h))     # brazo (hombro→codo)
    w = _unitario(P(i_m) - P(i_c))     # antebrazo (codo→muñeca)
    s = _unitario(P(i_m) - P(i_h))     # hombro→muñeca
    if u is None or w is None or s is None:
        return None

    r, a, f = a_torso(u)
    elevacion = math.degrees(math.acos(float(np.clip(-a, -1.0, 1.0))))
    azimut    = math.degrees(math.atan2(lado * r, f))
    codo      = math.degrees(math.acos(float(np.clip(np.dot(u, w), -1.0, 1.0))))
    rs, _, fs = a_torso(s)
    azimut_m  = math.degrees(math.atan2(lado * rs, fs))
    sv = a_torso(P(i_m) - P(i_h))      # hombro→muñeca en METROS, ejes del torso
    wr, wa, wf = a_torso(w)             # antebrazo en ejes del torso

    return {
        "azimut":        azimut,
        "elevacion":     elevacion,
        "codo":          codo,
        "azimut_muneca": azimut_m,
        "azimut_fiable": AZIMUT_ELEV_MIN < elevacion < 180.0 - AZIMUT_ELEV_MIN,
        "ref":           ref,
        "antebrazo": w,        # unitario codo→muñeca, ejes de cámara
        "arriba":    arriba,   # vertical del torso, ejes de cámara
        "derecha":   derecha,  # ejes del torso (para el eje del codo del robot)
        "delante":   delante,
        "lado":      lado,
        "hombro_muneca": np.array([lado * sv[0], sv[1], sv[2]]),   # (fuera, arriba, delante) [m]
        # PASO 3 — DIRECCIONES unitarias en (fuera, arriba, delante), como el TRON 2:
        "dir_brazo":     np.array([lado * r,  a,  f]),    # hombro→codo
        "dir_antebrazo": np.array([lado * wr, wa, wf]),   # codo→muñeca
    }

def _lm_hand(hand_world_lm, i):
    l = hand_world_lm.landmark[i]
    return np.array([l.x, l.y, l.z], float)

def _wrap(x):
    return (x + math.pi) % (2 * math.pi) - math.pi


# (Aquí había una versión ANTIGUA de calcular_pronosupinacion, con "arriba", que
#  ANULABA a la nueva —la de "eje_ref", al principio del archivo— porque Python se
#  queda con la última definición. Eliminada.)

def flexion_muneca_rel_antebrazo(hand_world_lm, antebrazo):
    """Flexión (rad) de la mano respecto al ANTEBRAZO, no a la cámara."""
    a = _unitario(antebrazo)
    if a is None:
        return None
    mcp = (_lm_hand(hand_world_lm, LM_INDICE_MCP) + _lm_hand(hand_world_lm, LM_CORAZON_MCP) +
           _lm_hand(hand_world_lm, LM_ANULAR_MCP) + _lm_hand(hand_world_lm, LM_MENIQUE_MCP)) / 4.0
    d   = mcp - _lm_hand(hand_world_lm, LM_MUNECA)
    lat = _lm_hand(hand_world_lm, LM_MENIQUE_MCP) - _lm_hand(hand_world_lm, LM_INDICE_MCP)
    eje = _unitario(lat - (lat @ a) * a)               # bisagra ⟂ antebrazo
    if eje is None:
        return None
    d_p = _unitario(d - (d @ eje) * eje)
    if d_p is None:
        return None
    return -math.atan2(float(np.cross(a, d_p) @ eje), float(a @ d_p))

def calcular_angulos_brazo_humano(pose_world_lm, brazo: str = "derecho",
                                  vis_min: float = POSE_VISIBILIDAD_MIN):
    """Ángulos del brazo usando los puntos 3D 'world' de MediaPipe Pose
    (profundidad ESTIMADA por la red neuronal, poco fiable en el eje z)."""
    lm = pose_world_lm.landmark
    return _angulos_desde_puntos(
        lambda i: np.array([lm[i].x, lm[i].y, lm[i].z]),
        lambda i: lm[i].visibility, brazo, vis_min)


def profundidad_robusta(depth_frame: np.ndarray, px: int, py: int,
                        radio: int = PROF_RADIO_PX, percentil: float = PROF_PERCENTIL):
    """Profundidad (m) en un parche alrededor de (px, py), en coordenadas del mapa
    de profundidad. Usa un percentil BAJO (no la mediana): en los bordes del brazo
    el parche mezcla brazo (cerca) y fondo (lejos), y así nos quedamos con el brazo."""
    h, w = depth_frame.shape
    if not (0 <= px < w and 0 <= py < h):
        return None
    region  = depth_frame[max(0, py - radio):min(h, py + radio + 1),
                          max(0, px - radio):min(w, px + radio + 1)]
    validos = region[region > 0]
    if len(validos) < PROF_MIN_PIXELES:
        return None
    return float(np.percentile(validos, percentil)) / 1000.0


class EstimadorLongitudesBrazo:
    """
    Mide cuánto miden el brazo (hombro→codo) y el antebrazo (codo→muñeca) del
    usuario, y sirve para dos cosas:
      · comprobar que un codo detectado es CREÍBLE (huesos con su longitud normal)
      · reconstruir el codo cuando MediaPipe lo coloca mal o no lo ve

    Las longitudes se APRENDEN SOLO tras llamar a iniciar_calibracion() (al pulsar
    [A]): se promedian 'n_objetivo' fotogramas válidos y luego se CONGELAN.
    Si se pasa 'manual' = (brazo, antebrazo) en metros, no hace falta calibrar.
    """
    BANDA_BRAZO     = (0.22, 0.38)   # límites absolutos razonables (m)
    BANDA_ANTEBRAZO = (0.18, 0.34)

    def __init__(self, manual=None, tol: float = LONG_BRAZO_TOL,
                 n_objetivo: int = CALIB_HUESOS_FRAMES):
        self.manual     = manual
        self.tol        = tol
        self.n_objetivo = n_objetivo
        self.h1, self.h2 = [], []
        self._fijas     = None     # (brazo, antebrazo) ya congeladas
        self.calibrando = False
        self.ultimo_rel = None     # último vector hombro→codo CREÍBLE (para desambiguar)
        self.motivo_fallo = ""     # por qué falló la última medición estéreo (diagnóstico)

    # — Estado de la calibración —
    @property
    def calibrado(self) -> bool:
        return self.manual is not None or self._fijas is not None

    @property
    def progreso(self) -> int:
        return len(self.h1)

    @property
    def longitudes(self):
        if self.manual is not None:
            return tuple(self.manual)
        return self._fijas

    def iniciar_calibracion(self):
        """Empieza a aprender los huesos (se llama al pulsar [A])."""
        if self.manual is not None:
            return
        self.h1, self.h2 = [], []
        self._fijas      = None
        self.calibrando  = True
        self.ultimo_rel  = None

    def codo_creible(self, S, E, W, aprender: bool = True) -> bool:
        l1, l2 = float(np.linalg.norm(E - S)), float(np.linalg.norm(W - E))
        en_banda = (self.BANDA_BRAZO[0] <= l1 <= self.BANDA_BRAZO[1] and
                    self.BANDA_ANTEBRAZO[0] <= l2 <= self.BANDA_ANTEBRAZO[1])
        ref = self.longitudes
        if ref is None:
            ok = en_banda
        else:
            ok = (abs(l1 - ref[0]) <= self.tol * ref[0] and
                  abs(l2 - ref[1]) <= self.tol * ref[1])
        if ok and aprender and en_banda and self.calibrando:
            self.h1.append(l1)
            self.h2.append(l2)
            if len(self.h1) >= self.n_objetivo:
                self._fijas     = (float(np.median(self.h1)), float(np.median(self.h2)))
                self.calibrando = False
                print(f"🦴 Huesos calibrados: brazo={self._fijas[0]:.3f} m  "
                      f"antebrazo={self._fijas[1]:.3f} m")
        if ok:
            self.ultimo_rel = E - S
        return ok

    def reconstruir_codo(self, S, W, abajo=np.array([0.0, 1.0, 0.0])):
        """
        Posición del codo sabiendo hombro S, muñeca W y las longitudes de los dos
        huesos. Si el brazo está estirado, el codo cae en la línea S→W. Si no, hay
        una circunferencia de posiciones posibles; se elige el punto más cercano a
        donde estaba el codo en el último fotograma creíble (el codo se mueve de forma
        continua) y, si no hay ninguno, el más 'caído' hacia 'abajo' (gravedad, ejes cámara).
        """
        ref = self.longitudes
        if ref is None:
            return None
        L1, L2 = ref
        v = W - S
        d = float(np.linalg.norm(v))
        if d < 1e-6:
            return None
        u = v / d
        if d >= L1 + L2:                       # brazo estirado (o más): codo en la línea
            if d > (L1 + L2) * (1.0 + CODO_ESTIRADO_MARGEN):
                return None                    # muñeca mal medida → no inventar un codo recto
            return S + u * (d * L1 / (L1 + L2))
        if d <= abs(L1 - L2) + 1e-3:
            return None
        a = (L1 ** 2 - L2 ** 2 + d ** 2) / (2.0 * d)
        h = math.sqrt(max(L1 ** 2 - a ** 2, 0.0))
        pref = self.ultimo_rel if self.ultimo_rel is not None else abajo
        n = pref - np.dot(pref, u) * u
        nn = float(np.linalg.norm(n))
        if nn < 1e-6:
            n = np.cross(u, np.array([1.0, 0.0, 0.0]))
            nn = float(np.linalg.norm(n))
            if nn < 1e-6:
                return None
        return S + u * a + (n / nn) * h


def corregir_muneca_por_longitud(S, px, py, z_medida, L, ancho, alto, f_px, z_ref=None,
                                  radio=None):
    """
    La muñeca NO puede estar más lejos del hombro que brazo+antebrazo (L).
    Si lo está, lo que falla es su PROFUNDIDAD (p.ej. el estéreo midió la pared de
    detrás de la mano); su posición en la IMAGEN (px, py) sí es fiable. Se recoloca
    sobre el mismo rayo de la cámara, justo a distancia L del hombro S.
    De las dos soluciones (delante / detrás) se elige la más cercana a z_ref
    (profundidad relativa de MediaPipe) o, si no la hay, a la medida.
    Devuelve el punto corregido, o None si la medida ya era posible.
    """
    d = np.array([(px - ancho / 2.0) / f_px, (py - alto / 2.0) / f_px, 1.0])  # rayo (z = 1)
    if np.linalg.norm(d * z_medida - S) <= L:
        return None
    # Se recoloca a distancia `radio` del hombro (por defecto L = brazo estirado).
    # Usar L SIEMPRE forzaba el codo a 0° (brazo recto) cada vez que actuaba.
    L = L if radio is None else float(min(radio, L))
    a = float(d @ d)
    b = -2.0 * float(d @ S)
    c = float(S @ S) - L * L
    disc = b * b - 4.0 * a * c
    if disc < 0.0:                       # el rayo no llega a la esfera: su punto más cercano
        z = float(d @ S) / a
    else:
        r = math.sqrt(disc)
        z1, z2 = (-b - r) / (2.0 * a), (-b + r) / (2.0 * a)   # delante / detrás del hombro
        ref = z_ref if z_ref is not None else z_medida
        z = z1 if abs(z1 - ref) <= abs(z2 - ref) else z2
    return d * max(z, PROF_Z_MIN)


def calcular_angulos_brazo_estereo(pose_lm, frame_depth, f_px: float,
                                   brazo: str = "derecho",
                                   vis_min: float = POSE_VISIBILIDAD_MIN,
                                   ancho: int = ANCHO_CAM, alto: int = ALTO_CAM,
                                   estimador: "EstimadorLongitudesBrazo" = None,
                                   pose_world_lm=None):
    """
    Ángulos del brazo usando la profundidad REAL de la OAK-D:
      · posición en la imagen (x, y)  ← MediaPipe Pose (pose_landmarks, normalizados)
      · profundidad (z)               ← mapa estéreo, en el píxel de cada articulación
    Cada articulación se proyecta a 3D con pixel_a_3d() y luego se calculan los
    ángulos igual que con MediaPipe.

    Si una articulación no tiene profundidad estéreo válida, en vez de perder el
    brazo entero se rellena (ver PROF_RELLENO_MEDIAPIPE): parche más grande y, si
    tampoco, profundidad relativa de MediaPipe (pose_world_lm) anclada al estéreo.

    Con un 'estimador':
      · un codo con huesos de longitud imposible se RECONSTRUYE con hombro y muñeca
      · si devuelve None, 'estimador.motivo_fallo' explica por qué
    El resultado lleva "fuentes" (de dónde salió la profundidad de hombro/codo/muñeca:
    E = estéreo, E+ = estéreo parche grande, M = MediaPipe anclado, R = reconstruido).
    """
    nombres = {PS_HOMBRO_IZQ: "hombro izq", PS_HOMBRO_DER: "hombro der",
               PS_CODO_IZQ: "codo izq",     PS_CODO_DER: "codo der",
               PS_MUNECA_IZQ: "muñeca izq", PS_MUNECA_DER: "muñeca der",
               PS_CADERA_IZQ: "cadera izq", PS_CADERA_DER: "cadera der"}
    fallos = []

    def fallar():
        if estimador is not None:
            estimador.motivo_fallo = "; ".join(fallos) if fallos else "puntos insuficientes"
        return None

    lm  = pose_lm.landmark
    wl  = pose_world_lm.landmark if pose_world_lm is not None else None
    dh, dw = frame_depth.shape

    if brazo == "derecho":
        i_h, i_c, i_m, i_h2 = PS_HOMBRO_DER, PS_CODO_DER, PS_MUNECA_DER, PS_HOMBRO_IZQ
    else:
        i_h, i_c, i_m, i_h2 = PS_HOMBRO_IZQ, PS_CODO_IZQ, PS_MUNECA_IZQ, PS_HOMBRO_DER
    caderas = (PS_CADERA_IZQ, PS_CADERA_DER)

    def usable(i):
        l = lm[i]
        return l.visibility >= vis_min and 0.0 <= l.x < 1.0 and 0.0 <= l.y < 1.0

    def motivo_no_usable(i):
        l = lm[i]
        if l.visibility < vis_min:
            return f"{nombres[i]}: visibilidad {l.visibility:.2f} < {vis_min:.2f}"
        return f"{nombres[i]}: fuera de imagen"

    # ── 1) Puntos imprescindibles VISIBLES en la imagen ───────────────────────
    codo_calibrable = estimador is not None and estimador.longitudes is not None
    for i in (i_h, i_h2, i_m):
        if not usable(i):
            fallos.append(motivo_no_usable(i))
    if not usable(i_c) and not codo_calibrable:
        fallos.append(motivo_no_usable(i_c) + " (y sin huesos calibrados para reconstruirlo)")
    if fallos:
        return fallar()

    # ── 2) Profundidad estéreo de cada punto (parche normal → parche grande) ──
    def z_estereo(xn, yn, percentil):
        for radio, etiqueta in ((PROF_RADIO_PX, "E"), (2 * PROF_RADIO_PX, "E+")):
            z = profundidad_robusta(frame_depth, int(xn * dw), int(yn * dh),
                                    radio=radio, percentil=percentil)
            if z is not None and PROF_Z_MIN < z < PROF_Z_MAX:
                return z, etiqueta
            if not PROF_RELLENO_MEDIAPIPE:
                break          # comportamiento antiguo: un solo intento
        return None, None

    z, fuente = {}, {}
    # Hombros: medidos en el PECHO (ver HOMBRO_PROF_HACIA_TORSO)
    x_med = (lm[i_h].x + lm[i_h2].x) / 2.0
    y_med = (lm[i_h].y + lm[i_h2].y) / 2.0
    for i in (i_h, i_h2):
        xs = lm[i].x + HOMBRO_PROF_HACIA_TORSO * (x_med - lm[i].x)
        ys = lm[i].y + HOMBRO_PROF_HACIA_TORSO * (y_med - lm[i].y)
        zi, f = z_estereo(xs, ys, 50)
        if zi is not None:
            z[i], fuente[i] = zi, f
    for i in (i_c, i_m) + caderas:
        if usable(i):
            zi, f = z_estereo(lm[i].x, lm[i].y, PROF_PERCENTIL)
            if zi is not None:
                z[i], fuente[i] = zi, f

    # Descarta puntos cuya profundidad se va muy lejos del resto (= se midió el fondo)
    if z:
        z_med = float(np.median(list(z.values())))
        for i in list(z):
            if abs(z[i] - z_med) > PROF_DISPERSION_Z_MAX:
                fallos.append(f"{nombres[i]}: estéreo incoherente ({z[i]:.2f} m vs {z_med:.2f} m)")
                del z[i], fuente[i]

    # ── 3) Relleno de los que faltan con MediaPipe anclado al estéreo ─────────
    anclas = [a for a in (i_h, i_h2) + caderas if a in z and fuente[a] != "M"]

    def z_mediapipe(i):
        """Profundidad de MediaPipe anclada al estéreo del primer punto ancla."""
        a = anclas[0]
        return float(np.clip(z[a] + (wl[i].z - wl[a].z), PROF_Z_MIN + 0.01, PROF_Z_MAX - 0.01))

    puede_mp = PROF_RELLENO_MEDIAPIPE and wl is not None and bool(anclas)

    # ── 3a) Estéreo de codo y muñeca VALIDADO con MediaPipe (idea del TRON 2) ──
    # MediaPipe da una profundidad RELATIVA poco precisa pero nunca disparatada;
    # el estéreo es preciso pero a veces lee el FONDO (pared tras la mano) o el
    # torso. Se predice dónde debería estar cada punto (MediaPipe anclado al
    # hombro) y, si el estéreo se aleja más de PROF_TOL_MEDIAPIPE, no se usa:
    #   · codo con huesos calibrados → se descarta y se RECONSTRUYE (paso 4)
    #   · muñeca (o codo sin huesos) → se usa la predicción de MediaPipe ("M!")
    #
    # CORRECCIÓN (28-sep): sustituir la MUÑECA por la predicción de MediaPipe
    # mezclaba dos fuentes (codo del estéreo + muñeca de MediaPipe) y FABRICABA
    # flexiones falsas: en T-pose el codo salía 75-86° (MediaPipe solo decía 26°).
    # Ahora solo se valida el CODO, y solo con huesos calibrados: si no cuadra, se
    # reconstruye con los huesos (su flexión depende solo de hombro-muñeca, que es
    # estéreo). La muñeca sigue protegida por corregir_muneca_por_longitud (3b).
    if puede_mp and PROF_TOL_MEDIAPIPE > 0 and codo_calibrable:
        if i_c in z and fuente[i_c] != "M":
            if abs(z[i_c] - z_mediapipe(i_c)) > PROF_TOL_MEDIAPIPE:
                del z[i_c], fuente[i_c]
    # El codo sin estéreo se prefiere RECONSTRUIR con los huesos (paso 4, más exacto);
    # MediaPipe solo se usa para él si no hay huesos calibrados.
    necesarios = (i_h, i_h2, i_m) + ((i_c,) if usable(i_c) and not codo_calibrable else ())
    for i in necesarios:
        if i in z:
            continue
        if puede_mp:
            z[i], fuente[i] = z_mediapipe(i), "M"
        else:
            fallos.append(f"{nombres[i]}: sin profundidad estéreo"
                          + ("" if anclas else " (ni en hombros ni en caderas)"))
    if any(i not in z for i in (i_h, i_h2, i_m)):
        return fallar()

    pts = {i: np.array(pixel_a_3d(lm[i].x * ancho, lm[i].y * alto, zi, ancho, alto, f_px))
           for i, zi in z.items()}

    # ── 3b) Muñeca imposible (más lejos del hombro que brazo+antebrazo) ───────
    # Suele ser el estéreo leyendo el FONDO tras la mano (brazo en alto, mano
    # pequeña en la imagen). Se corrige solo su profundidad, sobre su rayo.
    if estimador is not None and estimador.longitudes is not None:
        _L = sum(estimador.longitudes) * (1.0 + CODO_ESTIRADO_MARGEN)
        # Si la muñeca es imposible, se recoloca a la ÚLTIMA distancia hombro-muñeca
        # buena (así se conserva la flexión del codo en vez de enderezarlo de golpe).
        _W = corregir_muneca_por_longitud(
            pts[i_h], lm[i_m].x * ancho, lm[i_m].y * alto, float(pts[i_m][2]),
            _L, ancho, alto, f_px,
            z_ref=z_mediapipe(i_m) if puede_mp else None,
            radio=getattr(estimador, "ultima_d_sw", None))
        if _W is None:
            estimador.ultima_d_sw = float(np.linalg.norm(pts[i_m] - pts[i_h]))
        else:
            pts[i_m], fuente[i_m] = _W, "L"

    # ── 4) Comprobación / reconstrucción del codo ─────────────────────────────
    codo_estimado = False
    if estimador is not None:
        codo_medido = pts.get(i_c)
        if codo_medido is not None and not estimador.codo_creible(
                pts[i_h], codo_medido, pts[i_m], aprender=lm[i_c].visibility >= 0.7):
            del pts[i_c]                        # codo falso → se intenta reconstruir
        if i_c not in pts:
            E = estimador.reconstruir_codo(pts[i_h], pts[i_m])
            if E is not None:
                pts[i_c], fuente[i_c] = E, "R"
                codo_estimado = True
            elif codo_medido is not None:
                # No se puede reconstruir (p.ej. codo MUY doblado, mano en el hombro):
                # mejor el codo medido, aunque sea dudoso, que perder el brazo.
                pts[i_c] = codo_medido
            elif puede_mp and usable(i_c):
                zc = z_mediapipe(i_c)
                pts[i_c] = np.array(pixel_a_3d(lm[i_c].x * ancho, lm[i_c].y * alto,
                                               zc, ancho, alto, f_px))
                fuente[i_c] = "M"
    if i_c not in pts:
        fallos.append("codo: sin posición (ni medida ni reconstruible)")
        return fallar()

    res = _angulos_desde_puntos(
        lambda i: pts[i],
        lambda i: 1.0 if i in pts else 0.0,
        brazo, vis_min)
    if res is None:
        fallos.append("geometría degenerada (hombros superpuestos)")
        return fallar()
    res["codo_estimado"] = codo_estimado
    res["vis"]     = (lm[i_h].visibility, lm[i_c].visibility, lm[i_m].visibility)
    res["fuentes"] = f"h:{fuente.get(i_h, '?')} c:{fuente.get(i_c, '?')} m:{fuente.get(i_m, '?')}"
    if estimador is not None:
        estimador.motivo_fallo = ""
    return res


def angulos_humano_a_q_brazo(azimut_rad: float, elevacion_rad: float, codo_rad: float):
    """
    PASO 4 — ángulos del brazo humano (rad) → objetivos de joint1, joint2 y joint3
    del ARCTOS (rad), con la tabla ARM_IMITACION de config.py y recortados a
    IMITAR_LIMITES y a LIMITES_CTRL_BRAZO.
    """
    fuentes = {"azimut": azimut_rad, "elevacion": elevacion_rad, "codo": codo_rad}
    q = []
    for k, joint in enumerate(("joint1", "joint2", "joint3")):
        fuente, signo, offset, escala = ARM_IMITACION[joint]
        v = offset + signo * escala * fuentes[fuente]
        lo, hi = IMITAR_LIMITES[joint]
        lo = max(lo, LIMITES_CTRL_BRAZO[k][0])
        hi = min(hi, LIMITES_CTRL_BRAZO[k][1])
        q.append(float(np.clip(v, lo, hi)))
    return np.array(q)


def corregir_con_tpose(ang: dict, tpose_med):
    """
    Ajusta (azimut, elevación, codo) [GRADOS] para que la T-pose MEDIDA en la
    calibración coincida con la T-pose ideal T_POSE_HUMANA.
      · azimut : desplazamiento (con envoltura a ±180)
      · elevación: lineal a trozos con 3 puntos fijos 0→0, T_medida→T_ideal, 180→180
                   (así el brazo colgando sigue en 0 y el brazo arriba en 180)
      · codo   : desplazamiento, sin bajar de 0
    Si tpose_med es None, devuelve los ángulos tal cual.
    """
    az, el, co = ang["azimut"], ang["elevacion"], ang["codo"]
    if tpose_med is None:
        return az, el, co
    az_t, el_t, co_t = tpose_med
    az_i, el_i, co_i = T_POSE_HUMANA
    az = az - (az_t - az_i)
    az = (az + 180.0) % 360.0 - 180.0
    if el <= el_t:
        el = el * el_i / el_t
    else:
        el = el_i + (el - el_t) * (180.0 - el_i) / (180.0 - el_t)
    el = float(np.clip(el, 0.0, 180.0))
    co = max(0.0, co - (co_t - co_i))
    return az, el, co


def angulos_humano_a_q_brazo_rel(az_deg, el_deg, co_deg, ref_deg, q_ref):
    """
    Modo RELATIVO. La pose de reposo del sim (q_ref = ctrl[0:3] al empezar) equivale a
    la T-pose medida (ref_deg = az, elev, codo en GRADOS). Cada joint se mueve el
    incremento del ángulo humano respecto a esa T-pose, con el signo/escala de
    ARM_IMITACION, y se recorta a IMITAR_LIMITES y LIMITES_CTRL_BRAZO.
    """
    d_az = (az_deg - ref_deg[0] + 180.0) % 360.0 - 180.0
    fuentes = {"azimut":    math.radians(d_az),
               "elevacion": math.radians(el_deg - ref_deg[1]),
               "codo":      math.radians(co_deg - ref_deg[2])}
    q = []
    for k, joint in enumerate(("joint1", "joint2", "joint3")):
        fuente, signo, _offset, escala = ARM_IMITACION[joint]
        v = q_ref[k] + signo * escala * fuentes[fuente]
        lo, hi = IMITAR_LIMITES[joint]
        lo = max(lo, LIMITES_CTRL_BRAZO[k][0])
        hi = min(hi, LIMITES_CTRL_BRAZO[k][1])
        q.append(float(np.clip(v, lo, hi)))
    return np.array(q)


def limitar_velocidad_articular(q_obj, q_prev, dt: float, vel_max: float):
    """Mueve q_prev hacia q_obj, como mucho vel_max·dt rad por joint en este fotograma."""
    paso = vel_max * max(dt, 1e-3)
    return q_prev + np.clip(np.asarray(q_obj) - np.asarray(q_prev), -paso, paso)


def _fmt_ang(a) -> str:
    """Formato corto de ángulos para la terminal."""
    if a is None:
        return "sin datos"
    return f"az={a['azimut']:6.1f}°  elev={a['elevacion']:5.1f}°  codo={a['codo']:5.1f}°"


# ══════════════════════════════════════════════════════════════════════════════
# DETECCIÓN DE LA MANO SOBRE UN RECORTE GUIADO POR POSE
# ══════════════════════════════════════════════════════════════════════════════

# Puntos de la mano en MediaPipe POSE: (muñeca, meñique, índice, pulgar, codo)
_PS_MANO = {"derecho": (16, 18, 20, 22, 14), "izquierdo": (15, 17, 19, 21, 13)}


def caja_recorte_mano(pose_lm, brazo: str, ancho: int, alto: int,
                      vis_min: float = 0.3):
    """
    Cuadrado (x0, y0, lado) en PÍXELES de una imagen de ancho×alto que contiene la
    mano del lado 'brazo', usando los puntos de mano de MediaPipe Pose.
    Devuelve None si Pose no ve esa muñeca.
    """
    lm = pose_lm.landmark
    i_m, i_me, i_in, _i_pu, i_co = _PS_MANO[brazo]
    if lm[i_m].visibility < vis_min:
        return None

    def px(i):
        return np.array([lm[i].x * ancho, lm[i].y * alto])

    w = px(i_m)
    nudillos = [px(i) for i in (i_me, i_in) if lm[i].visibility >= vis_min]
    if nudillos:
        k = np.mean(nudillos, axis=0)
        d = float(np.linalg.norm(k - w))
        centro = w + 0.6 * (k - w)          # el centro de la mano está pasados los nudillos
    else:
        # Sin nudillos: se prolonga el antebrazo (codo → muñeca)
        e = px(i_co)
        v = w - e
        d = 0.35 * float(np.linalg.norm(v))
        centro = w + 0.25 * v

    lado = max(MANO_RECORTE_FACTOR * d, MANO_RECORTE_MIN * alto)
    lado = int(min(lado, 0.6 * alto))    # tope: una mano nunca ocupa más del 60 % de la altura
    x0 = int(np.clip(centro[0] - lado / 2, 0, ancho - lado))
    y0 = int(np.clip(centro[1] - lado / 2, 0, alto - lado))
    return x0, y0, lado


def detectar_mano_en_recorte(detector, imagen_bgr, caja, tam: int = MANO_RECORTE_PX):
    """
    Ejecuta MediaPipe Hands sobre el recorte 'caja' de 'imagen_bgr' ampliado a tam×tam
    y devuelve el resultado con los landmarks NORMALIZADOS pasados a coordenadas de la
    imagen completa (0..1), como si Hands hubiera procesado la imagen entera.
    Los world landmarks (metros) no dependen del recorte y se dejan tal cual.
    Devuelve None si no encuentra mano en el recorte.
    """
    x0, y0, lado = caja
    alto, ancho = imagen_bgr.shape[:2]
    rec = imagen_bgr[y0:y0 + lado, x0:x0 + lado]
    if rec.shape[0] < 8 or rec.shape[1] < 8:
        return None
    rec = cv2.resize(rec, (tam, tam), interpolation=cv2.INTER_LINEAR)
    rec = cv2.cvtColor(rec, cv2.COLOR_BGR2RGB)
    rec.flags.writeable = False
    res = detector.process(rec)
    if not res.multi_hand_landmarks:
        return None
    for mano in res.multi_hand_landmarks:
        for l in mano.landmark:
            l.x = (x0 + l.x * lado) / ancho
            l.y = (y0 + l.y * lado) / alto
    return res


# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES DE RETARGETING BIOMECÁNICO
# ══════════════════════════════════════════════════════════════════════════════

def calcular_flexion(p1, p2, p3) -> float:
    """
    Flexión en la articulación p2 formada por los segmentos p1→p2 y p2→p3.
    Devuelve un valor ≥ 0 en radianes (0 = dedo extendido).
    """
    v1 = np.array(p1) - np.array(p2)
    v2 = np.array(p3) - np.array(p2)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    dot = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
    return max(0.0, (np.pi - np.arccos(dot)) - 0.10)


def calcular_abertura(p_base1, p_punta1, p_base2, p_punta2) -> float:
    """Ángulo de separación angular entre dos dedos (en radianes, puede ser < 0)."""
    v1 = np.array(p_punta1) - np.array(p_base1)
    v2 = np.array(p_punta2) - np.array(p_base2)
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    return np.arccos(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)) - 0.18


def calcular_distancia(p1, p2) -> float:
    """Distancia euclidiana 3D entre dos puntos."""
    return float(np.linalg.norm(np.array(p1) - np.array(p2)))


def calcular_flexion_muneca(hand_world_lm, ref_vec=None, eje_lat_fijo=None):
    """
    Calcula la flexión/extensión de la muñeca en el plano de bisagra correcto.

    Modo calibración  (ref_vec=None):
        Devuelve (vec_adelante, eje_lateral) — congela la posición neutra.

    Modo medición (ref_vec, eje_lat_fijo provistos):
        Devuelve el ángulo de flexión en radianes (+ flexión, - extensión).
    """
    def lm(i):
        l = hand_world_lm.landmark[i]
        return np.array([l.x, l.y, l.z], float)

    mcp_centro = (lm(LM_INDICE_MCP) + lm(LM_CORAZON_MCP) +
                  lm(LM_ANULAR_MCP) + lm(LM_MENIQUE_MCP)) / 4.0
    direccion  = mcp_centro - lm(LM_MUNECA)
    n          = np.linalg.norm(direccion)
    if n < 1e-6:
        return (np.array([0, 1, 0], float), np.array([1, 0, 0], float)) \
               if ref_vec is None else 0.0
    direccion /= n

    if ref_vec is None:
        # — Modo calibración —
        eje = lm(LM_MENIQUE_MCP) - lm(LM_INDICE_MCP)
        eje = eje - np.dot(eje, direccion) * direccion
        n2  = np.linalg.norm(eje)
        eje = eje / n2 if n2 > 1e-6 else np.array([1.0, 0.0, 0.0])
        return direccion, eje

    # — Modo medición —
    eje    = eje_lat_fijo if eje_lat_fijo is not None else np.array([1.0, 0.0, 0.0])
    ref_p  = ref_vec  - np.dot(ref_vec,  eje) * eje
    dir_p  = direccion - np.dot(direccion, eje) * eje
    nr, nd = np.linalg.norm(ref_p), np.linalg.norm(dir_p)
    if nr < 1e-6 or nd < 1e-6:
        return 0.0
    ref_p /= nr
    dir_p /= nd
    cross = np.cross(ref_p, dir_p)
    return -np.arctan2(np.dot(cross, eje), np.dot(ref_p, dir_p))


# ══════════════════════════════════════════════════════════════════════════════
# RETARGETING: LANDMARKS 3D → data.ctrl[]
# ══════════════════════════════════════════════════════════════════════════════

# ── Bodies de yema por dedo (nombres exactos del MJCF) ───────────────────────
_BODY_YEMA = {
    "indice":  "right_I-FingerTipAssembly_ec49c16c",
    "corazon": "right_M-FingerTipAssembly_34afb748",
    "anular":  "right_M-FingerTipAssembly_424a8e75",
    "menique": "right_P-FingerTipAssembly_cd219176",
}
_BODY_PULGAR_YEMA = "right_T-DP_b7429e50"

def hay_contacto_yema(modelo: mujoco.MjModel, datos: mujoco.MjData,
                      dedo: str) -> bool:
    """True si la falange distal del pulgar toca la del dedo indicado."""
    id_pulgar = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, _BODY_PULGAR_YEMA)
    id_dedo   = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, _BODY_YEMA[dedo])
    for i in range(datos.ncon):
        c  = datos.contact[i]
        b1 = modelo.geom_bodyid[c.geom1]
        b2 = modelo.geom_bodyid[c.geom2]
        if (b1 == id_pulgar and b2 == id_dedo) or \
           (b1 == id_dedo   and b2 == id_pulgar):
            return True
    return False

def retarget_a_ctrl(modelo: mujoco.MjModel, datos: mujoco.MjData,
                    lm3d: list, hand_world_lm, estado: dict,
                    suav_dedos: SuavizadorND) -> dict:
    """
    Calcula y escribe datos.ctrl[0..N_ACT-1] a partir de landmarks 3D.

    Flujo:
      1. Aberturas laterales (abducción entre dedos)
      2. Detección de pinza (distancia pulgar→cada dedo)
      3. Control de muñeca con latch de seguridad
      4. Flexión de cada dedo (MCP + PIP/DIP)
      5. Pose del pulgar (oposición + abducción)
      6. Override de pinza (cierre dirigido a un dedo concreto)
      7. Suavizado de dedos (media móvil)
      8. Clip de seguridad anatómica

    Devuelve el estado actualizado.
    """
    # ctrl_mano: vista sobre la porción de mano de datos.ctrl[], desplazada
    # OFFSET_MANO posiciones porque el brazo ocupa ahora los primeros índices.
    # Todo lo de abajo sigue usando los índices 0..16 de siempre.
    ctrl_mano = datos.ctrl[OFFSET_MANO: OFFSET_MANO + N_ACT]

    # — 1. Aberturas (Con umbrales calibrados y Convergencia Activa) —
    
    # 1.1 Vectores largos (MCP -> DIP)
    ang_indice  = calcular_abertura(lm3d[9],  lm3d[11], lm3d[5],  lm3d[7])
    ang_anular  = calcular_abertura(lm3d[9],  lm3d[11], lm3d[13], lm3d[15])
    ang_menique = calcular_abertura(lm3d[13], lm3d[15], lm3d[17], lm3d[19])

    # 1.2 Distancias físicas entre las articulaciones medias (PIP)
    dist_pip_indice_corazon = calcular_distancia(lm3d[6], lm3d[10])
    dist_pip_corazon_anular = calcular_distancia(lm3d[10], lm3d[14])
    dist_pip_anular_menique = calcular_distancia(lm3d[14], lm3d[18])

    # 1.3 Zonas Muertas INDIVIDUALES (en metros)
    UMBRAL_INDICE_CORAZON = 0.028  
    UMBRAL_CORAZON_ANULAR = 0.022  
    UMBRAL_ANULAR_MENIQUE = 0.020  

    # 1.4 Ángulos de Convergencia (Radianes)
    # Valores que fuerzan a los dedos a inclinarse hacia el corazón (dedo ancla).
    # Ajusta estos valores si la colisión en MuJoCo es demasiado fuerte o se queda corta.
    CONV_INDICE  = -0.18  # Fuerza al índice a inclinarse hacia el centro
    CONV_ANULAR  = -0.15  # Fuerza al anular a inclinarse hacia el centro
    CONV_MENIQUE = -0.18  # Fuerza al meñique a pegarse al anular

    # 1.5 Aplicar la compuerta lógica con convergencia
    sep_indice  = CONV_INDICE  if dist_pip_indice_corazon < UMBRAL_INDICE_CORAZON else ang_indice
    sep_anular  = CONV_ANULAR  if dist_pip_corazon_anular < UMBRAL_CORAZON_ANULAR else ang_anular
    sep_menique = CONV_MENIQUE if dist_pip_anular_menique < UMBRAL_ANULAR_MENIQUE else ang_menique

    # — 2. Detección de pinza con histéresis y ratio continuo —
    dist_pulgar = {
        "indice":  calcular_distancia(lm3d[4], lm3d[8]),
        "corazon": calcular_distancia(lm3d[4], lm3d[12]),
        "anular":  calcular_distancia(lm3d[4], lm3d[16]),
        "menique": calcular_distancia(lm3d[4], lm3d[20]),
    }

    # — Detección de combos multi-dedo ────────────────────────────────────────
    # Se evalúan ANTES que la búsqueda de dedo individual para tener prioridad.
    # Prioridad: indice_corazon > corazon_anular > anular_menique
    # Cada combo se activa cuando AMBOS dedos entran en su umbral propio,
    # y se libera cuando CUALQUIERA de los dos supera su umbral de salida.
    dedo_bloqueado_actual = estado.get("dedo_bloqueado")

    # — Combo índice + corazón —
    combo2_activa = False
    if not estado["modo_pinza"] or dedo_bloqueado_actual == "indice_corazon":
        if not estado["modo_pinza"]:
            combo2_activa = (
                dist_pulgar["indice"]  < _UMBRAL_COMBO2_ON["indice"] and
                dist_pulgar["corazon"] < _UMBRAL_COMBO2_ON["corazon"]
            )
        else:
            combo2_activa = not (
                dist_pulgar["indice"]  > _UMBRAL_COMBO2_OFF["indice"] or
                dist_pulgar["corazon"] > _UMBRAL_COMBO2_OFF["corazon"]
            )

    # — Combo corazón + anular —
    combo1_activa = False
    if not combo2_activa and (not estado["modo_pinza"] or
                               dedo_bloqueado_actual == "corazon_anular"):
        if not estado["modo_pinza"]:
            combo1_activa = (
                dist_pulgar["corazon"] < _UMBRAL_COMBO_ON["corazon"] and
                dist_pulgar["anular"]  < _UMBRAL_COMBO_ON["anular"]
            )
        else:
            combo1_activa = not (
                dist_pulgar["corazon"] > _UMBRAL_COMBO_OFF["corazon"] or
                dist_pulgar["anular"]  > _UMBRAL_COMBO_OFF["anular"]
            )

    # — Combo anular + meñique —
    combo3_activa = False
    if not combo2_activa and not combo1_activa and (not estado["modo_pinza"] or
                                                     dedo_bloqueado_actual == "anular_menique"):
        if not estado["modo_pinza"]:
            combo3_activa = (
                dist_pulgar["anular"]  < _UMBRAL_COMBO3_ON["anular"] and
                dist_pulgar["menique"] < _UMBRAL_COMBO3_ON["menique"]
            )
        else:
            combo3_activa = not (
                dist_pulgar["anular"]  > _UMBRAL_COMBO3_OFF["anular"] or
                dist_pulgar["menique"] > _UMBRAL_COMBO3_OFF["menique"]
            )

    combo_activa = combo2_activa or combo1_activa or combo3_activa

    # — Detección de dedo individual (histéresis) ─────────────────────────────
    dedo_candidato = min(dist_pulgar, key=dist_pulgar.get)
    dist_min       = dist_pulgar[dedo_candidato]

    if combo2_activa:
        modo_pinza = True
        estado["dedo_bloqueado"] = "indice_corazon"
    elif combo1_activa:
        modo_pinza = True
        estado["dedo_bloqueado"] = "corazon_anular"
    elif combo3_activa:
        modo_pinza = True
        estado["dedo_bloqueado"] = "anular_menique"
    elif not estado["modo_pinza"]:
        if dist_min < PINZA_UMBRAL_ON[dedo_candidato]:
            modo_pinza               = True
            estado["dedo_bloqueado"] = dedo_candidato
        else:
            modo_pinza = False
    else:
        if dedo_bloqueado_actual in ("corazon_anular", "indice_corazon", "anular_menique"):
            modo_pinza               = False
            estado["dedo_bloqueado"] = None
        else:
            dist_dedo_bloqueado = dist_pulgar[dedo_bloqueado_actual]
            if dist_dedo_bloqueado > PINZA_UMBRAL_OFF[dedo_bloqueado_actual]:
                modo_pinza               = False
                estado["dedo_bloqueado"] = None
            else:
                modo_pinza = True

# Si las pinzas están deshabilitadas por teclado, forzamos la desactivación.
    if not estado.get("pinza_habilitada", True):
        modo_pinza = False
        estado["dedo_bloqueado"] = None

    dedo_activo = estado["dedo_bloqueado"] if modo_pinza else dedo_candidato

    # Ratio continuo de cierre — para combos se usa el promedio de distancias
    if dedo_activo == "corazon_anular":
        dist_ref         = (dist_pulgar["corazon"] + dist_pulgar["anular"]) / 2.0
        umbral_on_activo = (_UMBRAL_COMBO_ON["corazon"] + _UMBRAL_COMBO_ON["anular"]) / 2.0
    elif dedo_activo == "indice_corazon":
        dist_ref         = (dist_pulgar["indice"] + dist_pulgar["corazon"]) / 2.0
        umbral_on_activo = (_UMBRAL_COMBO2_ON["indice"] + _UMBRAL_COMBO2_ON["corazon"]) / 2.0
    elif dedo_activo == "anular_menique":
        dist_ref         = (dist_pulgar["anular"] + dist_pulgar["menique"]) / 2.0
        umbral_on_activo = (_UMBRAL_COMBO3_ON["anular"] + _UMBRAL_COMBO3_ON["menique"]) / 2.0
    else:
        dist_ref         = dist_pulgar[dedo_activo]
        umbral_on_activo = PINZA_UMBRAL_ON[dedo_activo]
    ratio_pinza = float(np.clip(
        1.0 - (dist_ref - umbral_on_activo) / (PINZA_DIST_MAX - umbral_on_activo),
        0.0, 1.0
    ))

# — 3. Muñeca (Estabilizada) —
    calc_muneca = 0.0
    if estado["vec_neutro"] is not None:
        flexion_raw = calcular_flexion_muneca(
            hand_world_lm, estado["vec_neutro"], estado["eje_lateral"])
        
        ZONA_MUERTA = 0.25  # Aumentado para absorber el ruido Z de MediaPipe
        GANANCIA    = 1.40  # Reducido (antes 2.2) para evitar amplificar temblores
        
        if abs(flexion_raw) < ZONA_MUERTA:
            calc_muneca = 0.0
        else:
            calc_muneca = np.sign(flexion_raw) * (abs(flexion_raw) - ZONA_MUERTA) * GANANCIA
            
        calc_muneca = np.clip(calc_muneca, -1.134, 0.610)

    if modo_pinza:
        if not estado["pinza_previa"]:
            estado["ultima_pos_palma"] = ctrl_mano[0]
        if abs(calc_muneca - estado["ultima_pos_palma"]) > 0.45:
            estado["ultima_pos_palma"] += (
                calc_muneca - estado["ultima_pos_palma"]) * 0.15  # Más suave en pinza
        ctrl_mano[0] = float(estado["ultima_pos_palma"])
    else:
        if estado["muneca_bloqueada"]:
            ctrl_mano[0] = 0.610
            if calc_muneca < UMBRAL_LIBERACION:
                estado["muneca_bloqueada"] = False
        else:
            # Filtro de suavizado reforzado: 96% valor anterior, 4% nuevo valor
            ctrl_mano[0] = float(np.clip(
                ctrl_mano[0] * 0.96 + calc_muneca * 0.04, -1.134, 0.610))
            if calc_muneca >= UMBRAL_BLOQUEO:
                estado["muneca_bloqueada"] = True

    # — 4 + 5. Dedos y pulgar (valores brutos, sin suavizar aún) —
    ctrl_raw = np.array([ctrl_mano[i] for i in range(N_ACT)], dtype=float)

    # Meñique  — lm: 17=MCP  18=PIP  19=DIP  20=punta
    ctrl_raw[1] = -sep_menique * FUERZA_ABD + 0.15
    ctrl_raw[2] = calcular_flexion(lm3d[0],  lm3d[17], lm3d[18]) * FUERZA_NUDILLOS * GANANCIA_DEDOS["menique_mcp"]
    ctrl_raw[3] = calcular_flexion(lm3d[17], lm3d[18], lm3d[19]) * FUERZA_PUNTAS   * GANANCIA_DEDOS["menique_pip"]  # 19=DIP, no 20=punta
    # Anular  — lm: 13=MCP  14=PIP  15=DIP  16=punta
    ctrl_raw[4] = -sep_anular * FUERZA_ABD
    ctrl_raw[5] = calcular_flexion(lm3d[0],  lm3d[13], lm3d[14]) * FUERZA_NUDILLOS * GANANCIA_DEDOS["anular_mcp"]
    ctrl_raw[6] = calcular_flexion(lm3d[13], lm3d[14], lm3d[15]) * FUERZA_PUNTAS   * GANANCIA_DEDOS["anular_pip"]   # 15=DIP, no 16=punta
    # Corazón  — lm: 9=MCP  10=PIP  11=DIP  12=punta  (abducción fija)
    ctrl_raw[7] = 0.0
    ctrl_raw[8] = calcular_flexion(lm3d[0],  lm3d[9],  lm3d[10]) * FUERZA_NUDILLOS * GANANCIA_DEDOS["corazon_mcp"]
    ctrl_raw[9] = calcular_flexion(lm3d[9],  lm3d[10], lm3d[11]) * FUERZA_PUNTAS   * GANANCIA_DEDOS["corazon_pip"]  # 11=DIP, no 12=punta
    # Índice  — lm: 5=MCP  6=PIP  7=DIP  8=punta
    ctrl_raw[10] = sep_indice * FUERZA_ABD
    ctrl_raw[11] = calcular_flexion(lm3d[0],  lm3d[5],  lm3d[6])  * FUERZA_NUDILLOS * GANANCIA_DEDOS["indice_mcp"]
    ctrl_raw[12] = calcular_flexion(lm3d[5],  lm3d[6],  lm3d[7])  * FUERZA_PUNTAS   * GANANCIA_DEDOS["indice_pip"]   # 7=DIP, no 8=punta

    # ── Seguimiento colectivo en zona de puño ─────────────────────────────────
    # Cuando el índice cierra, arrastra al resto progresivamente.
    # Compensa la oclusión de MediaPipe: al cerrar el puño las yemas del anular
    # y meñique desaparecen de la vista y MediaPipe los pierde.
    # El suavizador se reduce a ventana=1 (sin dilución) durante el puño.
    UMBRAL_PUNO = 0.60   # umbral más bajo para detectar antes el intento de puño
    en_puno = ctrl_raw[11] > UMBRAL_PUNO or ctrl_raw[5] > UMBRAL_PUNO
    if en_puno:
        suav_dedos.set_ventana(1)   # sin suavizado: el cierre llega al máximo
        factor = max(
            (ctrl_raw[11] - UMBRAL_PUNO) / (1.80 - UMBRAL_PUNO),
            (ctrl_raw[5]  - UMBRAL_PUNO) / (1.80 - UMBRAL_PUNO),
        )
        factor = float(np.clip(factor, 0.0, 1.0))
        # MCP de cada dedo: arrastra con ganancia anatómica
        for idx_ctrl, ref_ctrl, g in [
            (2,  11, 1.05),   # meñique mcp
            (5,  11, 1.08),   # anular  mcp  ← ya tiene señal directa, refuerza
            (8,  11, 1.03),   # corazón mcp
        ]:
            ctrl_raw[idx_ctrl] = max(ctrl_raw[idx_ctrl],
                                     ctrl_raw[ref_ctrl] * g * factor)
        # PIP de cada dedo
        for idx_ctrl, ref_ctrl, g in [
            (3,  12, 1.10),   # meñique pip
            (6,  12, 1.12),   # anular  pip
            (9,  12, 1.05),   # corazón pip
        ]:
            ctrl_raw[idx_ctrl] = max(ctrl_raw[idx_ctrl],
                                     ctrl_raw[ref_ctrl] * g * factor)
    else:
        suav_dedos.set_ventana(4)   # suavizado normal fuera del puño

    # ── Pulgar — Oposición (CMC) y Abducción (ABD) por Proyección Transversal ──
    def _lm_w(i):
        l = hand_world_lm.landmark[i]
        return np.array([l.x, l.y, l.z])

    ix_mcp = _lm_w(5)   # Nudillo Índice
    pi_mcp = _lm_w(17)  # Nudillo Meñique
    th_tip = _lm_w(4)   # Punta del pulgar (la parte que realmente viaja)

    # 1. Creamos un "carril" que va desde el índice hasta el meñique
    v_palma = pi_mcp - ix_mcp
    ancho_palma = np.linalg.norm(v_palma)

    if ancho_palma > 1e-6:
        dir_palma = v_palma / ancho_palma
        
        # 2. Vector desde el índice hasta donde está el pulgar actualmente
        v_pulgar = th_tip - ix_mcp
        
        # 3. Proyectamos el pulgar sobre el carril de la palma.
        # ratio_cruce = 0.0 -> pulgar en reposo (alineado con el índice)
        # ratio_cruce = 1.0 -> pulgar tocando la base del meñique
        ratio_cruce = np.dot(v_pulgar, dir_palma) / ancho_palma
        
        # 4. Mapeo Directo a los motores (Basado en los valores de tu captura)
        
        # CMC (Oposición): En reposo = -0.1. Cruzado = 0.576.
        # Usamos un multiplicador agresivo (1.3) para garantizar que alcance el 0.576
        calc_cmc = (ratio_cruce * 1.3) - 0.10
        ctrl_raw[13] = float(np.clip(calc_cmc, LIMITES_CTRL[13][0], LIMITES_CTRL[13][1]))
        
        # ABD (Abducción): En reposo = ~0.65. Cruzado = -0.314.
        # Relación inversa: Cuanto más cruzas, más negativo se vuelve para aplastarse contra la palma
        calc_abd = 0.65 - (ratio_cruce * 1.3)
        ctrl_raw[14] = float(np.clip(calc_abd, LIMITES_CTRL[14][0], LIMITES_CTRL[14][1]))
    else:
        ctrl_raw[13], ctrl_raw[14] = 0.0, 0.30

    # ── Lógica Desacoplada para Flexión/Extensión del Pulgar ──
    flex_raw_mcp = calcular_flexion(lm3d[1], lm3d[2], lm3d[3])
    flex_raw_ip  = calcular_flexion(lm3d[2], lm3d[3], lm3d[4])

    # Nudillo del Pulgar (MCP - Joint 15)
    if flex_raw_mcp < UMBRAL_EXT_PULGAR_MCP:
        # Zona de Extensión: Aplanamos el valor hacia 0 para abrir el dedo por completo
        ctrl_raw[15] = (flex_raw_mcp / UMBRAL_EXT_PULGAR_MCP) * 0.05
    else:
        # Zona de Flexión: Aplicamos ganancia para asegurar un buen agarre
        ctrl_raw[15] = 0.05 + (flex_raw_mcp - UMBRAL_EXT_PULGAR_MCP) * PULGAR_GANANCIA_MCP

    # Punta del Pulgar (IP - Joint 16)
    if flex_raw_ip < UMBRAL_EXT_PULGAR_IP:
        # Zona de Extensión: Filtra el "temblor" de la punta cuando la mano está abierta
        ctrl_raw[16] = (flex_raw_ip / UMBRAL_EXT_PULGAR_IP) * 0.05
    else:
        # Zona de Flexión: Ganancia agresiva para que la yema baje correctamente
        ctrl_raw[16] = 0.05 + (flex_raw_ip - UMBRAL_EXT_PULGAR_IP) * PULGAR_GANANCIA_IP

    # — 6. Suavizado de dedos (ctrl[1..16]) — solo para movimiento libre —————
    # Los joints de pinza se sobreescriben después del filtro (ver paso 7).
    # Al entrar en pinza se vacía el buffer para no mezclar valores anteriores.
    if modo_pinza and not estado["pinza_previa"]:
        suav_dedos.reset()
    ctrl_raw[1:] = suav_dedos.actualizar(ctrl_raw[1:])

    # — 7. Clip de seguridad anatómica —
    # Debug throttled: imprime todos los dedos cada ~0.5 s sin bloquear el bucle
    if estado["camara_activa"] and (int(datos.time * 2) % 1 == 0) and \
       abs(datos.time * 2 - int(datos.time * 2)) < 0.03:
        print(
            f"[CTRL] "
            f"MNQ {ctrl_raw[2]:.2f}/{ctrl_raw[3]:.2f} | "
            f"ANU {ctrl_raw[5]:.2f}/{ctrl_raw[6]:.2f} | "
            f"COR {ctrl_raw[8]:.2f}/{ctrl_raw[9]:.2f} | "
            f"IND {ctrl_raw[11]:.2f}/{ctrl_raw[12]:.2f} | "
            f"PUNO={'SI' if en_puno else 'no'}"
        )
    for i, (lo, hi) in enumerate(LIMITES_CTRL):
        ctrl_mano[i] = float(np.clip(ctrl_raw[i], lo, hi))

    # — 8. Override de pinza POST-suavizado — escribe directo a datos.ctrl ————
    #
    # CRÍTICO: se aplica DESPUÉS del suavizador y del clip para que los valores
    # lleguen a MuJoCo exactamente como se calibraron en el visor, sin dilución
    # por el filtro de media móvil.
    #
    # Valores calibrados manualmente en el visor MuJoCo para cada pinza:
    #   Se leen directamente del panel "Control" con la pose de contacto activa.
    #   Para calibrar una nueva pinza: alcanza la pose en el visor → copia los
    #   valores del panel aquí → reinicia el script.
    #
    # Mapeo ctrl[] → joint del panel:
    #   ctrl[1]=p-abd  ctrl[2]=p-mcp  ctrl[3]=p-pip   (meñique)
    #   ctrl[4]=r-abd  ctrl[5]=r-mcp  ctrl[6]=r-pip   (anular)
    #   ctrl[7]=m-abd  ctrl[8]=m-mcp  ctrl[9]=m-pip   (corazón)
    #   ctrl[10]=i-abd ctrl[11]=i-mcp ctrl[12]=i-pip  (índice)
    #   ctrl[13]=t-cmc ctrl[14]=t-abd ctrl[15]=t-mcp ctrl[16]=t-pip (pulgar)
    PINZA_CTRL_CONTACTO = {
        # ── Pulgar ↔ Índice ───────────────────────────────────────────────────
        "indice": {
            10: 0.000,   # índice ABD
            11: 0.491,   # índice MCP
            12: 1.250,   # índice PIP
            13: 0.000,   # pulgar CMC
            14: 0.469,   # pulgar ABD
            15: 0.469,   # pulgar MCP
            16: 0.888,   # pulgar IP
        },

        # ── Pulgar ↔ Corazón ──────────────────────────────────────────────────
        "corazon": {
            8:  0.916,   # corazón MCP
            9:  1.540,   # corazón PIP
            13: 0.426,   # pulgar CMC
            14: 0.113,   # pulgar ABD
            15: 0.174,   # pulgar MCP
            16: 1.720,   # pulgar IP
        },

        # ── Pulgar ↔ Anular ───────────────────────────────────────────────────
        "anular": {
            4: -0.0565,  # anular ABD
            5:  1.230,   # anular MCP
            6:  0.675,   # anular PIP
            13: 0.000,   # pulgar CMC
            14: -0.282,  # pulgar ABD 
            15: 0.905,   # pulgar MCP
            16: 0.526,   # pulgar IP
        },

        # ── Pulgar ↔ Meñique ──────────────────────────────────────────────────
        "menique": {
            1:  0.0995,  # meñique ABD
            2:  1.130,   # meñique MCP
            3:  0.366,   # meñique PIP
            13: 0.576,   # pulgar CMC
            14: -0.301,  # pulgar ABD
            15: 0.207,   # pulgar MCP
            16: 0.888,   # pulgar IP
        },

        # ── Pulgar ↔ Corazón + Anular (perro / sombra) ────────────────────────
        "corazon_anular": {
            4:  0.066,   # anular ABD
            5:  1.040,   # anular MCP
            6:  0.867,   # anular PIP
            7:  0.000,   # corazón ABD (fijo)
            8:  1.130,   # corazón MCP
            9:  0.888,   # corazón PIP
            13: 0.406,   # pulgar CMC
            14: 0.0171,  # pulgar ABD
            15: 0.229,   # pulgar MCP
            16: 0.217,   # pulgar IP
        },

        # ── Pulgar ↔ Índice + Corazón ─────────────────────────────────────────
        "indice_corazon": {
            7:  0.0565,  # corazón ABD
            8:  0.916,   # corazón MCP
            9:  0.835,   # corazón PIP
            10: -0.0571, # índice ABD
            11: 0.840,   # índice MCP
            12: 0.643,   # índice PIP
            13: 0.419,   # pulgar CMC
            14: 0.291,   # pulgar ABD
            15: 0.000,   # pulgar MCP
            16: 0.526,   # pulgar IP
        },

        # ── Pulgar ↔ Anular + Meñique ─────────────────────────────────────────
        "anular_menique": {
            1:  0.194,   # meñique ABD
            2:  0.982,   # meñique MCP
            3:  0.739,   # meñique PIP
            4: -0.0377,  # anular ABD
            5:  0.916,   # anular MCP
            6:  0.984,   # anular PIP
            13: 0.236,   # pulgar CMC
            14: -0.212,  # pulgar ABD
            15: 0.982,   # pulgar MCP
            16: 0.292,   # pulgar IP
        },
    }

    if modo_pinza:
        for idx, val in PINZA_CTRL_CONTACTO[dedo_activo].items():
            lo, hi = LIMITES_CTRL[idx]
            ctrl_mano[idx] = float(np.clip(val, lo, hi))
        # Para pinzas multi-dedo se verifica contacto en cualquiera de los dedos
        if dedo_activo == "corazon_anular":
            estado["pinza_tocando"] = (
                hay_contacto_yema(modelo, datos, "corazon") or
                hay_contacto_yema(modelo, datos, "anular")
            )
        elif dedo_activo == "indice_corazon":
            estado["pinza_tocando"] = (
                hay_contacto_yema(modelo, datos, "indice") or
                hay_contacto_yema(modelo, datos, "corazon")
            )
        elif dedo_activo == "anular_menique":
            estado["pinza_tocando"] = (
                hay_contacto_yema(modelo, datos, "anular") or
                hay_contacto_yema(modelo, datos, "menique")
            )
        else:
            estado["pinza_tocando"] = hay_contacto_yema(modelo, datos, dedo_activo)
    else:
        estado["pinza_tocando"] = False

    estado["pinza_previa"]  = modo_pinza
    estado["calc_muneca"]   = calc_muneca
    estado["dedo_activo"]   = dedo_activo
    estado["modo_pinza"]    = modo_pinza
    estado["dist_pulgar"]   = dist_pulgar      # para el diagnóstico de pinzas
    return estado


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE DEPTHAI  (OAK-D: color + estéreo para profundidad real)
# ══════════════════════════════════════════════════════════════════════════════

def crear_pipeline_oak(ancho: int = ANCHO_CAM, alto: int = ALTO_CAM) -> dai.Pipeline:
    pipeline = dai.Pipeline()

    cam_rgb = pipeline.create(dai.node.ColorCamera)
    cam_rgb.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam_rgb.setInterleaved(False)

    if CAM_FOV_COMPLETO:
        # ── SENSOR COMPLETO (4:3) ────────────────────────────────────────────
        # El IMX378 es 4056x3040 (4:3). El modo 1080p es 16:9, y el firmware lo
        # obtiene RECORTANDO franjas arriba y abajo → se pierde ~24 % de altura.
        # Pidiendo 12 MP y reduciendo en el ISP (1/3 → 1352x1014) se conserva
        # TODO el campo de visión vertical: VFOV ~42° → ~55°.
        # 1352x1014 y 640x480 tienen exactamente la misma relación 4:3, así que
        # el preview es un reescalado limpio, SIN recorte adicional.
        cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_12_MP)
        cam_rgb.setIspScale(1, 3)
    else:
        cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)

    cam_rgb.setPreviewSize(ancho, alto)
    cam_rgb.setPreviewKeepAspectRatio(True)
    cam_rgb.setFps(CAM_FPS)

    mono_izq = pipeline.create(dai.node.MonoCamera)
    mono_der = pipeline.create(dai.node.MonoCamera)
    for cam, socket in [
        (mono_izq, dai.CameraBoardSocket.CAM_B),
        (mono_der, dai.CameraBoardSocket.CAM_C),
    ]:
        # THE_400_P es el modo "binned" del OV9282: usa el sensor ENTERO (1280x800)
        # → mantiene todo el FOV vertical. NO cambiar a 720p: eso sí recorta.
        cam.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
        cam.setBoardSocket(socket)
        cam.setFps(CAM_FPS)

    stereo = pipeline.create(dai.node.StereoDepth)
    stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
    stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)
    stereo.setOutputSize(ancho, alto)   # misma medida que el color → mismos píxeles
    stereo.setLeftRightCheck(True)      # descarta píxeles donde las dos cámaras no coinciden
    stereo.setSubpixel(STEREO_SUBPIXEL) # profundidad más fina (menos "escalones")
    if STEREO_EXTENDED:
        stereo.setExtendedDisparity(True)

    # ── Post-procesado EN LA CÁMARA (0 % de CPU del PC) ──────────────────────
    # Los agujeros del mapa de profundidad sobre el brazo (superficie lisa, poco
    # textura, movimiento) son la causa principal de que el brazo "se pierda":
    # profundidad_robusta() devuelve None y la articulación se descarta entera.
    if STEREO_FILTROS:
        try:
            _cfg = stereo.initialConfig.get()
            _cfg.postProcessing.speckleFilter.enable      = True
            _cfg.postProcessing.speckleFilter.speckleRange = 50
            _cfg.postProcessing.spatialFilter.enable      = True
            _cfg.postProcessing.spatialFilter.holeFillingRadius = STEREO_HOLE_FILLING
            _cfg.postProcessing.spatialFilter.numIterations     = 1
            _cfg.postProcessing.temporalFilter.enable    = bool(STEREO_TEMPORAL)
            _cfg.postProcessing.thresholdFilter.minRange = int(PROF_Z_MIN * 1000)
            _cfg.postProcessing.thresholdFilter.maxRange = int(PROF_Z_MAX * 1000)
            stereo.initialConfig.set(_cfg)
            print("🧹 [OAK] Filtros de profundidad activados "
                  f"(hole-filling={STEREO_HOLE_FILLING}, temporal={STEREO_TEMPORAL})")
        except Exception as _e_pp:
            print(f"⚠️  [OAK] No se pudieron aplicar los filtros de profundidad: {_e_pp}")

    mono_izq.out.link(stereo.left)
    mono_der.out.link(stereo.right)

    xout_c = pipeline.create(dai.node.XLinkOut)
    xout_c.setStreamName("color")
    cam_rgb.preview.link(xout_c.input)

    # Imagen del ISP (1352x1014 con CAM_FOV_COMPLETO): mismo campo de visión que el
    # preview pero 2,1x más píxeles. Solo se usa para recortar la mano (MANO_RECORTE_HD).
    if MANO_RECORTE and MANO_RECORTE_HD and CAM_FOV_COMPLETO:
        xout_hd = pipeline.create(dai.node.XLinkOut)
        xout_hd.setStreamName("color_hd")
        cam_rgb.isp.link(xout_hd.input)

    xout_d = pipeline.create(dai.node.XLinkOut)
    xout_d.setStreamName("depth")
    stereo.depth.link(xout_d.input)

    return pipeline

def mostrar_menu_grafico(cola_retorno):
    import tkinter as tk
    ventana = tk.Tk()
    ventana.title("Skill Shield Nivel 6")
    ventana.geometry("380x150")

    # Forzar que aparezca visible y encima de todo
    ventana.lift()
    ventana.attributes('-topmost', True)
    ventana.focus_force()
    ventana.update()  # <- clave: fuerza el refresco antes del mainloop
    try:
        ventana.eval('tk::PlaceWindow . center')
    except:
        pass

    modo_elegido = "SIMULACION"

    def set_simulacion():
        nonlocal modo_elegido
        modo_elegido = "SIMULACION"
        ventana.quit()

    def set_hardware():
        nonlocal modo_elegido
        modo_elegido = "HARDWARE_REAL"
        ventana.quit()

    tk.Label(ventana, text="¿Qué modo de operación deseas iniciar?", font=("Arial", 11, "bold")).pack(pady=15)
    tk.Button(ventana, text="💻 Solo Simulación Virtual (MuJoCo)", command=set_simulacion, width=35, bg="#e0f7fa").pack(pady=5)
    tk.Button(ventana, text="🤖 Mano Física (USB) + Gemelo Digital", command=set_hardware, width=35, bg="#e8f5e9").pack(pady=5)
    
    ventana.mainloop()
    ventana.destroy()
    cola_retorno.put(modo_elegido)
    
# ══════════════════════════════════════════════════════════════════════════════
# FÍSICA EN TIEMPO REAL — hilo propio (idea tomada del proyecto TRON 2)
# ══════════════════════════════════════════════════════════════════════════════

class HiloFisica(threading.Thread):
    """
    Avanza la simulación MuJoCo al ritmo del RELOJ REAL y refresca el visor a
    FISICA_HZ, en un hilo aparte. Antes se hacían 4 mj_step por fotograma de
    cámara: a ~8 FPS la simulación iba al ~8 % del tiempo real (robot "a cámara
    lenta" y REAL siempre por detrás de CMD).

    Reparto del acceso a `datos` (un único candado):
      · El bucle principal TIENE el candado casi siempre (lee y escribe datos:
        ctrl, IK, pinzas, teclas...), y lo SUELTA solo durante lo lento (esperar
        a la cámara, MediaPipe) con `with fisica.soltar():`.
      · Mientras está suelto, este hilo avanza la física lo que haga falta para
        alcanzar al reloj real y refresca el visor.
    Así nunca se tocan `datos` desde dos hilos a la vez y no hace falta reordenar
    el bucle principal.
    """

    def __init__(self, modelo, datos, visor, antes_de_paso=None):
        super().__init__(daemon=True)
        self.modelo, self.datos, self.visor = modelo, datos, visor
        self.antes_de_paso = antes_de_paso   # PASO 7.1: se llama antes de CADA mj_step
        self.lock   = threading.Lock()
        self.activo = True
        self.factor = 0.0          # tiempo simulado / tiempo real (1.00 = tiempo real)

    def empezar(self):
        """Lo llama el bucle principal: se queda el candado y arranca el hilo."""
        self.lock.acquire()
        self.start()

    def parar(self):
        """Lo llama el bucle principal al salir del modo teleoperación."""
        self.activo = False
        self.lock.release()
        self.join(timeout=1.0)

    @contextmanager
    def soltar(self):
        """El bucle principal suelta la simulación mientras hace algo lento."""
        self.lock.release()
        try:
            yield
        finally:
            self.lock.acquire()

    def run(self):
        ts      = float(self.modelo.opt.timestep)
        periodo = 1.0 / FISICA_HZ
        deuda   = 0.0                               # tiempo real aún no simulado (s)
        t_ant   = time.perf_counter()
        t_med, sim_med = t_ant, 0.0
        while self.activo:
            t0 = time.perf_counter()
            with self.lock:
                if not self.activo:
                    break
                ahora = time.perf_counter()
                # Si el bucle principal retuvo el candado mucho rato, no se intenta
                # recuperar TODO de golpe (se tiraría demasiado tiempo calculando).
                deuda = min(deuda + (ahora - t_ant), FISICA_RETRASO_MAX)
                t_ant = ahora
                n = int(deuda / ts)
                for _ in range(n):
                    if self.antes_de_paso is not None:     # PASO 7.1: comando continuo
                        self.antes_de_paso(self.modelo, self.datos, ts)
                    mujoco.mj_step(self.modelo, self.datos)
                deuda   -= n * ts
                sim_med += n * ts
                if self.visor.is_running():
                    self.visor.sync()
            if ahora - t_med >= 1.0:
                self.factor = sim_med / (ahora - t_med)
                t_med, sim_med = ahora, 0.0
            espera = periodo - (time.perf_counter() - t0)
            if espera > 0:
                time.sleep(espera)


# ══════════════════════════════════════════════════════════════════════════════
# BUCLE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # ── MENÚ DE ARRANQUE CON ZENITY (compatible con Wayland/GNOME) ──────────
    # zenity es la herramienta de diálogos nativa de GNOME, siempre visible.
    # Si no está instalada: sudo apt install zenity
    import subprocess
    global MODO_EJECUCION
    try:
        resultado = subprocess.run(
            [
                'zenity', '--question',
                '--title=Skill Shield Nivel 6',
                '--text=¿Qué modo de operación deseas iniciar?',
                '--ok-label=💻  Simulación Virtual (MuJoCo)',
                '--cancel-label=🤖  Mano Física (USB) + Gemelo Digital',
                '--width=420',
                '--height=50',
            ],
            capture_output=True
        )
        stderr_txt = resultado.stderr.decode(errors="ignore").strip() if resultado.stderr else ""

        if resultado.returncode == 0:
            # Botón OK pulsado → Simulación
            MODO_EJECUCION = "SIMULACION"
        elif resultado.returncode == 1 and not stderr_txt:
            # Botón Cancel pulsado limpiamente, sin errores → el usuario eligió Hardware real
            MODO_EJECUCION = "HARDWARE_REAL"
        else:
            # Cualquier otro código, o zenity escribió algo en stderr → no sabemos si el
            # usuario llegó a ver la ventana. Por seguridad, NUNCA asumimos hardware real.
            if stderr_txt:
                print(f"⚠️  Zenity no pudo mostrar la ventana correctamente: {stderr_txt}")
            print("   Por seguridad, arrancando en SIMULACION.")
            MODO_EJECUCION = "SIMULACION"
    except FileNotFoundError:
        print("⚠️  zenity no encontrado → arrancando en SIMULACION por defecto.")
        print("   Para instalar: sudo apt install zenity")
        MODO_EJECUCION = "SIMULACION"
    except Exception as e:
        print(f"⚠️  Error inesperado al lanzar el selector de modo ({e}).")
        print("   Por seguridad, arrancando en SIMULACION.")
        MODO_EJECUCION = "SIMULACION"

    print(f"🚀 Iniciando Skill Shield Nivel 6 en modo: {MODO_EJECUCION}")
    # ─────────────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────
    # ────────────────────────────────────────────────────

    # — Cargar modelo MuJoCo (UNA SOLA VEZ) —
    modelo = mujoco.MjModel.from_xml_path(RUTA_XML)
    datos  = mujoco.MjData(modelo)
    visor  = mujoco.viewer.launch_passive(modelo, datos)

    # ── INICIALIZACIÓN DEL HARDWARE REAL ──
    mano_real = None
    if MODO_EJECUCION == "HARDWARE_REAL":
        mano_real = OrcaHardwareWrapper(puerto=PUERTO_HARDWARE)
        mano_real.conectar()
    # ───────────────────────────────────────

    # ── Configurar perspectiva inicial de la cámara ──
    with visor.lock():
        # Punto objetivo al que mira la cámara (X, Y, Z) — recentrado a medio
        # camino entre la base del brazo y la zona de trabajo de la mano
        # (antes 0.05/0.0/0.15, ajustado solo para ver la mano de cerca).
        visor.cam.lookat[0] = 0.15
        visor.cam.lookat[1] = 0.0
        visor.cam.lookat[2] = 0.25

        # ── PERSPECTIVA para ver el brazo entero, no solo la mano ──
        visor.cam.distance = 1.1     # Alejado (antes 0.55, quedaba pegado a la mano)
        visor.cam.azimuth = 90      # Misma vista diagonal de siempre
        visor.cam.elevation = -20    # Un poco menos picado que antes (-30), para abarcar el brazo
    # ─────────────────────────────────────────────────────────────────────────

    print(f"✅ Modelo MuJoCo cargado: {modelo.nu} actuadores, {modelo.nsensor} sensores.")

    # ── Cargar logo IDI / Grupo Elecnor para el HUD ───────────────────────────
    # Se generan tres variantes:
    #   · _logo_bgr / _logo_alpha        → ventana de teleoperación (750×750 px)
    #   · _logo_bgr_sm / _logo_alpha_sm  → panel de modo autónomo  (180×450 px)
    #   · _logo_mj_px / _logo_mj_w/h     → píxeles RGB para mjr_drawPixels
    _logo_bgr,    _logo_alpha    = _cargar_logo(RUTA_LOGO, alto_px=70)
    _logo_bgr_sm, _logo_alpha_sm = _cargar_logo(RUTA_LOGO, alto_px=35)
    _logo_mj_px, _logo_mj_w, _logo_mj_h = _preparar_logo_mujoco(RUTA_LOGO, alto_px=80)
    if _logo_bgr is not None:
        print(f"✅ Logo IDI cargado ({_logo_bgr.shape[1]}×{_logo_bgr.shape[0]} px).")
    if _logo_mj_px is not None:
        print(f"✅ Logo IDI para MuJoCo HUD preparado ({_logo_mj_w}×{_logo_mj_h} px).")
    # ─────────────────────────────────────────────────────────────────────────

    print(f"✅ Modelo MuJoCo cargado: {modelo.nu} actuadores, {modelo.nsensor} sensores.")
    if modelo.nu != OFFSET_MANO + N_ACT:
        print(f"⚠  ADVERTENCIA: El modelo tiene {modelo.nu} actuadores "
              f"pero el código espera {OFFSET_MANO + N_ACT} "
              f"({OFFSET_MANO} de brazo + {N_ACT} de mano). Revisa LIMITES_CTRL.")

    # Vista (NO copia) sobre la porción de datos.ctrl[] que corresponde a la
    # mano: escribir en ctrl_mano[i] escribe directamente en
    # datos.ctrl[OFFSET_MANO + i]. Así todo el código de mano de más abajo
    # sigue usando los mismos índices 0..16 de siempre, sin tocarlo.
    ctrl_mano = datos.ctrl[OFFSET_MANO: OFFSET_MANO + N_ACT]

    # ── Índices articulares del BRAZO, para la IK (calculados una sola vez) ──
    dof_idx_brazo  = [modelo.jnt_dofadr[mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, j)]
                       for j in ARM_JOINTS]
    qpos_idx_brazo = [modelo.jnt_qposadr[mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, j)]
                       for j in ARM_JOINTS]
    # Body del efector, para leer su posición REAL al calibrar con [A]
    mano_mount_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "mano_mount")
    # ── Gravedad de la mano: gravcomp NO se hereda de mano_mount a sus hijos ──
    print(f"⚖️  Masa colgando de mano_mount: {modelo.body_subtreemass[mano_mount_id]:.2f} kg")
    if HAND_GRAVCOMP:
        _n_comp = 0
        for _b in range(1, modelo.nbody):
            _p = _b
            while _p > 0 and _p != mano_mount_id:
                _p = modelo.body_parentid[_p]
            if _p == mano_mount_id:
                modelo.body_gravcomp[_b] = 1.0
                _n_comp += 1
        print(f"⚖️  Gravedad compensada en {_n_comp} cuerpos de la mano (HAND_GRAVCOMP).")
    # Postura "de descanso" hacia la que la IK sesga los grados de libertad
    # redundantes (6 joints para solo 3 restricciones de posición) cuando no
    # hay una preferencia más fuerte marcada por el objetivo de la cámara.
    postura_referencia_brazo = np.array(POSICION_STANDBY_BRAZO, dtype=float)

    # — Entorno de trabajo [3]: se carga escondido —
    taller = EntornoTaller(modelo, datos)
    taladro = EntornoTaladro(modelo, datos)
    demo_taladro = DemoTaladro(modelo, taladro)      # [5] demo automática del taladro

    # Aplicar posición de standby inicial (brazo fijo por ahora, sin IK)
    for i, v in enumerate(POSICION_STANDBY_BRAZO):
        datos.ctrl[i] = float(v)
    for i, v in enumerate(POSICION_STANDBY):
        ctrl_mano[i] = float(v)
    mujoco.mj_step(modelo, datos)

    # — Suavizadores —
    suav_dedos = SuavizadorND(n_dim=N_ACT - 1, ventana=4)  # ctrl[1..16]

    # — Estado compartido de control —
    estado: dict = {
        "camara_activa":    False,
        "muneca_bloqueada": False,
        "pinza_previa":     False,
        "ultima_pos_palma": 0.0,
        "vec_neutro":       None,   # Vector muñeca→MCP calibrado
        "eje_lateral":      None,   # Eje de bisagra de la muñeca
        "neutro_camara_brazo": None,   # (x,y,z) de la muñeca al calibrar con [A]
        "punto_neutro_brazo":  None,   # posición REAL del efector al calibrar con [A]
        "objetivo_brazo":      None,   # punto 3D objetivo actual para el efector del brazo
        "calc_muneca":      0.0,
        "dedo_activo":      "indice",
        "modo_pinza":       False,
        "dedo_bloqueado":   None,     # fija el dedo mientras la pinza está activa
        "ratio_pinza":      0.0,      # factor continuo 0.0 (abierta) → 1.0 (cerrada)
        "pinza_tocando":    False,
        "pinza_habilitada": True,
        # ── Pelota de gomaespuma ────────────────────────────────────────────
        "pelota_visible":   False,
        # ── Soporte / pedestal ──────────────────────────────────────────────
        "soporte_visible":  False,    # True cuando el soporte está activo en MuJoCo
        "spawn_actual":     PUNTOS_SPAWN["arriba"], # ← Guarda la configuración de la pose
    }
    # — Variables de dataset e IA —
    grabando        = False
    buffer_episodio = []   # filas (qpos+ctrl) del episodio que se está grabando ahora
    tarea_actual    = None # nombre de la tarea/maniobra que se está grabando ahora
    modo_autonomo = False
    modo_ia_real  = False
    modo_demo_taladro = False   # [5] demo automática: coger taladro y agujerear el techo
    red_neuronal  = None
    reloj_ia      = 0.0

    pipeline = crear_pipeline_oak()
    salir    = False

    print("\n  Controles: [A] Activar | [S] Standby | [G] Grabar | "
          "[E] Entrenar tarea actual | [Shift+E] Entrenar todas | [P] Pelota ON/OFF | [I] Modo IA (red neuronal) | "
          "[M] Demo Maniobra Autónoma | [4] Taladro | [5] Demo taladro | [Q] Salir\n")

    # Asegurar que el destornillador empieza oculto (fuera de escena)
    _ocultar_destornillador(modelo, datos)
    estado["destornillador_visible"] = False
    
    NOMBRE_VENTANA = "OrcaHand Teleop OAK-D + MuJoCo"  # sin em dash —
    cv2.namedWindow(NOMBRE_VENTANA, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(NOMBRE_VENTANA, int(ANCHO_CAM * ESCALA_VENTANA), int(ALTO_CAM * ESCALA_VENTANA))

    # El logo IDI se dibuja directamente dentro del visor MuJoCo mediante
    # mjr_drawPixels (ver _dibujar_logo_mujoco). No se abre ninguna ventana
    # adicional de OpenCV para el logo.

    while not salir:

        # ══════════════════════════════════════════════════
        # ESTADO A — MODO AUTÓNOMO (Exploración con Ruido/Variación)
        # ══════════════════════════════════════════════════
        if modo_autonomo:
            cv2.destroyAllWindows()
            cv2.namedWindow("Control Autonomo", cv2.WINDOW_AUTOSIZE)

            PINZA_CTRL_CONTACTO = {
                "indice": {10: 0.000, 11: 0.491, 12: 1.250, 13: 0.000, 14: 0.469, 15: 0.469, 16: 0.888},
                "corazon": {8: 0.916, 9: 1.540, 13: 0.426, 14: 0.113, 15: 0.174, 16: 1.720},
                "anular": {4: -0.0565, 5: 1.230, 6: 0.675, 13: 0.000, 14: -0.282, 15: 0.905, 16: 0.526},
                "menique": {1: 0.0995, 2: 1.130, 3: 0.366, 13: 0.576, 14: -0.301, 15: 0.207, 16: 0.888},
                "corazon_anular": {4: 0.066, 5: 1.040, 6: 0.867, 7: 0.000, 8: 1.130, 9: 0.888, 13: 0.406, 14: 0.0171, 15: 0.229, 16: 0.217},
                "indice_corazon": {7: 0.0565, 8: 0.916, 9: 0.835, 10: -0.0571, 11: 0.840, 12: 0.643, 13: 0.419, 14: 0.291, 15: 0.000, 16: 0.526},
                "anular_menique": {1: 0.194, 2: 0.982, 3: 0.739, 4: -0.0377, 5: 0.916, 6: 0.984, 13: 0.236, 14: -0.212, 15: 0.982, 16: 0.292},
            }

            lista_pinzas = list(PINZA_CTRL_CONTACTO.keys())
            intento_actual = 0

            ESTADO_INICIO   = 0
            ESTADO_BAJAR    = 1
            ESTADO_CERRAR   = 2
            ESTADO_SUBIR    = 3
            ESTADO_EVALUAR  = 4
            ESTADO_RESETEAR = 5
            ESTADO_EXITO    = 6
            
            estado_maniobra = ESTADO_INICIO
            tiempo_estado   = 0.0

            # Variables para almacenar la variación única de cada intento
            ruido_muneca = 0.0
            ruido_dedos = {}

            print(f"🤖 Iniciando exploración estocástica. Intentos base: {len(lista_pinzas)}")

            while modo_autonomo and not salir:
                dt = modelo.opt.timestep * 4 
                target_ctrl = np.array(datos.ctrl)
                
                nombre_pinza = lista_pinzas[intento_actual]
                controles_pinza = PINZA_CTRL_CONTACTO[nombre_pinza]

                if estado_maniobra == ESTADO_INICIO:
                    for i, v in enumerate(POSICION_STANDBY):
                        target_ctrl[i] = float(v)
                    target_ctrl[0] = -0.40 
                    
                    if tiempo_estado > 1.0:
                        # Generar ruido aleatorio para este intento específico
                        # La muñeca variará entre +/- 0.15 radianes de su posición ideal (0.55)
                        ruido_muneca = np.random.uniform(-0.15, 0.15)
                        
                        # Cada dedo de la pinza tendrá una variación de +/- 10% en su fuerza
                        ruido_dedos = {idx: np.random.uniform(-0.10, 0.10) for idx in controles_pinza.keys()}
                        
                        estado_maniobra = ESTADO_BAJAR
                        tiempo_estado = 0.0

                elif estado_maniobra == ESTADO_BAJAR:
                    # Aplicamos el ruido a la bajada
                    target_ctrl[0] = 0.55 + ruido_muneca
                    if tiempo_estado > 1.5:
                        estado_maniobra = ESTADO_CERRAR
                        tiempo_estado = 0.0

                elif estado_maniobra == ESTADO_CERRAR:
                    target_ctrl[0] = 0.55 + ruido_muneca
                    for idx, val in controles_pinza.items():
                        # Aplicamos el ruido al cierre y aseguramos que no rompa los límites anatómicos
                        val_con_ruido = val + ruido_dedos[idx]
                        lo, hi = LIMITES_CTRL[idx]
                        target_ctrl[idx] = float(np.clip(val_con_ruido, lo, hi))
                        
                    if tiempo_estado > 1.5: 
                        estado_maniobra = ESTADO_SUBIR
                        tiempo_estado = 0.0

                elif estado_maniobra == ESTADO_SUBIR:
                    target_ctrl[0] = -0.60 
                    for idx, val in controles_pinza.items():
                        val_con_ruido = val + ruido_dedos[idx]
                        lo, hi = LIMITES_CTRL[idx]
                        target_ctrl[idx] = float(np.clip(val_con_ruido, lo, hi))
                        
                    if tiempo_estado > 2.0:
                        estado_maniobra = ESTADO_EVALUAR
                        tiempo_estado = 0.0

                elif estado_maniobra == ESTADO_EVALUAR:
                    jnt_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, "phillips_screwdriver_joint")
                    qa = modelo.jnt_qposadr[jnt_id]
                    z_objeto = datos.qpos[qa + 2] 

                    if z_objeto > 0.26:
                        print(f"✅ ¡ÉXITO! Pinza '{nombre_pinza}' (Ruido muñeca: {ruido_muneca:+.2f}). Z={z_objeto:.2f}m")
                        estado_maniobra = ESTADO_EXITO
                    else:
                        print(f"❌ Falló con '{nombre_pinza}' (Ruido: {ruido_muneca:+.2f}). Z={z_objeto:.2f}m")
                        estado_maniobra = ESTADO_RESETEAR
                    tiempo_estado = 0.0

                elif estado_maniobra == ESTADO_RESETEAR:
                    for i, v in enumerate(POSICION_STANDBY):
                        target_ctrl[i] = float(v)
                    target_ctrl[0] = -0.60 
                    
                    if tiempo_estado > 1.5:
                        # Variación al respawn del destornillador
                        _spawn_destornillador(modelo, datos)
                        jnt_id = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_JOINT, "phillips_screwdriver_joint")
                        qa = modelo.jnt_qposadr[jnt_id]
                        datos.qpos[qa] += np.random.uniform(-0.01, 0.01)   # Variar X +/- 1cm
                        datos.qpos[qa+1] += np.random.uniform(-0.01, 0.01) # Variar Y +/- 1cm
                        mujoco.mj_forward(modelo, datos)
                        
                        intento_actual += 1
                        if intento_actual >= len(lista_pinzas):
                            print("🔄 Reiniciando ciclo de pinzas con nuevos valores aleatorios.")
                            intento_actual = 0
                            
                        estado_maniobra = ESTADO_INICIO
                        tiempo_estado = 0.0

                elif estado_maniobra == ESTADO_EXITO:
                    target_ctrl[0] = -0.60
                    for idx, val in controles_pinza.items():
                        val_con_ruido = val + ruido_dedos[idx]
                        lo, hi = LIMITES_CTRL[idx]
                        target_ctrl[idx] = float(np.clip(val_con_ruido, lo, hi))

                    if tiempo_estado > 2.0:
                        estado_maniobra = ESTADO_RESETEAR
                        tiempo_estado = 0.0

                tiempo_estado += dt

                FACTOR_SUAVIZADO = 0.08 
                for i, (lo, hi) in enumerate(LIMITES_CTRL):
                    ctrl_mano[i] = float(np.clip(
                        ctrl_mano[i] * (1.0 - FACTOR_SUAVIZADO) + target_ctrl[i] * FACTOR_SUAVIZADO, lo, hi))

                if visor.is_running():
                    for _ in range(4): 
                        mujoco.mj_step(modelo, datos)
                    visor.sync()
                    # ── Logo IDI — HUD inferior centrado del visor MuJoCo ────
                    _dibujar_logo_mujoco(visor, _logo_mj_px,
                                         _logo_mj_w, _logo_mj_h)
                else:
                    salir = True 

                # --- HUD ---
                panel = np.zeros((180, 450, 3), dtype=np.uint8)
                nombres_estado = ["INICIO", "BAJANDO", "CERRANDO", "SUBIENDO", "EVALUANDO", "RESETEANDO", "¡EXITO!"]
                
                cv2.putText(panel, f"MODO AUTONOMO - VARIACION ACTIVA", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                cv2.putText(panel, f"Prueba: '{nombre_pinza}'", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 150, 0), 2)
                cv2.putText(panel, f"Variacion Muneca: {ruido_muneca:+.2f} rad", (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                cv2.putText(panel, f"Fase: {nombres_estado[estado_maniobra]}", (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                color_hud = (0, 255, 0) if estado_maniobra == ESTADO_EXITO else (200, 200, 200)
                cv2.putText(panel, f"T. de fase:  {tiempo_estado:.2f} s", (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_hud, 1)
                cv2.putText(panel, "[S] Salir al teleop  |  [Q] Cerrar app", (10, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                # ── Logo IDI en esquina inferior derecha del panel ─────────────
                _superponer_logo(panel, _logo_bgr_sm, _logo_alpha_sm,
                                 margen=5, posicion="bottom-right")
                cv2.imshow("Control Autonomo", panel)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("s"):
                    modo_autonomo = False
                    cv2.destroyWindow("Control Autonomo")
                elif key == ord("q"):
                    salir = True

        # ══════════════════════════════════════════════════
        # ESTADO A2 — MODO IA REAL (Aprendizaje por demostración)
        # Usa el modelo ACT entrenado con [E] a partir de tus episodios
        # grabaciones [G]. En cada paso: mantiene un historial de los últimos
        # fotogramas de postura (en vez de un reloj global), predice la acción
        # (ctrl) y la aplica — así distingue "voy abriendo" de "voy cerrando"
        # aunque la postura instantánea coincida.
        # ══════════════════════════════════════════════════
        elif modo_ia_real:
            cv2.destroyAllWindows()
            cv2.namedWindow("Modo IA Real", cv2.WINDOW_AUTOSIZE)

            print("🧠 Modo IA real activo (ACT) — reproduciendo comportamiento aprendido, "
                  "con ensamblado temporal.")

            usar_hardware_real = (MODO_EJECUCION == "HARDWARE_REAL"
                                   and mano_real and mano_real.conectado)
            if usar_hardware_real:
                print("🤖 HARDWARE REAL activo — la mano física reproducirá "
                      "la maniobra a la vez que la simulación.")
                ultimo_hardware_target = construir_hardware_target(datos)
            else:
                ultimo_hardware_target = None

            modelo_ia = red_neuronal["modelo"]
            mu_x, sigma_x = red_neuronal["mu_x"], red_neuronal["sigma_x"]
            mu_y, sigma_y = red_neuronal["mu_y"], red_neuronal["sigma_y"]
            ventana_k     = red_neuronal["ventana"]
            chunk_h       = red_neuronal["chunk"]
            dt_objetivo   = red_neuronal["dt_objetivo"]
            print(f"   Ritmo de reproducción: {dt_objetivo*1000:.0f} ms/fotograma "
                  f"(~{1/dt_objetivo:.1f} fps, el mismo ritmo al que se grabó).")

            # Historial de qpos: se inicializa repitiendo el primer fotograma real
            # (los actuadores de mano empiezan en OFFSET_MANO, no en 0)
            qpos_inicial = [
                datos.qpos[modelo.jnt_qposadr[modelo.actuator_trnid[OFFSET_MANO + i, 0]]]
                for i in range(N_ACT)
            ]
            historial = deque([qpos_inicial] * ventana_k, maxlen=ventana_k)

            # — Ensamblado temporal (temporal ensembling, como en el paper de ACT) —
            # En cada paso real se predice un bloque NUEVO completo. Se guardan los
            # últimos 'chunk_h' bloques predichos; para decidir la acción del paso
            # actual, se combinan (con pesos exponenciales, más peso a lo más
            # reciente) todas las predicciones que distintos bloques hicieron para
            # ESE mismo instante. Esto suaviza mucho la ejecución y evita saltos
            # bruscos entre bloques consecutivos.
            # PESO_EXP alto = las predicciones recientes pesan mucho más que las
            # antiguas → el movimiento sigue de cerca lo que la red predice AHORA,
            # en vez de mezclarse con predicciones de hace ~2s (que causaban el
            # efecto de "cámara lenta" al promediarse casi por igual).
            # Con chunk=30 y dt≈67ms: PESO_EXP=0.01 → decae solo hasta 0.75 en
            # 2s (casi uniforme, mucha inercia). PESO_EXP=0.15 → decae hasta 0.01
            # en 2s (prioriza fuertemente lo reciente, movimiento mucho más ágil).
            PESO_EXP = 0.15   # 'm' del paper — más alto = confía más en lo reciente
            buffer_bloques = deque(maxlen=chunk_h)  # cada elemento: bloque (chunk_h, N_ACT)
            interrumpido = False

            while modo_ia_real and not salir:
                t_inicio_paso = time.perf_counter()

                # — 1. Predecir un bloque nuevo a partir del historial actual —
                entrada_t = torch.tensor([list(historial)], dtype=torch.float32)
                entrada_norm = (entrada_t - mu_x) / sigma_x
                with torch.no_grad():
                    pred_norm, _, _ = modelo_ia(entrada_norm)   # z=0 (sin demostración)
                bloque_ctrl = (pred_norm[0] * sigma_y + mu_y).numpy()  # (chunk_h, N_ACT)
                buffer_bloques.append(bloque_ctrl)

                # — 2. Ensamblar: recoger, de cada bloque guardado, la predicción
                #      correspondiente al instante ACTUAL, y promediarlas con pesos
                #      exponenciales (el bloque más reciente pesa más) —
                predicciones_paso = []
                for k, bloque_pasado in enumerate(reversed(buffer_bloques)):
                    # k=0 → bloque recién predicho (usa su paso 0)
                    # k=1 → bloque predicho un paso antes (usa su paso 1)... etc.
                    if k < bloque_pasado.shape[0]:
                        predicciones_paso.append((k, bloque_pasado[k]))

                pesos = np.array([math.exp(-PESO_EXP * k) for k, _ in predicciones_paso])
                pesos /= pesos.sum()
                salida = sum(w * p for w, (_, p) in zip(pesos, predicciones_paso))

                # — 3. Aplicar con clip de seguridad anatómica (el ensamblado ya
                #      suaviza, así que aquí no hace falta el filtro exponencial
                #      adicional que usábamos antes) —
                for i, (lo, hi) in enumerate(LIMITES_CTRL):
                    ctrl_mano[i] = float(np.clip(salida[i], lo, hi))

                if visor.is_running():
                    for _ in range(4):
                        mujoco.mj_step(modelo, datos)
                    visor.sync()
                    _dibujar_logo_mujoco(visor, _logo_mj_px, _logo_mj_w, _logo_mj_h)
                else:
                    salir = True
                    break

                # — Enviar también a la mano física, si estamos en HARDWARE_REAL —
                # (con límite de salto máximo: la IA puede predecir cambios más
                # bruscos que una teleoperación humana, así que aquí SÍ se limita,
                # a diferencia de la teleoperación manual)
                if usar_hardware_real:
                    objetivo_hw = construir_hardware_target(datos)
                    objetivo_hw = limitar_salto_hardware(objetivo_hw, ultimo_hardware_target)
                    mano_real.enviar_posiciones(objetivo_hw)
                    ultimo_hardware_target = objetivo_hw

                qpos_state = [
                    datos.qpos[modelo.jnt_qposadr[modelo.actuator_trnid[OFFSET_MANO + i, 0]]]
                    for i in range(N_ACT)
                ]

                # — Red de seguridad: si la predicción desestabiliza la física —
                if not np.all(np.isfinite(qpos_state)) or np.max(np.abs(qpos_state)) > 10.0:
                    print("⚠️  Modo IA real: la simulación se ha desestabilizado. "
                          "Volviendo a STANDBY por seguridad.")
                    modo_ia_real = False
                    for i, v in enumerate(POSICION_STANDBY):
                        ctrl_mano[i] = float(v)
                    mujoco.mj_forward(modelo, datos)
                    if usar_hardware_real:
                        mano_real.enviar_posiciones(construir_hardware_target(datos))
                    cv2.destroyWindow("Modo IA Real")
                    break
                historial.append(qpos_state)

                # --- HUD ---
                panel = np.zeros((150, 420, 3), dtype=np.uint8)
                titulo_hud = "MODO IA REAL (ACT) - Ensamblado temporal"
                if usar_hardware_real:
                    titulo_hud += "  [HARDWARE REAL]"
                cv2.putText(panel, titulo_hud, (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.46, (0, 100, 255) if usar_hardware_real
                            else (0, 255, 255), 2)
                cv2.putText(panel, f"Historial: {ventana_k}  |  Bloque: {chunk_h}  |  "
                                    f"Bloques activos: {len(buffer_bloques)}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
                cv2.putText(panel, f"Ritmo: {dt_objetivo*1000:.0f} ms/fotograma "
                                    f"(~{1/dt_objetivo:.1f} fps, velocidad real)", (10, 85),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 200), 1)
                cv2.putText(panel, "[S] Salir al teleop  |  [Q] Cerrar app", (10, 120),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                _superponer_logo(panel, _logo_bgr_sm, _logo_alpha_sm,
                                  margen=5, posicion="bottom-right")
                cv2.imshow("Modo IA Real", panel)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("s"):
                    modo_ia_real = False
                    if usar_hardware_real:
                        for i, v in enumerate(POSICION_STANDBY):
                            ctrl_mano[i] = float(v)
                        mano_real.enviar_posiciones(construir_hardware_target(datos))
                    cv2.destroyWindow("Modo IA Real")
                elif key == ord("q"):
                    if usar_hardware_real:
                        for i, v in enumerate(POSICION_STANDBY):
                            ctrl_mano[i] = float(v)
                        mano_real.enviar_posiciones(construir_hardware_target(datos))
                    salir = True

                # — Control de ritmo real: esperamos lo que haga falta para que
                #   este fotograma dure lo mismo que duró al grabarlo. Si el
                #   cálculo (predicción + física + render) ya ha tardado más que
                #   eso, no esperamos nada (vamos lo más rápido que se pueda,
                #   pero nunca más rápido que el ritmo real grabado) —
                elapsed = time.perf_counter() - t_inicio_paso
                if elapsed < dt_objetivo:
                    time.sleep(dt_objetivo - elapsed)

        # ══════════════════════════════════════════════════
        # ESTADO A3 — DEMO AUTOMÁTICA DEL TALADRO [5]
        # Sin cámara: el brazo coge el taladro, lo lleva al techo, aprieta el
        # gatillo y hace un agujero. La física avanza aquí al ritmo del reloj real.
        # ══════════════════════════════════════════════════
        elif modo_demo_taladro:
            cv2.destroyAllWindows()
            NOMBRE_DEMO = "Demo Taladro"
            cv2.namedWindow(NOMBRE_DEMO, cv2.WINDOW_AUTOSIZE)
            if taller.disponible and taller.visible:
                taller.ocultar(modelo, datos)               # un escenario cada vez
            if not demo_taladro.iniciar(modelo, datos, visor):
                modo_demo_taladro = False
                cv2.destroyWindow(NOMBRE_DEMO)
                continue
            ts_demo  = float(modelo.opt.timestep)
            deuda    = 0.0
            t_ant    = time.perf_counter()
            periodo  = 1.0 / FISICA_HZ
            while modo_demo_taladro and not salir:
                t0 = time.perf_counter()
                deuda = min(deuda + (t0 - t_ant), FISICA_RETRASO_MAX)
                t_ant = t0
                n_pasos = int(deuda / ts_demo)
                for _ in range(n_pasos):
                    demo_taladro.paso(modelo, datos, ts_demo)   # ctrl de brazo y mano
                    mujoco.mj_step(modelo, datos)
                deuda -= n_pasos * ts_demo

                if visor.is_running():
                    visor.sync()
                    _dibujar_logo_mujoco(visor, _logo_mj_px, _logo_mj_w, _logo_mj_h)
                else:
                    salir = True

                # --- HUD ---
                panel = np.zeros((200, 470, 3), dtype=np.uint8)
                cv2.putText(panel, "DEMO TALADRO (brazo + OrcaHand derecha)", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                cv2.putText(panel, f"Fase: {demo_taladro.fase}", (10, 55),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                rpm = demo_taladro.omega * 60.0 / (2 * math.pi)
                cv2.putText(panel, f"Motor: {'ON ' if demo_taladro.motor else 'OFF'}  ({rpm:4.0f} rpm)",
                            (10, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0) if demo_taladro.motor else (160, 160, 160), 1)
                cv2.putText(panel, f"Indice (gatillo): {datos.ctrl[OFFSET_MANO + 11]:.2f} rad",
                            (10, 107), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
                if demo_taladro.error:
                    cv2.putText(panel, demo_taladro.error, (10, 160), cv2.FONT_HERSHEY_SIMPLEX,
                                0.42, (0, 0, 255), 1)
                cv2.putText(panel, "Agujero:", (10, 135), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                            (200, 200, 200), 1)
                cv2.rectangle(panel, (85, 124), (285, 140), (90, 90, 90), 1)
                cv2.rectangle(panel, (85, 124), (85 + int(200 * demo_taladro.progreso), 140),
                              (0, 165, 255), -1)
                txt_teclas = ("[5] Repetir  |  [S] Volver al teleop  |  [Q] Cerrar"
                              if demo_taladro.terminada else "[S] Cancelar y volver al teleop  |  [Q] Cerrar")
                cv2.putText(panel, txt_teclas, (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
                _superponer_logo(panel, _logo_bgr_sm, _logo_alpha_sm, margen=5, posicion="bottom-right")
                cv2.imshow(NOMBRE_DEMO, panel)

                key = cv2.waitKey(1) & 0xFF
                if key == ord("s"):
                    demo_taladro.terminar(modelo, datos)
                    modo_demo_taladro = False
                    cv2.destroyWindow(NOMBRE_DEMO)
                elif key == ord("5") and demo_taladro.terminada:
                    demo_taladro.iniciar(modelo, datos, visor)
                    t_ant = time.perf_counter()
                elif key == ord("q"):
                    salir = True

                espera = periodo - (time.perf_counter() - t0)
                if espera > 0:
                    time.sleep(espera)

        # ══════════════════════════════════════════════════
        # ESTADO B — TELEOPERACIÓN HUMANA (cámara activa)
        # ══════════════════════════════════════════════════
        else:
            print("⚡ Conectando OAK-D (puede tardar ~2 s)...")

            with dai.Device(pipeline) as device:
                # ── PROYECTOR IR DE PUNTOS (OAK-D Pro) ────────────────────────
                # Añade textura donde la piel/manga no tiene ninguna: es la causa
                # nº1 de que el estéreo del BRAZO (fino, poca textura, 1.5-2 m)
                # dé profundidades disparatadas (ver el codo a 86-106° del 28-sep
                # con el brazo casi recto). Sin efecto en el color/RGB.
                try:
                    device.setIrLaserDotProjectorBrightness(800)   # mA, máx. ~1200 en la Pro
                    # device.setIrFloodLightBrightness(200)        # solo si la sala está oscura
                    print("💡 [OAK] Proyector IR de puntos activado (800 mA)")
                except Exception as e_ir:
                    try:
                        device.setIrLaserDotProjectorIntensity(0.65)   # API alternativa (0.0-1.0)
                        print("💡 [OAK] Proyector IR de puntos activado (intensidad 0.65)")
                    except Exception as e_ir2:
                        print(f"⚠️  [OAK] No se pudo activar el proyector IR: {e_ir} / {e_ir2}")

                q_color = device.getOutputQueue("color", maxSize=1, blocking=False)
                usar_hd = MANO_RECORTE and MANO_RECORTE_HD and CAM_FOV_COMPLETO
                q_hd    = device.getOutputQueue("color_hd", maxSize=4, blocking=False) \
                          if usar_hd else None
                buf_hd  = deque(maxlen=6)
                t_ult_print_pinza = 0.0
                origen_mano = "-"
                # maxSize=4: guardamos varios mapas de profundidad para poder elegir
                # el que corresponde EN EL TIEMPO al fotograma de color (ver bucle).
                q_depth = device.getOutputQueue("depth", maxSize=4, blocking=False)
                buf_depth = deque(maxlen=6)   # paquetes de profundidad recientes
                _fps_n, _fps_t0, _fps_val = 0, time.perf_counter(), 0.0

                # Focal REAL de la cámara para este tamaño de fotograma (viene de la
                # calibración de fábrica). Si falla, se usa F_PX de config.py.
                try:
                    _K = device.readCalibration().getCameraIntrinsics(
                        dai.CameraBoardSocket.CAM_A, ANCHO_CAM, ALTO_CAM)
                    f_px_cam = float(_K[0][0])
                    print(f"📷 Focal calibrada OAK-D: {f_px_cam:.1f} px "
                          f"(fotograma {ANCHO_CAM}x{ALTO_CAM})")
                except Exception as e_cal:
                    f_px_cam = F_PX
                    print(f"⚠️  No se pudo leer la calibración ({e_cal}); uso F_PX={F_PX}")

                angulos_brazo    = None   # últimos ángulos válidos del brazo humano
                t_ult_ang_valido = 0.0    # perf_counter() del último frame con _ang != None
                t_ult_print_ang  = 0.0
                est_brazo        = EstimadorLongitudesBrazo(LONG_BRAZO_MANUAL)
                suav_brazo       = SuavizadorND(n_dim=3, ventana=IMITAR_SUAVIZADO)
                brazo_imit_activo = False   # True cuando el brazo ya está imitando
                refs_tpose       = []       # (az, elev, codo) medidos durante la calibración
                tpose_med        = None     # mediana de refs_tpose (None = sin corrección)
                tpose_ref        = tuple(T_POSE_HUMANA)   # T-pose usada como referencia
                q_ref_sim        = None     # pose de reposo del sim (joint1-3) al empezar a imitar
                q_imit           = None     # último objetivo enviado a joint1..3 (rad)
                hib              = None     # datos del híbrido (alcance y ejes del ARCTOS)
                q_ik_prev        = None     # última solución de la IK (continuidad)
                peso_hib         = HIBRIDO_PESO
                suav_obj         = SuavizadorND(n_dim=3, ventana=HIBRIDO_SUAVIZADO)
                suav_codo        = SuavizadorND(n_dim=3, ventana=HIBRIDO_SUAVIZADO)
                ik_info          = None     # (obj. codo, obj. muñeca, peso codo) para el debug
                oe_brazo         = FiltroOneEuro()   # PASO 5: dirección del brazo
                oe_antebrazo     = FiltroOneEuro()   # PASO 5: dirección del antebrazo
                t_atasco         = None     # PASO 6: desde cuándo la IK está atascada
                t_ult_rescate    = 0.0      # PASO 6: último cambio de solución (espera entre cambios)
                lat_local        = None     # índice→meñique de la mano del robot (ejes de la mano)
                lat_cal          = []       # muestras para calibrarlo en la T-pose
                mano_girada      = False    # PASO 6: robot en configuración "girada"
                t_prev_imit      = time.perf_counter()
                t_ult_print_q    = 0.0
                # ── Paso 5: pronosupinación ──
                prono_idx    = ARM_JOINTS.index(PRONO_JOINT)   # 5 = joint6 (ctrl[5])
                roll_ref     = None      # giro neutro medido en la T-pose
                refs_roll    = []
                q_prono_ref  = float(POSICION_STANDBY_BRAZO[prono_idx])
                q_prono      = q_prono_ref
                d_prev       = 0.0
                t_prev_prono = time.perf_counter()
                t_ult_print_roll = 0.0
                estado["antebrazo"] = None
                estado["arriba"]    = None
                estado["eje_codo"]  = None

                # ── PASO 7 — brazo preciso y sin saltos ──
                # 7.1: el generador suave escribe ctrl de joint1..3 y del giro de muñeca
                #      antes de cada mj_step; el bucle solo le PUBLICA objetivos.
                gen_brazo = None
                if SUAVE_ACTIVO and MODO_BRAZO == "imitacion":
                    gen_brazo = GeneradorSuave((0, 1, 2, prono_idx), SUAVE_VEL_MAX, SUAVE_ACEL_MAX)
                    gen_brazo.activar(datos)
                    print(f"🧈 Comando continuo del brazo activo (vel. máx {SUAVE_VEL_MAX} rad/s, "
                          f"acel. máx {SUAVE_ACEL_MAX} rad/s²)")

                def _enviar_brazo(indices, valores):
                    """Objetivos del brazo: al generador suave (si está activo) o directos."""
                    if gen_brazo is not None and gen_brazo.activo:
                        gen_brazo.enviar(datos, indices, valores)
                    else:
                        for _i_b, _v_b in zip(indices, valores):
                            datos.ctrl[_i_b] = float(_v_b)

                # 7.2: filtro de saltos + zona muerta; 7.3: modo fino / congelar
                filtro_saltos = FiltroSaltos()
                zm_palma      = ZonaMuerta(ZONA_MUERTA_PALMA)
                zm_codo       = ZonaMuerta(ZONA_MUERTA_PALMA)
                canal_palma   = CanalFino(FINO_ESCALA, vel_salida=FINO_SALIDA_VEL)
                canal_giro    = CanalFino(FINO_ESCALA_GIRO, angular=True, vel_salida=1.0)
                dirs_ok       = None     # últimas direcciones (brazo, antebrazo) aceptadas
                brazo_fino, brazo_congelado = False, False
                q6_obj_prev   = None     # último objetivo fiable del giro (modo mundo)

                # — Física en tiempo real en su propio hilo (ver HiloFisica) —
                fisica  = HiloFisica(modelo, datos, visor,
                                     antes_de_paso=gen_brazo.paso if gen_brazo is not None else None) \
                          if FISICA_EN_HILO else None
                _soltar = fisica.soltar if fisica is not None else nullcontext
                if fisica is not None:
                    fisica.empezar()
                    print(f"⚙️  Física en tiempo real: hilo propio a {FISICA_HZ} Hz "
                          f"(paso {modelo.opt.timestep * 1000:.1f} ms)")

                while not modo_autonomo and not modo_ia_real and not modo_demo_taladro \
                        and not salir:
                    # — Captura de frames (COLOR y PROFUNDIDAD SINCRONIZADOS) —
                    # Antes se hacía q_color.get() y q_depth.get() por separado: como
                    # son colas independientes, el mapa de profundidad podía ir 1-2
                    # fotogramas desfasado respecto al color. Con el brazo en
                    # movimiento eso significa leer la profundidad DEL FONDO en el
                    # píxel de la muñeca → z descartada → "brazo perdido".
                    with _soltar():                   # esperar a la cámara: la física sigue
                        _pkt_color = q_color.get()
                    frame_bgr  = _pkt_color.getCvFrame()
                    _t_color   = _pkt_color.getTimestamp()

                    while True:                       # vaciar lo que haya llegado
                        _p = q_depth.tryGet()
                        if _p is None:
                            break
                        buf_depth.append(_p)
                    if not buf_depth:                 # primer fotograma: esperar
                        buf_depth.append(q_depth.get())

                    _pkt_depth  = min(
                        buf_depth,
                        key=lambda p: abs((p.getTimestamp() - _t_color).total_seconds()))
                    frame_depth = _pkt_depth.getFrame()

                    # Imagen HD para el recorte de la mano (la más cercana en el tiempo)
                    frame_hd = None
                    if q_hd is not None:
                        while True:
                            _p = q_hd.tryGet()
                            if _p is None:
                                break
                            buf_hd.append(_p)
                        if buf_hd:
                            _pkt_hd = min(
                                buf_hd,
                                key=lambda p: abs((p.getTimestamp() - _t_color).total_seconds()))
                            if abs((_pkt_hd.getTimestamp() - _t_color).total_seconds()) < 0.05:
                                frame_hd = _pkt_hd.getCvFrame()

                    # — Medidor de FPS reales del bucle —
                    _fps_n += 1
                    if _fps_n >= 15:
                        _ahora  = time.perf_counter()
                        _fps_val = _fps_n / max(1e-6, _ahora - _fps_t0)
                        _fps_n, _fps_t0 = 0, _ahora
                        if POSE_MEDIR_FPS:
                            print(f"\r⏱️  Bucle teleop: {_fps_val:5.1f} FPS   ",
                                  end="", flush=True)

                    frame_rgb   = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    frame_rgb.flags.writeable = False   # evita una copia en MediaPipe


                    # — Detección de CUERPO (solo visual por ahora) —
                    # Se dibuja ANTES que la mano para que los dedos queden encima.
                    with _soltar():                   # MediaPipe Pose: la física sigue
                        resultado_pose = detector_pose.process(frame_rgb)
                    if MOSTRAR_ESQUELETO_CUERPO and resultado_pose.pose_landmarks:
                        mp_draw.draw_landmarks(
                            frame_bgr, resultado_pose.pose_landmarks,
                            mp_pose.POSE_CONNECTIONS,
                            landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style())

                    # — Ángulos del brazo humano (paso 3: solo calcular y mostrar) —
                    if resultado_pose.pose_world_landmarks and resultado_pose.pose_landmarks:
                        _calib_antes = est_brazo.calibrando   # ¿estamos aún en la T-pose de calibración?
                        _ang_mp = calcular_angulos_brazo_humano(
                            resultado_pose.pose_world_landmarks, BRAZO_HUMANO)
                        _ang_es = calcular_angulos_brazo_estereo(
                            resultado_pose.pose_landmarks, frame_depth, f_px_cam, BRAZO_HUMANO,
                            estimador=est_brazo,
                            pose_world_lm=resultado_pose.pose_world_landmarks)
                        _ang = _ang_es if BRAZO_FUENTE_3D == "estereo" else _ang_mp
                        # FUSIÓN DE DIRECCIONES (28-sep): el estéreo daba codos de 86-106°
                        # con el brazo casi recto (MediaPipe: 12-36°). Cada segmento (brazo,
                        # antebrazo) usa la dirección del estéreo SOLO si se parece a la de
                        # MediaPipe; si se desvía más de FUSION_DIR_MAX_DEG, usa MediaPipe.
                        if BRAZO_FUENTE_3D == "estereo" and _ang_es is not None \
                                and _ang_mp is not None and FUSION_DIR_MAX_DEG > 0 \
                                and "dir_brazo" in _ang_es and "dir_brazo" in _ang_mp:
                            _ang_es["fusion"] = ""
                            for _k, _et in (("dir_brazo", "B"), ("dir_antebrazo", "A")):
                                # PASO 7.2: mezcla gradual (antes: cambio de golpe → salto)
                                _ang_es[_k], _w_es = fusionar_direccion(_ang_es[_k], _ang_mp[_k])
                                if _w_es < 0.99:
                                    _ang_es["fusion"] += f"{_et}{100 * (1 - _w_es):.0f}%"
                            if _ang_es["fusion"]:          # el codo, coherente con las direcciones
                                _ang_es["codo"] = math.degrees(math.acos(float(np.clip(
                                    _ang_es["dir_brazo"] @ _ang_es["dir_antebrazo"], -1.0, 1.0))))
                        if _calib_antes and _ang is not None:
                            refs_tpose.append((_ang["azimut"], _ang["elevacion"], _ang["codo"]))

                        if _ang is not None:
                            # Con el brazo casi vertical el azimut es ruido: se
                            # conserva el último valor fiable.
                            if not _ang["azimut_fiable"] and angulos_brazo is not None:
                                _ang["azimut"]        = angulos_brazo["azimut"]
                                _ang["azimut_muneca"] = angulos_brazo["azimut_muneca"]
                            angulos_brazo    = _ang
                            t_ult_ang_valido = time.perf_counter()

                            _col = (0, 255, 0) if _ang["azimut_fiable"] else (0, 200, 255)
                            _y0  = ALTO_CAM - 62
                            for _k, _txt in enumerate((
                                    f"Brazo {BRAZO_HUMANO} [{BRAZO_FUENTE_3D}] ref:{_ang['ref']}"
                                    + ("  CODO ESTIMADO" if _ang.get("codo_estimado") else ""),
                                    f"Azimut    {angulos_brazo['azimut']:7.1f}",
                                    f"Elevacion {_ang['elevacion']:7.1f}",
                                    f"Codo      {_ang['codo']:7.1f}")):
                                cv2.putText(frame_bgr, _txt, (10, _y0 + 15 * _k),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, _col, 1)
                        else:
                            cv2.putText(frame_bgr,
                                        f"Brazo {BRAZO_HUMANO}: sin datos ({BRAZO_FUENTE_3D}) "
                                        + (est_brazo.motivo_fallo[:55] if BRAZO_FUENTE_3D == "estereo" else ""),
                                        (10, ALTO_CAM - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)

                        if DEBUG_ANGULOS_BRAZO and \
                           (time.time() - t_ult_print_ang) >= DEBUG_ANGULOS_CADA_S:
                            t_ult_print_ang = time.time()
                            _extra = ""
                            if _ang_es is not None:
                                _v = _ang_es["vis"]
                                _extra = (f"   vis(h/c/m)={_v[0]:.2f}/{_v[1]:.2f}/{_v[2]:.2f}"
                                          f"   prof[{_ang_es['fuentes']}]"
                                          + (f"  [MP en {_ang_es['fusion']}]" if _ang_es.get("fusion") else "")
                                          + ("  [CODO ESTIMADO]" if _ang_es["codo_estimado"] else ""))
                            else:
                                _extra = f"   [SIN DATOS ESTEREO: {est_brazo.motivo_fallo or '?'}]"
                            _lon = est_brazo.longitudes
                            _extra += (f"   huesos={_lon[0]:.2f}/{_lon[1]:.2f}m" if _lon else
                                       "   huesos=aprendiendo")
                            print(f"[ANGULOS BRAZO {BRAZO_HUMANO}] "
                                  f"ESTEREO: {_fmt_ang(_ang_es)}   |   "
                                  f"MEDIAPIPE: {_fmt_ang(_ang_mp)}{_extra}")

                        # ══ PASO 4 — el brazo ARCTOS IMITA los ángulos del brazo humano ══
                        # Solo con la cámara activa ([A]) y los huesos ya calibrados. joint4-6
                        # (giro de antebrazo y muñeca) se quedan en su valor de standby.
                        #
                        # _ang_uso: si el frame actual falló (depth ruidosa, oclusión de
                        # un instante) pero tenemos un ángulo válido de hace poco (< 
                        # ANG_BRAZO_HOLD_S), lo seguimos usando en vez de congelar el brazo.
                        # Si ya ha pasado más tiempo que eso, se considera que el brazo se
                        # ha perdido de verdad y no se actualiza (mejor que "adivinar").
                        if _ang is not None:
                            _ang_uso = _ang
                        elif angulos_brazo is not None and \
                                (time.perf_counter() - t_ult_ang_valido) <= ANG_BRAZO_HOLD_S:
                            _ang_uso = angulos_brazo
                        else:
                            _ang_uso = None

                        if _ang_uso is not None and "antebrazo" in _ang_uso:
                            estado["antebrazo"] = _ang_uso["antebrazo"]
                            estado["arriba"]    = _ang_uso["arriba"]
                            # Eje del codo del ARCTOS: horizontal y perpendicular al plano
                            # vertical del brazo (el que fija joint1 con tu azimut). Con el
                            # brazo vertical el azimut ya es el último fiable → no degenera.
                            _az  = math.radians(_ang_uso["azimut"])
                            _dir = (_ang_uso["lado"] * math.sin(_az) * _ang_uso["derecha"]
                                    + math.cos(_az) * _ang_uso["delante"])
                            estado["eje_codo"] = _unitario(np.cross(_ang_uso["arriba"], _dir))
                            estado["az_brazo"] = _ang_uso["azimut"]
                            estado["torso"]    = (_ang_uso["derecha"], _ang_uso["arriba"],
                                                  _ang_uso["delante"], _ang_uso["lado"])

                        if MODO_BRAZO == "imitacion" and estado["camara_activa"] \
                                and est_brazo.calibrado and _ang_uso is not None:
                            _t = time.perf_counter()
                            if not brazo_imit_activo:
                                # T-pose medida durante la calibración → referencia de postura
                                tpose_med = None
                                if IMITAR_CALIBRAR_TPOSE and len(refs_tpose) >= 10:
                                    _r = np.median(np.array(refs_tpose, dtype=float), axis=0)
                                    if 45.0 < _r[1] < 135.0:
                                        tpose_med = (float(_r[0]), float(_r[1]), float(_r[2]))
                                        print(f"📐 T-pose medida: az={_r[0]:.1f}°  elev={_r[1]:.1f}°  "
                                              f"codo={_r[2]:.1f}°  (ideal {T_POSE_HUMANA[0]:.0f}/"
                                              f"{T_POSE_HUMANA[1]:.0f}/{T_POSE_HUMANA[2]:.0f}) "
                                              f"→ sesgo elev {_r[1] - T_POSE_HUMANA[1]:+.1f}°")
                                    else:
                                        print(f"⚠️  T-pose medida incoherente (elev={_r[1]:.1f}°): "
                                              "no se aplica corrección. Repite [S] y [A] con el brazo horizontal.")
                                tpose_ref = tpose_med if tpose_med is not None else tuple(T_POSE_HUMANA)
                                # Arranque suave: se parte de donde YA está el brazo
                                q_imit = np.array([datos.ctrl[0], datos.ctrl[1], datos.ctrl[2]])
                                q_ref_sim = q_imit.copy()   # el reposo del sim ↔ tu T-pose (modo relativo)
                                if IMITAR_REFERENCIA == "relativo":
                                    print(f"🔗 Referencia RELATIVA: reposo del sim q1={q_ref_sim[0]:.2f} "
                                          f"q2={q_ref_sim[1]:.2f} q3={q_ref_sim[2]:.2f} ↔ tu T-pose. "
                                          "El brazo no se mueve al calibrar.")
                                suav_brazo.reset()
                                hib = preparar_hibrido(modelo, datos, qpos_idx_brazo)
                                q_ik_prev = None
                                suav_obj.reset()
                                suav_codo.reset()
                                oe_brazo.reset()
                                oe_antebrazo.reset()
                                t_atasco, mano_girada = None, False
                                lat_local, lat_cal = None, []    # se recalibra en esta T-pose
                                # PASO 7: filtros de saltos, zona muerta y modo fino desde cero
                                filtro_saltos.reset(); zm_palma.reset(); zm_codo.reset()
                                canal_palma.reset(); canal_giro.reset()
                                dirs_ok, q6_obj_prev = None, None
                                brazo_fino, brazo_congelado = False, False
                                aplicar_modo_brazo(False, False, (), gen_brazo)
                                if IK_RESCATE_GIRADA and hib["lo"][1] > -1.0:
                                    print(f"ℹ️  Rescate 'codo al otro lado' inactivo: IMITAR_LIMITES['joint2'] "
                                          f"empieza en {hib['lo'][1]:.2f} (hace falta < -1.0 para inclinar "
                                          f"el hombro hacia atrás).")
                                print(f"🖐️  Híbrido listo: alcance ARCTOS = {hib['alcance']:.3f} m  "
                                      f"(brazo {hib['L_brazo']:.3f} m + antebrazo {hib['L_antebrazo']:.3f} m)"
                                      f"  modo={HIBRIDO_MODO}  objetivo={HIBRIDO_OBJETIVO} "
                                      f"(hombro→punta {hib['alcance_punta']:.3f} m, codo→punta "
                                      f"{hib['L_antebrazo_punta']:.3f} m)")
                                brazo_imit_activo = True
                                t_prev_imit = _t
                                print("🦾 Imitación del brazo ACTIVADA.")
                            _dt_imit    = min(_t - t_prev_imit, 0.1)
                            t_prev_imit = _t

                            if IMITAR_REFERENCIA == "relativo":
                                _q_obj = angulos_humano_a_q_brazo_rel(
                                    _ang_uso["azimut"], _ang_uso["elevacion"], _ang_uso["codo"],
                                    tpose_ref, q_ref_sim)
                                _el_c = _ang_uso["elevacion"] - tpose_ref[1]  # Δ respecto a tu T-pose
                            else:
                                _az_c, _el_c, _co_c = corregir_con_tpose(_ang_uso, tpose_med)
                                _q_obj = angulos_humano_a_q_brazo(
                                    math.radians(_az_c),
                                    math.radians(_el_c),
                                    math.radians(_co_c))
                            # ══ PASO 2 — HÍBRIDO: tu mano decide dónde va la mano del robot ══
                            _obj_mano = None
                            ik_info   = None
                            if peso_hib > 0.0 and hib is not None and HIBRIDO_MODO == "codo_muneca" \
                                    and "dir_brazo" in _ang_uso:
                                # PASO 3: tus DIRECCIONES → objetivos de codo y muñeca → IK
                                _d_b = _ang_uso["dir_brazo"]
                                _d_a = _ang_uso["dir_antebrazo"]
                                _t_oe = time.perf_counter()
                                _lon_h = est_brazo.longitudes or (0.30, 0.28)

                                def _objetivos(db, da):
                                    if HIBRIDO_OBJETIVO == "palma":
                                        return objetivos_codo_palma(datos, db, da, hib, _lon_h)
                                    return objetivos_codo_muneca(datos, db, da, hib)

                                # PASO 7.2: FILTRO DE SALTOS, antes del One Euro (que dejaría
                                # pasar el salto creyendo que es un movimiento rápido)
                                if SALTO_VEL_MAX > 0:
                                    if _ang is None and dirs_ok is not None:
                                        _d_b, _d_a = dirs_ok      # sin medida nueva: la última BUENA
                                    elif filtro_saltos.aceptar(_objetivos(_d_b, _d_a), _t_oe) \
                                            or dirs_ok is None:
                                        dirs_ok = (_d_b, _d_a)
                                    else:
                                        _d_b, _d_a = dirs_ok      # medida imposible → la última buena
                                if FILTRO_ONE_EURO:       # PASO 5: filtro sobre las direcciones
                                    _d_b0, _d_a0 = _d_b, _d_a
                                    _d_b = _unitario(oe_brazo(_d_b, _t_oe))
                                    _d_a = _unitario(oe_antebrazo(_d_a, _t_oe))
                                    if _d_b is None or _d_a is None:
                                        _d_b, _d_a = _d_b0, _d_a0
                                _d_a = enderezar(_d_b, _d_a)
                                _w_c = peso_codo_humano(_d_b, _d_a)
                                _oc, _om = _objetivos(_d_b, _d_a)
                                if not FILTRO_ONE_EURO:   # sin One Euro: medias móviles de antes
                                    _oc = suav_codo.actualizar(_oc)
                                    _om = suav_obj.actualizar(_om)
                                # PASO 7.2: zona muerta → quieto de verdad cuando estás quieto
                                _oc, _om = zm_codo(_oc), zm_palma(_om)
                                # PASO 7.3: modo fino / congelado (sobre la palma)
                                _om = canal_palma(_om, _t_oe,
                                                  limitar=lambda p: limitar_alcance_palma(datos, p, hib))
                                _modo_b = canal_palma.modo
                                if _modo_b != "normal":
                                    _w_c = 0.0            # en fino/congelado manda solo la palma
                                if _modo_b == "congelado" and q_ik_prev is not None:
                                    _q_ik, _ec_ik, _em_ik = q_ik_prev.copy(), 0.0, 0.0
                                else:
                                    _q_ik, _ec_ik, _em_ik = resolver_ik_codo_muneca(
                                        modelo, datos, _oc, _om, _w_c, hib,
                                        q_inicial=q_ik_prev if q_ik_prev is not None else _q_obj,
                                        q_ref=q_ik_prev, w_cont=IK_PESO_CONTINUIDAD)

                                # PASO 6: RESCATE — si lleva un rato atascada (o está "girada"),
                                # probar otras posturas de partida. Todo se compara por COSTE:
                                # error + penalización por girar la base + por ir "girada".
                                _err_ik = math.hypot(_w_c * _ec_ik, _em_ik)
                                _t_ik   = time.perf_counter()
                                _q1_ref = float(_q_obj[0])          # base que pide tu azimut
                                _girada = es_girada(_q_ik, _q1_ref)
                                if (_err_ik <= IK_RESCATE_ERROR and not _girada) or \
                                        (_modo_b != "normal" and not IK_RESCATE_EN_FINO):
                                    t_atasco = None               # (en fino/congelado no hay rescate)
                                elif t_atasco is None:
                                    t_atasco = _t_ik
                                elif (_t_ik - t_atasco >= IK_RESCATE_TIEMPO
                                      and _t_ik - t_ult_rescate >= IK_RESCATE_ESPERA):
                                    _semillas = [("tu postura (ángulos)", _q_obj),
                                                 ("reposo", np.array(POSICION_STANDBY_BRAZO[:3], dtype=float))]
                                    # La configuración girada solo tiene sentido con el codo
                                    # DOBLADO de verdad (con el brazo recto no aporta nada).
                                    if IK_RESCATE_GIRADA and hib["lo"][1] <= -1.0 \
                                            and _w_c >= 0.9 * HIBRIDO_PESO_CODO:
                                        _semillas += [("codo al otro lado", semilla_girada(_q_ik)),
                                                      ("codo al otro lado (ángulos)", semilla_girada(_q_obj))]
                                    _q_r, _err_r, _c_r, _nom_r = rescatar_ik(
                                        modelo, datos, _oc, _om, _w_c, hib, _semillas,
                                        q_actual=_q_ik, q1_ref=_q1_ref)
                                    _c_act = coste_ik(_q_ik, _err_ik, _q_ik, _q1_ref)
                                    if _q_r is not None and _c_r < IK_RESCATE_MEJORA * _c_act:
                                        print(f"[IK RESCATE] desde '{_nom_r}': error "
                                              f"{100 * _err_ik:.1f} → {100 * _err_r:.1f} cm"
                                              f"{'  (GIRADA)' if es_girada(_q_r, _q1_ref) else ''}")
                                        _q_ik = _q_r
                                        t_ult_rescate = _t_ik
                                    t_atasco = None
                                q_ik_prev = _q_ik.copy()
                                ik_info   = (_oc, _om, _w_c)
                                _p_h = 1.0 if _modo_b != "normal" else peso_hib   # fino/congelado: solo IK
                                _q_obj = (1.0 - _p_h) * np.asarray(_q_obj) + _p_h * _q_ik
                                for _k, _jn in enumerate(("joint1", "joint2", "joint3")):
                                    _q_obj[_k] = float(np.clip(_q_obj[_k], *IMITAR_LIMITES[_jn]))
                            elif peso_hib > 0.0 and hib is not None and est_brazo.longitudes \
                                    and "hombro_muneca" in _ang_uso:
                                _obj_mano = suav_obj.actualizar(objetivo_mano_hibrido(
                                    datos, _ang_uso["hombro_muneca"],
                                    sum(est_brazo.longitudes), hib))
                                _q_ik = resolver_ik_brazo(
                                    modelo, datos, _obj_mano,
                                    dof_idx_brazo[:3], qpos_idx_brazo[:3],
                                    nombre_body_efector="mano_mount",
                                    offset_local_efector=OFFSET_LOCAL_MUNON,
                                    n_iter=HIBRIDO_IK_ITER, paso_max=HIBRIDO_IK_PASO,
                                    # parte de la solución anterior (sin saltos de postura);
                                    # la primera vez, de TU postura por ángulos
                                    q_inicial=q_ik_prev if q_ik_prev is not None else _q_obj)
                                q_ik_prev = _q_ik.copy()
                                _q_obj = (1.0 - peso_hib) * np.asarray(_q_obj) + peso_hib * _q_ik
                                for _k, _jn in enumerate(("joint1", "joint2", "joint3")):
                                    _q_obj[_k] = float(np.clip(_q_obj[_k], *IMITAR_LIMITES[_jn]))
                            if not (FILTRO_ONE_EURO and ik_info is not None):
                                _q_obj = suav_brazo.actualizar(_q_obj)   # (con One Euro ya viene filtrado)
                            if gen_brazo is not None and gen_brazo.activo:
                                # PASO 7.1: solo se publica el objetivo; el hilo de física
                                # lo alcanza de forma continua (vel. y acel. limitadas)
                                q_imit = np.asarray(_q_obj, dtype=float).copy()
                                _enviar_brazo((0, 1, 2), q_imit)
                            else:
                                q_imit = limitar_velocidad_articular(
                                    _q_obj, q_imit, _dt_imit, IMITAR_VEL_MAX)
                                for _i in range(3):
                                    datos.ctrl[_i] = float(q_imit[_i])

                            if DEBUG_ANGULOS_BRAZO and (time.time() - t_ult_print_q) >= DEBUG_ANGULOS_CADA_S:
                                t_ult_print_q = time.time()
                                _q_real = [datos.qpos[_qi] for _qi in qpos_idx_brazo[:3]]
                                _sim_real = (fisica.factor if fisica is not None
                                             else 4 * modelo.opt.timestep / max(_dt_imit, 1e-3))
                                _hold_txt = "" if _ang is not None else \
                                    f"  [HOLD {time.perf_counter() - t_ult_ang_valido:.2f}s]"
                                _modo_txt = ("" if canal_palma.modo == "normal" else
                                             f"  [{canal_palma.modo.upper()}]")
                                if SALTO_VEL_MAX > 0 and filtro_saltos.rechazados:
                                    _modo_txt += f"  [saltos filtrados: {filtro_saltos.rechazados}]"
                                if gen_brazo is not None and gen_brazo.activo:
                                    _modo_txt += (f"  [OBJ q1={q_imit[0]:5.2f} q2={q_imit[1]:5.2f} "
                                                  f"q3={q_imit[2]:5.2f}]")
                                print(f"[BRAZO IMITA] humano az={_ang_uso['azimut']:6.1f}° "
                                      f"elev={_ang_uso['elevacion']:5.1f}° ({'Δ' if IMITAR_REFERENCIA == 'relativo' else 'corr'} {_el_c:5.1f}°) "
                                      f"codo={_ang_uso['codo']:5.1f}°  →  "
                                      f"CMD q1={datos.ctrl[0]:6.2f} q2={datos.ctrl[1]:5.2f} q3={datos.ctrl[2]:5.2f}  |  "
                                      f"REAL q1={_q_real[0]:6.2f} q2={_q_real[1]:5.2f} q3={_q_real[2]:5.2f} rad  |  "
                                      f"sim/real={_sim_real:.2f}x{_hold_txt}{_modo_txt}")
                                if ik_info is not None:
                                    _oc, _om, _w_c = ik_info
                                    _ec = np.linalg.norm(_oc - datos.xanchor[hib["j_codo"]])
                                    _em = np.linalg.norm(
                                        _om - (datos.xpos[hib["b_mano"]]
                                               + datos.xmat[hib["b_mano"]].reshape(3, 3) @ hib["off_punta"]))
                                    print(f"[HIBRIDO codo+muñeca] error codo={100 * _ec:4.1f} cm "
                                          f"(peso {_w_c:.2f})   error muñeca={100 * _em:4.1f} cm   "
                                          f"muñeca obj=({_om[0]:.2f}, {_om[1]:.2f}, {_om[2]:.2f}) m")
                                if _obj_mano is not None:
                                    _bm = mujoco.mj_name2id(modelo, mujoco.mjtObj.mjOBJ_BODY, "mano_mount")
                                    _err = np.linalg.norm(_obj_mano - datos.xpos[_bm])
                                    print(f"[HIBRIDO] objetivo=({_obj_mano[0]:.2f}, {_obj_mano[1]:.2f}, "
                                          f"{_obj_mano[2]:.2f}) m   error mano={100 * _err:4.1f} cm   "
                                          f"peso={peso_hib:.2f}")

                    # — Estado de la calibración de huesos / imitación (HUD) —
                    if MODO_BRAZO == "imitacion" and estado["camara_activa"]:
                        if est_brazo.calibrando:
                            cv2.putText(frame_bgr,
                                        f"CALIBRANDO HUESOS {est_brazo.progreso}/{est_brazo.n_objetivo}"
                                        f" - manten T-pose (brazo estirado)",
                                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 2)
                        elif est_brazo.calibrado and brazo_imit_activo:
                            if brazo_congelado:
                                _txt_b, _col_b = "BRAZO: CONGELADO [C]", (0, 165, 255)
                            elif brazo_fino:
                                _txt_b, _col_b = f"BRAZO: FINO x{FINO_ESCALA:.2f} [F]", (255, 255, 0)
                            else:
                                _txt_b, _col_b = "BRAZO: IMITANDO", (0, 255, 0)
                            cv2.putText(frame_bgr, _txt_b, (10, 50),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, _col_b, 1)
                        elif est_brazo.calibrado:
                            cv2.putText(frame_bgr,
                                        f"BRAZO: {'HIBRIDO' if peso_hib > 0 else 'ANGULOS'} [H]",
                                        (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                    # — Detección de mano —
                    # 1º) Recorte alrededor de TU mano (la del BRAZO_HUMANO) según Pose.
                    # 2º) Si Pose no ve la muñeca o en el recorte no hay mano, imagen
                    #     completa como antes (p.ej. mano cerca de la cámara sin cuerpo).
                    resultado   = None
                    origen_mano = "-"
                    if MANO_RECORTE and resultado_pose.pose_landmarks:
                        _img_rec = frame_hd if frame_hd is not None else frame_bgr
                        _caja = caja_recorte_mano(resultado_pose.pose_landmarks, BRAZO_HUMANO,
                                                  _img_rec.shape[1], _img_rec.shape[0])
                        if _caja is not None:
                            with _soltar():           # MediaPipe Hands: la física sigue
                                resultado = detectar_mano_en_recorte(
                                    detector_mano_recorte, _img_rec, _caja)
                            if resultado is not None:
                                origen_mano = f"recorte{'-HD' if frame_hd is not None else ''} {_caja[2]}px"
                            # Recuadro del recorte en la ventana (coordenadas del preview)
                            _sx = ANCHO_CAM / _img_rec.shape[1]
                            _sy = ALTO_CAM  / _img_rec.shape[0]
                            cv2.rectangle(frame_bgr,
                                          (int(_caja[0] * _sx), int(_caja[1] * _sy)),
                                          (int((_caja[0] + _caja[2]) * _sx),
                                           int((_caja[1] + _caja[2]) * _sy)),
                                          (255, 200, 0) if resultado is not None else (0, 0, 255), 1)
                    if resultado is None:
                        with _soltar():               # MediaPipe Hands: la física sigue
                            resultado = detector_mano.process(frame_rgb)
                        if resultado.multi_hand_landmarks:
                            origen_mano = "imagen completa"
                    mano_ok      = False
                    calc_m_hud   = 0.0

                    if resultado.multi_hand_landmarks:
                        hand_lm  = resultado.multi_hand_landmarks[0]
                        hand_wlm = resultado.multi_hand_world_landmarks[0]

                        # ══ PASO 5 — PRONOSUPINACIÓN → joint6 ══
                        if estado["camara_activa"] and estado["antebrazo"] is not None:
                            roll = calcular_pronosupinacion(hand_wlm, estado["antebrazo"],
                                                            estado["eje_codo"])
                            _t = time.perf_counter()
                            _dt = min(_t - t_prev_prono, 0.1)
                            t_prev_prono = _t
                            if roll is not None:
                                if roll_ref is None:
                                    # Calibrando: T-pose con el PULGAR HACIA ARRIBA
                                    refs_roll.append(roll)
                                    if len(refs_roll) >= 15:
                                        # media circular (no se rompe cerca de ±180°)
                                        roll_ref = float(np.angle(np.mean(np.exp(1j * np.array(refs_roll)))))
                                        q_prono_ref = float(datos.ctrl[prono_idx])
                                        q_prono, d_prev = q_prono_ref, 0.0
                                        print(f"🔄 Giro neutro calibrado: {math.degrees(roll_ref):.1f}°")
                                else:
                                    d = d_prev + _wrap((roll - roll_ref) - d_prev)   # sin saltos
                                    d = float(np.clip(d, -PRONO_LIMITE, PRONO_LIMITE))
                                    d_prev = d
                                    q_obj  = q_prono_ref + PRONO_SIGNO * PRONO_ESCALA * d
                                    # ORIENTACIÓN EN EL MUNDO: con el brazo imitado, se busca el
                                    # joint6 que deja la mano del robot como la tuya en el espacio
                                    # (no un giro relativo, que fallaba si la IK elegía otra postura).
                                    _q6_mundo = None
                                    if PRONO_MODO == "mundo" and hib is not None and brazo_imit_activo \
                                            and estado.get("torso") is not None:
                                        _lat_h = lateral_mano_humana_mundo(hand_wlm, estado["torso"], hib)
                                        if _lat_h is not None and lat_local is None:
                                            # Calibración (justo tras [A], T-pose y pulgar arriba):
                                            # tu mano ahora ≡ mano del robot en su T-pose.
                                            _m = _perp(_lat_h, hib["eje6_tpose"])
                                            if _m is not None:
                                                lat_cal.append(_m)
                                            if len(lat_cal) >= 10:
                                                _m = _perp(np.mean(lat_cal, axis=0), hib["eje6_tpose"])
                                                if _m is not None:
                                                    lat_local = hib["R_mano_tpose"].T @ _m
                                                    print("🖐️  Orientación de la mano calibrada (modo mundo)")
                                        elif _lat_h is not None:
                                            _q6_mundo = q6_para_orientacion(
                                                datos, hib, lat_local, _lat_h,
                                                float(datos.qpos[qpos_idx_brazo[prono_idx]]))
                                    if _q6_mundo is not None:
                                        q_obj = _equivalente_en_rango(_q6_mundo, q_prono,
                                                                      *LIMITES_CTRL_BRAZO[prono_idx])
                                        q6_obj_prev = q_obj
                                    elif PRONO_MODO == "mundo" and lat_local is not None \
                                            and q6_obj_prev is not None:
                                        # PASO 7.2: el modo mundo no es fiable en ESTE fotograma →
                                        # se mantiene su último objetivo (antes se pasaba al giro
                                        # relativo, que da otro valor → tirón de muñeca)
                                        q_obj = q6_obj_prev
                                    elif hib is not None and peso_hib > 0.0 and ik_info is not None \
                                            and estado.get("az_brazo") is not None:
                                        _e_h = hib["ejes"] @ _eje_codo_humano_torso(
                                            math.radians(estado["az_brazo"]))
                                        _dot = float(_e_h @ datos.xaxis[hib["j_codo"]])
                                        if abs(_dot) > 0.3:             # zona muerta: sin parpadeos
                                            _gir = (1.0 if _dot >= 0 else -1.0) != hib["signo_codo"]
                                            if _gir != mano_girada:
                                                print(f"🔁 Robot {'GIRADO (codo al otro lado)' if _gir else 'normal'}"
                                                      f": giro de muñeca {'compensado +180°' if _gir else 'sin compensar'}")
                                            mano_girada = _gir
                                        if mano_girada:
                                            q_obj = _equivalente_en_rango(
                                                q_obj + math.pi, q_prono,
                                                *LIMITES_CTRL_BRAZO[prono_idx])
                                    # PASO 7.3: modo fino / congelado también para el giro
                                    _lo6, _hi6 = LIMITES_CTRL_BRAZO[prono_idx]
                                    q_obj = float(canal_giro(
                                        q_obj, _t,
                                        limitar=lambda v: _equivalente_en_rango(
                                            float(v[0]), q_prono, _lo6, _hi6))[0])
                                    q_suav = q_prono + PRONO_SUAVIZADO * (q_obj - q_prono)
                                    paso   = PRONO_VEL_MAX * _dt
                                    q_prono = q_prono + float(np.clip(q_suav - q_prono, -paso, paso))
                                    _enviar_brazo((prono_idx,), (q_prono,))  # PASO 7.1

                                    if DEBUG_ANGULOS_BRAZO and time.time() - t_ult_print_roll >= DEBUG_ANGULOS_CADA_S:
                                        t_ult_print_roll = time.time()
                                        print(f"[PRONO{' mundo' if _q6_mundo is not None else ''}] "
                                              f"giro={math.degrees(d):6.1f}°  →  "
                                              f"q6 CMD={q_prono:5.2f}  REAL={datos.qpos[qpos_idx_brazo[prono_idx]]:5.2f} rad")
                        datos.ctrl[4] = JOINT5_FIJO      # joint5 siempre recto

                        # Dibujar esqueleto en el frame
                        mp_draw.draw_landmarks(
                            frame_bgr, hand_lm, mp_hands.HAND_CONNECTIONS,
                            mp_styles.get_default_hand_landmarks_style(),
                            mp_styles.get_default_hand_connections_style())

                        # Profundidad de la muñeca (solo para HUD)
                        lm0 = hand_lm.landmark[LM_MUNECA]
                        px  = int(lm0.x * ANCHO_CAM)
                        py  = int(lm0.y * ALTO_CAM)
                        # La profundidad se muestrea con coordenadas normalizadas, así
                        # da igual si su tamaño difiere un poco del del color.
                        z   = profundidad_en_pixel(
                            frame_depth,
                            int(lm0.x * frame_depth.shape[1]),
                            int(lm0.y * frame_depth.shape[0])) or 0.40
                        x_m, y_m, _ = pixel_a_3d(px, py, z, f_px=f_px_cam)
                        
                        # Convertir a frame de mano 3D
                        lm3d = landmarks_a_3d(hand_wlm, es_mano_izq=False)

                        # ── Pelota en MuJoCo: la cámara solo informa, no spawnea ──
                        # El spawn/ocultado se controla exclusivamente con [P].
                        # La detección por cámara sirve de feedback visual en el HUD.

                        # — Retargeting y control de MuJoCo —
                        if estado["camara_activa"]:
                            estado = retarget_a_ctrl(
                                modelo, datos, lm3d, hand_wlm, estado, suav_dedos)
                            calc_m_hud = estado["calc_muneca"]

                            # ── Diagnóstico de pinzas ──
                            if DEBUG_PINZA and (time.time() - t_ult_print_pinza) >= DEBUG_PINZA_CADA_S:
                                t_ult_print_pinza = time.time()
                                _dp = estado.get("dist_pulgar", {})
                                _txt = "  ".join(
                                    f"{_d}={100 * _dp[_d]:4.1f}/{100 * PINZA_UMBRAL_ON[_d]:.1f}"
                                    for _d in ("indice", "corazon", "anular", "menique") if _d in _dp)
                                print(f"\n[PINZA] cm pulgar→yema (medido/umbral): {_txt}  |  "
                                      f"activa={estado.get('modo_pinza')} "
                                      f"dedo={estado.get('dedo_bloqueado')}  "
                                      f"habilitada={estado.get('pinza_habilitada', True)}  "
                                      f"mano de: {origen_mano}")
                            if MODO_BRAZO == "ik" and estado["neutro_camara_brazo"] is not None:
                                estado["objetivo_brazo"] = mapear_muneca_a_objetivo_brazo(
                                    x_m, y_m, z, estado["neutro_camara_brazo"],
                                    punto_neutro_brazo=estado["punto_neutro_brazo"])

                                # ── IK: lleva el efector (el muñón, origen de
                                # mano_mount, SIN offset — el mismo punto que se
                                # calibró con [A]) al objetivo calculado arriba.
                                # Si no hay objetivo (cámara aún sin calibrar) el
                                # brazo simplemente se queda donde esté — no se
                                # toca datos.ctrl[0:6] en ese caso.
                                q_brazo = resolver_ik_brazo(
                                    modelo, datos, estado["objetivo_brazo"],
                                    dof_idx_brazo, qpos_idx_brazo,
                                    nombre_body_efector="mano_mount",
                                    offset_local_efector=OFFSET_LOCAL_MUNON,
                                    postura_referencia=postura_referencia_brazo,
                                    ganancia_null=0.05)
                                for i in range(len(ARM_JOINTS)):
                                    datos.ctrl[i] = float(q_brazo[i])

                                # Debug temporal — lo quitaremos cuando ya tengamos el brazo moviéndose
                                if int(datos.time * 2) % 1 == 0 and \
                                   abs(datos.time * 2 - int(datos.time * 2)) < 0.03:
                                    print(f"[BRAZO] objetivo → "
                                          f"X={estado['objetivo_brazo'][0]:.3f}  "
                                          f"Y={estado['objetivo_brazo'][1]:.3f}  "
                                          f"Z={estado['objetivo_brazo'][2]:.3f}")
                             # ── Resaltado de yemas en pinza ──────────────────────
                        if estado.get("modo_pinza"):
                            punta_por_dedo = {
                                "indice":  8,
                                "corazon": 12,
                                "anular":  16,
                                "menique": 20,
                            }
                            # Yema del pulgar (siempre landmark 4)
                            lm_th  = hand_lm.landmark[4]
                            px_th  = int(lm_th.x * ANCHO_CAM)
                            py_th  = int(lm_th.y * ALTO_CAM)
                            cv2.circle(frame_bgr, (px_th, py_th), 11, (0, 0, 255), -1)
                            cv2.circle(frame_bgr, (px_th, py_th), 11, (255, 255, 255), 2)

                            # Para combos multi-dedo se resaltan las dos yemas correspondientes
                            dedos_resaltar = (
                                ["corazon", "anular"]  if estado["dedo_activo"] == "corazon_anular"  else
                                ["indice",  "corazon"] if estado["dedo_activo"] == "indice_corazon"  else
                                ["anular",  "menique"] if estado["dedo_activo"] == "anular_menique"  else
                                [estado["dedo_activo"]]
                            )
                            for d in dedos_resaltar:
                                lm_tip = hand_lm.landmark[punta_por_dedo[d]]
                                px_tip = int(lm_tip.x * ANCHO_CAM)
                                py_tip = int(lm_tip.y * ALTO_CAM)
                                cv2.circle(frame_bgr, (px_tip, py_tip), 11, (0, 0, 255), -1)
                                cv2.circle(frame_bgr, (px_tip, py_tip), 11, (255, 255, 255), 2)

                        # Grabación de dataset para entrenamiento de IA
                        # (fuera del bloque de "modo_pinza": debe grabar SIEMPRE que
                        # 'grabando' esté activo, sea pinza, puño, o cualquier gesto)
                        # Se acumula en memoria (buffer_episodio) y se guarda como un
                        # episodio independiente al parar la grabación con [G].
                        if grabando:
                            qpos_state = [
                                datos.qpos[modelo.jnt_qposadr[
                                    modelo.actuator_trnid[OFFSET_MANO + i, 0]]]
                                for i in range(N_ACT)
                            ]
                            fila = (qpos_state + [float(ctrl_mano[i]) for i in range(N_ACT)]
                                    + [time.time()])
                            buffer_episodio.append(fila)


                        pct = int(min(100, max(0,
                            (-calc_m_hud / abs(UMBRAL_BLOQUEO)) * 100)))
                        if estado["muneca_bloqueada"]:
                            cv2.putText(frame_bgr,
                                        "MUNECA BLOQUEADA — extiende para liberar",
                                        (10, 100),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 0, 255), 1)
                        else:
                            cv2.putText(frame_bgr,
                                        f"Flexion muneca: {pct}%",
                                        (10, 100),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 200, 100), 1)

                        if estado.get("modo_pinza"):
                            cv2.putText(frame_bgr,
                                        f"PINZA -> {estado['dedo_activo'].upper()}",
                                        (10, 120),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 100, 0), 2)
                        mano_ok = True

                        if not estado.get("pinza_habilitada", True):
                            cv2.putText(frame_bgr,
                                        "PINZAS DESACTIVADAS [Espacio]",
                                        (10, 80),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

                        mano_ok = True

                    else:
                        msg = ("⚠ Mano perdida — posición mantenida"
                               if estado["camara_activa"] else "Buscando mano...")
                        cv2.putText(frame_bgr, msg, (10, 85),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 165, 255), 1)

                    # — Teclado Avanzado (usamos waitKeyEx para captar flechas) —
                    key = cv2.waitKeyEx(1)

                    if key == 32:  # 32 es el código ASCII del Espacio
                        estado["pinza_habilitada"] = not estado.get("pinza_habilitada", True)
                        estado_txt = "HABILITADA" if estado["pinza_habilitada"] else "DESHABILITADA"
                        print(f"🤏 Detección de pinza predefinida: {estado_txt}.")
                        
                        # Si se deshabilita mientras hacías una pinza, la forzamos a soltar
                        if not estado["pinza_habilitada"]:
                            estado["modo_pinza"] = False
                            estado["dedo_bloqueado"] = None

                    elif key == ord("a") and not estado["camara_activa"]:
                        estado["camara_activa"] = True
                        suav_dedos.reset()
                        # Paso 4: empieza la calibración de huesos y la imitación arranca
                        # de nuevo cuando termine (el brazo humano debe estar en T-pose).
                        brazo_imit_activo = False
                        refs_tpose = []
                        tpose_med  = None
                        roll_ref, refs_roll, d_prev = None, [], 0.0
                        if MODO_BRAZO == "imitacion":
                            est_brazo.iniciar_calibracion()
                            if IMITAR_REFERENCIA == "absoluto" and IMITAR_TPOSE_SIM_AL_CALIBRAR:
                                _qT = angulos_humano_a_q_brazo(
                                    math.radians(T_POSE_HUMANA[0]),
                                    math.radians(T_POSE_HUMANA[1]),
                                    math.radians(T_POSE_HUMANA[2]))
                                _enviar_brazo((0, 1, 2), _qT)   # PASO 7.1: va a la T-pose sin tirón
                            if est_brazo.manual is None:
                                print("🦴 Calibrando huesos: pon el BRAZO ESTIRADO en T-pose "
                                      f"y no te muevas (~{CALIB_HUESOS_FRAMES} fotogramas)...")
                        if resultado.multi_hand_world_landmarks:
                            v, e = calcular_flexion_muneca(resultado.multi_hand_world_landmarks[0])
                            estado["vec_neutro"]  = v
                            estado["eje_lateral"] = e
                            estado["neutro_camara_brazo"] = (x_m, y_m, z)
                            # El brazo parte de donde YA está en la simulación
                            # en este instante: el muñón (origen de
                            # mano_mount), el mismo punto que persigue la IK
                            # — así no queda ningún desfase que corregir de
                            # golpe nada más calibrar.
                            estado["punto_neutro_brazo"] = tuple(datos.xpos[mano_mount_id])
                        print("✅ Cámara ACTIVA — muñeca calibrada en posición neutra "
                              "(el brazo parte de su posición actual).")

                    elif key == ord("s"):
                        estado["camara_activa"] = False
                        estado["muneca_bloqueada"] = False
                        if grabando and tarea_actual:
                            ruta = guardar_episodio(
                                buffer_episodio, os.path.join(EPISODIOS_DIR, tarea_actual))
                            if ruta:
                                print(f"💾 Episodio guardado antes de standby: {ruta} "
                                      f"({len(buffer_episodio)} fotogramas).")
                            buffer_episodio = []
                        grabando = False
                        suav_dedos.reset()
                        # PASO 7.1: el brazo vuelve al reposo de forma continua (sin tirón)
                        brazo_fino, brazo_congelado = False, False
                        canal_palma.reset(); canal_giro.reset()
                        aplicar_modo_brazo(False, False, (), gen_brazo)
                        _enviar_brazo(range(len(POSICION_STANDBY_BRAZO)), POSICION_STANDBY_BRAZO)
                        for i, v in enumerate(POSICION_STANDBY):
                            ctrl_mano[i] = float(v)
                        print("⏸ STANDBY — posición de reposo restaurada (brazo + mano).")

                    elif key == ord("h"):
                        peso_hib = 0.0 if peso_hib > 0.0 else (HIBRIDO_PESO or 1.0)
                        q_ik_prev = None
                        suav_obj.reset()
                        suav_codo.reset()
                        oe_brazo.reset()
                        oe_antebrazo.reset()
                        t_atasco = None
                        filtro_saltos.reset(); zm_palma.reset(); zm_codo.reset()
                        canal_palma.reset(); canal_giro.reset()
                        dirs_ok = None
                        brazo_fino, brazo_congelado = False, False
                        aplicar_modo_brazo(False, False, (), gen_brazo)
                        print(f"🖐️  Brazo: {('HÍBRIDO (' + HIBRIDO_MODO + ')') if peso_hib > 0 else 'solo ÁNGULOS'}"
                              f"  (peso={peso_hib:.2f})")

                    elif key in (ord("f"), ord("F")):
                        # PASO 7.3 — MODO FINO: el robot se mueve FINO_ESCALA veces lo que tú
                        if not (brazo_imit_activo and estado["camara_activa"] and peso_hib > 0.0
                                and HIBRIDO_MODO == "codo_muneca"):
                            print("⚠ Modo fino: solo con el brazo IMITANDO en híbrido 'codo_muneca' "
                                  "([A] + T-pose; [H] si estás en 'solo ángulos').")
                        else:
                            brazo_fino = not brazo_fino
                            aplicar_modo_brazo(brazo_fino, brazo_congelado,
                                               (canal_palma, canal_giro), gen_brazo)
                            print(f"🎯 Modo FINO ACTIVADO: el brazo se mueve x{FINO_ESCALA:.2f} lo que tú, "
                                  "desde donde está." if brazo_fino else
                                  "↩️  Modo fino desactivado: el brazo vuelve a imitarte (suavemente).")

                    elif key in (ord("c"), ord("C")):
                        # PASO 7.3 — CONGELAR: el brazo se queda quieto (la mano sigue)
                        if not (brazo_imit_activo and estado["camara_activa"] and peso_hib > 0.0
                                and HIBRIDO_MODO == "codo_muneca"):
                            print("⚠ Congelar: solo con el brazo IMITANDO en híbrido 'codo_muneca'.")
                        else:
                            brazo_congelado = not brazo_congelado
                            aplicar_modo_brazo(brazo_fino, brazo_congelado,
                                               (canal_palma, canal_giro), gen_brazo)
                            print("🧊 Brazo CONGELADO (la mano sigue funcionando). [C] para seguir."
                                  if brazo_congelado else
                                  ("▶️  Brazo descongelado: sigue en modo fino DESDE AQUÍ." if brazo_fino
                                   else "▶️  Brazo descongelado: vuelve a imitarte (suavemente)."))

                    elif key == ord("g") and estado["camara_activa"]:
                        grabando = not grabando
                        if grabando:
                            print(f"\n📝 Tareas ya grabadas: "
                                  f"{', '.join(_listar_tareas_grabadas()) or '(ninguna todavía)'}")
                            entrada = input(
                                f"   Nombre de la tarea/maniobra "
                                f"[{tarea_actual or 'nueva tarea'}]: ").strip()
                            if entrada:
                                tarea_actual = _nombre_seguro(entrada)
                            elif tarea_actual is None:
                                tarea_actual = _nombre_seguro("tarea_1")
                            buffer_episodio = []
                            print(f"🔴 GRABANDO... (tarea: '{tarea_actual}')")
                        else:
                            ruta_tarea = os.path.join(EPISODIOS_DIR, tarea_actual)
                            ruta = guardar_episodio(buffer_episodio, ruta_tarea)
                            if ruta:
                                print(f"⏹ Grabación pausada. Episodio guardado: "
                                      f"{ruta} ({len(buffer_episodio)} fotogramas).")
                            else:
                                print("⏹ Grabación pausada. (episodio vacío, no se guardó)")
                            buffer_episodio = []

                    elif key == ord("e"):
                        # Entrena SOLO la última tarea usada (rápido, para iterar
                        # sobre una maniobra concreta sin tocar las demás)
                        if tarea_actual is None:
                            print("❌ No hay ninguna tarea seleccionada todavía. "
                                  "Graba con [G] primero.")
                        else:
                            os.makedirs(MODELOS_DIR, exist_ok=True)
                            ruta_episodios = os.path.join(EPISODIOS_DIR, tarea_actual)
                            ruta_pesos = os.path.join(MODELOS_DIR, f"{tarea_actual}.pth")
                            print(f"\n▶ Entrenando solo la tarea actual: '{tarea_actual}'")
                            entrenar_ia(ruta_episodios, ruta_pesos)

                    elif key == ord("E"):
                        # Mayúscula: reentrena TODAS las tareas grabadas (más lento,
                        # útil tras cambiar algo estructural del modelo)
                        print("\n📋 Reentrenando TODAS las tareas grabadas...")
                        entrenar_todas_las_tareas()

                    elif key == ord("1"):
                        # [1] — Toggle pelota + soporte universal
                        if not estado["pelota_visible"]:
                            _spawn_pelota(modelo, datos, estado["spawn_actual"]["pelota"])
                            
                            # Solo spawneamos el soporte si la mano está en la posición "arriba"
                            if estado["spawn_actual"] == PUNTOS_SPAWN["arriba"]:
                                _spawn_soporte(modelo, datos, estado["spawn_actual"]["soporte"])
                            
                            estado["pelota_visible"] = True
                            print("🟡 Pelota SPAWNEADA.")
                        else:
                            _ocultar_pelota(modelo, datos)
                            
                            # Ocultamos la mesa solo si el destornillador no la está usando en "arriba"
                            if not (estado.get("destornillador_visible", False) and estado["spawn_actual"] == PUNTOS_SPAWN["arriba"]):
                                _ocultar_soporte(modelo, datos)
                                
                            estado["pelota_visible"] = False
                            print("⬛ Pelota OCULTADA.")

                    elif key == ord("2"):
                        # [2] — Toggle destornillador
                        if not estado.get("destornillador_visible", False):
                            _spawn_destornillador(modelo, datos, estado["spawn_actual"]["destornillador"])
                            
                            # Si estamos en "arriba", traemos la mesa universal
                            if estado["spawn_actual"] == PUNTOS_SPAWN["arriba"]:
                                _spawn_soporte(modelo, datos, estado["spawn_actual"]["soporte"])
                                
                            estado["destornillador_visible"] = True
                            print("🔧 Destornillador SPAWNEADO.")
                        else:
                            _ocultar_destornillador(modelo, datos)
                            
                            # Ocultamos la mesa solo si la pelota tampoco la necesita
                            if not estado["pelota_visible"]:
                                _ocultar_soporte(modelo, datos)
                                
                            estado["destornillador_visible"] = False
                            print("⬛ Destornillador OCULTADO.")

                    elif key == ord("3"):
                        # [3] — Toggle entorno de trabajo (mesa + herramientas)
                        if not taller.disponible:
                            print("⚠ El entorno de trabajo no está en el modelo "
                                  "(falta el include de mesa_trabajo.xml).")
                        elif taller.alternar(modelo, datos):
                            print("🧰 Entorno de trabajo MOSTRADO (alicates, destornillador, "
                                  "bombilla y fusible recolocados).")
                            if TALLER_ENCUADRAR_CAMARA:
                                visor.cam.lookat[:]  = TALLER_CAMARA["lookat"]
                                visor.cam.distance   = TALLER_CAMARA["distancia"]
                                visor.cam.azimuth    = TALLER_CAMARA["azimut"]
                                visor.cam.elevation  = TALLER_CAMARA["elevacion"]
                        else:
                            print("⬛ Entorno de trabajo OCULTADO.")

                    elif key == ord("4"):
                        # [4] — Escenario taladro (techo + peana + taladro)
                        if not taladro.disponible:
                            print("⚠ El escenario taladro no está en el modelo (ejecuta "
                                  "taladro/preparar_taladro.py y añade el include).")
                        else:
                            if taller.disponible and taller.visible:
                                taller.ocultar(modelo, datos)     # uno cada vez
                            if taladro.alternar(modelo, datos):
                                print("🔩 Escenario taladro MOSTRADO: coge el taladro por la "
                                      "empuñadura y llévalo al techo.")
                                visor.cam.lookat[:]  = (0.5 * TALADRO_POS_SOPORTE[0],
                                                        0.5 * TALADRO_POS_SOPORTE[1], 0.55)
                                visor.cam.distance   = 1.9
                                visor.cam.elevation  = -12
                            else:
                                print("⬛ Escenario taladro OCULTADO.")

                    elif key == ord("5"):
                        # [5] — Demo automática: coger el taladro, llevarlo al techo,
                        #       apretar el gatillo y hacer un agujero (sin cámara)
                        if not demo_taladro.ok:
                            print("⚠ La demo del taladro no está disponible (mira los avisos "
                                  "del arranque).")
                        else:
                            if grabando and tarea_actual:
                                guardar_episodio(
                                    buffer_episodio, os.path.join(EPISODIOS_DIR, tarea_actual))
                                buffer_episodio = []
                            grabando = False
                            estado["camara_activa"] = False
                            modo_demo_taladro = True
                            break

                    # ── FLECHAS DE DIRECCIÓN ──────────────────────────────────
                    # PENDIENTE DE REDISEÑO: antes teletransportaban el body
                    # mocap "right_mount" (mano suelta); ese body ya no existe
                    # porque la mano cuelga del brazo (ver _mover_mano arriba).
                    # Por ahora solo eligen qué juego de PUNTOS_SPAWN usar para
                    # el destornillador — NO reorientan la mano. Para recuperar
                    # el control manual de orientación, habría que rehacerlas
                    # como 3 posturas fijas de joint4/5/6 (y decidir cómo
                    # conviven con la IK de posición, que ya usa esos 3 DOF de
                    # forma redundante para alcanzar el objetivo).
                    elif key in (65362, 2490368):
                        estado["spawn_actual"] = PUNTOS_SPAWN["arriba"]

                    elif key in (65361, 2424832):
                        estado["spawn_actual"] = PUNTOS_SPAWN["izquierda"]

                    elif key in (65364, 2621440):
                        estado["spawn_actual"] = PUNTOS_SPAWN["abajo"]

                    elif key in (65363, 2555904):
                        estado["spawn_actual"] = PUNTOS_SPAWN["derecha"]

                    elif key == ord("m"):
                        # Demo programado: prueba pinzas fijas con ruido aleatorio
                        if grabando and tarea_actual:
                            guardar_episodio(
                                buffer_episodio, os.path.join(EPISODIOS_DIR, tarea_actual))
                            buffer_episodio = []
                        modo_autonomo = True
                        grabando = False
                        estado["camara_activa"] = False
                        break

                    elif key == ord("i"):
                        # Modo IA real: elige qué tarea/maniobra quieres que reproduzca
                        modelos_disponibles = _listar_modelos_entrenados()
                        if not modelos_disponibles:
                            print("❌ No hay ninguna tarea entrenada todavía. "
                                  "Graba con [G] y entrena con [E] primero.")
                        else:
                            print("\n📋 Tareas entrenadas disponibles:")
                            for idx, nombre in enumerate(modelos_disponibles, start=1):
                                print(f"   [{idx}] {nombre}")
                            eleccion = input(
                                f"   Elige nº de tarea a reproducir (1-{len(modelos_disponibles)}, "
                                f"o vacío para cancelar): ").strip()
                            if eleccion.isdigit() and 1 <= int(eleccion) <= len(modelos_disponibles):
                                tarea_elegida = modelos_disponibles[int(eleccion) - 1]
                                ruta_pesos = os.path.join(MODELOS_DIR, f"{tarea_elegida}.pth")
                                red_neuronal = cargar_ia(ruta_pesos)
                                if red_neuronal is not None:
                                    print(f"🎯 Tarea seleccionada: '{tarea_elegida}'")
                                    if grabando:
                                        guardar_episodio(
                                            buffer_episodio,
                                            os.path.join(EPISODIOS_DIR, tarea_actual))
                                        buffer_episodio = []
                                    modo_ia_real = True
                                    grabando = False
                                    estado["camara_activa"] = False
                                    break
                            else:
                                print("   Cancelado.")

                    elif key == ord("q"):
                        salir = True

                    # — Paso de simulación MuJoCo —
                    if visor.is_running():
                        # Si estamos en modo hardware, enviamos los datos a los servos
                        if MODO_EJECUCION == "HARDWARE_REAL" and mano_real and mano_real.conectado:
                            hardware_target = construir_hardware_target(datos)
                            mano_real.enviar_posiciones(hardware_target)
                        # Escenario taladro: agarre asistido (si está visible)
                        if taladro.disponible:
                            taladro.actualizar(modelo, datos)

                        # Mueve el Gemelo Digital en ambos modos. Con FISICA_EN_HILO
                        # lo hace HiloFisica al ritmo del reloj real; si no, como antes.
                        if fisica is None:
                            for _ in range(4):
                                if gen_brazo is not None:        # PASO 7.1
                                    gen_brazo.paso(modelo, datos, modelo.opt.timestep)
                                mujoco.mj_step(modelo, datos)
                            visor.sync()
                        # ── Logo IDI — HUD inferior centrado del visor MuJoCo ──
                        _dibujar_logo_mujoco(visor, _logo_mj_px, _logo_mj_w, _logo_mj_h)
                    else:
                        salir = True  # Ventana MuJoCo cerrada por el usuario

                    # — HUD de estado —
                    est_str = "ACTIVO" if estado["camara_activa"] else "STANDBY"
                    c_hud   = (0, 255, 0) if estado["camara_activa"] else (0, 0, 255)
                    cv2.putText(frame_bgr, est_str, (10, 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, c_hud, 2)
                    # FPS reales: si bajan de ~15, MediaPipe Pose pierde el seguimiento
                    # y tendrás parpadeo del esqueleto por mucho que ajustes lo demás.
                    cv2.putText(frame_bgr, f"{_fps_val:4.1f} FPS", (10, 45),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                (0, 255, 0) if _fps_val >= 15 else (0, 165, 255), 1)
                    if grabando:
                        cv2.circle(frame_bgr, (ANCHO_CAM - 20, 20), 8, (0, 0, 255), -1)
                        cv2.putText(frame_bgr, "REC", (ANCHO_CAM - 60, 25),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

                    cv2.imshow(
                        NOMBRE_VENTANA,
                        _superponer_logo(
                            cv2.resize(frame_bgr,
                                       (int(ANCHO_CAM * ESCALA_VENTANA),
                                        int(ALTO_CAM * ESCALA_VENTANA))),
                            _logo_bgr, _logo_alpha,
                            margen=12, posicion="top-left"))

                # Salimos de teleoperación (modo autónomo / IA / salir): esos
                # modos avanzan la física por su cuenta → se para el hilo.
                if fisica is not None:
                    fisica.parar()
                    fisica = None
                if gen_brazo is not None:        
                    gen_brazo.desactivar()

    # — Limpieza —
    cv2.destroyAllWindows()
    detector_mano.close()
    detector_mano_recorte.close()
    detector_pose.close()
    if visor.is_running():
        visor.close()
        
    if mano_real is not None:
        mano_real.desconectar()
        
    # Destruimos la ventana de Tkinter de forma segura al cerrar la app
    try:
        ventana.destroy()
    except:
        pass
        
    print("👋 Fin del programa.")


if __name__ == "__main__":
    main()