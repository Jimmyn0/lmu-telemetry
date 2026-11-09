@echo off
rem Releve d'une course entiere : a lancer avant une course contre l'IA.
rem S'arrete tout seul apres 15 minutes de roulage, ou avec Ctrl+C.
cd /d "%~dp0"
.venv\Scripts\python.exe -m tools.sonde_live --roulage 900 %*
pause
