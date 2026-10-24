# Bitácora del proyecto

Registro de todo lo que hicimos, decidimos y descubrimos, para no olvidarnos. Lo más nuevo va arriba
en **Estado actual**; abajo queda la historia completa, en orden.

---

## Estado actual (23/10/2026)

**Qué anda, probado en la PC real** (Windows 11, Python 3.14, DualSense `14:3a:9a:03:eb:f3`):
- Háptica por Bluetooth directo (`dshaptics`): ~95 reportes/s, 0 errores.
- vDS compilado e instalado: el joystick aparece como DualSense USB, con HidHide escondiendo el real.
- Panel DualSense Control: la háptica salió por la placa virtual
  `Altavoces (2- DualSense Wireless Controller)` (4 canales, float32), el modo reactivo capturó
  `Parlantes EDIFIER` y el botón de apagar funcionó (`apagado 14:3a:9a:03:eb:f3`).

**Escrito pero todavía sin probar en la PC:**
- La modificación de vDS que silencia el parlante (`vds-mods/0001-silenciar-parlante.patch`).
  Compilada y probada acá en Linux; falta compilarla con MSVC en Windows.
- El instalador unificado (`instalar.bat`) y la nueva estructura de carpetas.

**Hito (23/10, 15:04-15:14): háptica nativa en Death Stranding Director's Cut por Bluetooth**, con el
vDS nuevo y Steam Input desactivado para el juego. El usuario: "todo funcionó, lo único que no noto son
los gatillos adaptativos". Ver la etapa 8.

**Publicado (23/10, 19:41):** https://github.com/LDsAragon/dualsense-control-haptics-bt (público, MIT).
La primera corrida de la CI pasó entera: pruebas, compilación de vDS y del `.exe`, y autoprueba en un Windows
limpio. El usuario creó la primera release, `0.0.1` ("First BareBones Test For Haptics Over BT"). Ver la etapa 11.

**Pendientes / ideas:**
- [x] `instalar.bat` completo con la nueva estructura: compiló e instaló bien (14:08).
- [x] Reinstalar el vDS nuevo (`herramientas/recompilar-vds.bat`).
- [x] Ajuste de Steam: desactivar Steam Input para el juego (documentado en el README).
- [x] Probar con un juego con háptica nativa: Death Stranding Director's Cut, anduvo.
- [x] Gatillos confirmados en el joystick real desde el panel ("funcionó perfecto", 15:47).
- [ ] Probar en la PC: Modo normal / Modo vDS y Restablecer joystick (etapa 9).
- [ ] Probar en la PC: pestaña "Joysticks y luces" (etapa 10), idealmente con dos joysticks.
- [ ] Confirmar el interruptor del parlante en un juego.
- [ ] Adjuntar el `.exe` a la release `0.0.1` (Run workflow) y probarlo en la PC.
- [ ] Actualizar las acciones de GitHub (aviso de Node.js 20).
- [ ] Reportar a vDS el bug de `--ports` en Windows (ver más abajo). Ofrecerle también la modificación del parlante.
- [ ] Captura de audio de un solo proceso (modo reactivo sin Discord/Spotify).
- [ ] Perfil "juego" para el modo reactivo (compuerta y compresor).
- [x] Gatillos adaptativos desde el panel (etapa 8).

---

## Datos clave (para no tener que redescubrirlos)

