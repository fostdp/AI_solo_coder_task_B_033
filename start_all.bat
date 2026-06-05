@echo off
chcp 65001
title 地下管廊综合监控系统 - 启动脚本

echo ========================================
echo 地下管廊综合监控与智能运维系统
echo ========================================
echo.

echo [1/5] 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python，请先安装Python 3.9+
    pause
    exit /b 1
)
echo [完成] Python环境正常

echo.
echo [2/5] 检查依赖...
cd /d "%~dp0backend"
python -c "import fastapi, uvicorn, motor, paho.mqtt, httpx" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 正在安装依赖...
    pip install -r requirements.txt
)
echo [完成] 依赖检查通过

echo.
echo [3/5] 正在启动各服务...
echo 请在新窗口中分别启动以下服务：
echo.

cd /d "%~dp0"

echo 正在启动短信模拟器...
start "短信模拟器" cmd /k "cd /d "%~dp0scripts" && python sms_simulator.py"
timeout /t 2 >nul

echo 正在启动MQTT PLC模拟器...
start "MQTT PLC模拟器" cmd /k "cd /d "%~dp0scripts" && python mqtt_plc_simulator.py"
timeout /t 2 >nul

echo 正在启动后端API服务...
start "后端API服务" cmd /k "cd /d "%~dp0backend" && python main.py"
timeout /t 3 >nul

echo 正在启动LoRa网关模拟器...
start "LoRa网关模拟器" cmd /k "cd /d "%~dp0scripts" && python lora_gateway_simulator.py"
timeout /t 2 >nul

echo.
echo [4/5] 正在启动前端服务器...
start "前端服务" cmd /k "cd /d "%~dp0frontend" && python -m http.server 8080"
timeout /t 2 >nul

echo.
echo ========================================
echo 所有服务启动完成！
echo ========================================
echo.
echo 访问地址：
echo   前端界面: http://localhost:8080
echo   API文档: http://localhost:8000/docs
echo   健康检查: http://localhost:8000/api/
echo.
echo 前置要求（如未启动请先启动）：
echo   1. MongoDB服务
echo   2. MQTT Broker (端口1883)
echo.
echo MongoDB初始化命令：
echo   cd mongodb
echo   mongo ^< init.js
echo.
pause
