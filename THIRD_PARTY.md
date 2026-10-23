# Créditos y licencias de terceros / Third-party notices

Este proyecto se apoya en el trabajo de otros. / This project builds on the work of others.

| Proyecto | Qué usamos | Licencia | Cómo |
|---|---|---|---|
| [SAxense](https://github.com/egormanga/SAxense) (egormanga / Sdore) | Investigación del protocolo de háptica del DualSense por Bluetooth (reporte `0x32`, CRC) | MPL-2.0 | Reimplementado en Python en `app/dshaptics.py`; no se copia su código. **Crédito pedido por el autor:** https://apps.sdore.me/SAxense |
| [vDS](https://github.com/hurryman2212/vds) (hurryman2212) | Puente USB ↔ Bluetooth (joystick virtual) | MIT | Se descarga y compila desde su repositorio en un commit fijo (`vds-mods/VDS_COMMIT`), con nuestras modificaciones (`vds-mods/*.patch`). El `.exe` incluye esos binarios compilados. |
| [usbip-win2](https://github.com/vadimgrn/usbip-win2) (vadimgrn) | Cliente USB/IP para Windows | GPL-3.0 | **No se redistribuye:** se baja su instalador oficial y firmado al instalar. |
| [HidHide](https://github.com/nefarius/HidHide) (Nefarius Software Solutions) | Esconder el joystick Bluetooth real | MIT | **No se redistribuye:** se baja su instalador oficial al instalar. |
| [Opus](https://opus-codec.org/) | Códec del audio del parlante en vDS | BSD-3-Clause | Viene con la compilación de vDS (vcpkg) como `opus.dll`. |
| [cython-hidapi](https://github.com/trezor/cython-hidapi) | Acceso HID | BSD-3-Clause / GPL-3.0 / HIDAPI (a elección) | Dependencia de Python. |
| [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | Audio WASAPI con loopback | MIT | Dependencia de Python. |
| [NumPy](https://numpy.org/), [SciPy](https://scipy.org/) | Filtros y remuestreo | BSD-3-Clause | Dependencias de Python. |
| [python-soundfile](https://github.com/bastibe/python-soundfile) | Lectura de archivos de audio | BSD-3-Clause | Dependencia de Python. |
| [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme) | Tema del panel | MIT | Dependencia de Python. |

Referencias de investigación citadas por SAxense: [daidr/dualsense-tester](https://github.com/daidr/dualsense-tester),
[Controllers Wiki: DualSense](https://controllers.fandom.com/wiki/Sony_DualSense),
[PS4 Dev Wiki: DS4-BT](https://psdevwiki.com/ps4/DS4-BT), [chiaki-ng](https://github.com/streetpea/chiaki-ng).
Codificación de los efectos de gatillo: investigación de Nielk1 (TriggerEffectGenerator).

"PlayStation", "PS5", "DualSense" y "DualSense Edge" son marcas de Sony Interactive Entertainment Inc.
Este proyecto no está afiliado a Sony.
