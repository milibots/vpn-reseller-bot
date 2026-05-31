# Reseller VPN Telegram Bot

A highly customizable and lightweight Telegram bot designed for VPN resellers. It integrates with the central API, allows clients to purchase and renew subscriptions, manages a localized wallet system with manual card deposit verification, and supports native Telegram 10.0 styling features.

## 🚀 Fast One-Click Installation

To automatically install the bot, configure the settings, set up the database, and create a systemctl system service, run the following command on your Linux VPS:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/milibots/vpn-reseller-bot/main/install.sh)"
🗑️ Fast One-Click Uninstallation
If you wish to completely remove the bot, stop and delete its background service, and wipe the database and installation directory, execute:
code
Bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/milibots/vpn-reseller-bot/main/uninstall.sh)"
🛠 Manual Installation
If you prefer to install the prerequisites manually:
Clone the repository:
code
Bash
git clone https://github.com/milibots/vpn-reseller-bot.git
cd vpn-reseller-bot
Run the application (it will automatically build the virtual environment and install missing libraries):
code
Bash
python3 resellerbot.py
