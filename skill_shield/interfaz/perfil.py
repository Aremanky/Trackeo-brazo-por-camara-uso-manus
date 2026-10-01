"""
PerfilBucle: mide cuántos ms se van en cada fase del bucle de teleoperación.

(Extraído de Skill_Shield_Nivel_6.py — código sin cambios, solo reubicado.)
"""
import time


class PerfilBucle:
    """
    FLUIDEZ — mide cuántos ms se van en cada fase del bucle de teleoperación y lo
    imprime cada PERFIL_BUCLE_CADA_S segundos, p. ej.:
      ⏱️  [PERFIL] 12.3 FPS (81 ms/vuelta) → cámara 3 | pose 31 | brazo 9 | mano 4 | ...
    Así se ve QUÉ frena la cámara en cada ordenador en vez de adivinarlo.
    "esperando a la física" es la parte de esos ms en la que el bucle esperaba a que
    HiloFisica terminara su lote de mj_step para devolverle el candado.
    """

    def __init__(self, fisica=None, cada_s=3.0):
        self.fisica = fisica
        self.cada_s = cada_s
        self._reset(time.perf_counter())

    def _reset(self, ahora):
        self.acum, self.orden, self.n = {}, [], 0
        self.t_rep = self.t = ahora
        if self.fisica is not None:
            self.fisica.espera_candado = 0.0

    def inicio(self):
        """Al principio de cada vuelta."""
        self.t = time.perf_counter()
        self.n += 1

    def marca(self, fase: str):
        """Cierra la fase 'fase' (lo transcurrido desde la marca anterior)."""
        ahora = time.perf_counter()
        if fase not in self.acum:
            self.acum[fase] = 0.0
            self.orden.append(fase)
        self.acum[fase] += ahora - self.t
        self.t = ahora

    def informe(self):
        """Al final de cada vuelta: imprime si ya toca."""
        ahora = time.perf_counter()
        if self.n == 0 or ahora - self.t_rep < self.cada_s:
            return
        n, dur = self.n, ahora - self.t_rep
        fases = " | ".join(f"{f} {1000 * self.acum[f] / n:.0f}" for f in self.orden)
        extra = ""
        if self.fisica is not None:
            extra = f"  (de ello, esperando a la física: {1000 * self.fisica.espera_candado / n:.0f} ms)"
        print(f"\n⏱️  [PERFIL] {n / dur:4.1f} FPS ({1000 * dur / n:.0f} ms/vuelta) → {fases} ms{extra}")
        self._reset(ahora)
