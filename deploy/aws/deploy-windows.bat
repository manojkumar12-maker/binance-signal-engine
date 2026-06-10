@echo off
REM ============================================================
REM WINDOWS ONE-CLICK EC2 DEPLOYMENT
REM ============================================================
REM This script automatically SSHs into your EC2 and runs the
REM one-click deployment script
REM 
REM Prerequisites:
REM 1. AWS EC2 instance created
REM 2. Key pair downloaded (.pem file)
REM 3. EC2 Public IP address
REM 4. PuTTY or OpenSSH installed
REM ============================================================

title Binance Signal Engine - EC2 Deploy
color 0A

echo.
echo  ============================================
echo   BINANCE SIGNAL ENGINE - ONE-CLICK DEPLOY
echo  ============================================
echo.

REM Check for SSH client
where ssh >nul 2>nul
if %errorlevel% == 0 (
    echo [OK] OpenSSH found
    set SSH_CLIENT=openssh
) else (
    where plink >nul 2>nul
    if %errorlevel% == 0 (
        echo [OK] PuTTY found
        set SSH_CLIENT=putty
    ) else (
        echo [ERROR] No SSH client found!
        echo Please install OpenSSH or PuTTY:
        echo   - OpenSSH: Settings ^> Apps ^> Optional Features ^> OpenSSH Client
        echo   - PuTTY: https://www.chiark.greenend.org.uk/~sgtatham/putty/
        pause
        exit /b 1
    )
)

REM Get user input
echo.
echo Enter your EC2 details:
echo.

set /p EC2_IP="EC2 Public IP (e.g., 3.85.123.45): "
if "%EC2_IP%"=="" (
    echo [ERROR] IP address is required!
    pause
    exit /b 1
)

set /p KEY_PATH="Path to .pem file (e.g., C:\Users\You\Downloads\key.pem): "
if "%KEY_PATH%"=="" (
    echo [ERROR] Key path is required!
    pause
    exit /b 1
)

if not exist "%KEY_PATH%" (
    echo [ERROR] Key file not found: %KEY_PATH%
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   CONFIGURATION
echo  ============================================
echo   EC2 IP: %EC2_IP%
echo   Key:    %KEY_PATH%
echo   User:   ubuntu
echo  ============================================
echo.

set /p CONFIRM="Proceed with deployment? (Y/N): "
if /I not "%CONFIRM%"=="Y" (
    echo Deployment cancelled.
    pause
    exit /b 0
)

echo.
echo [1/3] Connecting to EC2 instance...
echo.

REM Create temporary script to run on server
set TEMP_SCRIPT=%TEMP%\ec2-deploy-cmd.sh
echo #!/bin/bash > "%TEMP_SCRIPT%"
echo echo "Starting one-click deployment..." >> "%TEMP_SCRIPT%"
echo curl -fsSL https://raw.githubusercontent.com/manojkumar12-maker/binance-signal-engine/master/deploy/aws/one-click-deploy.sh ^| bash >> "%TEMP_SCRIPT%"

if "%SSH_CLIENT%"=="openssh" (
    echo [2/3] Using OpenSSH...
    echo.
    echo Copying deployment script to server...
    scp -i "%KEY_PATH%" -o StrictHostKeyChecking=no "%TEMP_SCRIPT%" ubuntu@%EC2_IP%:/tmp/deploy.sh
    
    echo.
    echo Running deployment script...
    echo This will take 5-10 minutes. Please wait...
    echo.
    ssh -i "%KEY_PATH%" -o StrictHostKeyChecking=no ubuntu@%EC2_IP% "bash /tmp/deploy.sh"
    
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Deployment failed!
        echo.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Using PuTTY...
    echo.
    echo Please run these commands manually in PuTTY:
    echo.
    echo   curl -fsSL https://raw.githubusercontent.com/manojkumar12-maker/binance-signal-engine/master/deploy/aws/one-click-deploy.sh ^| bash
    echo.
    pause
    exit /b 0
)

echo.
echo  ============================================
echo   DEPLOYMENT COMPLETE!
echo  ============================================
echo.
echo   Your app is running at:
echo   http://%EC2_IP%
echo   http://%EC2_IP%:8080
 echo.
echo   Health Check:
echo   http://%EC2_IP%/health
 echo.
echo   IMPORTANT: Edit .env file:
echo   ssh -i "%KEY_PATH%" ubuntu@%EC2_IP%
echo   nano ~/binance-signal-engine/.env
 echo.
echo   Then restart:
echo   sudo systemctl restart binance-signal
 echo.
echo   Update dashboard API URL to:
echo   http://%EC2_IP%:8080/api
 echo.
pause
