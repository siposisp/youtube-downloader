# YouTube Downloader

A Flask web application for downloading YouTube videos or extracting audio from one or multiple links. Links can be pasted directly into the interface or loaded from TXT, DOCX, or XLSX files.

The application shows download progress, returns a single file when only one link is processed, and creates a ZIP archive when multiple links are processed.

> Use this tool only for content you own, content in the public domain, or content you are authorized to download.

## Features

- Video downloads using the best quality available to `yt-dlp`.
- Audio extraction to MP3.
- Support for one or multiple links.
- Link input from:
  - pasted text;
  - `.txt` files;
  - `.docx` documents;
  - `.xlsx` spreadsheets.
- Automatic YouTube URL normalization.
- Download progress shown in the web interface.
- Direct file download when only one result is generated.
- Automatic `videos.zip` or `audios.zip` creation when multiple results are generated.
- Configurable download concurrency.
- Optional HTTP Basic authentication.
- Optional `cookies.txt` support.
- Optional proxy support through environment variables.
- Local Windows execution or Docker deployment.

## Tech Stack

- Python
- Flask
- yt-dlp
- FFmpeg
- Deno
- python-docx
- openpyxl
- Docker

## Project Structure

A typical project layout looks like this:

```text
youtube-downloader/
├── app.py
├── requirements.txt
├── Dockerfile
├── .dockerignore
├── templates/
│   └── index.html
└── cookies.txt          # optional; never commit this file
```

If the Windows one-click launcher is used, the project can also be distributed like this:

```text
youtube-downloader-launcher/
├── iniciar.bat
└── downloader/
    ├── app.py
    ├── requirements.txt
    ├── Dockerfile
    └── templates/
        └── index.html
```

## Quick Start on Windows

The recommended option for end users is to use `iniciar.bat`.

Double-click:

```text
iniciar.bat
```

The launcher automatically checks whether the following components are available:

- Python;
- FFmpeg;
- Deno;
- the `.venv` virtual environment;
- the dependencies listed in `requirements.txt`.

Already installed components are not installed again. If `requirements.txt` changes, Python dependencies are updated automatically.

Once setup is complete, the application starts and opens:

```text
http://127.0.0.1:5000
```

### Launcher Requirement

The Windows machine must have `winget` available. On modern Windows 10 and Windows 11 installations, it is usually provided through Microsoft's **App Installer**.

## Manual Installation

### 1. Clone the repository

```bash
git clone https://github.com/siposisp/youtube-downloader.git
cd youtube-downloader
```

### 2. Create a virtual environment

Windows:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Install FFmpeg

FFmpeg must be available in `PATH`.

On Windows:

```cmd
winget install --id Gyan.FFmpeg -e
```

Verify the installation:

```cmd
ffmpeg -version
```

### 5. Install Deno

On Windows:

```cmd
winget install --id DenoLand.Deno -e
```

Verify the installation:

```cmd
deno --version
```

### 6. Run the application

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Usage

### Download from pasted links

1. Open the application.
2. Paste one or more YouTube links.
3. If you enter multiple links, place one link per line.
4. Choose:
   - **Video**, or
   - **Audio MP3**.
5. Click **Download**.
6. Wait for the progress bar to finish.

If only one link is processed, the browser downloads the resulting file directly.

If multiple links are processed, the application creates:

```text
videos.zip
```

or:

```text
audios.zip
```

depending on the selected format.

### Download from a file

You can also upload:

```text
.txt
.docx
.xlsx
```

The application automatically extracts supported YouTube links from the file.

The maximum upload size for the input file is 10 MB.

## Video Quality

The application should allow `yt-dlp` to select the best available video stream and best available audio stream, then merge them using FFmpeg.

The actual maximum quality depends on the formats YouTube exposes for a specific video, the active session, the YouTube client selected by `yt-dlp`, and current platform restrictions.

To inspect the formats available for a video:

```bash
python -m yt_dlp -F "VIDEO_URL"
```

If you use cookies:

```bash
python -m yt_dlp --cookies cookies.txt -F "VIDEO_URL"
```

If 1080p, 1440p, or 2160p formats appear in the list but the application downloads a lower resolution, review the `format` configuration inside `download_video()`.

If high-resolution formats do not appear in `-F`, the limitation happens before FFmpeg processing: those formats are not being exposed to `yt-dlp` for that session.

A recommended format selector for maximum available quality is:

```python
"format": "bv*+ba/b"
```

This lets `yt-dlp` prioritize the best available video and audio streams without forcing a specific codec or container before quality selection.

> Higher resolutions may use VP9 or AV1 instead of H.264. These codecs preserve the original available quality but may not be supported by older media players.

## YouTube Cookies

Some content may require authentication.

The application supports a Netscape-format cookie file:

```text
cookies.txt
```

By default, the project looks for it in the project root.

You can define a different path with:

```text
COOKIES_FILE
```

> **Important:** `cookies.txt` contains session information. Never commit it to GitHub or distribute it with the project.

Add this to `.gitignore`:

```gitignore
cookies.txt
.venv/
__pycache__/
*.pyc
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `COOKIES_FILE` | Path to the cookies file | `cookies.txt` |
| `MAX_CONCURRENT_DOWNLOADS` | Maximum number of simultaneous downloads | `1` |
| `APP_USERNAME` | HTTP Basic authentication username | unset |
| `APP_PASSWORD` | HTTP Basic authentication password | unset |
| `YTDLP_PROXY` | Optional proxy used by yt-dlp | unset |
| `PORT` | Flask HTTP port | `5000` |

If both `APP_USERNAME` and `APP_PASSWORD` are defined, the website requires authentication before use.

## Local Network Access

The application listens on:

```text
0.0.0.0
```

This allows other devices on the same local network to access it using the host computer's local IP address:

```text
http://192.168.1.X:5000
```

You may need to allow Python or port `5000` through Windows Firewall.

## Docker

The repository includes a `Dockerfile`.

Build the image:

```bash
docker build -t youtube-downloader .
```

Run it:

```bash
docker run --rm -p 5000:5000 youtube-downloader
```

Then open:

```text
http://localhost:5000
```

For public deployments, use authentication and manage cookies through secrets. Never bake session cookies or passwords into the Docker image or repository.

## Troubleshooting

### `FFmpeg is not available in PATH`

Check:

```bash
ffmpeg -version
```

If FFmpeg was just installed, close and reopen the terminal.

### `Deno is not available in PATH`

Check:

```bash
deno --version
```

### `HTTP Error 429: Too Many Requests`

YouTube is temporarily rate-limiting requests. Reduce the number of simultaneous downloads and try again later.

### `Sign in to confirm you're not a bot`

The session may require authentication, or the cookies may have expired. If you use `cookies.txt`, export a new valid session.

### Video downloads at low resolution

First inspect the formats visible to `yt-dlp`:

```bash
python -m yt_dlp -F "VIDEO_URL"
```

If high-resolution formats are listed, check the application's format selector.

If they are not listed, the quality limitation is upstream of the application and FFmpeg cannot recreate a higher-resolution source.

## Security

- Never commit `cookies.txt`.
- Never hard-code passwords into the source code.
- Use environment variables for credentials.
- Do not run Flask with `debug=True` on a public server.
- Protect the application with authentication when exposing it to the Internet.

## License and Usage

This project is intended for personal and educational use. Users are responsible for complying with copyright law, platform terms of service, and any other applicable regulations.
