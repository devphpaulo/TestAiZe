@echo off
setlocal
set "ROOT=%~dp0"
set "APP=%ROOT%aplicativo\ExecutorLocal\ExecutorLocal.exe"
if not exist "%APP%" (
  echo O executavel nao foi encontrado em:
  echo %APP%
  echo Descompacte o pacote completo antes de iniciar.
  pause
  exit /b 1
)
"%APP%" --data-dir "%ROOT%."
if errorlevel 1 pause
