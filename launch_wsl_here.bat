@echo off
REM Simple WSL launcher - drops you in the current folder in Ubuntu
set "CURRENT=%CD%"
set "WSLPATH=%CURRENT:C:=/mnt/c%"
set "WSLPATH=%WSLPATH:\=/%"

echo Opening WSL Ubuntu-22.04 in: %WSLPATH%
wsl -d Ubuntu-22.04 --cd "%WSLPATH%"