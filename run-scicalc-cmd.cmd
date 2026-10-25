@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if errorlevel 1 goto missing_python

start "" pythonw.exe "%~dp0scicalc-cmd.pyw"
exit /b 0

:missing_python
echo [SciCalc CMD] 未找到 pythonw.exe。
echo 请先安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
pause
exit /b 1
