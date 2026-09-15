import os
import re
import time
import uuid
import shutil
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from flask import Flask, render_template, request, jsonify, send_file, Response
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from openpyxl import load_workbook

import yt_dlp


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# =========================================================
# CONFIGURACIÓN
# =========================================================

# Archivo de cookies exportado (formato Netscape, cookies.txt).
# Más confiable que leer el navegador directamente, y funciona
# igual en tu PC o en un servidor remoto (ahí no hay navegador
# con tu sesión iniciada).
#
# Cómo generarlo:
#   1. Instala la extensión "Get cookies.txt LOCALLY" en Chrome/Firefox.
#   2. Inicia sesión en youtube.com.
#   3. Exporta las cookies del sitio y guarda el archivo como
#      cookies.txt junto a este script (o cambia la ruta abajo).
#
# La sesión expira con el tiempo: si vuelves a ver errores de
# "confirma que no eres un bot", vuelve a exportar el archivo.
COOKIES_FILE = os.environ.get("COOKIES_FILE", "cookies.txt")


def _prepare_writable_cookiefile(source_path):
    """
    yt-dlp reescribe el archivo de cookies después de cada descarga
    (para guardar cookies de sesión que YouTube va rotando). En Render,
    los "Secret Files" se montan como solo lectura (/etc/secrets/...),
    así que si apuntamos yt-dlp directo ahí, falla al intentar guardar
    y la descarga se cae. Por eso copiamos el archivo a una carpeta
    temporal escribible al iniciar el servidor, y usamos esa copia.
    """
    if not source_path or not Path(source_path).exists():
        return None

    writable_path = Path(tempfile.gettempdir()) / "cookies_writable.txt"

    try:
        shutil.copyfile(source_path, writable_path)
        return str(writable_path)
    except Exception as error:
        print(
            f"No se pudo copiar el archivo de cookies a una ruta "
            f"escribible: {error}",
            flush=True,
        )
        return source_path


# Ruta que realmente usa yt-dlp (copia escribible), distinta de
# COOKIES_FILE (la fuente original, que puede ser de solo lectura).
ACTIVE_COOKIES_FILE = _prepare_writable_cookiefile(COOKIES_FILE)


MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", 1))

# Usuario/clave simples para poder exponer la app a internet
# sin que cualquiera con la URL pueda usarla. Defínelos como
# variables de entorno antes de iniciar la app:
#   APP_USERNAME=tu_usuario
#   APP_PASSWORD=tu_clave
# Si no se definen, la app queda sin autenticación (solo para
# uso puramente local).
APP_USERNAME = os.environ.get("APP_USERNAME")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

# Proxy opcional para las descargas (formato: http://usuario:clave@host:puerto
# o socks5://host:puerto). Útil cuando el servidor corre en un datacenter
# (Render, AWS, etc.) y YouTube empieza a bloquear o pedir verificación extra
# por venir de una IP de nube en vez de una IP residencial. Sin esto definido,
# las descargas salen directo desde la IP del servidor.
YTDLP_PROXY = os.environ.get("YTDLP_PROXY")

jobs = {}
jobs_lock = threading.Lock()

URL_PATTERN = re.compile(r'https?://[^\s<>"\']+')


# =========================================================
# AUTENTICACIÓN BÁSICA (opcional)
# =========================================================

def _check_auth(auth):
    if not APP_USERNAME or not APP_PASSWORD:
        return True
    return (
        auth
        and auth.username == APP_USERNAME
        and auth.password == APP_PASSWORD
    )


def requires_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not APP_USERNAME or not APP_PASSWORD:
            # Sin credenciales configuradas, no se exige login.
            return view(*args, **kwargs)

        auth = request.authorization

        if not _check_auth(auth):
            return Response(
                "Autenticación requerida.",
                401,
                {"WWW-Authenticate": 'Basic realm="Descargas"'},
            )

        return view(*args, **kwargs)

    return wrapped


# =========================================================
# UTILIDADES DE LINKS
# =========================================================

