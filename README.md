# Descargador de YouTube

Aplicación web personal para descargar videos o audio de YouTube en lote,
a partir de enlaces pegados directamente o extraídos de un archivo TXT,
DOCX o XLSX. Procesa las descargas como una cola (una a la vez) y entrega
el resultado como un archivo único o un ZIP si son varios.

## Características

- Extrae y normaliza enlaces de YouTube (`youtube.com`, `youtu.be`,
  `shorts`, `music.youtube.com`, etc.) desde texto pegado o desde
  archivos `.txt`, `.docx` (texto, tablas e hipervínculos) y `.xlsx`
  (celdas e hipervínculos).
- Descarga en formato **video (MP4, H.264/AAC)** o **audio (MP3, 320kbps)**.
- Procesa los enlaces en cola, uno a la vez, con progreso en tiempo real.
- Empaqueta automáticamente en ZIP cuando hay más de un resultado.
- Autenticación básica opcional (usuario/clave) para exponerla en internet.
- Pensada para correr localmente, en tu red local, o desplegada en
  Render (u otro host compatible con Docker).

## Requisitos

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/) instalado y disponible en el `PATH`
  (requerido por yt-dlp para convertir/unir audio y video).
- [Deno](https://deno.com/) instalado y disponible en el `PATH`
  (requerido por yt-dlp para resolver el JavaScript de YouTube).
- Un archivo `cookies.txt` con tu sesión de YouTube exportada (ver abajo).

## Instalación local

```bash
pip install -r requirements.txt
```

## Cookies de YouTube

Algunos videos requieren una sesión iniciada para descargarse. Exporta
tus cookies así:

1. Instala la extensión **"Get cookies.txt LOCALLY"** en tu navegador.
2. Inicia sesión en youtube.com.
3. Exporta las cookies del sitio y guarda el archivo como `cookies.txt`
   en la raíz del proyecto (junto a `app.py`).

La sesión expira con el tiempo. Si empiezas a ver errores de "confirma
que no eres un bot", vuelve a exportar el archivo.

> `cookies.txt` nunca debe subirse al repositorio ni a control de
> versiones — contiene tu sesión de YouTube. Ya está excluido en
> `.dockerignore`; agrégalo también a tu `.gitignore` si usas git.

## Variables de entorno

| Variable                  | Requerida | Descripción                                                                 | Default       |
|----------------------------|-----------|-------------------------------------------------------------------------------|---------------|
| `COOKIES_FILE`             | No        | Ruta al archivo de cookies exportado.                                        | `cookies.txt` |
| `MAX_CONCURRENT_DOWNLOADS` | No        | Descargas simultáneas. Con `1`, se procesa como cola secuencial.             | `1`           |
| `APP_USERNAME`             | No*       | Usuario para autenticación básica.                                           | —             |
| `APP_PASSWORD`             | No*       | Clave para autenticación básica.                                             | —             |
| `PORT`                     | No        | Puerto en el que escucha el servidor (lo inyecta Render automáticamente).    | `5000`        |

\* Si defines `APP_USERNAME` y `APP_PASSWORD`, la app queda protegida con
login. Si dejas alguna sin definir, la app queda **sin autenticación**
— solo recomendable para uso puramente local.

## Uso local

```bash
python app.py
```

La app queda disponible en `http://localhost:5000`. Al iniciar valida
que `ffmpeg` y `deno` estén en el `PATH`; si falta alguno, te avisa al
intentar una descarga.

### Acceso desde otros dispositivos de tu red

El servidor escucha en `0.0.0.0`, así que otros dispositivos en la
misma red wifi pueden acceder usando la IP local de tu computador
(ej. `http://192.168.1.X:5000`). Revisa que el firewall permita la
conexión en redes privadas.

## Despliegue en Render (Docker)

1. Sube el proyecto a un repositorio de GitHub (sin `cookies.txt`).
2. En Render: **New → Web Service**, conecta el repo, entorno **Docker**,
   plan **Free**.
3. En **Environment**, agrega `APP_USERNAME` y `APP_PASSWORD`.
4. En **Secret Files**, agrega un archivo con path `/app/cookies.txt`
   con el contenido de tu `cookies.txt` exportado.
5. Deploy. Render construye la imagen (instala `ffmpeg` y `deno` según
   el `Dockerfile`) y entrega una URL pública.

**Limitaciones del free tier de Render:** el servicio se suspende tras
15 minutos de inactividad (la siguiente visita tarda ~30-60s en
responder), y cuenta con solo 512 MB de RAM / 0.1 CPU — por eso la app
está configurada para procesar descargas en cola (`MAX_CONCURRENT_DOWNLOADS=1`)
en vez de en paralelo.

## Estructura del proyecto

```
.
├── app.py              # Aplicación Flask (lógica, rutas, cola de descargas)
├── templates/
│   └── index.html      # Interfaz web
├── requirements.txt    # Dependencias de Python
├── Dockerfile           # Imagen para despliegue (incluye ffmpeg y deno)
├── .dockerignore
└── cookies.txt         # Tu sesión de YouTube (NO subir al repo)
```

## Formatos de entrada aceptados

- **Enlaces pegados directamente**: cualquier texto que contenga URLs
  de YouTube; se extraen y normalizan automáticamente.
- **Archivo `.txt`**: texto plano con enlaces en cualquier parte.
- **Archivo `.docx`**: enlaces en párrafos, tablas e hipervínculos reales
  de Word.
- **Archivo `.xlsx`**: enlaces en el contenido de las celdas o como
  hipervínculos.

Tamaño máximo de archivo subido: 10 MB.

## Solución de problemas

| Síntoma                                            | Causa probable                                                        |
|-----------------------------------------------------|-------------------------------------------------------------------------|
| "YouTube solicitó verificar la sesión"               | `cookies.txt` desactualizado o ausente. Vuelve a exportarlo.            |
| "YouTube limitó temporalmente las solicitudes (429)" | Demasiadas solicitudes seguidas. Espera unos minutos.                   |
| "FFmpeg no está disponible en PATH"                  | Falta instalar FFmpeg o falta reiniciar la terminal tras instalarlo.    |
| "Falta un runtime JavaScript compatible"             | Falta instalar Deno o falta reiniciarlo en el `PATH`.                   |
| La app tarda ~1 min en responder tras un rato sin uso | Comportamiento normal del free tier de Render (spin down).             |

## Nota legal

Descargar contenido de YouTube puede estar sujeto a los Términos de
Servicio de la plataforma. Esta herramienta está pensada para uso
personal.
