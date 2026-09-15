@echo off
setlocal EnableExtensions EnableDelayedExpansion
title YouTube Downloader

REM ============================================================
REM UBICACION DEL PROYECTO
REM ============================================================

set "PROJECT_DIR=%~dp0downloader"

if not exist "%PROJECT_DIR%" (
    echo.
    echo [ERROR] No se encontro la carpeta:
    echo %PROJECT_DIR%
    echo.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

echo.
echo ============================================
echo        YOUTUBE DOWNLOADER - INICIO
echo ============================================
echo.


REM ============================================================
REM 1. COMPROBAR WINGET
REM ============================================================

where winget >nul 2>&1

if errorlevel 1 (
    echo [ERROR] No se encontro winget.
    echo.
    echo Instala "App Installer" desde Microsoft Store
    echo y vuelve a ejecutar iniciar.bat.
    echo.
    pause
    exit /b 1
)


REM ============================================================
REM 2. BUSCAR PYTHON
REM ============================================================

call :find_python

if not defined PYTHON_EXE (

    echo [INFO] Python no esta instalado.
    echo [INFO] Instalando Python 3.12...

    winget install ^
        --id Python.Python.3.12 ^
        -e ^
        --scope user ^
        --accept-package-agreements ^
        --accept-source-agreements

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar Python.
        pause
        exit /b 1
    )

    call :refresh_path
    call :find_python

    if not defined PYTHON_EXE (
        echo.
        echo [ERROR] Python fue instalado,
        echo pero todavia no se pudo localizar.
        echo.
        echo Cierra esta ventana y vuelve
        echo a ejecutar iniciar.bat.
        echo.
        pause
        exit /b 1
    )

) else (

    echo [OK] Python encontrado:
    "%PYTHON_EXE%" --version

)


REM ============================================================
REM 3. COMPROBAR FFMPEG
REM ============================================================

ffmpeg -version >nul 2>&1

if errorlevel 1 (

    echo.
    echo [INFO] FFmpeg no esta instalado.
    echo [INFO] Instalando FFmpeg...

    winget install ^
        --id Gyan.FFmpeg ^
        -e ^
        --accept-package-agreements ^
        --accept-source-agreements

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar FFmpeg.
        pause
        exit /b 1
    )

    call :refresh_path

    ffmpeg -version >nul 2>&1

    if errorlevel 1 (
        echo.
        echo [ERROR] FFmpeg fue instalado,
        echo pero aun no aparece en PATH.
        echo.
        echo Cierra esta ventana y vuelve
        echo a ejecutar iniciar.bat.
        echo.
        pause
        exit /b 1
    )

) else (

    echo [OK] FFmpeg encontrado.

)


REM ============================================================
REM 4. COMPROBAR DENO
REM ============================================================

deno --version >nul 2>&1

if errorlevel 1 (

    echo.
    echo [INFO] Deno no esta instalado.
    echo [INFO] Instalando Deno...

    winget install ^
        --id DenoLand.Deno ^
        -e ^
        --scope user ^
        --accept-package-agreements ^
        --accept-source-agreements

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar Deno.
        pause
        exit /b 1
    )

    call :refresh_path

    deno --version >nul 2>&1

    if errorlevel 1 (
        echo.
        echo [ERROR] Deno fue instalado,
        echo pero aun no aparece en PATH.
        echo.
        echo Cierra esta ventana y vuelve
        echo a ejecutar iniciar.bat.
        echo.
        pause
        exit /b 1
    )

) else (

    echo [OK] Deno encontrado.

)


REM ============================================================
REM 5. COMPROBAR REQUIREMENTS
REM ============================================================

if not exist "%PROJECT_DIR%\requirements.txt" (

    echo.
    echo [ERROR] No se encontro:
    echo %PROJECT_DIR%\requirements.txt
    echo.

    pause
    exit /b 1
)


REM ============================================================
REM 6. CREAR ENTORNO VIRTUAL
REM ============================================================

set "VENV_PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "VENV_CREATED=0"

if not exist "%VENV_PYTHON%" (

    echo.
    echo [INFO] Creando entorno virtual...

    "%PYTHON_EXE%" -m venv "%PROJECT_DIR%\.venv"

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )

    set "VENV_CREATED=1"

) else (

    echo [OK] Entorno virtual existente.

)


REM ============================================================
REM 7. ACTUALIZAR PIP LA PRIMERA VEZ
REM ============================================================

if "!VENV_CREATED!"=="1" (

    echo.
    echo [INFO] Actualizando pip...

    "%VENV_PYTHON%" -m pip install --upgrade pip

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo actualizar pip.
        pause
        exit /b 1
    )

)


REM ============================================================
REM 8. COMPROBAR SI REQUIREMENTS CAMBIO
REM ============================================================

set "REQ_HASH="

for /f %%H in ('
    powershell -NoProfile -Command ^
    "(Get-FileHash -Algorithm SHA256 -LiteralPath '%PROJECT_DIR%\requirements.txt').Hash"
') do (
    set "REQ_HASH=%%H"
)

set "HASH_FILE=%PROJECT_DIR%\.venv\.requirements.sha256"
set "OLD_HASH="

if exist "%HASH_FILE%" (
    set /p OLD_HASH=<"%HASH_FILE%"
)


if /I not "!REQ_HASH!"=="!OLD_HASH!" (

    echo.
    echo [INFO] Instalando/actualizando dependencias...

    "%VENV_PYTHON%" -m pip install ^
        -r "%PROJECT_DIR%\requirements.txt"

    if errorlevel 1 (
        echo.
        echo [ERROR] Fallo la instalacion de dependencias.
        pause
        exit /b 1
    )

    >"%HASH_FILE%" echo !REQ_HASH!

    echo [OK] Dependencias instaladas.

) else (

    echo [OK] Las dependencias ya estan instaladas.

)


REM ============================================================
REM 9. COMPROBAR APP.PY
REM ============================================================

if not exist "%PROJECT_DIR%\app.py" (

    echo.
    echo [ERROR] No se encontro app.py.
    echo.

    pause
    exit /b 1
)


REM ============================================================
REM 10. INICIAR
REM ============================================================

echo.
echo ============================================
echo              TODO LISTO
echo ============================================
echo.

echo Abriendo YouTube Downloader...
echo.
echo http://127.0.0.1:5000
echo.
echo Para cerrar el programa usa CTRL+C.
echo.


REM Abrir navegador despues de 2 segundos
start "" cmd /c ^
"timeout /t 2 /nobreak >nul & start "" http://127.0.0.1:5000"


REM Ejecutar Flask
set PYTHONUNBUFFERED=1

"%VENV_PYTHON%" "%PROJECT_DIR%\app.py"


echo.
echo La aplicacion se ha detenido.
pause

exit /b 0



REM ============================================================
REM FUNCIONES
REM ============================================================

:find_python

set "PYTHON_EXE="

where py >nul 2>&1

if not errorlevel 1 (

    for /f "delims=" %%P in (
        'py -3 -c "import sys; print(sys.executable)" 2^>nul'
    ) do (
        set "PYTHON_EXE=%%P"
    )

)

if defined PYTHON_EXE goto :eof


where python >nul 2>&1

if not errorlevel 1 (

    for /f "delims=" %%P in (
        'python -c "import sys; print(sys.executable)" 2^>nul'
    ) do (
        set "PYTHON_EXE=%%P"
    )

)

goto :eof



:refresh_path

for /f "usebackq delims=" %%P in (
    `powershell -NoProfile -Command ^
    "[Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')"`
) do (
    set "PATH=%%P"
)

goto :eof