def normalize_youtube_url(url):
    """
    Convierte enlaces de YouTube a:
    https://www.youtube.com/watch?v=VIDEO_ID

    Elimina parámetros como:
    &list=...
    &start_radio=...
    &pp=...
    """
    url = url.strip().rstrip(".,;:!?)]}")

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    host = parsed.netloc.lower()

    if host.startswith("www."):
        host = host[4:]

    video_id = None

    if host == "youtu.be":
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            video_id = parts[0]

    elif host in {
        "youtube.com",
        "m.youtube.com",
        "music.youtube.com",
    }:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]

        else:
            parts = [part for part in parsed.path.split("/") if part]

            if len(parts) >= 2 and parts[0] in {
                "shorts",
                "embed",
                "live",
            }:
                video_id = parts[1]

    if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return f"https://www.youtube.com/watch?v={video_id}"

    return None


def extract_urls(text):
    urls = []

    for raw_url in URL_PATTERN.findall(text or ""):
        normalized = normalize_youtube_url(raw_url)

        if normalized:
            urls.append(normalized)

    return list(dict.fromkeys(urls))


# =========================================================
# ARCHIVOS TXT / WORD / EXCEL
# =========================================================

def read_uploaded_file(file):
    extension = Path(file.filename).suffix.lower()
    urls = []

    if extension == ".txt":
        text = file.read().decode("utf-8", errors="ignore")
        urls.extend(extract_urls(text))

    elif extension == ".docx":
        document = Document(file)

        for paragraph in document.paragraphs:
            urls.extend(extract_urls(paragraph.text))

        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    urls.extend(extract_urls(cell.text))

        for relationship in document.part.rels.values():
            if relationship.reltype == RT.HYPERLINK:
                urls.extend(extract_urls(relationship.target_ref))

    elif extension == ".xlsx":
        workbook = load_workbook(
            file,
            read_only=True,
            data_only=True,
        )

        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is not None:
                        urls.extend(extract_urls(str(cell.value)))

                    if cell.hyperlink and cell.hyperlink.target:
                        urls.extend(extract_urls(cell.hyperlink.target))

    else:
        raise ValueError(
            "Formato no compatible. Usa TXT, DOCX o XLSX."
        )

    return list(dict.fromkeys(urls))


# =========================================================
# LIMPIEZA DE TRABAJOS TEMPORALES
# =========================================================

def cleanup_old_jobs(max_age_seconds=3600):
    now = time.time()

    with jobs_lock:
        stale_ids = [
            job_id
            for job_id, job in jobs.items()
            if now - job.get("created_at", now) > max_age_seconds
        ]

        stale_dirs = [
            jobs[job_id].get("temp_directory") for job_id in stale_ids
        ]

        for job_id in stale_ids:
            jobs.pop(job_id, None)

    for temp_directory in stale_dirs:
        if temp_directory:
            shutil.rmtree(temp_directory, ignore_errors=True)


# =========================================================
# MENSAJES DE ERROR AMIGABLES
# =========================================================

def friendly_download_error(error):
    message = str(error)
    lower = message.lower()

    if "429" in lower or "too many requests" in lower:
        return (
            "YouTube limitó temporalmente las solicitudes (error 429). "
            "Espera unos minutos antes de volver a intentarlo, o baja "
            "el número de descargas simultáneas."
        )

    if "sign in to confirm you're not a bot" in lower:
        return (
            "YouTube solicitó verificar la sesión. Esto puede ser porque "
            "cookies.txt expiró (vuelve a exportarlo), o porque YouTube "
            "está bloqueando la IP del servidor por venir de un datacenter "
            "(prueba configurando YTDLP_PROXY con un proxy residencial)."
        )

    if (
        "http error 403" in lower
        or "unable to download webpage" in lower
        or ("blocked" in lower and "ip" in lower)
    ):
        return (
            "YouTube bloqueó la solicitud, probablemente por venir de una "
            "IP de datacenter (común en hosting en la nube como Render). "
            "Prueba configurando la variable YTDLP_PROXY con un proxy "
            "residencial, o espera e intenta de nuevo más tarde."
        )

    if "read-only file system" in lower and "cookie" in lower:
        return (
            "No se pudo escribir el archivo de cookies (sistema de solo "
            "lectura). Si esto persiste, revisa que COOKIES_FILE apunte "
            "a la copia temporal editable, no directo al secret file."
        )

    if "no such file" in lower and "cookie" in lower:
        return (
            f"No se encontró el archivo de cookies ({COOKIES_FILE}). "
            "Expórtalo desde tu navegador e ingrésalo en esa ruta."
        )

    if "failed to decrypt" in lower and "cookie" in lower:
        return "No se pudieron leer correctamente las cookies."

    if "javascript runtime" in lower or "js runtime" in lower:
        return (
            "Falta un runtime JavaScript compatible. "
            "Instala Deno y reinicia la consola antes de ejecutar la aplicación."
        )

    if "requested format is not available" in lower:
        return "YouTube no ofreció un formato compatible para este video."

    return "No se pudo descargar este enlace."


