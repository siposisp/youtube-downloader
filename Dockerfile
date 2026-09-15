FROM python:3.11-slim

# ffmpeg: requerido por yt-dlp para convertir/mux audio y video.
# curl + unzip: necesarios para instalar Deno.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Deno: requerido por yt-dlp para resolver el JS de YouTube.
ENV DENO_INSTALL="/usr/local"
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="/usr/local/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render inyecta la variable PORT; el comando de arranque la usa.
# Un solo worker: el estado de los trabajos (jobs) vive en memoria
# de un único proceso, no se comparte entre workers. --threads
# permite atender varias requests (ej. polling de progreso) mientras
# la descarga corre en el hilo de fondo.
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 1 --threads 8 --timeout 0 app:app
