@echo off
setlocal
cd /d "%~dp0"

set "CFG=%~dp0scummvm.ini"
set "VOICES=%~dp0agitwo-voices"

if not exist "scummvm.exe" goto noscummvm
if not exist "game\RESOURCE.MAP" goto nogame

:menu
cls
echo.
echo   Quest for Glory I - Voiced Edition
echo.
echo   1. Play QFG1 Voiced
echo   2. Configure ScummVM  (graphics, audio, scalers)
echo   3. Exit
echo.
set "choice="
set /p choice=Select an option: 

if "%choice%"=="1" goto play
if "%choice%"=="2" goto configure
if "%choice%"=="3" goto end
goto menu

:play
scummvm.exe --config="%CFG%" --extrapath="%VOICES%" -p "game" --auto-detect
goto end

:configure
rem Make sure the game is listed in the launcher so per-game options can be set.
findstr /R /C:"^\[" "%CFG%" 2>nul | find /V /I "[scummvm]" >nul 2>&1
if errorlevel 1 scummvm.exe --config="%CFG%" --add -p "game" >nul 2>&1
scummvm.exe --config="%CFG%" --extrapath="%VOICES%"
goto menu

:nogame
echo.
echo   No Quest for Glory game files found.
echo.
echo   Copy your QFG1 EGA files into the "game" folder next to this launcher.
echo   It is the folder that contains RESOURCE.MAP and RESOURCE.000 to RESOURCE.004
echo.
echo   Steam: ...\Quest for Glory Collection\QG1\EGA
echo.
pause
goto end

:noscummvm
echo.
echo   scummvm.exe was not found.
echo.
echo   Make sure this BAT file is in the same folder as scummvm.exe.
echo.
pause

:end
endlocal
