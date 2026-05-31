#!/bin/bash
# ---------------------------------------------------------------------------
# Automated Direct Updater Script (No Git Required)
# ---------------------------------------------------------------------------
set -e

# Clear the screen
clear

echo "========================================================="
echo "           RESELLER BOT AUTOMATED DIRECT UPDATER         "
echo "========================================================="
echo "Updating resellerbot.py directly from GitHub..."
echo "---------------------------------------------------------"

# Ensure we are in the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Temporary backup directory
BACKUP_DIR="/tmp/reseller_bot_backup_$(date +%s)"
mkdir -p "$BACKUP_DIR"

echo "Backing up local database and configuration..."
if [ -f "reseller_bot.db" ]; then
    cp reseller_bot.db "$BACKUP_DIR/"
    echo "✔ reseller_bot.db backed up safely."
fi
if [ -f "reseller_config.json" ]; then
    cp reseller_config.json "$BACKUP_DIR/"
    echo "✔ reseller_config.json backed up safely."
fi

# Directly download the python file, overwriting the old one
echo "Downloading the latest resellerbot.py script..."
curl -sSL -o resellerbot.py "https://raw.githubusercontent.com/milibots/vpn-reseller-bot/main/resellerbot.py"
echo "✔ resellerbot.py updated."

# Restore local database and configuration
echo "Restoring local database and configuration..."
if [ -f "$BACKUP_DIR/reseller_bot.db" ]; then
    cp "$BACKUP_DIR/reseller_bot.db" ./
fi
if [ -f "$BACKUP_DIR/reseller_config.json" ]; then
    cp "$BACKUP_DIR/reseller_config.json" ./
fi

# Update dependencies inside the virtual environment
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

# Restart background daemon service
if systemctl list-units --type=service --all | grep -Fq 'resellerbot.service'; then
    echo "Restarting resellerbot systemd service..."
    sudo systemctl restart resellerbot
fi

echo "========================================================="
echo "   Update completed successfully! All data preserved.    "
echo "========================================================="
