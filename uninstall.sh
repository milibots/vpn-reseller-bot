#!/bin/bash
# ---------------------------------------------------------------------------
# Automated Uninstaller Script for Reseller VPN Bot
# ---------------------------------------------------------------------------
set -e

# Clear the screen
clear

echo "========================================================="
echo "           RESELLER BOT AUTOMATED UNINSTALLER            "
echo "========================================================="
echo "This script will completely remove the bot and its service."
echo "---------------------------------------------------------"

# Confirm before uninstallation
read -p "Are you sure you want to completely uninstall the bot? (y/n): " confirm
if [[ "$confirm" != "y" && "$confirm" != "yes" ]]; then
    echo "Uninstallation canceled."
    exit 0
fi

# Stop and disable systemd service if active
if systemctl list-units --type=service --all | grep -Fq 'resellerbot.service'; then
    echo "Stopping resellerbot systemd service..."
    sudo systemctl stop resellerbot || true
    echo "Disabling resellerbot systemd service..."
    sudo systemctl disable resellerbot || true
fi

# Remove systemd service file
if [ -f "/etc/systemd/system/resellerbot.service" ]; then
    echo "Removing systemd service unit file..."
    sudo rm -f /etc/systemd/system/resellerbot.service
    echo "Reloading systemd manager configuration..."
    sudo systemctl daemon-reload
fi

# Remove installation directory
INSTALL_DIR="$HOME/resellerbot"
if [ -d "$INSTALL_DIR" ]; then
    echo "Deleting installation directory: $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
fi

echo "========================================================="
echo "   Reseller Bot has been completely uninstalled.        "
echo "========================================================="