# =========================================================
# PROGRESO (varias descargas en paralelo)
# =========================================================

def _update_job_progress(job_id):
    """
    Recalcula el progreso global del trabajo a partir del
    progreso individual de cada item. Se llama cada vez que
    cambia el estado de un item.
    """
    job = jobs.get(job_id)

    if not job:
        return

    items = job["items"]
    total = len(items)

    if total == 0:
        return

    done = sum(1 for item in items.values() if item["status"] in ("finished", "error"))
    in_progress_fraction = sum(
        item["progress"]
        for item in items.values()
        if item["status"] == "downloading"
    )

    overall = (done + in_progress_fraction) / total * 100
    job["progress"] = round(min(overall, 99.9 if done < total else 100), 1)

    active_titles = [
        item["title"] or f"video {index}"
        for index, item in items.items()
        if item["status"] == "downloading"
    ]

    if active_titles:
        job["message"] = (
            f"Descargando {done}/{total} completados "
            f"({len(active_titles)} en curso): " + ", ".join(active_titles[:3])
        )
    else:
        job["message"] = f"Procesando {done}/{total}..."


def create_progress_hook(job_id, index):
    def hook(data):
        job = jobs.get(job_id)

        if not job:
            return

        item = job["items"][index]

        status = data.get("status")
        info = data.get("info_dict") or {}
        title = info.get("title")

        if title:
            item["title"] = title

        if status == "downloading":
            downloaded = data.get("downloaded_bytes", 0)
            total_bytes = (
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or 0
            )

            fraction = (downloaded / total_bytes) if total_bytes else 0
            # Evita retrocesos cuando audio/video se descargan aparte.
            item["progress"] = max(item["progress"], min(fraction, 0.95))
            item["status"] = "downloading"

        elif status == "finished":
            item["progress"] = 0.97
            item["status"] = "downloading"

        _update_job_progress(job_id)

    return hook


def create_postprocessor_hook(job_id, index):
    def hook(data):
        job = jobs.get(job_id)

        if not job:
            return

        item = job["items"][index]
        status = data.get("status")

        if status == "started":
            item["progress"] = 0.98
        elif status == "finished":
            item["progress"] = 0.99

        _update_job_progress(job_id)

    return hook


# =========================================================
# YT-DLP
# =========================================================

def common_ydl_options(output_folder, progress_hook, postprocessor_hook):
    options = {
        "outtmpl": str(output_folder / "%(title)s.%(id)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [progress_hook],
        "postprocessor_hooks": [postprocessor_hook],
        "quiet": True,
        "no_warnings": True,
        # El cliente "android" de YouTube suele recibir menos
        # verificaciones anti-bot que el cliente web por defecto,
        # lo que ayuda cuando se descarga desde una IP de datacenter.
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
    }

    if ACTIVE_COOKIES_FILE and Path(ACTIVE_COOKIES_FILE).exists():
        options["cookiefile"] = ACTIVE_COOKIES_FILE

    if YTDLP_PROXY:
        options["proxy"] = YTDLP_PROXY

    return options


def download_audio(url, output_folder, progress_hook, postprocessor_hook):
    options = common_ydl_options(output_folder, progress_hook, postprocessor_hook)

    options.update({
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
    })

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


def download_video(url, output_folder, progress_hook, postprocessor_hook):
    options = common_ydl_options(output_folder, progress_hook, postprocessor_hook)

    options.update({
        "format": (
            "bestvideo[ext=mp4][vcodec^=avc1]"
            "+bestaudio[ext=m4a]"
            "/best[ext=mp4][vcodec^=avc1]"
        ),
        "merge_output_format": "mp4",
    })

    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])


