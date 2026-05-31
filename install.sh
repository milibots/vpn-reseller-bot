#!/bin/bash
# ---------------------------------------------------------------------------
# Automated Setup Script for Reseller VPN Bot
# ---------------------------------------------------------------------------
set -e

# Clear the screen
clear

echo "========================================================="
echo "           RESELLER BOT AUTOMATED INSTALLER              "
echo "========================================================="
echo "Target Directory: $HOME/resellerbot"
echo "---------------------------------------------------------"

# Create installation directory
INSTALL_DIR="$HOME/resellerbot"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Install System Prerequisites (Debian/Ubuntu based systems)
if ! command -v python3 &> /dev/null; then
    echo "Python3 is missing. Installing Python3 and system prerequisites..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv git curl
    else
        echo "Package manager 'apt-get' not found. Please install Python3 manually."
        exit 1
    fi
fi

# Download the latest resellerbot.py from GitHub
echo "Downloading main application script..."
curl -sSL -o resellerbot.py https://raw.githubusercontent.com/milibots/vpn-reseller-bot/main/resellerbot.py

# Setup python virtual environment
echo "Configuring Python virtual environment (.venv)..."
python3 -m venv .venv
source .venv/bin/activate

# Install Python packages
echo "Installing required Python libraries..."
pip install --upgrade pip
pip install aiogram==3.12.0 sqlalchemy==2.0.23 requests==2.31.0 colorama==0.4.6 rich==13.7.0

# Start interactive installation inside the venv
echo "========================================================="
echo "   Launching Bot Setup Wizard inside Virtual Env...      "
echo "========================================================="
python resellerbot.py
