@echo off
REM ============================================================
REM  Lanceur Jarvis pour Windows.
REM  Contourne la PowerShell Execution Policy : les .ps1 telecharges
REM  (mark of the web) sont bloques par defaut, ce qui fait echouer
REM  ".\jarvis.ps1 ..." avec "l'execution de scripts est desactivee".
REM  Un .bat n'est PAS soumis a cette politique : il appelle jarvis.ps1
REM  en -ExecutionPolicy Bypass et transmet les arguments.
REM
REM  Usage :  jarvis.bat setup   |   jarvis.bat run   |   jarvis.bat api
REM ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0jarvis.ps1" %*
