@echo off
cd /d "%~dp0"
python generate_code.py
echo.
echo Codes above. This window will close soon, copy them first.
pause >nul
