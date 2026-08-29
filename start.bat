@echo off
title Anime MP3 Formatter - Launcher
cd /d "%~dp0"

echo ============================================
echo   Anime MP3 Formatter - arrancando...
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encuentra "python" en el PATH. Instala Python 3.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] No se encuentra "npm" en el PATH. Instala Node.js.
    pause
    exit /b 1
)

if not exist "backend\venv\Scripts\python.exe" (
    echo [setup] Creando entorno virtual de Python...
    python -m venv "backend\venv"
    if errorlevel 1 goto :fail
    echo [setup] Instalando dependencias del backend...
    "backend\venv\Scripts\python.exe" -m pip install --upgrade pip
    "backend\venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
    if errorlevel 1 goto :fail
)

if not exist "frontend\node_modules" (
    echo [setup] Instalando dependencias del frontend...
    pushd frontend
    call npm install
    popd
    if errorlevel 1 goto :fail
)

echo.
echo [run] Backend  -^> http://localhost:5000
start "Anime MP3 - Backend" /d "%~dp0backend" cmd /k venv\Scripts\python.exe app.py

echo [run] Frontend -^> http://localhost:5173
start "Anime MP3 - Frontend" /d "%~dp0frontend" cmd /k npm run dev

echo.
echo [wait] Esperando a que arranque el frontend...
timeout /t 8 /nobreak >nul

echo [open] Abriendo el navegador...
start "" http://localhost:5173

echo.
echo Listo. Cierra las ventanas "Backend" y "Frontend" para parar los servidores.
timeout /t 5 /nobreak >nul
exit /b 0

:fail
echo.
echo [ERROR] Fallo durante la instalacion. Revisa los mensajes de arriba.
pause
exit /b 1
