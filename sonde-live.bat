@echo off
rem Diagnostic de la memoire partagee : a lancer avant d'aller en piste.
rem S'arrete tout seul apres 5 minutes de roulage.
cd /d "%~dp0"
.venv\Scripts\python.exe -m tools.sonde_live %*
pause
