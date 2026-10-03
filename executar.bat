@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Criando o ambiente virtual...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo.
        echo Erro ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo Instalando as dependencias...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Erro ao instalar as dependencias.
    pause
    exit /b 1
)

echo Iniciando o launcher...
".venv\Scripts\python.exe" src\launcher.py

endlocal
