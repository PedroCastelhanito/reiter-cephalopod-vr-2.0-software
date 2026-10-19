@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b %errorlevel%
.venv\Scripts\python.exe -m pytest tests/controller/test_microcontroller_firmware.py -q