# =========================================================
# PROCESAR TRABAJO (cola de descargas)
#
# Se procesan de a MAX_CONCURRENT_DOWNLOADS a la vez. Con el
# default de 1, es una cola secuencial pura: cada video espera
# a que termine el anterior.
# =========================================================

def _download_one(job_id, index, url, download_type, output_folder):
    job = jobs[job_id]

    progress_hook = create_progress_hook(job_id, index)
    postprocessor_hook = create_postprocessor_hook(job_id, index)

    try:
        if download_type == "video":
            download_video(url, output_folder, progress_hook, postprocessor_hook)
        else:
            download_audio(url, output_folder, progress_hook, postprocessor_hook)

        job["items"][index]["status"] = "finished"
        job["items"][index]["progress"] = 1.0
        return True, None

    except Exception as error:
        friendly_error = friendly_download_error(error)
        raw_message = str(error).strip().splitlines()[-1] if str(error).strip() else ""

        print(f"Error descargando {url}: {error}", flush=True)

        # Se agrega un fragmento del error real (acotado) para que se
        # pueda diagnosticar el problema sin tener que entrar a los
        # logs del servidor.
        detailed_error = friendly_error
        if raw_message:
            detailed_error += f" (detalle: {raw_message[:200]})"

        job["items"][index]["status"] = "error"
        job["items"][index]["progress"] = 1.0
        job["items"][index]["error"] = detailed_error
        return False, detailed_error

    finally:
        _update_job_progress(job_id)


