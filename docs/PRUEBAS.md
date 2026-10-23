# Probar DualSense Control en otra máquina

Gracias por probarlo. Las pruebas automáticas cubren el protocolo y el `.exe` en un Windows limpio,
pero **el Bluetooth, los drivers y los juegos solo se pueden probar en máquinas reales**. Para eso sirve
esta guía.

## Antes de empezar

- Windows 10 1903 o más nuevo, de 64 bits.
- Un DualSense (o DualSense Edge) y un adaptador Bluetooth.
- Cerrá DS4Windows, DSX y cualquier programa que tome joysticks.
- Anotá: modelo de PC o adaptador Bluetooth, versión de Windows (`winver`) y si ya tenías instalado
  HidHide, ViGEmBus o USB/IP.

## Lista de pruebas

Marcá cada una como ✅ (anduvo), ❌ (falló) o ➖ (no aplica).

### 1. Instalación
- [ ] El `.exe` abre y pide permiso de administrador.
- [ ] La pestaña **Instalación** muestra el estado (en una máquina nueva: todo "no instalado").
- [ ] **Instalar o reparar** abre una ventana, pide confirmación y termina con "LISTO".
      Si pidió reiniciar: después de reiniciar, volver a tocarlo también termina bien.
- [ ] Después de instalar, el estado muestra vDS "con nuestras modificaciones", y USB/IP y HidHide instalados.

### 2. Joystick virtual
- [ ] Con el joystick prendido, en **Joystick virtual (vDS)** aparece en la lista y **Conectar** funciona
      (columna "Conectado": sí).
- [ ] En el panel de sonido de Windows aparece "DualSense Wireless Controller".
- [ ] En **Háptica**, **Latido** se siente en el joystick.
- [ ] **Gatillos adaptativos → Gatillo de arma**: R2 se traba y hace "clic". **Apagar** los libera.
- [ ] Con un juego que tenga háptica nativa (y **Steam Input desactivado** para ese juego), la háptica
      del juego se siente. ¿Qué juego?: ________

### 3. Modos
- [ ] **Modo normal**: Steam (u otro programa) ve un DualSense Bluetooth común.
- [ ] Después de reiniciar, sigue en modo normal.
- [ ] **Modo vDS**: vuelve el joystick virtual.

### 4. Luces y joysticks
- [ ] **Joysticks y luces** lista el joystick con su dirección.
- [ ] **Identificar** hace parpadear la barra del joystick correcto.
- [ ] Color y jugador se aplican; al desconectar y volver a conectar el joystick, se vuelven a aplicar.
- [ ] (Con dos joysticks) Cada uno queda con su color.

### 5. Otros
- [ ] **Sonido por el joystick** apagado: el juego no suena por el parlante del joystick, pero vibra igual.
- [ ] **Reactivo al audio de la PC**: la música o un video hacen vibrar el joystick.
- [ ] **⏻ Apagar joystick** lo apaga.
- [ ] **Desinstalar vDS** deja el joystick como Bluetooth común.

## Si algo falla

1. En la pestaña **Instalación**, tocá **📦 Reportar problema**. Se arma un
   `DualSenseControl-reporte-<fecha>.zip` en tu Escritorio, con los registros del panel y de la instalación,
   un diagnóstico de Windows (Bluetooth, HidHide, USB/IP, programas que toman joysticks) y el registro de vDS.
2. Abrí un [*issue*](https://github.com/LDsAragon/dualsense-control-haptics-bt/issues/new) con:
   - qué prueba falló y qué pasó (y qué esperabas),
   - el `.zip` adjunto,
   - lo que anotaste en "Antes de empezar".

El `.zip` no tiene datos personales más allá de los nombres de dispositivos, programas abiertos que suelen
tomar joysticks y la dirección Bluetooth de tus joysticks. Revisalo antes de subirlo si querés.

## Problemas conocidos

- **El joystick se prende y se apaga solo**: casi siempre es Steam Input con un juego abierto. Desactivalo
  para ese juego. Detalles en `docs/BITACORA.md`, etapa 7.
- **"Windows protegió su PC"**: el `.exe` todavía no está firmado digitalmente.
- **Juegos con anti-cheat**: los drivers que usamos están firmados, pero cada anti-cheat es distinto. Si un
  juego se queja, pasá a **Modo normal**.
