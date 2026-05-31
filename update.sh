#!/bin/bash
# ---------------------------------------------------------------------------
# Automated Smart Updater Script for Reseller VPN Bot
# ---------------------------------------------------------------------------
set -e

# Clear the screen
clear

echo "========================================================="
echo "           RESELLER BOT AUTOMATED SMART UPDATER          "
echo "========================================================="
echo "Updating application to the latest version..."
echo "---------------------------------------------------------"

# Locate the root directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Define raw file source for bare-script installations
RAW_PYTHON_URL="https://raw.githubusercontent.com/milibots/vpn-reseller-bot/main/resellerbot.py"

# Create a temporary secure directory for backing up config & db
BACKUP_DIR="/tmp/reseller_bot_backup_$(date +%s)"
mkdir -p "$BACKUP_DIR"

echo "Creating safe local files backup..."
if [ -f "reseller_bot.db" ]; then
    cp reseller_bot.db "$BACKUP_DIR/"
    echo "✔ reseller_bot.db backed up."
fi
if [ -f "reseller_config.json" ]; then
    cp reseller_config.json "$BACKUP_DIR/"
    echo "✔ reseller_config.json backed up."
fi

# Syncing updates dynamically
if [ -d ".git" ]; then
    echo "Git repository detected. Syncing via Git..."
    git reset --hard
    git pull origin main || git pull origin master
else
    echo "Bare script installation detected. Downloading raw file from GitHub..."
    curl -sSL -o resellerbot.py "$RAW_PYTHON_URL"
    echo "✔ resellerbot.py updated."
fi

# Restoring database and configurations
echo "Restoring local database and configurations..."
if [ -f "$BACKUP_DIR/reseller_bot.db" ]; then
    cp "$BACKUP_DIR/reseller_bot.db" ./
fi
if [ -f "$BACKUP_DIR/reseller_config.json" ]; then
    cp "$BACKUP_DIR/reseller_config.json" ./
fi

# Checking and updating virtual environment packages
if [ -d ".venv" ]; then
    echo "Updating virtual environment requirements..."
    if [ -f ".venv/bin/python" ]; then
        .venv/bin/python -m pip install --upgrade pip
        .venv/bin/python -m pip install aiogram==3.12.0 sqlalchemy==2.0.23 requests==2.31.0 colorama==0.4.6 rich==13.7.0
    elif [ -f ".venv/Scripts/python.exe" ]; then
        .venv/Scripts/python.exe -m pip install --upgrade pip
        .venv/Scripts/python.exe -m pip install aiogram==3.12.0 sqlalchemy==2.0.23 requests==2.31.0 colorama==0.4.6 rich==13.7.0
    fi
fi

# Restarting systemctl daemon service if active
if systemctl list-units --type=service --all | grep -Fq 'resellerbot.service'; then
    echo "Restarting resellerbot background daemon service..."
    sudo systemctl restart resellerbot
fi

echo "========================================================="
echo "   Update completed successfully! All data preserved.    "
echo "========================================================="