def process_job(job_id, urls, download_type, temp_directory):
    job = jobs[job_id]

    try:
        output_folder = temp_directory / "downloads"
        output_folder.mkdir()

        total = len(urls)

        job["items"] = {
            index: {
                "title": None,
                "progress": 0,
                "status": "pending",
                "error": None,
            }
            for index in range(1, total + 1)
        }

        job["message"] = f"Iniciando {total} descarga(s)..."

        successful = 0
        failed = 0
        errors = []

        # Varias descargas en paralelo, limitadas por
        # MAX_CONCURRENT_DOWNLOADS para no saturar la red/CPU
        # ni provocar que YouTube limite las solicitudes.
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as executor:
            futures = {
                executor.submit(
                    _download_one, job_id, index, url, download_type, output_folder
                ): index
                for index, url in enumerate(urls, start=1)
            }

            for future in as_completed(futures):
                ok, error = future.result()

                if ok:
                    successful += 1
                else:
                    failed += 1
                    if error:
                        errors.append(error)

        expected_extension = ".mp4" if download_type == "video" else ".mp3"

        files = sorted(
            file
            for file in output_folder.iterdir()
            if file.is_file() and file.suffix.lower() == expected_extension
        )

        if not files:
            job["status"] = "error"
            job["progress"] = 0
            job["message"] = errors[-1] if errors else "No se pudo descargar ningún archivo."
            return

        if total == 1:
            result_file = files[0]
        else:
            zip_name = "videos.zip" if download_type == "video" else "audios.zip"
            result_file = temp_directory / zip_name

            job["message"] = "Preparando archivo ZIP..."
            job["progress"] = 99

            with zipfile.ZipFile(result_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for file in files:
                    zip_file.write(file, arcname=file.name)

        job["result_file"] = str(result_file)
        job["successful"] = successful
        job["failed"] = failed
        job["progress"] = 100
        job["status"] = "finished"

        if failed:
            job["message"] = (
                f"Listo: {successful} archivo(s) descargado(s) y {failed} con error."
            )
        else:
            job["message"] = "¡Listo! Descarga preparada correctamente."

    except Exception as error:
        print(error)
        job["status"] = "error"
        job["progress"] = 0
        job["message"] = friendly_download_error(error)


# =========================================================
# RUTAS
# =========================================================

@app.route("/")
@requires_auth
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
@requires_auth
def start_download():
    cleanup_old_jobs()

    if shutil.which("ffmpeg") is None:
        return jsonify({
            "error": (
                "FFmpeg no está disponible en PATH. "
                "Instálalo o reinicia la consola si acabas de instalarlo."
            )
        }), 400

    if shutil.which("deno") is None:
        return jsonify({
            "error": (
                "Deno no está disponible en PATH. "
                "Instálalo y reinicia la consola antes de continuar."
            )
        }), 400

    if COOKIES_FILE and not Path(COOKIES_FILE).exists():
        # No bloqueamos la descarga (algunos videos no requieren
        # sesión iniciada), pero avisamos en el log del servidor.
        print(
            f"Aviso: no se encontró {COOKIES_FILE}. "
            "Los videos que requieran sesión iniciada fallarán."
        )

    uploaded_file = request.files.get("file")
    direct_urls = request.form.get("urls", "")
    download_type = request.form.get("format")

    urls = []

    if direct_urls.strip():
        urls.extend(extract_urls(direct_urls))

    if uploaded_file and uploaded_file.filename:
        try:
            urls.extend(read_uploaded_file(uploaded_file))
        except Exception as error:
            return jsonify({"error": str(error)}), 400

    urls = list(dict.fromkeys(urls))

    if not urls:
        return jsonify({
            "error": (
                "No se encontraron enlaces válidos de YouTube. "
                "Pega un enlace o sube un archivo TXT, DOCX o XLSX."
            )
        }), 400

    if download_type not in ("video", "audio"):
        return jsonify({"error": "Formato no válido."}), 400

    job_id = str(uuid.uuid4())
    temp_directory = Path(tempfile.mkdtemp())

    with jobs_lock:
        jobs[job_id] = {
            "status": "processing",
            "progress": 0,
            "message": "Iniciando...",
            "total": len(urls),
            "items": {},
            "result_file": None,
            "temp_directory": str(temp_directory),
            "created_at": time.time(),
            "successful": 0,
            "failed": 0,
        }

    thread = threading.Thread(
        target=process_job,
        args=(job_id, urls, download_type, temp_directory),
        daemon=True,
    )

    thread.start()

    return jsonify({"job_id": job_id, "total": len(urls)})


@app.route("/progress/<job_id>")
@requires_auth
def progress(job_id):
    job = jobs.get(job_id)

    if not job:
        return jsonify({"error": "Trabajo no encontrado."}), 404

    done = sum(
        1 for item in job.get("items", {}).values()
        if item["status"] in ("finished", "error")
    )

    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
        "current": done,
        "total": job["total"],
        "successful": job.get("successful", 0),
        "failed": job.get("failed", 0),
    })


@app.route("/file/<job_id>")
@requires_auth
def download_file(job_id):
    job = jobs.get(job_id)

    if not job:
        return "Trabajo no encontrado.", 404

    if job["status"] != "finished":
        return "El archivo todavía no está preparado.", 400

    result_file = Path(job["result_file"])

    if not result_file.exists():
        return "Archivo no encontrado.", 404

    response = send_file(
        result_file,
        as_attachment=True,
        download_name=result_file.name,
    )

    def cleanup():
        temp_directory = job.get("temp_directory")

        if temp_directory:
            shutil.rmtree(temp_directory, ignore_errors=True)

        jobs.pop(job_id, None)

    response.call_on_close(cleanup)

    return response


if __name__ == "__main__":
    # host="0.0.0.0" para poder acceder desde otros dispositivos
    # de tu red (o desde internet si expones el puerto / usas un
    # túnel). Ver notas de despliegue más abajo en el chat.
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        threaded=True,
        use_reloader=False,
    )