#!/usr/bin/env bash

echo "Starting system setup for Windows"

# Check for Administrator privileges
net session >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Please run Git Bash as Administrator"
    exit 1
fi

# Check if Chocolatey is installed
if ! command -v choco >/dev/null 2>&1; then
    echo "Installing Chocolatey"

    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
        Set-ExecutionPolicy Bypass -Scope Process -Force;
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12;
        iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    "

    if [ $? -ne 0 ]; then
        echo "Chocolatey installation failed"
        exit 1
    fi
fi

echo "Installing Python, FFmpeg, and Ollama"

choco install -y python ffmpeg ollama

if [ $? -ne 0 ]; then
    echo "Package installation failed"
    exit 1
fi

echo ""
echo "Verifying installations"

python --version
ffmpeg -version | head -n 1
ollama --version

echo ""
echo "Setup completed"
echo "Please restart the application!"