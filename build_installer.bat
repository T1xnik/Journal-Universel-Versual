@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title StudentHub - сборка установщика

echo Закрываю запущенный StudentHub (если открыт)...
taskkill /f /im StudentHub.exe >nul 2>nul
timeout /t 2 /nobreak >nul

set "PY="
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PY (
        py -%%V -c "import sys; print(sys.version)" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if not defined PY (
    echo ОШИБКА: Python 3.11–3.14 не найден через команду py.
    goto fail
)
echo Используется: %PY%
%PY% -m pip install --upgrade pip
if errorlevel 1 goto fail
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto fail

if exist build rmdir /s /q build
if exist "dist\StudentHub" rmdir /s /q "dist\StudentHub"
if exist "dist\StudentHub" (
    echo ОШИБКА: не удаётся очистить dist\StudentHub - папку что-то держит.
    echo Закрой Проводник в этой папке и StudentHub.exe, подожди минуту ^(антивирус^) или перезагрузи ПК, затем запусти снова.
    goto fail
)
if not exist "StudentHub.pyw" (echo ОШИБКА: не найден StudentHub.pyw.& goto fail)
if not exist "StudentHub.ico" (echo ОШИБКА: не найден StudentHub.ico.& goto fail)

%PY% -m PyInstaller --noconfirm --clean --onedir --windowed --name StudentHub --icon "StudentHub.ico" --add-data "StudentHub.ico;." --collect-all PySide6 --collect-all shiboken6 --collect-all top_academy_api --collect-all httpx --collect-all pydantic --hidden-import qasync --exclude-module numpy --exclude-module scipy --exclude-module pandas --exclude-module matplotlib "StudentHub.pyw"
if errorlevel 1 goto fail
if not exist "dist\StudentHub\StudentHub.exe" (echo ОШИБКА: PyInstaller завершился, но EXE не найден.& goto fail)

call :find_iscc
if not defined ISCC (
    where winget >nul 2>nul
    if not errorlevel 1 (
        echo Inno Setup не найден - устанавливаю через winget...
        winget install -e --id JRSoftware.InnoSetup --silent --accept-package-agreements --accept-source-agreements
        call :find_iscc
    )
)
if not defined ISCC (
    echo ОШИБКА: Inno Setup не найден. Скачай с https://jrsoftware.org/isdl.php , установи и запусти файл снова.
    goto fail
)

"%ISCC%" "StudentHub-Setup.iss"
if errorlevel 1 goto fail
echo.
echo ГОТОВО: "%CD%\installer_output\"
explorer "%CD%\installer_output"
pause
exit /b 0

:find_iscc
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe") do (
    if not defined ISCC if exist %%P set "ISCC=%%~P"
)
exit /b 0

:fail
echo.
echo СБОРКА НЕ УДАЛАСЬ. Смотри текст ошибки выше и пришли скриншот.
pause
exit /b 1
