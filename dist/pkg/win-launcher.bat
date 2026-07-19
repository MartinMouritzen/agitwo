@echo off
cd /d "%~dp0"
if not exist "game\*.*" (
  echo.
  echo   Put your Quest for Glory 1 EGA files into the "game" folder next to this launcher,
  echo   then run this again.  (Steam: ...\Quest for Glory Collection\QG1\EGA )
  echo.
  pause
  exit /b
)
scummvm.exe --extrapath="%~dp0agitwo-voices" -p "game" --auto-detect