| Qué | Valor |
|---|---|
| Commit de vDS que usamos | `ec531599dfdd02e14ce68efd8c0d2dcb439894a5` (25/07/2026, "Synchronize the controller microphone mute LED") |
| usbip-win2 instalado | 0.9.8.1 (firmado por Cloudyne Systems, no hace falta el modo de prueba) |
| IDs USB del DualSense | Sony `054C`, DualSense `0CE6`, DualSense Edge `0DF2` |
| UUID HID de Bluetooth | `00001124-0000-1000-8000-00805f9b34fb` |
| Reporte háptico BT (SAxense) | `0x32`, 142 bytes, cada 10,667 ms, 32 frames estéreo int8 a 3 kHz, CRC32 sobre `0xA2` + 138 bytes |
| Reporte de vDS | `0x36`: control `0x11` + estado `0x10` (gatillos/LED) + háptica `0x12` + parlante `0x13`/auriculares `0x16` en Opus de 200 bytes |
| Placa de audio USB del DualSense | 4 canales, 48 kHz, 16 bits: 1-2 = parlante/auriculares, 3-4 = motores |
| Pipe de control de vdsd | `\\.\pipe\vdsd` |
| Registro de vdsd | `%ProgramData%\vDS\vdsd.log` |
| Configuración de joysticks de vDS | `%ProgramData%\vDS\vdsd.db` (sobrevive a reinstalar) |
| Interruptor del parlante | existe `%ProgramData%\vDS\speaker-muted` = parlante silenciado |
| Puerto USB/IP de vdsd | `usbip://127.0.0.1:3240/1-1` (puerto virtual 0) |

---

## Historia

### 1. Entender el terreno
- Analizamos **dualsense-bt-haptics** (awalol): ViGEmBus modificado + dispositivo de audio virtual
  renombrado + reportes de SAxense. Según su autor, solo anda en pocos juegos (Genshin) y tiene unos 200 ms de latencia.
- Analizamos **SAxense.c**: lee PCM s8 estéreo a 3 kHz por stdin y escribe reportes `0x32` a hidraw.
  El CRC arranca con la semilla `~0xEADA2D49`, que es el estado del CRC tras procesar el byte `0xA2`.
- Corrección propia: el reporte mide **142** bytes, no 141.

