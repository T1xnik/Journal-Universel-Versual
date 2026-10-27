@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title StudentHub - сборка EXE

set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys; print(sys.version)" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if not defined PY (
    echo ОШИБКА: Python 3.11–3.14 не найден через команду py.
    echo Установи Python и включи Python Launcher, затем запусти файл снова.
    pause
    exit /b 1
)

echo Используется: %PY%
%PY% -m pip install --upgrade pip
if errorlevel 1 goto fail
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto fail

if exist build rmdir /s /q build
if exist "dist\StudentHub" rmdir /s /q "dist\StudentHub"
if not exist "StudentHub.pyw" (echo ОШИБКА: не найден StudentHub.pyw.& goto fail)
if not exist "StudentHub.ico" (echo ОШИБКА: не найден StudentHub.ico.& goto fail)

%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name StudentHub --icon "StudentHub.ico" --add-data "StudentHub.ico;." --collect-all PySide6 --collect-all shiboken6 --collect-all top_academy_api --collect-all httpx --collect-all pydantic --hidden-import qasync --exclude-module numpy --exclude-module scipy --exclude-module pandas --exclude-module matplotlib "StudentHub.pyw"
if errorlevel 1 goto fail
if not exist "dist\StudentHub\StudentHub.exe" (echo ОШИБКА: PyInstaller завершился, но EXE не найден.& goto fail)
echo.
echo ГОТОВО: "%CD%\dist\StudentHub\StudentHub.exe"
echo Переноси всю папку dist\StudentHub целиком, не один EXE.
explorer "%CD%\dist\StudentHub"
pause
exit /b 0

:fail
echo.
echo СБОРКА НЕ УДАЛАСЬ. Смотри текст ошибки выше и пришли скриншот.
pause
exit /b 1
