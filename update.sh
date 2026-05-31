#!/bin/bash
# ---------------------------------------------------------------------------
# Automated Direct Updater Script (No Git Required)
# ---------------------------------------------------------------------------
set -e

# Define basic color codes for professional output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Clear the screen
clear

echo -e "${CYAN}=========================================================${NC}"
echo -e "           RESELLER BOT AUTOMATED DIRECT UPDATER         "
echo -e "${CYAN}=========================================================${NC}"
echo "Updating resellerbot.py directly from GitHub..."
echo "---------------------------------------------------------"

# Ensure we are in the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Verify curl is installed
if ! command -v curl &> /dev/null; then
    echo -e "${RED}❌ Error: curl is not installed on this system. Please install curl and try again.${NC}"
    exit 1
fi

# Temporary backup directory
BACKUP_DIR="/tmp/reseller_bot_backup_$(date +%s)"
mkdir -p "$BACKUP_DIR"

echo -e "${CYAN}Step 1: Backing up local database and configuration...${NC}"
if [ -f "reseller_bot.db" ]; then
    cp reseller_bot.db "$BACKUP_DIR/"
    echo -e "  ${GREEN}✔${NC} reseller_bot.db backed up safely."
else
    echo "  ⚠ No local reseller_bot.db found. Skipping database backup."
fi

if [ -f "reseller_config.json" ]; then
    cp reseller_config.json "$BACKUP_DIR/"
    echo -e "  ${GREEN}✔${NC} reseller_config.json backed up safely."
else
    echo "  ⚠ No local reseller_config.json found. Skipping configuration backup."
fi

# Directly download the python file, overwriting the old one
echo -e "${CYAN}Step 2: Downloading the latest resellerbot.py script...${NC}"
HTTP_STATUS=$(curl -s -w "%{http_code}" -o resellerbot.py "https://raw.githubusercontent.com/milibots/vpn-reseller-bot/main/resellerbot.py")

if [ "$HTTP_STATUS" -ne 200 ]; then
    echo -e "${RED}❌ Error: Failed to download script from GitHub (HTTP Status: $HTTP_STATUS).${NC}"
    echo "Restoring backups and aborting..."
    if [ -f "$BACKUP_DIR/reseller_bot.db" ]; then cp "$BACKUP_DIR/reseller_bot.db" ./ ; fi
    if [ -f "$BACKUP_DIR/reseller_config.json" ]; then cp "$BACKUP_DIR/reseller_config.json" ./ ; fi
    exit 1
fi
echo -e "  ${GREEN}✔${NC} resellerbot.py updated."

# Restore local database and configuration
echo -e "${CYAN}Step 3: Restoring local database and configuration...${NC}"
if [ -f "$BACKUP_DIR/reseller_bot.db" ]; then
    cp "$BACKUP_DIR/reseller_bot.db" ./
    echo -e "  ${GREEN}✔${NC} Database restored."
fi
if [ -f "$BACKUP_DIR/reseller_config.json" ]; then
    cp "$BACKUP_DIR/reseller_config.json" ./
    echo -e "  ${GREEN}✔${NC} Configuration restored."
fi

# Update dependencies inside the virtual environment
if [ -d ".venv" ]; then
    echo -e "${CYAN}Step 4: Updating virtual environment requirements...${NC}"
    if [ -f ".venv/bin/python" ]; then
        .venv/bin/python -m pip install --upgrade pip
        .venv/bin/python -m pip install aiogram==3.12.0 sqlalchemy==2.0.23 requests==2.31.0 colorama==0.4.6 rich==13.7.0
        echo -e "  ${GREEN}✔${NC} Dependencies inside virtual environment updated."
    elif [ -f ".venv/Scripts/python.exe" ]; then
        .venv/Scripts/python.exe -m pip install --upgrade pip
        .venv/Scripts/python.exe -m pip install aiogram==3.12.0 sqlalchemy==2.0.23 requests==2.31.0 colorama==0.4.6 rich==13.7.0
        echo -e "  ${GREEN}✔${NC} Dependencies inside Windows virtual environment updated."
    fi
else
    echo -e "${YELLOW}⚠ Warning: No virtual environment (.venv) found. Dynamic dependency installation will be performed by the Python script itself on boot.${NC}"
fi

# Clean up backup folder
rm -rf "$BACKUP_DIR"

# Restart background daemon service and verify status
echo -e "${CYAN}Step 5: Managing systemd services...${NC}"
if systemctl list-units --type=service --all | grep -Fq 'resellerbot.service'; then
    echo "Restarting resellerbot systemd service..."
    sudo systemctl restart resellerbot
    
    # Wait briefly for startup initialization to complete
    sleep 3
    
    echo -e "\n${CYAN}---------------------------------------------------------${NC}"
    echo -e "             CURRENT SYSTEMD DAEMON STATUS               "
    echo -e "${CYAN}---------------------------------------------------------${NC}"
    sudo systemctl status resellerbot.service --no-pager
    echo -e "${CYAN}---------------------------------------------------------${NC}"
else
    echo -e "${YELLOW}⚠ Warning: resellerbot.service is not installed on this system.${NC}"
    echo "You can launch the bot manually inside the virtual environment using:"
    echo "  source .venv/bin/activate && python resellerbot.py"
fi

echo -e "\n${GREEN}=========================================================${NC}"
echo -e "   Update completed successfully! All data preserved.    "
echo -e "${GREEN}=========================================================${NC}"
