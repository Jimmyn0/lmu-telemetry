@echo off
rem Construit le .exe a partager : double-clic sur ce fichier.
rem Tout le travail, pause finale comprise, est fait par tools\construire_exe.py.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo L'environnement Python du projet est absent.
  echo Fais d'abord l'installation decrite dans LISEZ-MOI.md, section Installation.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" tools\construire_exe.py