### 2. `dshaptics` (Python, Bluetooth directo)
- Modos: `list`, `diag`, `fx` (6 efectos), `file`, `loopback`, `apagar`.
- **Verificado byte a byte contra SAxense.c compilado** (CRC incluido).
- Bugs que encontramos al probar, ya corregidos:
  - La ganancia por defecto de `loopback` se filtraba a los otros modos (argparse compartido).
  - El remuestreador en vivo generaba un 1,2 % de muestras de más, que con el tiempo habría llenado el buffer.
  - Faltaba un pre-llenado del buffer en vivo, para absorber el jitter.
  - **Ráfagas al atrasarse:** ahora los turnos perdidos se saltean (lección del issue #3 de awalol).
- En la PC: `list` decía "ninguno" porque el joystick estaba emparejado pero no conectado del todo.
  Se solucionó volviendo a conectarlo desde Bluetooth, sin tocar código.
- Los auriculares PRO X2 (8 canales, 7.1 virtual de G HUB): WASAPI rechazaba la captura con `-9999`.
  Ahora se prueban varias combinaciones de formato, canales y tamaño de bloque.
- **Problema de transferencia:** una copia a la PC dejó una versión vieja del archivo.
  Desde entonces, cada copia se hace con un nombre nuevo y se verifica con md5.

### 3. Háptica nativa en juegos: el camino vDS
- DSX+ (pago) hace lo mismo con la misma investigación. Decidimos usar alternativas libres.
- Encontramos **vDS** (hurryman2212): USB/IP + HidHide + vdsd, que ya resolvía todo lo que íbamos a construir.
- **Compilación local:** el script instala Git, CMake y Build Tools; vcpkg trae Opus.
  En la PC ya había Build Tools 18 (`C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools`).
  Compiló en unos 15 s: `vdsd.exe` (457 KB), `vdsctl.exe` (60 KB), `opus.dll` (430 KB).
- **Instalación:** el instalador de usbip-win2 pidió reiniciar (código 3010). Después de reiniciar siguió bien.
- **Bug de vDS en Windows** (commit `ec53159`): `vdsctl attach ... --ports 0` devuelve
  `"no allowed virtual port"`. Causa: `validate_config_assignments` → `port_index_from_path` solo
  entiende las rutas del driver viejo (`\\.\vdsN`), pero en Windows los puertos ahora son `usbip://…`.
  **Solución:** conectar sin `--ports` (`"ports":[]` = cualquier puerto libre). Funcionó al primer intento.

### 4. Panel DualSense Control (`dsgui.py`)
- Tkinter + tema Sun Valley (`sv-ttk`). Dos pestañas: vDS y Háptica.
- Salida automática: con vDS conectado, la háptica va a los canales 3-4 de la placa virtual
  (el mismo camino que un juego); sin vDS, va por Bluetooth directo.
- Bugs encontrados al probarlo con simulaciones, ya corregidos:
  - Llamadas a Tkinter desde hilos de fondo ("main thread is not in main loop"): ahora hay una cola de mensajes.
  - La lectura del perfil se hacía desde un hilo.
  - El callback de audio podía correr antes de terminar la configuración.
  - El primer efecto tardaba 1,4 s (carga de SciPy): ahora se precarga y tarda ~25 ms.
- Botón **Apagar joystick**: `IOCTL_BTH_DISCONNECT_DEVICE` (0x41000C) sobre cada adaptador; el DualSense
  se apaga solo al perder el enlace. Estructuras verificadas contra el SDK (40 y 560 bytes).

### 5. Silenciar el parlante sin perder la vibración
- Problema: el audio del juego salía por los parlantes de la PC **y** por el joystick. Silenciar el
  dispositivo en Windows corta los 4 canales, háptica incluida.
- Modificación a vDS (`PcmAudioExtractor::push_usb_audio`): si existe `speaker-muted`, se ponen en cero
  los canales 1-2 antes de Opus. Se revisa cada 250 ms. En Windows usa `_dupenv_s`, para evitar el aviso C4996.
- Probado compilando `vds_protocol.cc` en Linux: parlante decodificado 12619 → **0**, háptica 77 → 77.
- La primera versión era un script que reemplazaba el archivo, verificando hashes CRLF
  (original `B69F2AF2…`, parcheado `ED7A1022…`).

### 6. Reorganización (esta etapa)
- Se pidió: bitácora, pasos más simples, carpetas, y que la compilación regenere vDS con la modificación
  incluida, en lugar de parchear a mano.
- **Decisión:** `instalar.bat` hace todo. Clona vDS con `core.autocrlf=false` (para que el `.patch` de
  fin de línea LF aplique sin problemas), fija el commit de `vds-mods/VDS_COMMIT`, aplica `vds-mods/*.patch`
  con `git apply --check` primero, compila, instala (reemplaza) y verifica la marca `speaker-muted` en el exe.
  Al volver a correrlo, hace `checkout --force` + `reset --hard` + `clean` y regenera desde cero.
- Flujo de git + parche probado acá: aplica, se regenera y vuelve a aplicar, y `--reverse --check`
  confirma que quedó aplicado.
- Los archivos viejos quedan en `_anterior/` (no se borran).

### 7. Incidente: el joystick se conecta y se desconecta (resuelto: juego abierto en Steam)
- Después de `instalar.bat` (14:08), cada sesión del puente dura unos 0,5 s: arranca, Windows carga
  el joystick virtual, llegan dos `hid out report_id=2` y enseguida
  `bluetooth-to-virtual stopped: HID read completion failed: El dispositivo no está conectado`.
  El enlace Bluetooth se cae y el joystick se reconecta; se repite.
- Con el vDS anterior (compilado a las 06:12) las sesiones duraban horas: la de las 13:02 duró hasta
  que apagamos el joystick a las 13:16.
- **Descartado:** mismo commit `ec53159` en las dos fuentes, misma versión de Opus (1.5.2 de vcpkg),
  drivers sin cambios ("already installed"), el panel (la primera caída fue antes de abrirlo) y el
  archivo `speaker-muted` (no existe, así que la modificación está inactiva).
  La única diferencia en el binario es la modificación (467968 → 469504 bytes).
- Distinto en las sesiones malas: Windows consulta varias veces el reporte de característica 9
  (emparejamiento) contra el joystick virtual.
- Hipótesis a separar: (a) algo del binario nuevo, (b) algo del joystick (por ejemplo, batería baja:
  el DualSense se corta al activar la luz o la vibración).
- Para separarlas: `herramientas/prueba-ab.bat` mide la batería sin vDS (nuevo comando `dshaptics bateria`),
  corre el vDS nuevo 25 s y el anterior 25 s, y deja marcas de tiempo en `logs/prueba-ab.log` para cruzarlas
  con `vdsd.log`. Claude tiene acceso de lectura a `C:\ProgramData\vDS`.

- **Resultado de la prueba A/B (14:47):** sin vDS, el joystick se mantuvo conectado y la batería estaba
  al 95 %. Con el vDS nuevo se apagó a los 0,67 s. El anterior no llegó a probarse (el joystick seguía
  apagado), pero a las 14:51:57, con el **vDS anterior** y el joystick prendido, **también se apagó**
  a los 0,34 s. Así quedó descartada nuestra compilación.
- **Causa:** el usuario cerró **un juego que tenía abierto en Steam** y a las 14:53:15 la sesión
  arrancó y se mantuvo (más de 18.000 reportes de entrada sin cortes).
- **Hipótesis (sin confirmar):** con un juego corriendo, Steam Input toma el joystick virtual "USB",
  lee el reporte de característica 9 (que trae la dirección Bluetooth real) y el 0x20 (firmware), manda
  reportes de salida, y el DualSense termina apagándose, como cuando se enchufa un joystick que ya
  estaba conectado por Bluetooth. Eso explica las consultas repetidas al reporte 9 que se veían solo
  en las sesiones malas.
- **Lecciones:** antes de culpar a una compilación, probar el binario anterior *en las mismas
  condiciones*. Y el registro de vdsd (`%ProgramData%\vDS\vdsd.log`) es la mejor fuente: el patrón
  "feature get report_id=9 repetido + `HID read completion failed`" indica que otro programa está
  tocando el joystick virtual.
- Herramientas nuevas que quedaron: `herramientas/prueba-ab.bat`, `herramientas/diag-windows.bat` y
  `dshaptics bateria`.

### 8. Death Stranding y los gatillos adaptativos
- Configuración que anduvo: vDS nuevo + **Steam Input desactivado** para el juego + parlantes como
  salida predeterminada. En los foros de Steam se mencionan los mismos requisitos (Steam Input
  apagado y la placa de audio del DualSense habilitada) y que por Bluetooth no anda sin un puente como vDS.
- Lo que muestra vdsd.log en la partida (15:04-15:14): el juego mandó unos 30.000 reportes de salida
  (`hid out report_id=2`, hasta unos 90 por segundo) y abrió y cerró la placa de audio
  (`audio out interface altsetting=1/0`), o sea háptica por audio. Una sola sesión del puente, sin cortes.
- **Gatillos:** el usuario no los notó. vDS los reenvía (si el juego activa `allow_right/left_trigger_ffb`,
  copia los 11 bytes del efecto), pero su rastreo no registra el contenido de los reportes, así que no se
  ve si el juego los pidió. Según los foros, en Death Stranding solo se endurecen con mucha carga.
- Para separar las dos cosas, agregamos efectos propios: `dshaptics gatillos duro|arma|vibracion|off`
  y botones en el panel. Codificación de los efectos oficiales (Nielk1): Feedback `0x21`, Weapon `0x25`,
  Vibration `0x26`, Off `0x05`. Van en el byte 0 con los bits `0x04`/`0x08` y en los bytes 10-20 y 21-31
  del "set state". Por USB (o el joystick virtual) es el reporte `0x02` de 48 bytes; por Bluetooth, el
  `0x31` de 78 bytes con el CRC en 74-77.
- **Verificado con el código real de vDS:** `DsOutputState::apply_usb_output_report` acepta nuestro
  reporte y `build_bt_state_report` produce el `0x31` con los 11 bytes de cada gatillo intactos y el CRC correcto.

### 9. Volver a la normalidad
- Los gatillos funcionaron desde el panel, así que la cadena completa está confirmada. En Death
  Stranding, entonces, el juego simplemente los usa poco.
- Pedido: una forma de "restablecer los joysticks a su forma normal". Lo resolvimos en dos niveles:
  - **Restablecer joystick** (panel, `dshaptics restablecer`): corta lo que esté sonando y deja los gatillos
    sin efecto (Off `0x05`). No cambia de modo. Hacía falta porque un efecto de gatillo queda puesto en el
    joystick hasta que algo lo cambie.
  - **Modo normal / Modo vDS** (`scripts/modo.ps1`, usado por `modo-normal.bat`, `modo-vds.bat` y los botones
    del panel). Normal: `sc stop vdsd` + `sc config vdsd start= demand` + `HidHideCLI --dev-unhide` de cualquier
    instancia con `054C` que haya quedado en `--dev-list` + gatillos en Off. vDS: `start= auto` + `sc start`.
    A diferencia de "Detener", **sobrevive al reinicio** (antes vDS volvía a arrancar con Windows).
- El panel lee `sc qc vdsd` (`AUTO_START` o `DEMAND_START`) y avisa si el estado no va a durar un reinicio.
- `pausar-vds.bat` y `reanudar-vds.bat` se movieron a `_anterior/`: los reemplazan los modos.

### 10. Identificar joysticks y color de la barra
- Pedido: identificar los distintos joysticks conectados y ponerles color a la barra.
- **Identidad = dirección Bluetooth.** Por Bluetooth, hidapi la da como `serial_number` (`143a9a03ebf3`).
  El joystick virtual de vDS **no tiene serie** (`iSerialNumber=0` en `ds5_usb.h`), pero vDS reenvía el
  pedido de característica `0x09` al joystick real (`feature get report_id=9 ... bluetooth_forward=yes`,
  y después lo guarda en caché), y sus bytes 1-6 son la dirección al revés. Funciona igual en los dos modos.
  La dirección se cachea por ruta de dispositivo para no abrirlo en cada refresco.
- **Luces:** byte 1 = `0x04` (color) y `0x10` (LEDs de jugador); byte 43 = patrón (PS5: J1 `0x04`,
  J2 `0x0A`, J3 `0x15`, J4 `0x1B`; usamos `0x1F` para J5); bytes 44-46 = RGB.
  Verificado con `DsOutputState` de vDS: un reporte con `#ff4000` y jugador 2 sale por Bluetooth con
  `ff 40 00` y `0x0a`.
- Panel: pestaña "Joysticks y luces" (lista, Identificar con parpadeo blanco/apagado que vuelve al color
  guardado, nombre, color, jugador, Aplicar y guardar). Configuración en `config/joysticks.json`,
  indexada por dirección. Se reaplica sola cuando aparece un par (dirección, ruta) nuevo, así que funciona
  al reconectar y al cambiar de modo. Probado con dos joysticks simulados.
- CLI: `dshaptics luces | identificar [mac] | color [mac] #RRGGBB [--jugador N] [--nombre ...]`.
- Limitación: un juego abierto puede pisar el color con el suyo.

### 11. GitHub, el `.exe` y las pruebas para terceros
- Decisiones del usuario: subirlo **conectando GitHub a Claude** (así Claude puede ver y arreglar la CI),
  repositorio **público** y licencia **MIT** (la misma que vDS).
- **Licencias:** SAxense (MPL-2.0) está reimplementado, no copiado, y se acredita como pide su autor. vDS
  (MIT) se compila con nuestras modificaciones y sus binarios van dentro del `.exe`. usbip-win2 (GPL-3.0) y
  HidHide **no se redistribuyen**: se bajan sus instaladores oficiales y firmados al instalar. Todo está
  detallado en `THIRD_PARTY.md`.
- **Git:** `.gitattributes` guarda todo con LF; en Windows salen `.bat` y `.ps1` con CRLF; el `.patch` y
  `VDS_COMMIT` quedan marcados `-text` (nunca se convierten), por lo que pasó en la etapa 6.
- **Pruebas automáticas** (`tests/`): 16 de Python (paridad byte a byte con la salida del `SAxense.c` original,
  guardada en `tests/fixtures/saxense_ref.bin`; CRC; gatillos; luces; dirección; remuestreo sin deriva;
  batería; estructuras de Windows) y una de C++ contra el código real de vDS (`tests/vds/run.sh`): silencio del
  parlante y conversión de gatillos y luces con `DsOutputState`. Todo pasa.
- **`.exe`** (`packaging/DualSenseControl.spec`, PyInstaller, un solo archivo de unos 60 MB, sin consola):
  - Recursos adentro (scripts, `vds-bin/`, `vds-packaging/`); al arrancar se copian a
    `%LOCALAPPDATA%\DualSenseControl\recursos\<versión>`, porque PyInstaller borra su carpeta temporal al cerrar.
    La configuración y los registros también van a `%LOCALAPPDATA%\DualSenseControl`.
  - Se eleva solo a administrador (ShellExecute "runas"); si no lo aceptan, sigue con funciones limitadas.
  - `instalar.ps1 -Binarios -Paquete -Logs`: instala vDS ya compilado, igual que `cmake --install`
    (`stop_service.ps1`, copiar `vdsd.exe`/`vdsctl.exe`/`opus.dll`, `install_service.ps1 -BinaryPath`).
  - Pestaña **Instalación** (estado, Instalar o reparar, Desinstalar, Reportar problema, registros).
    **Reportar problema** arma un `.zip` con registros, `diag-windows`, `vdsd.log` (últimos 2 MB), `vdsd.db` y la configuración.
  - `--self-test [json]`, `--cli <comando de dshaptics>` y `--version`.
  - Probado acá con un ejecutable de Linux armado con la misma receta y binarios de vDS de mentira:
    la autoprueba pasa, los 14 recursos se copian y `--cli` anda.
- **CI** (`.github/workflows/ci.yml`): Linux corre pytest y las pruebas contra vDS. Windows compila vDS con
  los parches (vcpkg del runner), corre pytest, arma el `.exe`, lo arranca con `--self-test` y lo sube como
  artefacto. Con un tag `v*` lo publica en Releases con su `.sha256`.
- Guía para terceros: `docs/PRUEBAS.md`.
- **Publicación:** Claude tiene acceso de solo lectura al repositorio (la app de Claude no está instalada
  en él), así que el usuario sube los cambios con GitHub Desktop desde `Documentos\GitHub\dualsense-control-haptics-bt`
  y Claude sigue la CI con `gh` (los registros completos no se pueden bajar desde la sesión: el almacenamiento
  de los logs de Actions está fuera de su red; los estados de los pasos sí se ven por la API).
  La carpeta `.github/` no se puede escribir con la copia directa de archivos: se copia con otro nombre y se mueve.
- **Primera CI** (run 40035175594, commit `4777ad2`): verde al primer intento. Pruebas en Linux 30 s;
  Windows 3 min 7 s (vDS + pytest + PyInstaller + autoprueba + SHA-256). Artefacto de 57 MB comprimido.
  La release `0.0.1` salió **sin el `.exe`**: la CI solo reaccionaba a etiquetas `v*` y el usuario la creó
  sin la "v". Se corrigió: ahora dispara con `release: published` (cualquier etiqueta) y con
  `workflow_dispatch` + `release_tag` para adjuntarlo a una release existente. La versión del código pasó a
  `0.0.1`, para coincidir con la de la release.
  Avisos: Node.js 20 deprecado en `actions/checkout@v4`, `setup-python@v5` y `upload-artifact@v4` (pasar a
  versiones nuevas), y `ubuntu-latest` migra a Ubuntu 26.

---

## Cómo actualizar vDS a una versión nueva
1. Cambiar el hash en `vds-mods/VDS_COMMIT`.
2. Correr `herramientas/recompilar-vds.bat`. Si una modificación ya no aplica, el script lo dice y no instala nada.
3. Si falla, rehacer el `.patch` sobre el commit nuevo (pedírselo a Claude) y volver al paso 2.
