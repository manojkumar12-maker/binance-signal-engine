# ============================================================
# WINDOWS POWERSHELL ONE-CLICK DEPLOYMENT
# ============================================================
# Run this in PowerShell as Administrator
# Right-click PowerShell → Run as Administrator
# Then run: .\deploy-aws.ps1
# ============================================================

#Requires -RunAsAdministrator

# Colors
$Green = "`e[32m"
$Red = "`e[31m"
$Yellow = "`e[33m"
$Blue = "`e[34m"
$Reset = "`e[0m"

function Write-Log($message) {
    Write-Host "$Green[$(Get-Date -Format 'HH:mm:ss')]$Reset $message"
}

function Write-Error($message) {
    Write-Host "$Red[ERROR]$Reset $message"
}

function Write-Warn($message) {
    Write-Host "$Yellow[WARNING]$Reset $message"
}

Clear-Host
Write-Host ""
Write-Host "============================================"
Write-Host "  BINANCE SIGNAL ENGINE - AWS DEPLOYMENT"
Write-Host "============================================"
Write-Host ""

# Check prerequisites
Write-Log "Checking prerequisites..."

# Check OpenSSH
$ssh = Get-Command ssh -ErrorAction SilentlyContinue
if (-not $ssh) {
    Write-Error "OpenSSH not found!"
    Write-Host "Installing OpenSSH..."
    Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
    Write-Log "OpenSSH installed. Please restart PowerShell and try again."
    pause
    exit
}

Write-Log "✅ OpenSSH found"

# Get EC2 details
Write-Host ""
Write-Host "Enter your EC2 details:"
Write-Host ""

$EC2_IP = Read-Host "EC2 Public IP (e.g., 3.85.123.45)"
if (-not $EC2_IP) {
    Write-Error "IP address is required!"
    pause
    exit
}

$KEY_PATH = Read-Host "Path to .pem file (e.g., C:\Users\You\Downloads\key.pem)"
if (-not $KEY_PATH) {
    Write-Error "Key path is required!"
    pause
    exit
}

if (-not (Test-Path $KEY_PATH)) {
    Write-Error "Key file not found: $KEY_PATH"
    pause
    exit
}

Write-Host ""
Write-Host "============================================"
Write-Host "  CONFIGURATION"
Write-Host "============================================"
Write-Host "  EC2 IP: $EC2_IP"
Write-Host "  Key:    $KEY_PATH"
Write-Host "  User:   ubuntu"
Write-Host "============================================"
Write-Host ""

$CONFIRM = Read-Host "Proceed with deployment? (Y/N)"
if ($CONFIRM -ne 'Y' -and $CONFIRM -ne 'y') {
    Write-Host "Deployment cancelled."
    pause
    exit
}

Write-Host ""
Write-Log "[1/3] Connecting to EC2 instance..."
Write-Host ""

# Create temporary script
$TEMP_SCRIPT = "$env:TEMP\ec2-deploy.sh"
@"
#!/bin/bash
echo "Starting one-click deployment..."
curl -fsSL https://raw.githubusercontent.com/manojkumar12-maker/binance-signal-engine/master/deploy/aws/one-click-deploy.sh | bash
"@ | Out-File -FilePath $TEMP_SCRIPT -Encoding utf8

Write-Log "[2/3] Copying deployment script to server..."

# Copy script to EC2
$SCP_RESULT = scp -i "$KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$TEMP_SCRIPT" "ubuntu@${EC2_IP}:/tmp/deploy.sh" 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to copy files to EC2!"
    Write-Host $SCP_RESULT
    pause
    exit
}

Write-Log "[3/3] Running deployment script..."
Write-Host "This will take 5-10 minutes. Please wait..."
Write-Host ""

# Run deployment script
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "ubuntu@$EC2_IP" "bash /tmp/deploy.sh"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Error "Deployment failed!"
    Write-Host ""
    pause
    exit
}

Write-Host ""
Write-Host "============================================"
Write-Host "  DEPLOYMENT COMPLETE!"
Write-Host "============================================"
Write-Host ""
Write-Host "  Your app is running at:"
Write-Host "  http://$EC2_IP"
Write-Host "  http://${EC2_IP}:8080"
Write-Host ""
Write-Host "  Health Check:"
Write-Host "  http://$EC2_IP/health"
Write-Host ""
Write-Host "  IMPORTANT: Edit .env file:"
Write-Host "  ssh -i "$KEY_PATH" ubuntu@$EC2_IP"
Write-Host "  nano ~/binance-signal-engine/.env"
Write-Host ""
Write-Host "  Then restart:"
Write-Host "  sudo systemctl restart binance-signal"
Write-Host ""
Write-Host "  Update dashboard API URL to:"
Write-Host "  http://${EC2_IP}:8080/api"
Write-Host ""
Write-Host "============================================"
Write-Host ""

pause
