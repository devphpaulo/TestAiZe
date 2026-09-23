@echo off
setlocal
set "ROOT=%~dp0"
set "APP=%ROOT%aplicativo\ExecutorLocal\ExecutorLocal.exe"
if not exist "%APP%" (
  echo O executavel nao foi encontrado. Descompacte o pacote completo.
  pause
  exit /b 1
)
"%APP%" --data-dir "%ROOT%." --backup
pause
