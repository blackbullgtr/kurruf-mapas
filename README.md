# kurruf-mapas

Mapas sin conexión para el minimapa de **Kurruf Ride**: las calles de Chile por región, en un
formato compacto (`.krm`) que la app descarga una vez y usa sin internet.

Cada mes, GitHub baja solo el extracto de Chile de [Geofabrik](https://download.geofabrik.de/south-america/chile.html),
lo convierte y publica los archivos en GitHub Pages:

```
https://TU-USUARIO.github.io/kurruf-mapas/v1/regions.json
https://TU-USUARIO.github.io/kurruf-mapas/v1/nuble.krm
...
```

## Configurarlo (una sola vez)

1. **Crear el repositorio** en GitHub: botón **New** → nombre `kurruf-mapas` → **Public** → *Create repository*.
   (Público para que GitHub Pages y los procesos automáticos sean gratis.)
2. **Subir los archivos**: *Add file → Upload files* y arrastra `build_maps.py`, `verify_krm.py`,
   `index.html` y `README.md`.
3. **Crear el proceso automático**: *Add file → Create new file*, escribe como nombre
   `.github/workflows/mapas.yml` (con las barras, GitHub crea las carpetas solo) y pega el contenido
   del archivo `mapas.yml`. *Commit changes*.
4. **Activar Pages**: *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
5. **Primera generación**: pestaña *Actions* → **Mapas Kurruf** → **Run workflow**.
   Tarda unos minutos. Cuando quede en verde, abre `https://TU-USUARIO.github.io/kurruf-mapas/v1/regions.json`.
6. **En la app** no hay que hacer nada: la dirección viene incluida y la app baja sola la región
   donde estás (y la vecina al acercarte al borde navegando).

Desde ahí se actualiza solo el día 3 de cada mes, y la app baja las versiones nuevas sola.

## Publicar un firmware nuevo (OTA)

1. En el proyecto ESP-IDF sube la versión en `sdkconfig` (`CONFIG_APP_PROJECT_VER="1.0.4"`) y compila.
2. En GitHub: entra a la carpeta **firmware** del repositorio → *Add file → Upload files* → arrastra
   `build/RIDE.bin` (reemplaza el anterior, siempre con el nombre `RIDE.bin`) → *Commit changes*.
3. Se publica solo en 1-2 minutos (pestaña *Actions*). Si el archivo no es un firmware de Kurruf
   Ride (por ejemplo el bootloader), el proceso falla en rojo y no se publica nada.
4. La app avisa "Firmware 1.0.4 disponible" y con un toque lo instala por WiFi.

La primera vez la carpeta `firmware` no existe: *Add file → Create new file*, escribe como nombre
`firmware/LEEME.txt` (con la barra, GitHub crea la carpeta), cualquier texto, *Commit*. Después
entra a la carpeta y sube `RIDE.bin` ahí.

## Correrlo en tu PC (opcional)

```
pip install osmium
python build_maps.py chile-latest.osm.pbf salida
python verify_krm.py salida/v1/nuble.krm
```

## Licencia de los datos

Datos © colaboradores de OpenStreetMap, bajo la licencia [ODbL](https://www.openstreetmap.org/copyright).
Los archivos `.krm` son una base de datos derivada y se publican bajo la misma licencia.
