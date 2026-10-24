# DualSense Control

[![CI](https://github.com/LDsAragon/dualsense-control-haptics-bt/actions/workflows/ci.yml/badge.svg)](https://github.com/LDsAragon/dualsense-control-haptics-bt/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/LDsAragon/dualsense-control-haptics-bt?include_prereleases)](https://github.com/LDsAragon/dualsense-control-haptics-bt/releases)

**Háptica real del DualSense de PS5 por Bluetooth en Windows: gratis y libre.**

> **English:** DualSense Control brings the PS5 DualSense's real haptic feedback (voice-coil actuators)
> and adaptive triggers to PC games **over Bluetooth**, for free. It wraps [vDS](https://github.com/hurryman2212/vds)
> (a virtual USB DualSense bridged to Bluetooth), builds on [SAxense](https://github.com/egormanga/SAxense)'s
> protocol research, and adds a control panel: modes, lightbar colors per controller, trigger tests,
> audio-reactive haptics, a speaker mute that keeps haptics, and one-click diagnostics.
> Download `DualSenseControl.exe` from [**Releases**](https://github.com/LDsAragon/dualsense-control-haptics-bt/releases), run it, click **Install**. Spanish UI.

Los juegos con háptica nativa (los ports de PlayStation, como Death Stranding) solo la mandan si el
DualSense está **por cable**. DualSense Control hace que Windows vea un DualSense "enchufado" y lo traduce
a Bluetooth. Además trae un panel para manejarlo todo:

| | |
|---|---|
| **Háptica nativa en juegos** | Por el joystick virtual de vDS (probado con Death Stranding Director's Cut) |
| **Gatillos adaptativos** | Los del juego, y efectos propios para probarlos |
| **Modo normal / Modo vDS** | Volver al DualSense Bluetooth común con un clic (para Steam, otros juegos o la PS5) |
| **Luces por joystick** | Identificar cuál es cuál, nombre, color de la barra y LEDs de jugador |
| **Parlante del joystick** | Silenciarlo sin perder la vibración |
| **Háptica reactiva** | Que el audio de la PC haga vibrar el joystick, para juegos sin háptica |
| **Diagnóstico** | "Reportar problema" junta registros y estado en un `.zip` |

> Software experimental, sin garantías. "PlayStation", "PS5", "DualSense" y "DualSense Edge" son marcas
> de Sony Interactive Entertainment. Este proyecto no está afiliado a Sony. Créditos y licencias de
> terceros en [THIRD_PARTY.md](THIRD_PARTY.md).

---

## Usarlo (recomendado): el `.exe`

1. Emparejá el DualSense por Bluetooth: mantené **PS + Create** hasta que la luz parpadee rápido y
   agregalo desde *Configuración → Bluetooth*.
2. Bajá **`DualSenseControl.exe`** de [**Releases**](https://github.com/LDsAragon/dualsense-control-haptics-bt/releases).
   Windows puede decir "Windows protegió su PC", porque el ejecutable todavía no tiene firma digital:
   *Más información → Ejecutar de todas formas*. Podés comparar la huella con el `.sha256` publicado.
3. Abrilo (pide permiso de administrador) y en la pestaña **Instalación** tocá **Instalar o reparar**.
   Instala USB/IP y HidHide (bajados de sus sitios oficiales, firmados) y el servicio de vDS.
   Si Windows pide reiniciar, reiniciá y volvé a tocar el botón.
4. En la pestaña **Joystick virtual (vDS)**, **Conectar**. Listo.

**Para jugar con háptica nativa:** en Steam, clic derecho en el juego → *Propiedades → Controlador →*
**Desactivar Steam Input**. Ver [Jugar con háptica nativa](#jugar-con-háptica-nativa-probado-con-death-stranding-directors-cut).

Requisitos: Windows 10 1903 o más nuevo de 64 bits y un adaptador Bluetooth. No hace falta Python.

## Usarlo desde el código fuente (para desarrollar)

Hace falta [Python 3.10+](https://www.python.org/) ("Add Python to PATH") y unos 5 GB para compilar vDS.

1. **`instalar.bat`**: instala y compila todo (pide permiso de administrador). La primera vez tarda;
   si Windows pide reiniciar, reiniciá y volvé a correrlo, que sigue solo.
2. **`abrir-panel.bat`**: el panel para manejar todo.
3. **`apagar-joystick.bat`**: apaga el DualSense con doble clic (también está en el panel).

**Volver a la normalidad, sin desinstalar nada:**
- **`modo-normal.bat`**: el DualSense vuelve a ser un joystick Bluetooth común (para Steam, otros juegos
  o la PS5) y **sigue así aunque reinicies**. Detiene vDS, le saca el arranque automático, se asegura de
  que HidHide no lo esconda y apaga los gatillos adaptativos.
- **`modo-vds.bat`**: vuelta al joystick virtual con háptica nativa (vDS arranca con Windows).
- En el panel están los mismos botones, más **Restablecer joystick**, que corta lo que esté sonando y
  saca los efectos de los gatillos sin cambiar de modo.

Para sacar todo: **`desinstalar.bat`**.

## Probarlo y reportar problemas

Ver **[docs/PRUEBAS.md](docs/PRUEBAS.md)**: qué probar en una máquina nueva y cómo mandar un reporte útil.
En cada cambio, GitHub Actions corre las pruebas automáticas y compila el `.exe` en un Windows limpio
(ver [Pruebas automáticas](#pruebas-automáticas)).

## Estructura

```
instalar.bat          instala o regenera TODO
abrir-panel.bat       abre DualSense Control
apagar-joystick.bat   apaga el joystick
modo-normal.bat       DualSense Bluetooth común (sobrevive al reinicio)
modo-vds.bat          joystick virtual con háptica nativa
desinstalar.bat       quita vDS y su servicio
app/                  el panel (dsgui.py) y el motor de háptica (dshaptics.py)
scripts/              lo que corren los .bat de arriba
vds-mods/             commit fijado de vDS + nuestras modificaciones (.patch)
herramientas/         extras: menú de consola, prueba, diagnósticos y recompilar vDS
config/               tus nombres, colores y jugadores por joystick (se crea solo)
docs/BITACORA.md      todo lo que hicimos, decidimos y descubrimos
docs/PRUEBAS.md       guía para probarlo en otras máquinas
tests/                pruebas automáticas (protocolo y modificaciones de vDS)
packaging/            receta de PyInstaller para DualSenseControl.exe
.github/workflows/    CI: pruebas, compilación del .exe y Releases
logs/                 registros (se crea solo)
.build/               fuente y compilación de vDS (se crea sola, se puede borrar)
```

## Qué hace `instalar.bat`

| Paso | Detalle |
|---|---|
| 1. Python | `pip install -r app/requirements.txt` |
| 2. Herramientas | Git, CMake, VC++ Redistributable y Visual C++ Build Tools con vcpkg (con winget, solo lo que falte) |
| 3. Fuente de vDS | Clon limpio en el commit de `vds-mods/VDS_COMMIT`, con `vds-mods/*.patch` aplicados encima |
| 4. Compilar | CMake + MSVC; vcpkg trae Opus |
| 5. Drivers | USB/IP (usbip-win2) y HidHide, con el instalador del propio vDS |
| 6. Instalar | Reemplaza vDS en `C:\Program Files\vDS`, arranca el servicio `vdsd` y verifica que traiga las modificaciones |
| 7. Joystick | Lo conecta como joystick virtual, si no estaba ya |

Se puede correr todas las veces que quieras: cada vez regenera vDS desde cero.
`herramientas\recompilar-vds.bat` hace solo los pasos 3, 4 y 6.

## El panel: DualSense Control

**Encabezado:** estado general y el botón **⏻ Apagar joystick**.

**Pestaña "Joystick virtual (vDS)"**
- **Modo del joystick:** **Modo vDS** (joystick virtual USB, háptica nativa) o **Modo normal** (DualSense
  Bluetooth común). Avisa si el estado actual no va a durar un reinicio.
- **Sonido por el joystick (parlante y auriculares):** interruptor para que el audio del juego salga
  solo por los parlantes de la PC. **La vibración sigue funcionando igual.** Viene incluido en la compilación de vDS (ver "Modificaciones a vDS").
- Lista de joysticks: encendido, registrado, conectado y perfil (`ds5` = DualSense, `dse` = DualSense Edge).
- **Conectar** / **Desconectar** y el registro de `vdsd` en vivo.

**Pestaña "Háptica"**
- **Salida automática:** con vDS conectado va por los **canales 3 y 4 de la placa del joystick virtual**
  (el mismo camino que usa un juego); con vDS detenido va por **Bluetooth directo**.
- Ocho **efectos** (latido, tono, pulsos, barrido, rumble, ping-pong, cada motor por separado) con intensidad.
- **Reactivo al audio de la PC:** elegís qué salida capturar, el corte de graves (se aplica al iniciar)
  y la ganancia (se ajusta en vivo).
- **Archivos:** WAV, MP3, FLAC u OGG, con opción de repetir.
- **Gatillos adaptativos:** Resistencia, Gatillo de arma (con "clic"), Vibración y Apagar, en uno o
  en los dos gatillos. Con vDS en marcha van por el joystick virtual, igual que en un juego; con vDS
  detenido, por Bluetooth directo. Con un juego abierto, el juego pisa estos efectos con los suyos.
- Medidor de nivel de lo que está sonando en ese momento.

**Pestaña "Joysticks y luces"**
- Lista los DualSense conectados con su **dirección Bluetooth**, que identifica a cada uno, en los dos
  modos. En modo vDS la dirección se pide al joystick real a través del joystick virtual.
- **Identificar:** hace parpadear la barra del joystick elegido, para saber cuál es cuál.
- **Nombre**, **color de la barra** (selector o colores rápidos) y **LEDs de jugador** 1 a 5, como en la PS5.
- **Aplicar y guardar:** queda en `config/joysticks.json` y se vuelve a aplicar solo cuando el joystick
  se reconecta o cambia de modo. Un juego abierto puede poner sus propios colores.
- En modo vDS aparecen los joysticks que estén conectados en la pestaña vDS (uno por joystick).

**Pestaña "Instalación"**
- Estado de todo: versión, vDS (y si trae nuestras modificaciones), servicio, USB/IP y HidHide.
- **Instalar o reparar** (con el `.exe` instala vDS ya compilado; desde el código, compila), **Desinstalar vDS**,
  **📦 Reportar problema** (arma un `.zip` en el Escritorio con registros, diagnóstico de Windows y el
  registro de vDS) y **Carpeta de registros**.
- Con el `.exe`, la configuración y los registros quedan en `%LOCALAPPDATA%\DualSenseControl`.

## Jugar con háptica nativa (probado con Death Stranding Director's Cut)

1. vDS en marcha y el joystick **conectado** (lo dice el panel).
2. En Steam: clic derecho en el juego → **Propiedades → Controlador → "Desactivar Steam Input"**.
   **Esto es obligatorio:** con Steam Input activado, Steam toma el joystick virtual y el DualSense
   se prende y se apaga solo (nos pasó, ver `docs/BITACORA.md`, etapa 7).
3. Dejá tus parlantes como salida predeterminada de Windows y que Discord no cambie los dispositivos
   solo. El juego encuentra la placa del DualSense por su cuenta.
4. Si no querés que los sonidos del juego salgan por el parlante del joystick, usá el interruptor
   **Sonido por el joystick** del panel. La vibración sigue igual.

En Death Stranding la háptica anduvo enseguida. Los gatillos adaptativos se notan poco: según los
jugadores, solo se endurecen con mucha carga encima. Para comprobar que funcionan, probalos desde el panel.

## Herramientas (`herramientas/`)

| Archivo | Para qué |
|---|---|
| `menu.bat` | Menú de consola con efectos y modos por Bluetooth directo. Podés arrastrarle un MP3 o WAV. |
| `probar.bat` | Prueba rápida: latido, barrido y ping-pong. |
| `diag.bat` | Lista todo lo que Windows expone por HID (guarda `logs/diag.txt`). |
| `prueba-ab.bat` | Diagnóstico: compara el vDS nuevo con el anterior (deja `logs/prueba-ab.log`). |
| `diag-windows.bat` | Diagnóstico: Bluetooth, HidHide, USB/IP y programas abiertos (deja `logs/diag-windows.txt`). |
| `recompilar-vds.bat` | Regenera vDS con las modificaciones y lo reinstala. |

`menu.bat`, `probar.bat` y `diag.bat` usan Bluetooth directo: hace falta el **modo normal**.

## Línea de comandos (`app/dshaptics.py`)

En **modo normal**, desde la carpeta `app`:

```
python dshaptics.py list                         # joysticks y salidas de audio
python dshaptics.py diag                         # todo lo que Windows expone por HID
python dshaptics.py fx heartbeat                 # tone, pulse, heartbeat, sweep, rumble, pingpong
python dshaptics.py fx tone --side left --freq 120
python dshaptics.py file cancion.mp3 --lowpass 200 --normalize
python dshaptics.py loopback --device EDIFIER --lowpass 150 -v
python dshaptics.py apagar                       # este funciona también con vDS en marcha
python dshaptics.py gatillos arma --lado derecho # duro, arma, vibracion, off (también con vDS)
python dshaptics.py restablecer                  # saca los efectos de los gatillos (también con vDS)
python dshaptics.py bateria                      # nivel de batería
python dshaptics.py luces                        # DualSense conectados: dirección, color, jugador
python dshaptics.py identificar 14:3a:9a:03:eb:f3
python dshaptics.py color 14:3a:9a:03:eb:f3 "#ff0000" --jugador 2 --nombre "Joystick de Lu"
```

`-v` muestra estadísticas: reportes por segundo (~94), buffer, cortes, turnos salteados y errores.
`--dry-run --dump archivo.bin` permite probar sin joystick.

## Cómo funciona

### La háptica del DualSense es audio

Por USB, el DualSense es también una placa de sonido de 4 canales a 48 kHz. Los canales 1 y 2 van
al parlante o a los auriculares, y los **canales 3 y 4 a los motores** izquierdo y derecho. Los juegos
no mandan órdenes de "vibrá": mandan audio. Por Bluetooth esa placa no existe, y por eso la háptica se pierde.

### El reporte Bluetooth `0x32` (investigación de SAxense)

Cada **10,667 ms** (~94 veces por segundo) se manda un reporte HID de 142 bytes:

```
byte 0         0x32               ID del reporte
byte 1         seq << 4           secuencia (0-15)
bytes 2-10     paquete 0x11       control: 0x91, largo 7, FE 00 00 00 00 FF, contador
bytes 11-76    paquete 0x12       0x92, largo 64, 32 muestras estéreo int8 a 3 kHz (L,R,L,R...)
bytes 77-137   ceros
bytes 138-141  CRC32              sobre 0xA2 + bytes 0-137 (0xA2 = cabecera BT de salida)
```

`dshaptics` filtra el audio por debajo de 1,35 kHz, lo remuestrea a 3 kHz y lo convierte a 8 bits.
Verificamos que sus reportes son **idénticos byte a byte** a los del `SAxense.c` original.

Reglas que aprendimos en el camino:
- **Un reporte por turno, nunca ráfagas.** Si el envío se atrasa, los turnos perdidos se saltean.
  El buffer del joystick es chico, y mandar reportes pegados para "ponerse al día" produce cortes
  (ver el issue #3 de dualsense-bt-haptics).
- El buffer en vivo arranca con un **pre-llenado** de la mitad, para absorber el jitter de la captura.

### vDS: un DualSense USB de mentira (pero completo)

```
Juego ─WASAPI─► Windows (usbaudio.sys) ─USB isócrono─► usbip-win2 ─TCP local─► vdsd ─Bluetooth─► DualSense
                         ▲                                                       │
                         └──────────── botones, gatillos, LED, micrófono ◄───────┘
```

- **usbip-win2** hace que Windows vea un dispositivo USB real, y por eso carga sus propios drivers
  de HID y de audio. El juego encuentra el joystick y su placa de sonido juntos, como si estuviera enchufado.
- **HidHide** esconde el DualSense Bluetooth real, para que los juegos no lo vean duplicado.
- **vdsd** traduce en las dos direcciones (vDS usa el reporte `0x36`, que además lleva el estado de los
  gatillos y el audio del parlante en Opus).

### Modificaciones a vDS (`vds-mods/`)

No parcheamos vDS a mano: `instalar.bat` lo clona en un commit fijo y le aplica nuestras modificaciones
antes de compilar, así siempre sale igual. Hoy hay una:

**`0001-silenciar-parlante.patch`: silenciar el parlante sin perder la vibración.** La placa de audio del
joystick virtual tiene 4 canales: el **1 y 2** van al parlante o a los auriculares del joystick (vDS los
manda en Opus) y el **3 y 4** a los motores. Silenciar el dispositivo en Windows no sirve, porque corta los
4 canales y con ellos la háptica. Con la modificación, mientras exista
**`C:\ProgramData\vDS\speaker-muted`**, vdsd pone en cero los canales 1 y 2 antes de codificarlos y
deja los 3 y 4 intactos. Lo revisa cada 250 ms, así que se cambia en vivo. El interruptor del panel solo
crea o borra ese archivo.

Lo probamos compilando el código de audio de vDS con la modificación: con el archivo presente, el parlante
decodificado queda en 0 y la háptica no cambia. Para agregar otras modificaciones o pasar a otra versión de
vDS, ver `vds-mods/README.md` y `docs/BITACORA.md`.

### Luces e identificación

- **Quién es quién:** por Bluetooth, Windows da la dirección como número de serie. El joystick virtual de
  vDS no tiene número de serie, así que se le pide el reporte de característica `0x09`
  (emparejamiento): vDS lo reenvía al joystick real, y los bytes 1-6 traen su dirección al revés.
- **Color y LEDs:** en el "set state", el byte 1 habilita el color (`0x04`) y los LEDs de jugador (`0x10`);
  el byte 43 es el patrón de LEDs (jugador 1 a 4: `0x04`, `0x0A`, `0x15`, `0x1B`, como la PS5) y los
  bytes 44-46, el RGB. Probado con el código de vDS: la conversión a Bluetooth los deja intactos.

### Apagar el joystick

No hay un comando HID para apagarlo. Se corta el enlace Bluetooth desde la PC
(`IOCTL_BTH_DISCONNECT_DEVICE` sobre el adaptador) y el DualSense se apaga solo, que es la misma
técnica que usan otras herramientas para PC. El joystick se busca entre los dispositivos Bluetooth
conectados de Windows, así que funciona tanto con vDS activo como sin él.

## Problemas que encontramos (y cómo se resolvieron)

| Problema | Causa | Solución |
|---|---|---|
| `list` no encuentra el joystick | Estaba emparejado pero no conectado del todo | Volver a conectarlo desde Bluetooth |
| Falla la captura de los auriculares de 8 canales | WASAPI rechaza algunas combinaciones de formato y canales | El script prueba float32/int16, 8/2 canales y varios tamaños de bloque |
| `vdsctl attach --ports 0` → "no allowed virtual port" | **Bug de vDS en Windows** (commit `ec53159`): valida `--ports` contra las rutas del driver viejo (`\\.\vdsN`), no contra las `usbip://` actuales | Conectar **sin `--ports`** (vDS usa cualquier puerto libre) |
| Una transferencia de archivos dejó una versión vieja | Caché del staging | Ahora cada copia se verifica con md5 |
| El audio del juego salía por los parlantes **y** por el joystick | Los juegos mandan sonido a los canales 1-2 del DualSense, y silenciarlo en Windows corta también la háptica | Modificación a vDS que silencia solo los canales 1-2, incluida al compilar, con un interruptor en el panel |
| El joystick se prendía y se apagaba solo con vDS | **Un juego abierto en Steam con Steam Input activado** (no era vDS: el vDS anterior fallaba igual) | Desactivar Steam Input para ese juego |
| La GUI podía colgarse | Llamadas a Tkinter desde hilos de fondo | Cola de mensajes: solo el hilo de la interfaz toca la ventana |
| El primer efecto tardaba 1,4 s | Carga diferida de SciPy | Se precarga al abrir el panel (~25 ms) |

## Problemas comunes

- **El joystick no aparece en `list`:** cerrá Steam, DS4Windows y DSX. Si vDS está en marcha, es normal
  (HidHide lo esconde): pasá a modo normal con `modo-normal.bat` o desde el panel.
- **"Fallos de escritura HID":** otro programa le manda reportes al joystick (Steam Input suele ser el culpable).
- **Se corta o tartamudea:** subí el buffer (`--buffer 100`) y mirá con `-v` que los reportes ronden los 94 por segundo.
- **Juegos con anti-cheat:** usbip-win2 y HidHide tienen drivers firmados (no hace falta el modo de prueba),
  pero cada anti-cheat es un mundo: si un juego se queja, pausá vDS.

---

## Pruebas automáticas

```
python -m pytest tests          # protocolo: paridad con SAxense, CRC, gatillos, luces, remuestreo...
bash tests/vds/run.sh           # contra el código real de vDS: silencio del parlante, gatillos, luces
```

La CI (`.github/workflows/ci.yml`) corre las dos en Linux. Después, en Windows: compila vDS con
`vds-mods/*.patch`, vuelve a correr las pruebas, arma `DualSenseControl.exe` con PyInstaller y lo arranca
con `--self-test` en una máquina limpia. La autoprueba verifica bibliotecas, tema, protocolo, que estén
los recursos y que vDS traiga nuestras modificaciones. Al **publicar una release** en GitHub le adjunta el
`.exe` y su `.sha256`, sin importar el nombre de la etiqueta. Para una release que ya existe:
*Actions → CI → Run workflow* con su etiqueta.

El `.exe` también sirve por consola: `DualSenseControl.exe --cli luces`, `--cli fx heartbeat`,
`--self-test resultado.json`, `--version`.

**Lo que no se puede probar automáticamente:** Bluetooth, drivers y juegos (las máquinas de CI no tienen
Bluetooth ni dejan instalar drivers). Para eso está [docs/PRUEBAS.md](docs/PRUEBAS.md).

---

## Créditos y referencias

Este proyecto existe gracias al trabajo de otros. La regla de SAxense: **si usás esta investigación, acreditala.**

### Investigación del protocolo
- **SAxense**, de egormanga (Sdore): la primera investigación pública de la háptica del DualSense por
  Bluetooth. Base de todo el envío por Bluetooth.
  [github.com/egormanga/SAxense](https://github.com/egormanga/SAxense) ·
  [apps.sdore.me/SAxense](https://apps.sdore.me/SAxense)
- Referencias que cita SAxense:
  [daidr/dualsense-tester](https://github.com/daidr/dualsense-tester) ·
  [Controllers Wiki: Sony DualSense](https://controllers.fandom.com/wiki/Sony_DualSense) ·
  [Controllers Wiki: Sony DualShock 4](https://controllers.fandom.com/wiki/Sony_DualShock_4) ·
  [PS4 Developer Wiki: DS4-BT](https://psdevwiki.com/ps4/DS4-BT) ·
  pistas sobre el formato PCM de [chiaki-ng](https://github.com/streetpea/chiaki-ng) (streetpea)

### Puente USB ↔ Bluetooth
- **vDS (virtual DualSense)**, de hurryman2212 (MIT): el joystick virtual USB que usamos.
  [github.com/hurryman2212/vds](https://github.com/hurryman2212/vds) ·
  micrófono, auriculares y USB/IP en Windows por [@TechAntohere](https://github.com/TechAntohere)
- **usbip-win2**, de vadimgrn: cliente USB/IP para Windows.
  [github.com/vadimgrn/usbip-win2](https://github.com/vadimgrn/usbip-win2) ·
  [releases](https://github.com/vadimgrn/usbip-win2/releases)
- **HidHide**, de Nefarius Software Solutions: esconde el joystick real.
  [github.com/nefarius/HidHide](https://github.com/nefarius/HidHide)
- **Opus**: códec del audio del parlante en vDS. [opus-codec.org](https://opus-codec.org/)

### Proyectos relacionados que estudiamos
- **dualsense-bt-haptics**, de awalol: reenvío de háptica por Bluetooth con ViGEmBus en Windows.
  [github.com/awalol/dualsense-bt-haptics](https://github.com/awalol/dualsense-bt-haptics) ·
  [issue #3 (ritmo exacto y un reporte por turno)](https://github.com/awalol/dualsense-bt-haptics/issues/3) ·
  [fork de ViGEmBus con DualSense](https://github.com/awalol/ViGEmBus/tree/simple_ds5_support)
- **DS5Dongle**, de awalol: base del manejo de paquetes de háptica en vDS.
  [github.com/awalol/DS5Dongle](https://github.com/awalol/DS5Dongle)
- **PadForge**, de hifihedgehog: remapeador libre con audio al parlante por Bluetooth (reporte `0x35`, Opus).
  [github.com/hifihedgehog/PadForge](https://github.com/hifihedgehog/PadForge)
- **ViGEmBus**, de nefarius: emulación de joysticks virtuales (proyecto ya retirado).
  [github.com/nefarius/ViGEmBus](https://github.com/nefarius/ViGEmBus)
- **DSX / DSX+**, de Paliverse: la alternativa paga.
  [github.com/Paliverse/DualSenseX](https://github.com/Paliverse/DualSenseX) ·
  [TweakTown: DSX v3.2 Beta agrega háptica por Bluetooth](https://tweaktown.com/news/112219/dsx-v3-2-beta-adds-native-playstation-dualsense-haptic-feedback-over-bluetooth-on-pc/index.html)

### Bibliotecas de Python
- [cython-hidapi](https://github.com/trezor/cython-hidapi) (paquete `hidapi`): acceso HID al joystick.
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch): PortAudio con captura loopback de WASAPI.
- [NumPy](https://numpy.org/) y [SciPy](https://scipy.org/): filtros y remuestreo.
- [python-soundfile](https://github.com/bastibe/python-soundfile): lectura de WAV, FLAC, OGG y MP3.
- [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme) (paquete `sv-ttk`): el tema del panel.

### Herramientas de compilación
- [Git](https://git-scm.com/), [CMake](https://cmake.org/), [vcpkg](https://github.com/microsoft/vcpkg),
  Visual C++ Build Tools 2022 y [winget](https://github.com/microsoft/winget-cli).

### Documentación de Windows
- [`IOCTL_BTH_DISCONNECT_DEVICE`](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/bthioctl/ni-bthioctl-ioctl_bth_disconnect_device)
  y [`BluetoothFindFirstDevice`](https://learn.microsoft.com/en-us/windows/win32/api/bluetoothapis/nf-bluetoothapis-bluetoothfindfirstdevice): apagar el joystick.
- [Grabación loopback de WASAPI](https://learn.microsoft.com/en-us/windows/win32/coreaudio/loopback-recording): el modo reactivo.
- [USB Audio Class en Windows (usbaudio.sys)](https://learn.microsoft.com/en-us/windows-hardware/drivers/audio/usb-audio-class-system-driver--usbaudio-sys-):
  el driver que carga Windows para la placa del joystick virtual.
