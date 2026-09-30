import os
import mujoco
 
# Carpeta donde está este propio script (arctos_urdf_description/urdf/)
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
 
ruta_entrada = os.path.join(_BASE_DIR, "arctos.urdf")
ruta_salida  = os.path.join(_BASE_DIR, "arctos_mjcf.xml")
 
modelo = mujoco.MjModel.from_xml_path(ruta_entrada)
mujoco.mj_saveLastXML(ruta_salida, modelo)
print(f"Convertido a {ruta_salida}")
