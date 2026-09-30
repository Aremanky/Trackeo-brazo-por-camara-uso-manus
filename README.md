# brazo-robotico


Creear entorno
```bash
python3 -m venv venv_nivel6
```
Activar entorno
```bash
source venv_nivel6/bin/activate
```
Descargar dependencias
```bash
pip install -r requirements.txt
```
Luego escribir esto
```bash
pip install opencv-python depthai mediapipe=0.10.14 mujoco torch
```
En caso de que mediapipe te diga que no fufa en su versión escribir esto
```bash
sudo rm -rf venv_nivel6
python3.12 -m venv venv_nivel6
source venv_nivel6/bin/activate
pip install -r requirements.txt
pip install opencv-python depthai mediapipe=0.10.14 mujoco torch
```

---
O simplemente arrancar con la opción
```bash
./arrancar_nivel6.sh
```

---
Lo más probable es que falle, pero es bueno para ir depurando el .txt

> [!NOTE]  
> Falta depurarlo probando en otros ordenadores, es decir, ver cuales módulos son intrínsecos del SO

> [!WARNING]  
> Si te da fallo al descargar dependencias ve al requirements.txt y borra de esa lista el modulo que te da problemas, debería de funcionar todo sin ese modulo ya que algunos son intrínsecos del SO y para ti no serán necesarios

> [!CAUTION]
> si el que te da error es PyGObject instala esto y no lo elimines de la lista
> ```bash
> sudo apt update && sudo apt install libcairo2-dev libgirepository1.0-dev
> ```
