# Modificaciones a vDS

`instalar.bat` clona vDS en el commit de `VDS_COMMIT`, aplica estos parches en orden (`git apply`)
y recién entonces compila. Así vDS siempre sale "de fábrica" con nuestras funciones, sin parchear a mano.

| Parche | Qué hace |
|---|---|
| `0001-silenciar-parlante.patch` | Mientras exista `%ProgramData%\vDS\speaker-muted`, silencia los canales 1-2 (parlante y auriculares del joystick) y deja pasar los 3-4 (háptica). Lo usa el interruptor "Sonido por el joystick" del panel. |

Para agregar un parche: editar el código en `.build/vds`, `git -C .build/vds diff > vds-mods/0002-algo.patch`,
y correr `herramientas/recompilar-vds.bat`.

Para pasar a otra versión de vDS: ver "Cómo actualizar vDS" en `docs/BITACORA.md`.
