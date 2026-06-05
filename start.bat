@echo off
chcp 65001 >nul
echo ============================================================
echo  地下管廊综合监控系统 - 一键启动脚本
echo ============================================================
echo.

where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Docker，请先安装Docker Desktop
    echo 下载地址: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Docker未运行，请先启动Docker Desktop
    pause
    exit /b 1
)

echo [1/5] 检查环境变量配置...
if not exist .env (
    echo   .env文件不存在，从.env.example复制...
    copy .env.example .env >nul
    echo   已创建 .env 文件
) else (
    echo   .env 文件已存在
)

echo.
echo [2/5] 检查Docker Compose版本...
docker compose version
echo.

echo [3/5] 停止已有服务（如果存在）...
docker compose down 2>nul
echo.

echo [4/5] 构建并启动所有服务（首次构建需要5-10分钟，请耐心等待）...
echo.
docker compose up -d --build

if %errorlevel% neq 0 (
    echo.
    echo [错误] 服务启动失败，请查看上方错误日志
    pause
    exit /b 1
)

echo.
echo [5/5] 等待服务就绪（约30-60秒）...
timeout /t 10 /nobreak >nul

echo.
echo ============================================================
echo  服务启动中，请等待30-60秒后访问以下地址:
echo ============================================================
echo.
echo  前端界面:      http://localhost:8080
echo  API文档:       http://localhost:8000/docs
echo  健康检查:      http://localhost:8000/api/health
echo  短信模拟器:    http://localhost:8001
echo.
echo ============================================================
echo  常用命令:
echo    docker compose ps          - 查看服务状态
echo    docker compose logs -f     - 查看实时日志
echo    docker compose down        - 停止所有服务
echo    docker compose down -v     - 停止并清除数据（谨慎使用）
echo ============================================================
echo.

choice /c YN /m "是否查看服务日志? [Y/N]"
if %errorlevel% equ 1 (
    docker compose logs -f
)

pause
