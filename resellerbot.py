# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import json
import re
import asyncio
import requests
import getpass
import logging
import urllib.parse
import csv
import io
import random
import string
from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_environment_and_install_dependencies():
    """Checks and automates the creation of virtual environment and dependencies."""
    is_venv = sys.prefix != sys.base_prefix
    if not is_venv:
        venv_dir = os.path.join(os.getcwd(), ".venv")
        if not os.path.exists(venv_dir):
            print("Virtual environment not found. Creating '.venv' in current directory...")
            try:
                subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
            except Exception as e:
                print(f"Error creating virtual environment: {e}")
                sys.exit(1)
        
        if os.name == "nt":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            
        print("Installing required dependencies inside the virtual environment...")
        try:
            subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([venv_python, "-m", "pip", "install", "aiogram==3.12.0", "sqlalchemy==2.0.23", "requests==2.31.0", "colorama==0.4.6", "rich==13.7.0"])
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)
            
        print("\nSetup completed. Relaunching script inside the virtual environment...")
        os.execv(venv_python, [venv_python] + sys.argv)

setup_environment_and_install_dependencies()

# Standard Library Imports
import os
import sys
import json
import re
import asyncio
import requests
import getpass
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Third-Party Library Imports
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, FSInputFile, Document
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, desc, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.inspection import inspect
from colorama import init, Fore, Style
from rich.console import Console
from rich.panel import Panel

init(autoreset=True)
console = Console()

log_handler = RotatingFileHandler("reseller_bot.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[log_handler, logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("reseller_bot")

CONFIG_PATH = "reseller_config.json"
TEXTS_PATH = "reseller_texts.json"

DEFAULT_TEXTS = {
    "welcome_text": "🌟 سلام **{first_name}** عزیز، به تحریم‌شکن شَب‌راه خوش آمدید.\n\n📊 رتبه کاربری شما: **{rank_name}**\nموجودی فعلی شما: **{balance}** تومان\n\nلطفاً جهت خرید یا مدیریت اشتراک‌های خود از دکمه‌های زیر استفاده کنید.",
    "main_menu_text": "🌟 منوی اصلی سیستم\n\n📊 سطح کاربری شما: **{rank_name}**\nموجودی کیف پول شما: **{balance}** تومان",
    "support_text": "📞 **ارتباط با پشتیبانی**\n\nدر صورت بروز هرگونه مشکل یا داشتن سوال درباره خرید و فعال‌سازی سرویس‌ها، با آیدی پشتیبانی در ارتباط باشید.",
    "wallet_text": "💳 **کیف پول حساب کاربری**\n\nموجودی فعلی شما: **{balance}** تومان\n\nجهت شارژ حساب خود می‌توانید از دکمه زیر اقدام نمایید.",
    "card_payment_instructions": "🧾 **درخواست واریز کارت به کارت**\n\n💵 مبلغ قابل پرداخت: **{amount}** تومان\n\n💳 شماره کارت جهت واریز:\n`{card_number}`\n\n👤 به نام:\n**{card_holder}**\n\n⚠️ لطفاً پس از انتقال وجه، تصویر فیش یا رسید واریزی خود را در همین بخش ارسال کنید.",
    "crypto_payment_instructions": "💎 **پرداخت با رمزارز {asset}**\n\n📍 لطفاً مبلغ مورد نظر خود را به آدرس زیر واریز نمایید:\n\n`{address}`\n\n⚠️ توجه: پس از تکمیل انتقال، لطفا کد پیگیری (TXID / Hash) یا عکس رسید پرداخت خود را در همین بخش ارسال نمایید.",
    "maintenance_text": "🔧 **ربات در حال حاضر در وضعیت بروزرسانی قرار دارد**\n\nدر این لحظه امکان ارائه خدمات وجود ندارد. لطفاً بعداً تلاش کنید یا با پشتیبانی در ارتباط باشید.",
    "shop_closed_text": "⚠️ **فروشگاه موقتاً تعطیل است**\n\nامکان ثبت سفارش جدید در حال حاضر وجود ندارد. از صبر و شکیبایی شما سپاسگزاریم.",
    "purchase_success_text": "🎉 **خرید شما با موفقیت انجام شد!**\n\n🔗 **لینک اشتراک اختصاصی:**\n`{sub_link}`\n\n",
    "insufficient_balance_text": "❌ **موجودی حساب شما کافی نیست!**\n\nقیمت پلن: **{price}** تومان\nموجودی شما: **{balance}** تومان\n\nلطفاً ابتدا حساب خود را شارژ کنید."
}

def load_or_create_texts():
    """Initializes and returns localized interface messages dynamically."""
    if os.path.exists(TEXTS_PATH):
        try:
            with open(TEXTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Ensure all default keys exist
                for k, v in DEFAULT_TEXTS.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
            
    with open(TEXTS_PATH, "w", encoding="utf-8") as f:
        json.dump(DEFAULT_TEXTS, f, indent=4, ensure_ascii=False)
    return DEFAULT_TEXTS

bot_texts = load_or_create_texts()

def save_texts_file():
    """Writes global text configurations back to the JSON file safely."""
    with open(TEXTS_PATH, "w", encoding="utf-8") as f:
        json.dump(bot_texts, f, indent=4, ensure_ascii=False)

def load_or_create_config():
    """Initializes and saves the setup configuration parameters dynamically."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "MAINTENANCE_MODE" not in data:
                    data["MAINTENANCE_MODE"] = False
                if "SHOP_CLOSED" not in data:
                    data["SHOP_CLOSED"] = False
                return data
        except Exception:
            pass

    console.print(Panel.fit(
        "[bold cyan]RESELLER BOT CONFIGURATION WIZARD[/bold cyan]\n[gray]Please complete the following steps in English[/gray]",
        border_style="cyan"
    ))
    
    bot_token = input(f"{Fore.CYAN}1. Enter Telegram Bot Token: {Style.RESET_ALL}").strip()
    admins_input = input(f"{Fore.CYAN}2. Enter Admin Telegram IDs (comma-separated): {Style.RESET_ALL}").strip()
    admin_ids = [int(aid.strip()) for aid in admins_input.split(",") if aid.strip().isdigit()]
    
    api_key = input(f"{Fore.CYAN}3. Enter Reseller API Key (X-API-Key): {Style.RESET_ALL}").strip()
    api_base_url = input(f"{Fore.CYAN}4. Enter API Base URL [default: https://bot.blkeyes.com]: {Style.RESET_ALL}").strip()
    if not api_base_url:
        api_base_url = "https://bot.blkeyes.com"
        
    print("\nVerifying connection to the reseller server...")
    headers = {"X-API-Key": api_key}
    try:
        r = requests.get(f"{api_base_url.rstrip('/')}/ma/api/v1/balance", headers=headers, timeout=10)
        if r.status_code == 200 and r.json().get("success"):
            console.print(f"[green]🟢 Verified! Central Wallet Balance: {r.json().get('balance')} Tomans[/green]")
        else:
            console.print("[yellow]⚠ API Key validation returned unverified. Saving configuration regardless...[/yellow]")
    except Exception as e:
        console.print(f"[red]❌ Connection failed: {e}. Saving configuration regardless...[/red]")

    card_number = input(f"{Fore.CYAN}5. Enter Bank Card Number for deposits: {Style.RESET_ALL}").strip()
    card_holder = input(f"{Fore.CYAN}6. Enter Card Holder Name: {Style.RESET_ALL}").strip()

    welcome_banner = input(f"{Fore.CYAN}7. Enter Welcome Banner Image URL (optional): {Style.RESET_ALL}").strip()

    ton_address = input(f"{Fore.CYAN}8. Enter TON Wallet Address for deposits (optional): {Style.RESET_ALL}").strip()
    usdt_address = input(f"{Fore.CYAN}9. Enter USDT (TRC20) Wallet Address for deposits (optional): {Style.RESET_ALL}").strip()
    trx_address = input(f"{Fore.CYAN}10. Enter TRX Wallet Address for deposits (optional): {Style.RESET_ALL}").strip()

    backup_choice = input(f"{Fore.CYAN}11. Enable automatic DB backups? (y/n) [default: n]: {Style.RESET_ALL}").strip().lower()
    backup_enabled = (backup_choice == 'y' or backup_choice == 'yes')
    
    backup_interval = 12
    if backup_enabled:
        backup_interval_input = input(f"{Fore.CYAN}12. Backup interval in hours [default: 12]: {Style.RESET_ALL}").strip()
        if backup_interval_input.isdigit():
            backup_interval = int(backup_interval_input)

    force_join_id = input(f"{Fore.CYAN}13. Enter Force Join Channel Chat ID (e.g. -100123456789) [optional]: {Style.RESET_ALL}").strip()
    force_join_chat_id = int(force_join_id) if (force_join_id and force_join_id.replace('-', '').isdigit()) else None
    
    force_join_link = ""
    if force_join_chat_id:
        force_join_link = input(f"{Fore.CYAN}14. Enter Force Join Channel Invite Link: {Style.RESET_ALL}").strip()
        
    support_username = input(f"{Fore.CYAN}15. Enter Support Username [default: @rnilaad]: {Style.RESET_ALL}").strip()
    if not support_username:
        support_username = "@rnilaad"
    elif not support_username.startswith("@"):
        support_username = "@" + support_username

    config_data = {
        "BOT_TOKEN": bot_token,
        "ADMIN_IDS": admin_ids,
        "API_KEY": api_key,
        "API_BASE_URL": api_base_url,
        "CARD_NUMBER": card_number or "6037997900000000",
        "CARD_HOLDER": card_holder or "Administrator",
        "WELCOME_BANNER_URL": welcome_banner,
        "TON_ADDRESS": ton_address,
        "USDT_ADDRESS": usdt_address,
        "TRX_ADDRESS": trx_address,
        "BACKUP_ENABLED": backup_enabled,
        "BACKUP_INTERVAL_HOURS": backup_interval,
        "FORCE_JOIN_CHAT_ID": force_join_chat_id,
        "FORCE_JOIN_LINK": force_join_link,
        "SUPPORT_USERNAME": support_username,
        "MAINTENANCE_MODE": False,
        "SHOP_CLOSED": False
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)
    
    console.print("[green]✔ Configuration written successfully.[/green]")

    service_choice = input(f"{Fore.CYAN}16. Would you like to create a systemctl service unit? (y/n): {Style.RESET_ALL}").strip().lower()
    if service_choice == 'y' or service_choice == 'yes':
        if os.name == "nt":
            venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        else:
            venv_python = os.path.join(os.getcwd(), ".venv", "bin", "python")
        create_systemd_service(venv_python)

    return config_data

config = load_or_create_config()

def save_config_file():
    """Writes global memory configurations back to the JSON file safely."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

DATABASE_URL = "sqlite:///reseller_bot.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class DBUser(Base):
    """Represents a client registered within the Telegram bot."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    balance = Column(Float, default=0.0)
    joined_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    is_banned = Column(Boolean, default=False)

class DBService(Base):
    """Represents a virtual private server subscription connected to the API."""
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    plan_id = Column(Integer, nullable=True)
    uuid = Column(String, index=True)
    name = Column(String, nullable=True)
    status = Column(String, default="active")
    sub_url = Column(String, nullable=True)
    expire_date = Column(String, nullable=True)

class DBTransaction(Base):
    """Represents a financial transaction including deposits, card top-ups, and purchases."""
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, default="pending")
    description = Column(String, nullable=True)
    date = Column(DateTime, default=datetime.utcnow)
    receipt_image_id = Column(String, nullable=True)
    tx_hash = Column(String, nullable=True)

class DBPlanOverride(Base):
    """Allows administrators to customize titles and prices of Reseller API plans."""
    __tablename__ = "plan_overrides"
    plan_id = Column(Integer, primary_key=True)
    custom_title = Column(String, nullable=True)
    custom_price = Column(Float, nullable=True)
    is_hidden = Column(Boolean, default=False)

Base.metadata.create_all(bind=engine)

def execute_db_migrations():
    """Inspects database model definitions and automatically coordinates schema corrections."""
    inspector = inspect(engine)
    with engine.connect() as conn:
        columns = [col["name"] for col in inspector.get_columns("users")]
        if "is_active" not in columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                conn.commit()
            except Exception as e:
                logger.error(f"Error migrating users is_active: {e}")

        if "is_banned" not in columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception as e:
                logger.error(f"Error migrating users is_banned: {e}")

        columns_tx = [col["name"] for col in inspector.get_columns("transactions")]
        if "tx_hash" not in columns_tx:
            try:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN tx_hash VARCHAR(255) NULL"))
                conn.commit()
            except Exception as e:
                logger.error(f"Error migrating transactions tx_hash: {e}")

        columns_po = [col["name"] for col in inspector.get_columns("plan_overrides")]
        if "is_hidden" not in columns_po:
            try:
                conn.execute(text("ALTER TABLE plan_overrides ADD COLUMN is_hidden BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception as e:
                logger.error(f"Error migrating plan_overrides is_hidden: {e}")

execute_db_migrations()

def get_or_create_db_user(session, tg_user):
    """Fetches a user profile from SQLite, or creates a new entry if not existing."""
    user = session.query(DBUser).filter(DBUser.telegram_id == tg_user.id).first()
    if not user:
        user = DBUser(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            joined_at=datetime.utcnow(),
            is_active=True,
            is_banned=False
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    else:
        if not user.is_active:
            user.is_active = True
            session.commit()
    return user

def calculate_user_rank(session, user_id):
    """Computes dynamic ranking tier based on cumulative successful purchase volumes."""
    total_spent = session.query(text("SUM(ABS(amount))")).select_from(DBTransaction).filter(
        DBTransaction.user_id == user_id,
        DBTransaction.type.in_(["Buy", "Renew"]),
        DBTransaction.status == "success"
    ).scalar() or 0.0
    
    if total_spent >= 1000000:
        return "💎 کاربر الماس (Diamond)", total_spent
    elif total_spent >= 500000:
        return "🥇 کاربر طلایی (Gold)", total_spent
    elif total_spent >= 200000:
        return "🥈 کاربر نقره‌ای (Silver)", total_spent
    else:
        return "🥉 کاربر برنزی (Bronze)", total_spent

# ---------------------------------------------------------------------------
# 3. Reseller API Client
# ---------------------------------------------------------------------------
class ResellerAPI:
    """Manages transactional and listing endpoints directed at the master API."""
    def __init__(self):
        """Initializes API client base URL and required authorization headers."""
        self.base_url = config["API_BASE_URL"].rstrip("/")
        self.headers = {"X-API-Key": config["API_KEY"]}

    def get_balance(self):
        """Fetches central wallet balance of the reseller account."""
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/balance", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_balance error: {e}")
        return None

    def get_plans(self):
        """Queries active server plans and customized reseller margins."""
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/plans", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_plans error: {e}")
        return None

    def buy_service(self, plan_id, name, client_id):
        """Requests creation of a new VPN account from the central server."""
        try:
            payload = {"plan_id": int(plan_id), "name": name, "reseller_client_id": int(client_id)}
            r = requests.post(f"{self.base_url}/ma/api/v1/buy", json=payload, headers=self.headers, timeout=20)
            return r.json(), r.status_code
        except Exception as e:
            logger.error(f"API buy_service error: {e}")
            return {"error": str(e)}, 500

    def get_service_details(self, service_id):
        """Returns diagnostic connection info and credentials of a subscription."""
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/services/{service_id}", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_service_details error: {e}")
        return None

    def get_client_services(self, client_id):
        """Lists active subscriptions matching a specific Telegram Client ID."""
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/services/client/{client_id}", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_client_services error: {e}")
        return None

    def toggle_service(self, service_id, action):
        """Updates active status of a service on the target panel (enable/disable)."""
        try:
            payload = {"service_ids": [int(service_id)], "action": action}
            r = requests.post(f"{self.base_url}/ma/api/v1/services/toggle", json=payload, headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API toggle_service error: {e}")
        return None

    def renew_service(self, service_id, plan_id):
        """Applies renewal action onto an existing service subscription."""
        try:
            payload = {"service_id": int(service_id), "plan_id": int(plan_id)}
            r = requests.post(f"{self.base_url}/ma/api/v1/services/renew", json=payload, headers=self.headers, timeout=20)
            return r.json(), r.status_code
        except Exception as e:
            logger.error(f"API renew_service error: {e}")
            return {"error": str(e)}, 500

api = ResellerAPI()

# ---------------------------------------------------------------------------
# 4. Bot & FSM Setup
# ---------------------------------------------------------------------------
bot = Bot(token=config["BOT_TOKEN"])
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

class Form(StatesGroup):
    """FSM states group for client checkout and top-up operations."""
    waiting_for_charge_amount = State()
    waiting_for_receipt = State()
    waiting_for_crypto_receipt = State()
    waiting_for_service_name = State()
    
class AdminStates(StatesGroup):
    """FSM states group for restricted administrative procedures."""
    waiting_for_broadcast_mode = State()
    waiting_for_broadcast_msg = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_charge_userid = State()
    waiting_for_charge_amount = State()
    waiting_for_plan_select = State()
    waiting_for_plan_title = State()
    waiting_for_plan_price = State()
    waiting_for_user_lookup = State()
    waiting_for_service_lookup = State()
    waiting_for_direct_message = State()
    waiting_for_config_key_select = State()
    waiting_for_config_key_value = State()
    waiting_for_text_key_select = State()
    waiting_for_text_key_value = State()
    waiting_for_texts_json_upload = State()

# ---------------------------------------------------------------------------
# 5. Global Middleware (Banned, Maintenance & Force Join Channel Checks)
# ---------------------------------------------------------------------------
class CustomSecurityMiddleware(BaseMiddleware):
    """Enforces subscription rules and terminates interaction sequences for banned clients."""
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        
        is_admin = user.id in config["ADMIN_IDS"]

        # 1. Check Maintenance Mode
        if config.get("MAINTENANCE_MODE") and not is_admin:
            maint_txt = bot_texts.get("maintenance_text", DEFAULT_TEXTS["maintenance_text"])
            if isinstance(event, Message):
                await event.reply(maint_txt, parse_mode="Markdown")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ ربات موقتاً به دلیل بروزرسانی از دسترس خارج است.", show_alert=True)
            return

        # 2. Check Ban Status
        with SessionLocal() as db:
            db_user = db.query(DBUser).filter(DBUser.telegram_id == user.id).first()
            if db_user and db_user.is_banned:
                ban_txt = "❌ **دسترسی شما به ربات مسدود شده است.**\n\nدر صورت وجود سوال یا مشکل با پشتیبانی در ارتباط باشید."
                if isinstance(event, Message):
                    await event.reply(ban_txt, parse_mode="Markdown")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ حساب شما مسدود شده است.", show_alert=True)
                return

        if is_admin:
            return await handler(event, data)
            
        # 3. Check Force Join Channel Status
        chat_id = config.get("FORCE_JOIN_CHAT_ID")
        link = config.get("FORCE_JOIN_LINK", "https://t.me/your_channel")
        
        if chat_id:
            try:
                member = await bot.get_chat_member(chat_id=chat_id, user_id=user.id)
                if member.status not in ["creator", "administrator", "member"]:
                    raise Exception("Not subscribed")
            except Exception:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📢 عضویت در کانال ما (Join Channel)", url=link)],
                    [InlineKeyboardButton(text="🔄 تایید عضویت (Check Subscription)", callback_data="btn_main_menu")]
                ])
                msg_text = (
                    "⚠️ **جهت استفاده از خدمات ربات، ابتدا باید عضو کانال ما شوید:**\n\n"
                    "لطفاً با دکمه زیر وارد کانال شده و دکمه تایید را فشار دهید."
                )
                if isinstance(event, Message):
                    await event.reply(msg_text, reply_markup=kb, parse_mode="Markdown")
                elif isinstance(event, CallbackQuery):
                    await event.message.edit_text(msg_text, reply_markup=kb, parse_mode="Markdown")
                    await event.answer()
                return
        return await handler(event, data)

dp.message.outer_middleware(CustomSecurityMiddleware())
dp.callback_query.outer_middleware(CustomSecurityMiddleware())

# ---------------------------------------------------------------------------
# 6. Keyboards
# ---------------------------------------------------------------------------
def main_menu_keyboard(tg_id):
    """Builds primary navigation interface featuring Telegram 10.0 button colors."""
    is_admin = tg_id in config["ADMIN_IDS"]
    kb = [
        [InlineKeyboardButton(text="🛒 خرید سرویس جدید", callback_data="btn_buy_service", style="primary")],
        [InlineKeyboardButton(text="🌐 سرویس‌های من", callback_data="btn_my_services", style="primary")],
        [InlineKeyboardButton(text="💳 کیف پول / موجودی", callback_data="btn_wallet"), InlineKeyboardButton(text="📞 پشتیبانی", callback_data="btn_support")]
    ]
    if is_admin:
        kb.append([InlineKeyboardButton(text="⚙️ پنل ادمین", callback_data="btn_admin_panel", style="danger")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_to_menu_keyboard():
    """Generates standard inline option leading back to home screen."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")]
    ])

# ---------------------------------------------------------------------------
# 7. Basic User Messages & Handlers (Persian interface for users)
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    """Welcomes new/existing users and shows current wallet status."""
    await state.clear()
    with SessionLocal() as db:
        user = get_or_create_db_user(db, message.from_user)
        rank_name, _ = calculate_user_rank(db, user.id)
        raw_welcome_txt = bot_texts.get("welcome_text", DEFAULT_TEXTS["welcome_text"])
        welcome_txt = raw_welcome_txt.format(
            first_name=user.first_name or '',
            rank_name=rank_name,
            balance=f"{int(user.balance):,}"
        )
        
        banner_url = config.get("WELCOME_BANNER_URL")
        if banner_url:
            try:
                await message.answer_photo(
                    photo=banner_url,
                    caption=welcome_txt,
                    reply_markup=main_menu_keyboard(message.from_user.id),
                    parse_mode="Markdown"
                )
                return
            except Exception as e:
                logger.error(f"Error sending welcome banner photo: {e}")

        await message.reply(welcome_txt, reply_markup=main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

@router.callback_query(F.data == "btn_main_menu")
async def main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Restores primary inline navigation when callback action is triggered."""
    await state.clear()
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        rank_name, _ = calculate_user_rank(db, user.id)
        raw_menu_txt = bot_texts.get("main_menu_text", DEFAULT_TEXTS["main_menu_text"])
        welcome_txt = raw_menu_txt.format(
            rank_name=rank_name,
            balance=f"{int(user.balance):,}"
        )
        
        banner_url = config.get("WELCOME_BANNER_URL")
        if banner_url:
            try:
                await callback.message.delete()
            except Exception:
                pass
            try:
                await callback.message.answer_photo(
                    photo=banner_url,
                    caption=welcome_txt,
                    reply_markup=main_menu_keyboard(callback.from_user.id),
                    parse_mode="Markdown"
                )
                await callback.answer()
                return
            except Exception as e:
                logger.error(f"Error showing welcome banner photo in menu callback: {e}")

        try:
            await callback.message.edit_text(welcome_txt, reply_markup=main_menu_keyboard(callback.from_user.id))
        except Exception:
            await callback.message.answer(welcome_txt, reply_markup=main_menu_keyboard(callback.from_user.id))
        await callback.answer()

@router.callback_query(F.data == "btn_support")
async def support_callback(callback: CallbackQuery):
    """Displays localized customer service and support details."""
    support_user = config.get("SUPPORT_USERNAME", "@rnilaad").replace("@", "")
    support_txt = bot_texts.get("support_text", DEFAULT_TEXTS["support_text"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ارسال پیام به پشتیبانی", url=f"https://t.me/{support_user}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(support_txt, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 8. Financial & Deposit Processing
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_wallet")
async def wallet_callback(callback: CallbackQuery):
    """Shows user balance inside a localized credit view card."""
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        raw_wallet_txt = bot_texts.get("wallet_text", DEFAULT_TEXTS["wallet_text"])
        txt = raw_wallet_txt.format(balance=f"{int(user.balance):,}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏧 افزایش موجودی (کارت به کارت)", callback_data="btn_charge_wallet", style="success")],
            [InlineKeyboardButton(text="💎 شارژ با ارز دیجیتال (Crypto)", callback_data="btn_charge_crypto", style="success")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
        ])
        await callback.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
        await callback.answer()

@router.callback_query(F.data == "btn_charge_wallet")
async def charge_wallet_callback(callback: CallbackQuery, state: FSMContext):
    """Prompts client for custom checkout amount via keyboard."""
    await callback.message.edit_text(
        "✏️ لطفاً مبلغ مورد نظر خود را برای شارژ حساب به **تومان** وارد کنید (به صورت عدد انگلیسی):",
        reply_markup=back_to_menu_keyboard()
    )
    await state.set_state(Form.waiting_for_charge_amount)
    await callback.answer()

@router.message(Form.waiting_for_charge_amount)
async def process_charge_amount(message: Message, state: FSMContext):
    """Checks and updates the current state with the provided top-up amount."""
    amount_str = message.text.strip()
    if not amount_str.isdigit():
        return await message.reply("❌ خطا: لطفاً مقدار را به صورت یک عدد عددی معتبر (انگلیسی) وارد کنید.")
    
    amount = int(amount_str)
    if amount < 1000:
        return await message.reply("❌ خطا: حداقل مبلغ شارژ ۱,۰۰۰ تومان می‌باشد.")
        
    await state.update_data(charge_amount=amount)
    
    card_num = config['CARD_NUMBER']
    card_holder_name = config['CARD_HOLDER']
    
    raw_payment_instructions = bot_texts.get("card_payment_instructions", DEFAULT_TEXTS["card_payment_instructions"])
    payment_txt = raw_payment_instructions.format(
        amount=f"{amount:,}",
        card_number=card_num,
        card_holder=card_holder_name
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 کپی شماره کارت", copy_text={"text": card_num}, style="success")],
        [InlineKeyboardButton(text="📋 کپی نام دارنده کارت", copy_text={"text": card_holder_name}, style="primary")],
        [InlineKeyboardButton(text="📋 کپی مبلغ (تومان)", copy_text={"text": str(amount)}, style="primary")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
    ])
    
    await message.reply(payment_txt, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Form.waiting_for_receipt)

@router.message(Form.waiting_for_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext):
    """Handles and forwards receipt image file to administrative team."""
    state_data = await state.get_data()
    amount = state_data["charge_amount"]
    photo_id = message.photo[-1].file_id
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, message.from_user)
        tx = DBTransaction(
            user_id=user.id,
            type="Charge",
            amount=amount,
            status="pending",
            description=f"درخواست شارژ کارت به کارت به مبلغ {amount:,}",
            receipt_image_id=photo_id
        )
        db.add(tx)
        db.commit()
        tx_id = tx.id

    await message.reply("✅ رسید شما با موفقیت ثبت شد و در انتظار تایید مدیریت قرار گرفت. به محض بررسی وضعیت آن به شما اطلاع داده خواهد شد.", reply_markup=back_to_menu_keyboard())
    await state.clear()

    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید رسید", callback_data=f"tx_approve_{tx_id}", style="success"),
            InlineKeyboardButton(text="❌ رد رسید", callback_data=f"tx_reject_{tx_id}", style="danger")
        ]
    ])
    
    for admin_id in config["ADMIN_IDS"]:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=f"⚡️ **رسید پرداخت جدید دریافت شد**\n\n👤 کاربر: {message.from_user.first_name} ({message.from_user.id})\n💵 مبلغ: **{amount:,}** تومان\n\nآیا این رسید را تایید می‌کنید؟",
                reply_markup=admin_markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")

# ---------------------------------------------------------------------------
# 8.1 Crypto Deposit Processing
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_charge_crypto")
async def charge_crypto_callback(callback: CallbackQuery):
    """Displays accessible cryptocurrency networks to user."""
    kb = []
    if config.get("TON_ADDRESS"):
        kb.append([InlineKeyboardButton(text="💎 شبکه TON", callback_data="cry_TON")])
    if config.get("USDT_ADDRESS"):
        kb.append([InlineKeyboardButton(text="💵 شبکه USDT (TRC-20)", callback_data="cry_USDT")])
    if config.get("TRX_ADDRESS"):
        kb.append([InlineKeyboardButton(text="🔴 شبکه TRX", callback_data="cry_TRX")])
        
    if not kb:
        return await callback.answer("⚠️ در حال حاضر هیچ درگاه پرداخت رمزارزی توسط مدیریت ثبت نشده است.", show_alert=True)
        
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_wallet")])
    await callback.message.edit_text("⚙️ لطفاً رمزارز مورد نظر خود را جهت واریز وجه انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("cry_"))
async def process_crypto_asset(callback: CallbackQuery, state: FSMContext):
    """Instructs clients with transaction targets and instructions."""
    asset = callback.data.split("_")[1]
    addr_key = f"{asset}_ADDRESS"
    address = config.get(addr_key, "")
    
    if not address:
        return await callback.answer("❌ آدرس این کیف پول پیکربندی نشده است.", show_alert=True)
        
    await state.update_data(crypto_asset=asset, crypto_address=address)
    
    raw_instructions = bot_texts.get("crypto_payment_instructions", DEFAULT_TEXTS["crypto_payment_instructions"])
    crypto_instructions = raw_instructions.format(
        asset=asset,
        address=address
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 کپی آدرس کیف پول", copy_text={"text": address}, style="success")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_charge_crypto")]
    ])
    
    await callback.message.edit_text(crypto_instructions, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Form.waiting_for_crypto_receipt)
    await callback.answer()

@router.message(Form.waiting_for_crypto_receipt)
async def process_crypto_receipt(message: Message, state: FSMContext):
    """Persists verification transaction records inside local databases."""
    state_data = await state.get_data()
    asset = state_data["crypto_asset"]
    photo_id = message.photo[-1].file_id if message.photo else None
    tx_hash = message.text.strip() if message.text else None
    
    if not photo_id and not tx_hash:
        return await message.reply("❌ خطا: لطفاً یک فیش تصویری ارسال کنید یا کد پیگیری (TXID) تراکنش را به صورت متنی وارد کنید.")
        
    with SessionLocal() as db:
        user = get_or_create_db_user(db, message.from_user)
        tx = DBTransaction(
            user_id=user.id,
            type=f"Crypto_{asset}",
            amount=0.0,
            status="pending",
            description=f"درخواست واریز رمزارز {asset}" + (f" با کد پیگیری: {tx_hash}" if tx_hash else ""),
            receipt_image_id=photo_id,
            tx_hash=tx_hash
        )
        db.add(tx)
        db.commit()
        tx_id = tx.id
        
    await message.reply("✅ رسید تراکنش رمزارز شما با موفقیت ثبت شد و جهت بررسی در اختیار مدیریت قرار گرفت.", reply_markup=back_to_menu_keyboard())
    await state.clear()
    
    admin_cap = (
        f"💎 **واریز رمزارز جدید ({asset})**\n\n"
        f"👤 کاربر: {message.from_user.first_name} ({message.from_user.id})\n"
        f"🔑 هش تراکنش: `{tx_hash or 'ارسال نشده'}`\n\n"
        f"جهت تایید این واریزی می‌توانید با تخصیص موجودی دستی از منوی ادمین اقدام نمایید."
    )
    
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و شارژ دستی کاربر", callback_data="adm_charge_user"),
            InlineKeyboardButton(text="❌ رد رسید", callback_data=f"tx_reject_{tx_id}", style="danger")
        ]
    ])
    
    for admin_id in config["ADMIN_IDS"]:
        try:
            if photo_id:
                await bot.send_photo(chat_id=admin_id, photo=photo_id, caption=admin_cap, reply_markup=admin_markup, parse_mode="Markdown")
            else:
                await bot.send_message(chat_id=admin_id, text=admin_cap, reply_markup=admin_markup, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error alerting admins for crypto transaction: {e}")

# ---------------------------------------------------------------------------
# 9. Purchase Flow with Premium Styles & Override Plan Logic
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_buy_service")
async def buy_service_callback(callback: CallbackQuery, state: FSMContext):
    """Creates plan selection displaying overrides customized by administrators."""
    await state.clear()
    
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        closed_txt = bot_texts.get("shop_closed_text", DEFAULT_TEXTS["shop_closed_text"])
        return await callback.message.edit_text(
            closed_txt,
            reply_markup=back_to_menu_keyboard(),
            parse_mode="Markdown"
        )
        
    await callback.message.edit_text("⏳ در حال دریافت لیست پلن‌ها از سرور...")
    
    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.message.edit_text("❌ خطا در ارتباط با سرور یا دریافت اطلاعات پلن‌ها. لطفا مجدداً تلاش کنید.", reply_markup=back_to_menu_keyboard())
        
    plans = plans_data.get("plans", [])
    if not plans:
        return await callback.message.edit_text("🛒 در حال حاضر پلن فعالی جهت فروش موجود نیست.", reply_markup=back_to_menu_keyboard())
        
    kb = []
    row = []
    with SessionLocal() as db:
        for p in plans:
            override = db.query(DBPlanOverride).filter(DBPlanOverride.plan_id == p['id']).first()
            if override and override.is_hidden:
                continue
                
            p_title = override.custom_title if (override and override.custom_title) else p['title']
            p_price = int(override.custom_price) if (override and override.custom_price is not None) else int(p['price'])
            
            btn_txt = f"📦 {p_title} - {p_price:,} ت"
            row.append(InlineKeyboardButton(text=btn_txt, callback_data=f"buy_plan_{p['id']}_{p_price}"))
            
            if len(row) == 2:
                kb.append(row)
                row = []
                
    if row:
        kb.append(row)
            
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")])
    await callback.message.edit_text("🛒 لطفاً یکی از پلن‌های زیر را جهت خرید انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("buy_plan_"))
async def buy_plan_callback(callback: CallbackQuery, state: FSMContext):
    """Evaluates checkout affordability and requests custom service descriptor."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان ثبت سفارش جدید وجود ندارد.", show_alert=True)

    parts = callback.data.split("_")
    plan_id = int(parts[2])
    price = int(parts[3])
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        if user.balance < price:
            raw_insufficient_txt = bot_texts.get("insufficient_balance_text", DEFAULT_TEXTS["insufficient_balance_text"])
            insufficient_txt = raw_insufficient_txt.format(
                price=f"{price:,}",
                balance=f"{int(user.balance):,}"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 افزایش موجودی حساب", callback_data="btn_charge_wallet", style="success")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_buy_service")]
            ])
            return await callback.message.edit_text(insufficient_txt, reply_markup=kb, parse_mode="Markdown")
            
    await state.update_data(buy_plan_id=plan_id, buy_price=price)
    
    name_instructions = (
        "✏️ لطفاً یک نام کوتاه انگلیسی (فقط حروف و اعداد بین ۳ تا ۱۲ کاراکتر) برای سرویس خود وارد کنید:\n\n"
        "مثال: `myvpn`\n\n"
        "🎲 یا می‌توانید از دکمه زیر جهت تولید نام کاملاً تصادفی استفاده کنید."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 تولید نام تصادفی", callback_data="btn_generate_random_name", style="primary")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_buy_service")]
    ])
    
    await callback.message.edit_text(name_instructions, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(Form.waiting_for_service_name)
    await callback.answer()

@router.callback_query(F.data == "btn_generate_random_name", Form.waiting_for_service_name)
async def generate_random_name_callback(callback: CallbackQuery, state: FSMContext):
    """Autogenerates a unique service configuration alias name."""
    rand_name = "v" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    await state.update_data(buy_service_name=rand_name)
    
    state_data = await state.get_data()
    price = state_data["buy_price"]
    
    confirm_txt = (
        "🧾 **پیش‌فاکتور نهایی خرید**\n\n"
        f"🖥 نام سرویس تصادفی تولید شده: `{rand_name}`\n"
        f"💵 قیمت نهایی: **{price:,}** تومان\n\n"
        "آیا مایل به پرداخت و نهایی کردن خرید هستید؟"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ پرداخت و تایید خرید", callback_data="confirm_buy_final", style="success"),
            InlineKeyboardButton(text="❌ انصراف", callback_data="btn_main_menu", style="danger")
        ]
    ])
    await callback.message.edit_text(confirm_txt, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

@router.message(Form.waiting_for_service_name)
async def process_service_name(message: Message, state: FSMContext):
    """Validates specified name format and displays confirmation invoice."""
    name = message.text.strip()
    if not re.match(r"^[a-zA-Z0-9]{3,12}$", name):
        return await message.reply("❌ خطا: نام سرویس فقط باید شامل حروف انگلیسی و اعداد بین ۳ تا ۱۲ کاراکتر باشد. مجدداً ارسال کنید:")
        
    state_data = await state.get_data()
    price = state_data["buy_price"]
    
    await state.update_data(buy_service_name=name)
    
    confirm_txt = (
        "🧾 **پیش‌فاکتور نهایی خرید**\n\n"
        f"🖥 نام سرویس: `{name}`\n"
        f"💵 قیمت نهایی: **{price:,}** تومان\n\n"
        "آیا مایل به پرداخت و نهایی کردن خرید هستید؟"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ پرداخت و تایید خرید", callback_data="confirm_buy_final", style="success"),
            InlineKeyboardButton(text="❌ انصراف", callback_data="btn_main_menu", style="danger")
        ]
    ])
    await message.reply(confirm_txt, reply_markup=kb, parse_mode="Markdown")

@router.callback_query(F.data == "confirm_buy_final")
async def confirm_buy_final_callback(callback: CallbackQuery, state: FSMContext):
    """Requests account creation and balance deduction, then returns the credential URL & Configs."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان ثبت سفارش جدید وجود ندارد.", show_alert=True)

    state_data = await state.get_data()
    plan_id = state_data.get("buy_plan_id")
    name = state_data.get("buy_service_name")
    price = state_data.get("buy_price")
    
    if not plan_id or not name:
        return await callback.message.edit_text("❌ خطا در بازیابی اطلاعات نشست خرید. مجدداً اقدام کنید.", reply_markup=back_to_menu_keyboard())
        
    await callback.message.edit_text("⏳ در حال برقراری ارتباط با سرور و پیکربندی اکانت...")
    
    with SessionLocal() as db:
        user = db.query(DBUser).filter(DBUser.telegram_id == callback.from_user.id).first()
        if not user or user.balance < price:
            return await callback.message.edit_text("❌ موجودی حساب شما کافی نیست یا کاربر یافت نشد.", reply_markup=back_to_menu_keyboard())
            
        res_data, status_code = api.buy_service(plan_id, name, callback.from_user.id)
        if status_code == 200 and res_data.get("success"):
            user.balance -= price
            
            new_service = DBService(
                service_id=res_data.get("service_id"),
                user_id=user.id,
                plan_id=plan_id,
                uuid=res_data.get("uuid"),
                name=name,
                status="active",
                sub_url=res_data.get("sub_url")
            )
            db.add(new_service)
            
            tx = DBTransaction(
                user_id=user.id,
                type="Buy",
                amount=-price,
                status="success",
                description=f"خرید سرویس {name}"
            )
            db.add(tx)
            db.commit()
            
            sub_link = res_data.get("sub_url", "")
            configs_list = res_data.get("configs", [])
            configs_list = [cfg for cfg in configs_list if "/sub/" not in cfg]
            
            raw_success_txt = bot_texts.get("purchase_success_text", DEFAULT_TEXTS["purchase_success_text"])
            success_txt = raw_success_txt.format(sub_link=sub_link)
            
            if configs_list:
                success_txt += "🔌 **کانفیگ‌های اتصال مستقیم شما:**\n\n"
                for index, cfg in enumerate(configs_list[:3]):
                    success_txt += f"**کانفیگ {index+1}:**\n`{cfg}`\n\n"
            
            kb_list = [
                [InlineKeyboardButton(text="📋 کپی سریع لینک اشتراک", copy_text={"text": sub_link}, style="success")],
                [InlineKeyboardButton(text="🔗 باز کردن حساب کاربری (مینی‌اپ)", url=sub_link, style="primary")],
                [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")]
            ]
            
            await callback.message.edit_text(success_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="Markdown")

            # Report purchase to Admins
            admin_msg = (
                f"🔔 **گزارش خرید سرویس جدید**\n\n"
                f"👤 خریدار: {user.first_name or 'نامشخص'} ({user.telegram_id})\n"
                f"📦 پلن خریداری شده: (کد پلن: {plan_id})\n"
                f"🖥 نام سرویس: `{name}`\n"
                f"💵 قیمت پرداخت شده: **{price:,}** تومان\n"
                f"🔑 شناسه (UUID): `{res_data.get('uuid')}`"
            )
            for admin_id in config["ADMIN_IDS"]:
                try:
                    await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Error sending buy report to admin {admin_id}: {e}")
        else:
            err_msg = res_data.get("error", "An error occurred during purchase creation.")
            await callback.message.edit_text(f"❌ **خطا در هنگام ساخت اکانت روی سرور:**\n\n`{err_msg}`", reply_markup=back_to_menu_keyboard(), parse_mode="Markdown")
            
    await state.clear()
    await callback.answer()

# ---------------------------------------------------------------------------
# 10. Services List & Dynamic 2-Row Column Layout Controls
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_my_services")
async def my_services_callback(callback: CallbackQuery):
    """Retrieves client subscriptions and populates active services menu."""
    await callback.message.edit_text("⏳ در حال دریافت لیست سرویس‌های شما از سرور...")
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        services = db.query(DBService).filter(DBService.user_id == user.id).all()
        
    if not services:
        return await callback.message.edit_text("🌐 شما هیچ سرویس فعالی ثبت نکرده‌اید.", reply_markup=back_to_menu_keyboard())
        
    kb = []
    row = []
    for s in services:
        row.append(InlineKeyboardButton(text=f"📡 {s.name or 'سرویس'}", callback_data=f"srv_view_{s.id}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
        
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")])
    await callback.message.edit_text("🌐 لیست سرویس‌های ثبت شده شما:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("srv_view_"))
async def srv_view_callback(callback: CallbackQuery):
    """Presents detailed subscription analytics with constrained admin-only toggle actions."""
    srv_id = int(callback.data.split("_")[2])
    
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv:
            return await callback.message.edit_text("❌ سرویس مورد نظر در سیستم یافت نشد.", reply_markup=back_to_menu_keyboard())
            
    await callback.message.edit_text("⏳ در حال دریافت جزئیات و ترافیک لحظه‌ای از سرور...")
    
    details = api.get_service_details(srv.service_id)
    if not details or not details.get("success"):
        detail_txt = (
            f"ℹ️ **جزئیات سرویس: {srv.name}**\n\n"
            f"🔑 شناسه (UUID): `{srv.uuid}`\n"
            f"📡 وضعیت: **{srv.status}**\n\n"
            "⚠️ دریافت اطلاعات مصرف حجم لایو از سرور مقدور نبود."
        )
        kb = [
            [
                InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data=f"srv_view_{srv.id}", style="primary"),
                InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="btn_my_services")
            ]
        ]
        return await callback.message.edit_text(detail_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
        
    status = details.get("status", "active")
    total_gb = details.get("traffic_total_gb", 0)
    used_gb = details.get("traffic_used_gb", 0)
    remain_gb = max(0.0, total_gb - used_gb)
    expire_date = details.get("expire_date") or "نامحدود"
    sub_url = details.get("sub_url") or srv.sub_url
    configs_list = details.get("configs", [])
    
    configs_list = [cfg for cfg in configs_list if "/sub/" not in cfg]
    
    with SessionLocal() as db:
        db_srv = db.query(DBService).get(srv_id)
        db_srv.status = status
        db_srv.expire_date = expire_date
        db_srv.sub_url = sub_url
        db.commit()

    detail_txt = (
        f"ℹ️ **مشخصات سرویس: {srv.name}**\n\n"
        f"📊 مصرف ترافیک: **{used_gb:.2f}** از **{total_gb:.2f} GB**\n"
        f"🔋 حجم باقیمانده: **{remain_gb:.2f} GB**\n"
        f"⏳ تاریخ انقضا: **{expire_date}**\n"
        f"📡 وضعیت: **{status}**\n\n"
        f"🔗 **لینک اشتراک:**\n`{sub_url}`"
    )
    
    kb = [
        [
            InlineKeyboardButton(text="📋 کپی لینک اشتراک", copy_text={"text": sub_url}, style="success"),
            InlineKeyboardButton(text="📸 دریافت کد QR", callback_data=f"srv_qr_{srv_id}", style="primary")
        ]
    ]
    
    if configs_list:
        cfg_row = []
        for index, cfg in enumerate(configs_list[:2]):
            proto_label = "VLESS" if "vless://" in cfg else "VMESS" if "vmess://" in cfg else "Config"
            cfg_row.append(InlineKeyboardButton(text=f"📋 کپی {proto_label} {index+1}", copy_text={"text": cfg}, style="primary"))
            if len(cfg_row) == 2:
                kb.append(cfg_row)
                cfg_row = []
        if cfg_row:
            kb.append(cfg_row)
            
    kb.append([
        InlineKeyboardButton(text="🔄 تمدید سرویس", callback_data=f"srv_renew_{srv_id}", style="success"),
        InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="btn_my_services")
    ])
    
    if callback.from_user.id in config["ADMIN_IDS"]:
        toggle_txt = "🔴 غیرفعال کردن سرویس" if status == "active" else "🟢 فعال کردن سرویس"
        kb.append([InlineKeyboardButton(text=toggle_txt, callback_data=f"srv_toggle_{srv_id}", style="danger")])
        
    await callback.message.edit_text(detail_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("srv_toggle_"))
async def srv_toggle_callback(callback: CallbackQuery):
    """Updates active status of a service on the target panel (enable/disable) for admins."""
    if callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("❌ دسترسی غیرمجاز: تنها مدیریت مجاز به قطع موقت سرویس‌ها می‌باشد.", show_alert=True)
        
    srv_id = int(callback.data.split("_")[2])
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    action = "disable" if srv.status == "active" else "enable"
    await callback.message.edit_text("⏳ در حال ارسال دستور تغییر وضعیت به سرور...")
    
    res = api.toggle_service(srv.service_id, action)
    if res and res.get("success"):
        await callback.answer("✅ وضعیت سرویس با موفقیت تغییر کرد.", show_alert=True)
    else:
        await callback.answer("❌ خطا در تغییر وضعیت سرویس در سرور.", show_alert=True)
        
    await srv_view_callback(callback)

@router.callback_query(F.data.startswith("srv_qr_"))
async def srv_qr_callback(callback: CallbackQuery):
    """Sends custom graphic representation QR image for subscription access."""
    srv_id = int(callback.data.split("_")[2])
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    qr_data = srv.sub_url or f"{config['API_BASE_URL'].rstrip('/')}/sub/{srv.uuid}"
    qr_api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={urllib.parse.quote(qr_data)}"
    
    await callback.message.edit_text("⏳ در حال تولید کد QR اختصاصی...")
    try:
        r = requests.get(qr_api_url, timeout=10)
        if r.status_code == 200:
            qr_file = BufferedInputFile(r.content, filename="qrcode.png")
            await callback.message.reply_photo(
                photo=qr_file,
                caption=f"📸 **کد QR لینک اشتراک سرویس: {srv.name}**\n\n`{qr_data}`",
                parse_mode="Markdown"
            )
            await callback.message.delete()
        else:
            raise Exception("Non-200 Response from API")
    except Exception as e:
        logger.error(f"Error creating QR code image: {e}")
        await callback.answer("❌ خطا در ایجاد عکس QR Code. لینک به صورت متن ارسال شد.", show_alert=True)
        await callback.message.reply(f"🔗 **لینک اشتراک شما:**\n\n`{qr_data}`", parse_mode="Markdown")

@router.callback_query(F.data.startswith("srv_renew_"))
async def srv_renew_callback(callback: CallbackQuery):
    """Forces renewal only to current service plan to maintain consistent parameters."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        closed_txt = bot_texts.get("shop_closed_text", DEFAULT_TEXTS["shop_closed_text"])
        return await callback.message.edit_text(
            closed_txt,
            reply_markup=back_to_menu_keyboard(),
            parse_mode="Markdown"
        )

    srv_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("⏳ در حال استعلام مشخصات پلن فعلی از سرور...")
    
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv or not srv.plan_id:
            return await callback.message.edit_text("❌ خطا: کد پلن اصلی متصل به این سرویس یافت نشد.", reply_markup=back_to_menu_keyboard())
            
        target_plan_id = srv.plan_id

    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.message.edit_text("❌ خطا در دریافت پلن‌ها از سرور.", reply_markup=back_to_menu_keyboard())
        
    plans = plans_data.get("plans", [])
    matched_plan = None
    for p in plans:
        if p["id"] == target_plan_id:
            matched_plan = p
            break
            
    if not matched_plan:
        return await callback.message.edit_text("❌ خطا: این پلن دیگر روی سرور اصلی فعال نیست یا امکان تمدید مستقیم آن وجود ندارد.", reply_markup=back_to_menu_keyboard())
        
    with SessionLocal() as db:
        override = db.query(DBPlanOverride).filter(DBPlanOverride.plan_id == matched_plan['id']).first()
        p_title = override.custom_title if (override and override.custom_title) else matched_plan['title']
        p_price = int(override.custom_price) if (override and override.custom_price is not None) else int(matched_plan['price'])

    kb = [
        [InlineKeyboardButton(text=f"🔄 تایید تمدید با {p_title} - {p_price:,} ت", callback_data=f"renew_confirm_{srv_id}_{matched_plan['id']}_{p_price}")],
        [InlineKeyboardButton(text="🔙 انصراف و بازگشت", callback_data=f"srv_view_{srv_id}")]
    ]
    
    await callback.message.edit_text(
        f"🔄 **درخواست تمدید سرویس: {srv.name}**\n\n"
        f"📦 پلن فعلی شما: **{p_title}**\n"
        f"💵 هزینه تمدید دوره: **{p_price:,}** تومان\n\n"
        "آیا مایل هستید سرویس شما برای یک دوره دیگر تمدید شود؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("renew_confirm_"))
async def renew_confirm_callback(callback: CallbackQuery):
    """Processes final renewal payment, deducts local balance, and registers state."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان تمدید سرویس وجود ندارد.", show_alert=True)

    parts = callback.data.split("_")
    srv_id = int(parts[2])
    plan_id = int(parts[3])
    price = int(parts[4])
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        if user.balance < price:
            return await callback.answer("❌ موجودی حساب شما برای این تمدید کافی نیست.", show_alert=True)
            
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    await callback.message.edit_text("⏳ در حال تمدید اشتراک بر روی سرور...")
    
    res_data, status_code = api.renew_service(srv.service_id, plan_id)
    if status_code == 200 and res_data.get("success"):
        with SessionLocal() as db:
            db_user = db.query(DBUser).filter(DBUser.telegram_id == callback.from_user.id).first()
            db_user.balance -= price
            
            tx = DBTransaction(
                user_id=db_user.id,
                type="Renew",
                amount=-price,
                status="success",
                description=f"تمدید سرویس {srv.name}"
            )
            db.add(tx)
            db.commit()
            
        await callback.answer("🎉 سرویس شما با موفقیت تمدید شد!", show_alert=True)

        admin_msg = (
            f"🔄 **گزارش تمدید سرویس**\n\n"
            f"👤 کاربر: {db_user.first_name or 'نامشخص'} ({db_user.telegram_id})\n"
            f"🖥 سرویس: `{srv.name}` (کد سرویس: {srv.service_id})\n"
            f"💵 هزینه تمدید: **{price:,}** تومان"
        )
        for admin_id in config["ADMIN_IDS"]:
            try:
                await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Error sending renewal report to admin {admin_id}: {e}")
    else:
        err = res_data.get("error", "Renewal unsuccessful.")
        await callback.answer(f"❌ خطا در تمدید: {err}", show_alert=True)
        
    await srv_view_callback(callback)

# ---------------------------------------------------------------------------
# 11. Admin Panel Functions (Broadcasting, Pagination, Custom Charge, Overrides)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_admin_panel")
async def admin_panel_callback(callback: CallbackQuery, state: FSMContext):
    """Renders administrative operations panel including diagnostics."""
    await state.clear()
    if callback.from_user.id not in config["ADMIN_IDS"]:
         return await callback.answer("Access Denied", show_alert=True)
         
    with SessionLocal() as db:
        total_users = db.query(DBUser).count()
        pending_txs = db.query(DBTransaction).filter(DBTransaction.status == "pending").all()
        
    maint_status = "🔴 فعال (تعمیرات)" if config.get("MAINTENANCE_MODE") else "🟢 غیرفعال (عادی)"
    shop_status = "🔴 بسته" if config.get("SHOP_CLOSED") else "🟢 باز"
    
    txt = (
        "⚙️ **پنل مدیریت ربات فروشگاهی نماینده**\n\n"
        f"👥 کل کاربران عضو شده: **{total_users}** کاربر\n"
        f"⏳ فیش‌های در انتظار بررسی: **{len(pending_txs)}** عدد\n\n"
        f"🔧 وضعیت تعمیرات: **{maint_status}**\n"
        f"🛒 وضعیت فروشگاه: **{shop_status}**"
    )
    
    kb = [
        [
            InlineKeyboardButton(text=f"🔧 تعمیرات: {'غیرفعال' if config.get('MAINTENANCE_MODE') else 'فعال'}", callback_data="adm_toggle_maint"),
            InlineKeyboardButton(text=f"🛒 فروشگاه: {'باز' if config.get('SHOP_CLOSED') else 'بسته'}", callback_data="adm_toggle_shop")
        ],
        [
            InlineKeyboardButton(text="📢 ارسال پیام همگانی (Broadcast)", callback_data="adm_broadcast_mode_select", style="primary"),
            InlineKeyboardButton(text="📊 آمار سیستم (Stats)", callback_data="adm_stats", style="success")
        ],
        [
            InlineKeyboardButton(text="🔍 جستجوی کاربر", callback_data="adm_user_panel_search"),
            InlineKeyboardButton(text="🔍 جستجوی سرویس", callback_data="adm_service_panel_search")
        ],
        [
            InlineKeyboardButton(text="👥 کل کاربران", callback_data="adm_view_users_0"), 
            InlineKeyboardButton(text="🛠 کل سرویس‌ها", callback_data="adm_view_services_0")
        ],
        [
            InlineKeyboardButton(text="💰 تراکنش‌ها", callback_data="adm_view_txs_0"), 
            InlineKeyboardButton(text="⚙️ پیکربندی متغیرها (Config)", callback_data="adm_edit_config_menu")
        ],
        [
            InlineKeyboardButton(text="✏️ شخصی‌سازی قیمت پلن‌ها", callback_data="adm_plan_customize_menu", style="primary"),
            InlineKeyboardButton(text="📝 مدیریت متون (Texts)", callback_data="adm_manage_texts_menu")
        ],
        [
            InlineKeyboardButton(text="🔌 استعلام موجودی وب‌سرویس اصلی", callback_data="adm_central_bal")
        ],
        [
            InlineKeyboardButton(text="📥 دانلود کاربران (CSV)", callback_data="adm_dl_users"),
            InlineKeyboardButton(text="📥 دانلود تراکنش‌ها (CSV)", callback_data="adm_dl_txs")
        ],
        [
            InlineKeyboardButton(text="📥 دانلود بکاپ SQL", callback_data="adm_dl_db_sql"),
            InlineKeyboardButton(text="📥 دانلود بکاپ DB", callback_data="adm_dl_db_bin")
        ]
    ]
    if pending_txs:
        kb.insert(0, [InlineKeyboardButton(text="✍️ بررسی فیش‌های در انتظار", callback_data="btn_admin_review_pending", style="success")])
        
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")])
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.0 Dynamic Configuration Keys Editor
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_edit_config_menu")
async def adm_edit_config_menu(callback: CallbackQuery):
    """Renders keyboard to select and update system config variables."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    txt = (
        "⚙️ **تنظیمات و پیکربندی متغیرهای سیستم**\n\n"
        "یکی از متغیرهای زیر را جهت ویرایش انتخاب کنید:"
    )
    
    # Render active list of available editable strings
    kb = [
        [InlineKeyboardButton(text="💳 شماره کارت بانکی", callback_data="cfg_edit_CARD_NUMBER")],
        [InlineKeyboardButton(text="👤 نام دارنده کارت", callback_data="cfg_edit_CARD_HOLDER")],
        [InlineKeyboardButton(text="📢 آیدی پشتیبانی تلگرام", callback_data="cfg_edit_SUPPORT_USERNAME")],
        [InlineKeyboardButton(text="🔗 لینک بنر تصویر شروع", callback_data="cfg_edit_WELCOME_BANNER_URL")],
        [InlineKeyboardButton(text="💎 آدرس ولت TON", callback_data="cfg_edit_TON_ADDRESS")],
        [InlineKeyboardButton(text="💵 آدرس ولت USDT", callback_data="cfg_edit_USDT_ADDRESS")],
        [InlineKeyboardButton(text="🔴 آدرس ولت TRX", callback_data="cfg_edit_TRX_ADDRESS")],
        [InlineKeyboardButton(text="🔑 آیدی کانال جوین اجباری", callback_data="cfg_edit_FORCE_JOIN_CHAT_ID")],
        [InlineKeyboardButton(text="📢 لینک کانال جوین اجباری", callback_data="cfg_edit_FORCE_JOIN_LINK")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ]
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("cfg_edit_"))
async def adm_cfg_edit_key(callback: CallbackQuery, state: FSMContext):
    """Sets state to collect custom value corresponding to selected setting key."""
    key = callback.data.replace("cfg_edit_", "")
    await state.update_data(editing_config_key=key)
    current_val = config.get(key, "تعریف نشده")
    
    await callback.message.edit_text(
        f"✏️ **ویرایش متغیر: {key}**\n\n"
        f"مقدار فعلی: `{current_val}`\n\n"
        "لطفاً مقدار جدید را ارسال نمایید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_edit_config_menu")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_config_key_value)
    await callback.answer()

@router.message(AdminStates.waiting_for_config_key_value)
async def process_cfg_key_value_save(message: Message, state: FSMContext):
    """Saves updated configuration key parameter in configuration storage file."""
    state_data = await state.get_data()
    key = state_data["editing_config_key"]
    val_str = message.text.strip()
    
    if key == "FORCE_JOIN_CHAT_ID":
        try:
            config[key] = int(val_str)
        except ValueError:
            return await message.reply("❌ خطا: آیدی کانال حتما باید به صورت یک عدد علامت‌دار (مانند 100123456789-) وارد شود.")
    else:
        config[key] = val_str
        
    save_config_file()
    await state.clear()
    
    await message.reply(
        f"✅ متغیر `{key}` با موفقیت ویرایش گردید و ثبت شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به منوی تنظیمات", callback_data="adm_edit_config_menu")]
        ])
    )

# ---------------------------------------------------------------------------
# 11.0.1 Dynamic External Texts Localization Manager
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_manage_texts_menu")
async def adm_manage_texts_menu(callback: CallbackQuery, state: FSMContext):
    """Provides complete text manager interface with dynamic file tools."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    await state.clear()
    
    txt = (
        "📝 **مدیریت و ویرایش متون و پیام‌های ربات**\n\n"
        "شما می‌توانید پیام‌های سیستمی ربات را به صورت تکی ویرایش نمایید، "
        "یا کل فایل پیام‌ها را به صورت JSON دانلود و پس از اعمال تغییرات دلخواه، آپلود کنید تا فوراً تغییر کند."
    )
    
    kb = [
        [InlineKeyboardButton(text="✏️ ویرایش پیام شروع (/start)", callback_data="txt_edit_welcome_text")],
        [InlineKeyboardButton(text="✏️ ویرایش پیام منوی اصلی", callback_data="txt_edit_main_menu_text")],
        [InlineKeyboardButton(text="✏️ ویرایش پیام راهنمای پشتیبانی", callback_data="txt_edit_support_text")],
        [InlineKeyboardButton(text="✏️ ویرایش پیام وضعیت تعمیرات", callback_data="txt_edit_maintenance_text")],
        [InlineKeyboardButton(text="✏️ ویرایش پیام تعطیلی فروشگاه", callback_data="txt_edit_shop_closed_text")],
        [InlineKeyboardButton(text="✏️ ویرایش پیام کارت به کارت", callback_data="txt_edit_card_payment_instructions")],
        [InlineKeyboardButton(text="📥 دانلود کل فایل متون (JSON)", callback_data="txt_download_json")],
        [InlineKeyboardButton(text="📤 آپلود فایل جدید متون (JSON)", callback_data="txt_upload_json")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ]
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("txt_edit_"))
async def adm_txt_edit_key(callback: CallbackQuery, state: FSMContext):
    """Sets state to collect custom text string for localized variable."""
    key = callback.data.replace("txt_edit_", "")
    await state.update_data(editing_text_key=key)
    current_val = bot_texts.get(key, DEFAULT_TEXTS.get(key, "تعریف نشده"))
    
    await callback.message.edit_text(
        f"✏️ **ویرایش متن سیستمی: {key}**\n\n"
        f"مقدار فعلی:\n`{current_val}`\n\n"
        "لطفاً متن جدید را تایپ و ارسال کنید:\n"
        "_(دقت کنید متغیرهایی مانند `{balance}`، `{amount}` و... در صورت وجود دست‌نخورده باقی بمانند)_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_manage_texts_menu")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_text_key_value)
    await callback.answer()

@router.message(AdminStates.waiting_for_text_key_value)
async def process_txt_key_value_save(message: Message, state: FSMContext):
    """Saves updated localized string in external texts dictionary storage."""
    state_data = await state.get_data()
    key = state_data["editing_text_key"]
    val_str = message.text.strip()
    
    # Store and apply live values
    bot_texts[key] = val_str
    save_texts_file()
    await state.clear()
    
    await message.reply(
        f"✅ پیام مربوط به متغیر `{key}` با موفقیت ویرایش و ثبت شد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به مدیریت متون", callback_data="adm_manage_texts_menu")]
        ])
    )

@router.callback_query(F.data == "txt_download_json")
async def txt_download_json_callback(callback: CallbackQuery):
    """Sends current reseller_texts.json raw format to admin."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    if not os.path.exists(TEXTS_PATH):
        load_or_create_texts()
        
    try:
        doc = FSInputFile(path=TEXTS_PATH, filename="reseller_texts.json")
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 فایل کامل متون و پیام‌های سیستمی ربات")
        await callback.answer("✅ فایل متون ارسال شد.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال فایل: {e}", show_alert=True)

@router.callback_query(F.data == "txt_upload_json")
async def txt_upload_json_callback(callback: CallbackQuery, state: FSMContext):
    """Requests replacement JSON document to overwrite current bot_texts."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "📤 **آپلود مستقیم فایل reseller_texts.json**\n\n"
        "لطفاً فایل متنی جدید خود را با فرمت `.json` و با نام ترجیحی `reseller_texts.json` در همین بخش ارسال نمایید:\n"
        "⚠️ هشدار: ساختار کلیدها باید دقیقاً مشابه نمونه اصلی باشد.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_manage_texts_menu")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_texts_json_upload)
    await callback.answer()

@router.message(AdminStates.waiting_for_texts_json_upload, F.document)
async def process_texts_json_upload_save(message: Message, state: FSMContext):
    """Validates uploaded texts configuration and overwrites the active dictionary."""
    doc: Document = message.document
    if not doc.file_name.endswith(".json"):
        return await message.reply("❌ خطا: فایل ارسالی باید دارای پسوند معتبر .json باشد.")
        
    await message.reply("⏳ در حال دریافت و اعتبارسنجی فایل متون...")
    
    try:
        file_info = await bot.get_file(doc.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        content = downloaded_file.read().decode("utf-8")
        parsed_data = json.loads(content)
        
        # Verify correctness by checking default structural keys
        missing_keys = [k for k in DEFAULT_TEXTS.keys() if k not in parsed_data]
        if missing_keys:
            return await message.reply(f"❌ خطا در قالب‌بندی: برخی از کلیدهای پیش‌فرض ساختاری ربات در این فایل یافت نشدند.\nکلیدهای مفقوده: `{', '.join(missing_keys)}`")
            
        # Overwrite file
        with open(TEXTS_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=4, ensure_ascii=False)
            
        # Reload internal dynamic global configurations
        global bot_texts
        bot_texts = load_or_create_texts()
        
        await state.clear()
        await message.reply(
            "✅ فایل جدید متون با موفقیت جایگزین شد و تغییرات بلافاصله روی ربات اعمال گردید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به مدیریت متون", callback_data="adm_manage_texts_menu")]
            ])
        )
    except Exception as e:
        await message.reply(f"❌ خطا در پردازش یا تجزیه ساختار فایل متون ارسالی: {e}")

# ---------------------------------------------------------------------------
# 11.1 Toggles (Maintenance & Shop Status)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_toggle_maint")
async def adm_toggle_maint(callback: CallbackQuery, state: FSMContext):
    """Toggles active state of Maintenance Mode."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    config["MAINTENANCE_MODE"] = not config.get("MAINTENANCE_MODE", False)
    save_config_file()
    status_word = "فعال" if config["MAINTENANCE_MODE"] else "غیرفعال"
    await callback.answer(f"🔧 وضعیت تعمیرات ربات {status_word} شد.", show_alert=True)
    await admin_panel_callback(callback, state)

@router.callback_query(F.data == "adm_toggle_shop")
async def adm_toggle_shop(callback: CallbackQuery, state: FSMContext):
    """Toggles active state of Shop Open/Closed."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    config["SHOP_CLOSED"] = not config.get("SHOP_CLOSED", False)
    save_config_file()
    status_word = "بسته" if config["SHOP_CLOSED"] else "باز"
    await callback.answer(f"🛒 فروشگاه {status_word} شد.", show_alert=True)
    await admin_panel_callback(callback, state)

# ---------------------------------------------------------------------------
# 11.2 Exports and Downloads
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_dl_users")
async def download_users_csv(callback: CallbackQuery):
    """Outputs internal registered users list into structured UTF-8 encoded CSV file format."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "Telegram ID", "Username", "First Name", "Balance (Tomans)", "Joined At", "Is Active", "Is Banned"])
    
    with SessionLocal() as db:
        users = db.query(DBUser).all()
        for u in users:
            writer.writerow([u.id, u.telegram_id, u.username or "", u.first_name or "", u.balance, u.joined_at, u.is_active, u.is_banned])
            
    csv_bytes = out.getvalue().encode("utf-8")
    doc = BufferedInputFile(csv_bytes, filename="users_export.csv")
    
    try:
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 لیست کامل کاربران عضو ربات")
        await callback.answer("✅ فایل با موفقیت صادر شد.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال فایل: {e}", show_alert=True)

@router.callback_query(F.data == "adm_dl_txs")
async def download_transactions_csv(callback: CallbackQuery):
    """Compiles local transactions data entries to standard CSV structure."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "User ID", "Type", "Amount", "Status", "Description", "Date", "Receipt Image ID", "TX Hash"])
    
    with SessionLocal() as db:
        txs = db.query(DBTransaction).all()
        for t in txs:
            writer.writerow([t.id, t.user_id, t.type, t.amount, t.status, t.description or "", t.date, t.receipt_image_id or "", t.tx_hash or ""])
            
    csv_bytes = out.getvalue().encode("utf-8")
    doc = BufferedInputFile(csv_bytes, filename="transactions_export.csv")
    
    try:
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 لیست کامل تراکنش‌های ثبت شده")
        await callback.answer("✅ فایل با موفقیت صادر شد.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال فایل: {e}", show_alert=True)

@router.callback_query(F.data == "adm_dl_db_bin")
async def download_db_binary(callback: CallbackQuery):
    """Packages live database file for direct secure administrative downloads."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    db_file_path = "reseller_bot.db"
    if not os.path.exists(db_file_path):
        return await callback.answer("❌ دیتابیس در مسیر جاری یافت نشد.", show_alert=True)
        
    try:
        doc = FSInputFile(path=db_file_path, filename="reseller_bot.db")
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 دیتابیس باینری فعلی سیستم (SQLite)")
        await callback.answer("✅ فایل دیتابیس با موفقیت ارسال شد.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال دیتابیس: {e}", show_alert=True)

@router.callback_query(F.data == "adm_dl_db_sql")
async def download_db_sql_dump(callback: CallbackQuery):
    """Produces structured logical SQL export containing DDL/DML statements."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    import sqlite3
    db_file_path = "reseller_bot.db"
    if not os.path.exists(db_file_path):
        return await callback.answer("❌ دیتابیس یافت نشد.", show_alert=True)
        
    try:
        conn = sqlite3.connect(db_file_path)
        out = io.StringIO()
        for line in conn.iterdump():
            out.write(line + "\n")
        conn.close()
        
        sql_bytes = out.getvalue().encode("utf-8")
        doc = BufferedInputFile(sql_bytes, filename="reseller_bot_dump.sql")
        
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 بکاپ کامل ساختاری و داده‌ای SQL")
        await callback.answer("✅ بکاپ SQL با موفقیت ارسال شد.")
    except Exception as e:
        await callback.answer(f"❌ خطا در تولید بکاپ: {e}", show_alert=True)

# ---------------------------------------------------------------------------
# 11.3 Stats Panel
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_stats")
async def adm_stats_callback(callback: CallbackQuery):
    """Queries and displays local database and central balance diagnostics."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text("⏳ در حال استخراج و تحلیل داده‌های مالی...")
    
    res = api.get_balance()
    central_bal_text = "خطا در اتصال به وب‌سرویس"
    if res and res.get("success"):
        central_bal_text = f"{int(res.get('balance', 0)):,} تومان"
        
    with SessionLocal() as db:
        total_users = db.query(DBUser).count()
        total_srv = db.query(DBService).count()
        total_pending = db.query(DBTransaction).filter(DBTransaction.status == "pending").count()
        user_balances_sum = sum(u.balance for u in db.query(DBUser).all())
        
    txt = (
        "📊 **گزارش آمار و فرآیندهای مالی ربات**\n\n"
        f"👥 کل کاربران عضو: **{total_users}** نفر\n"
        f"🛠 کل سرویس‌های فعال: **{total_srv}** عدد\n"
        f"⏳ فیش‌های معلق: **{total_pending}** عدد\n\n"
        f"💳 مجموع موجودی کاربران: **{int(user_balances_sum):,}** تومان\n"
        f"🔌 اعتبار تایید شده در وب‌سرویس اصلی: **{central_bal_text}**"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل ادمین", callback_data="btn_admin_panel")]
    ])
    await callback.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.4 Central API Balance Check
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_central_bal")
async def adm_central_bal_callback(callback: CallbackQuery):
    """Establishes transaction call on master API to query central reseller balance."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text("⏳ در حال استعلام تراز مالی وب‌سرویس...")
    res = api.get_balance()
    if res and res.get("success"):
            bal = res.get("balance", 0)
            txt = (
                "🔌 **موجودی حساب وب‌سرویس نماینده**\n\n"
                f"موجودی فعلی حساب شما در پنل اصلی: **{int(bal):,}** تومان\n\n"
                "تراکنش‌های خرید مستقیم از این اعتبار کسر می‌شود."
            )
    else:
        txt = "❌ دریافت اطلاعات موجودی وب‌سرویس اصلی با خطا مواجه شد."
            
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
        ])
        await callback.message.edit_text(txt, reply_markup=kb, parse_mode="Markdown")
        await callback.answer()

# ---------------------------------------------------------------------------
# 11.5 Plan Customization (Overrides) Menu
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_plan_customize_menu")
async def adm_plan_customize_menu(callback: CallbackQuery, state: FSMContext):
    """Presents existing plans from central server to override title or price."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    await callback.message.edit_text("⏳ در حال بارگذاری لیست پلن‌های فعال...")
    
    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.message.edit_text("❌ خطا در دریافت پلن‌ها از سرور.", reply_markup=back_to_menu_keyboard())
        
    plans = plans_data.get("plans", [])
    kb = []
    
    with SessionLocal() as db:
        for p in plans:
            override = db.query(DBPlanOverride).filter(DBPlanOverride.plan_id == p['id']).first()
            if override and override.is_hidden:
                color_emoji = "🔴"
            elif override and (override.custom_title or override.custom_price is not None):
                color_emoji = "🔵"
            else:
                color_emoji = "🟢"
                
            p_title = override.custom_title if (override and override.custom_title) else p['title']
            p_price = int(override.custom_price) if (override and override.custom_price is not None) else int(p['price'])
            
            btn_txt = f"{color_emoji} {p_title} ({p_price:,} ت)"
            kb.append([InlineKeyboardButton(text=btn_txt, callback_data=f"adm_override_select_{p['id']}")])
            
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل ادمین", callback_data="btn_admin_panel")])
    await callback.message.edit_text(
        "✏️ پلنی که قصد تغییر مشخصات محلی (عنوان، قیمت یا وضعیت نمایش) آن را دارید انتخاب کنید:\n\n"
        "🟢: فعال و بدون تغییر\n"
        "🔵: ویرایش شده محلی\n"
        "🔴: پنهان شده از دید کاربران",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("adm_override_select_"))
async def adm_override_select_callback(callback: CallbackQuery, state: FSMContext):
    """Displays choices to modify either title, price, or visibility of the selected plan."""
    plan_id = int(callback.data.split("_")[3])
    await state.update_data(target_plan_id=plan_id)
    
    with SessionLocal() as db:
        override = db.query(DBPlanOverride).get(plan_id)
        is_hidden = override.is_hidden if override else False
        
    visibility_btn_text = "👁‍🗨 نمایش مجدد به کاربران" if is_hidden else "👁‍🗨 پنهان کردن از کاربران"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ تغییر عنوان پلن (Title)", callback_data="adm_over_title"),
            InlineKeyboardButton(text="💵 تغییر قیمت فروش (Price)", callback_data="adm_over_price")
        ],
        [InlineKeyboardButton(text=visibility_btn_text, callback_data="adm_over_toggle_visibility")],
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="adm_plan_customize_menu")]
    ])
    await callback.message.edit_text(f"شما در حال ویرایش پلن (ID: {plan_id}) هستید. فیلد مورد نظر را انتخاب کنید:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "adm_over_toggle_visibility")
async def adm_over_toggle_visibility_callback(callback: CallbackQuery, state: FSMContext):
    """Toggles visible state parameter of the specified virtual plan layout."""
    state_data = await state.get_data()
    plan_id = state_data["target_plan_id"]
    
    with SessionLocal() as db:
        override = db.query(DBPlanOverride).get(plan_id)
        if not override:
            override = DBPlanOverride(plan_id=plan_id, is_hidden=True)
            db.add(override)
        else:
            override.is_hidden = not override.is_hidden
        db.commit()
        current_status = override.is_hidden
        
    msg = "❌ پلن از دید کاربران پنهان شد." if current_status else "✅ پلن مجدداً برای کاربران فعال و نمایان شد."
    await callback.answer(msg, show_alert=True)
    await adm_plan_customize_menu(callback, state)

@router.callback_query(F.data.startswith("adm_over_"))
async def adm_over_fields_callback(callback: CallbackQuery, state: FSMContext):
    """Prompts corresponding field change details from administrator."""
    field = callback.data.split("_")[2]
    if field == "title":
        await callback.message.edit_text("✏️ عنوان جدید پلن را وارد کنید (مثال: `پلن برنزی ۳۰ گیگ`):", reply_markup=back_to_menu_keyboard(), parse_mode="Markdown")
        await state.set_state(AdminStates.waiting_for_plan_title)
    elif field == "price":
        await callback.message.edit_text("💵 قیمت جدید فروش به کاربران را به **تومان** وارد کنید (به صورت عدد انگلیسی):", reply_markup=back_to_menu_keyboard(), parse_mode="Markdown")
        await state.set_state(AdminStates.waiting_for_plan_price)
    await callback.answer()

@router.message(AdminStates.waiting_for_plan_title)
async def process_plan_title_override(message: Message, state: FSMContext):
    """Saves customized title value inside local SQLite database."""
    new_title = message.text.strip()
    state_data = await state.get_data()
    plan_id = state_data["target_plan_id"]
    
    with SessionLocal() as db:
        override = db.query(DBPlanOverride).get(plan_id)
        if not override:
            override = DBPlanOverride(plan_id=plan_id, custom_title=new_title)
            db.add(override)
        else:
            override.custom_title = new_title
        db.commit()
        
    await message.reply("✅ عنوان پلن به صورت محلی ویرایش شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به منوی ویرایش پلن‌ها", callback_data="adm_plan_customize_menu")]
    ]))
    await state.clear()

@router.message(AdminStates.waiting_for_plan_price)
async def process_plan_price_override(message: Message, state: FSMContext):
    """Saves customized price value inside local SQLite database."""
    new_price_str = message.text.strip()
    if not new_price_str.isdigit():
        return await message.reply("❌ خطا: لطفاً مقدار عددی معتبری وارد کنید.")
        
    new_price = float(new_price_str)
    state_data = await state.get_data()
    plan_id = state_data["target_plan_id"]
    
    with SessionLocal() as db:
        override = db.query(DBPlanOverride).get(plan_id)
        if not override:
            override = DBPlanOverride(plan_id=plan_id, custom_price=new_price)
            db.add(override)
        else:
            override.custom_price = new_price
        db.commit()
        
    await message.reply("✅ قیمت فروش پلن به صورت محلی ویرایش شد.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به منوی ویرایش پلن‌ها", callback_data="adm_plan_customize_menu")]
    ]))
    await state.clear()

# ---------------------------------------------------------------------------
# 11.6 Individual User Configuration Management Console (Search User)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_user_panel_search")
async def adm_user_panel_search(callback: CallbackQuery, state: FSMContext):
    """Requests user Telegram ID or Username to launch search query."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "✏️ آیدی عددی تلگرام یا **نام کاربری بدون @** کاربر مورد نظر را جهت جستجو وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_user_lookup)
    await callback.answer()

@router.message(AdminStates.waiting_for_user_lookup)
async def process_user_lookup(message: Message, state: FSMContext):
    """Validates query and pulls matching user database record."""
    query = message.text.strip()
    
    with SessionLocal() as db:
        if query.isdigit():
            user = db.query(DBUser).filter(DBUser.telegram_id == int(query)).first()
        else:
            clean_username = query.replace("@", "")
            user = db.query(DBUser).filter(DBUser.username.ilike(clean_username)).first()
            
        if not user:
            return await message.reply("❌ خطا: کاربر مورد نظر در پایگاه داده ربات یافت نشد. مجددا تلاش کنید:")
            
        rank, total_spent = calculate_user_rank(db, user.id)
        ban_status = "🚫 مسدود شده" if user.is_banned else "🟢 فعال"
        
    await state.clear()
    
    txt = (
        "👤 **مشخصات و مدیریت تعاملی کاربر**\n\n"
        f"🏷 نام کاربر: **{user.first_name or 'نامشخص'}**\n"
        f"🌐 شناسه کاربری: `{user.telegram_id}`\n"
        f"💬 نام کاربری: @{user.username or 'ندارد'}\n"
        f"💳 موجودی کیف پول: **{int(user.balance):,}** تومان\n"
        f"🎖 سطح و رتبه کاربری: **{rank}**\n"
        f"📊 مجموع حجم تراکنش‌های موفق: **{int(total_spent):,}** تومان\n"
        f"📅 تاریخ عضویت: {user.joined_at.strftime('%Y-%m-%d %H:%M')}\n"
        f"📡 وضعیت دسترسی: **{ban_status}**"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 شارژ دستی حساب", callback_data=f"usr_action_charge_{user.telegram_id}"),
            InlineKeyboardButton(text="✉️ ارسال پیام مستقیم", callback_data=f"usr_action_msg_{user.telegram_id}")
        ],
        [InlineKeyboardButton(text="🚫 مسدود / آزاد سازی کاربر", callback_data=f"usr_action_toggleban_{user.telegram_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ])
    
    await message.reply(txt, reply_markup=kb, parse_mode="Markdown")

# ---------------------------------------------------------------------------
# 11.7 Search Service Panel
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_service_panel_search")
async def adm_service_panel_search(callback: CallbackQuery, state: FSMContext):
    """Requests Service ID, Name, or UUID to locate target service record."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "✏️ **کد لایو سرویس (ID)**، **نام سرویس** یا **کد UUID** هدف را جهت جستجو وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_service_lookup)
    await callback.answer()

@router.message(AdminStates.waiting_for_service_lookup)
async def process_service_lookup(message: Message, state: FSMContext):
    """Locates and displays specific service profile details and direct toggle controls."""
    query = message.text.strip()
    
    with SessionLocal() as db:
        if query.isdigit():
            srv = db.query(DBService).filter((DBService.service_id == int(query)) | (DBService.id == int(query))).first()
        else:
            srv = db.query(DBService).filter((DBService.name.ilike(query)) | (DBService.uuid == query)).first()
            
        if not srv:
            return await message.reply("❌ خطا: سرویس مورد نظر در سیستم یافت نشد. مجددا تلاش کنید:")
            
    # Load diagnostics live
    details = api.get_service_details(srv.service_id)
    status_str = "ناشناس"
    traffic_str = "نامشخص"
    sub_url = srv.sub_url or "نامشخص"
    
    if details and details.get("success"):
        status_str = details.get("status", "active")
        total_gb = details.get("traffic_total_gb", 0)
        used_gb = details.get("traffic_used_gb", 0)
        remain_gb = max(0.0, total_gb - used_gb)
        traffic_str = f"مصرف {used_gb:.2f} از {total_gb:.2f} GB (باقیمانده: {remain_gb:.2f} GB)"
        sub_url = details.get("sub_url", srv.sub_url)
        
    txt = (
        "📡 **اطلاعات فنی سرویس یافت شده**\n\n"
        f"🖥 نام سرویس: **{srv.name}**\n"
        f"🔑 شناسه وب‌سرویس اصلی: `{srv.service_id}`\n"
        f"🌐 شناسه کاربری خریدار (DB ID): `{srv.user_id}`\n"
        f"📊 مصرف ترافیک: **{traffic_str}**\n"
        f"📅 تاریخ انقضا: **{srv.expire_date or 'نامحدود'}**\n"
        f"🔌 وضعیت فعلی: **{status_str}**\n\n"
        f"🔗 لینک اتصال:\n`{sub_url}`"
    )
    
    toggle_label = "🔴 غیرفعال کردن سرویس" if status_str == "active" else "🟢 فعال کردن سرویس"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label, callback_data=f"srv_toggle_{srv.id}")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ])
    
    await message.reply(txt, reply_markup=kb, parse_mode="Markdown")
    await state.clear()

@router.callback_query(F.data.startswith("usr_action_"))
async def process_usr_interactive_actions(callback: CallbackQuery, state: FSMContext):
    """Processes interactive action clicks from user profile management keyboard."""
    parts = callback.data.split("_")
    action = parts[2]
    target_uid = int(parts[3])
    
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    if action == "toggleban":
        with SessionLocal() as db:
            user = db.query(DBUser).filter(DBUser.telegram_id == target_uid).first()
            if not user: return
            user.is_banned = not user.is_banned
            db.commit()
            new_status = user.is_banned
            
        msg = f"🚫 کاربر با موفقیت مسدود شد." if new_status else "🟢 کاربر با موفقیت آزاد گردید."
        await callback.answer(msg, show_alert=True)
        
        # Simulate lookup update
        class DummyMsg:
            def __init__(self, text, from_user, chat):
                self.text = text
                self.from_user = from_user
                self.chat = chat
            async def reply(self, text, reply_markup, parse_mode):
                await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                
        dummy = DummyMsg(str(target_uid), callback.from_user, callback.message.chat)
        await process_user_lookup(dummy, state)
        
    elif action == "charge":
        await state.update_data(charge_target_id=target_uid)
        await callback.message.edit_text(
            "✏️ مبلغ مورد نظر جهت اعمال تراز را وارد کنید:\n"
            "_(عدد مثبت مانند `50000` جهت افزایش و عدد منفی مانند `-20000` جهت کسر تراز)_",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 لغو", callback_data="btn_admin_panel")]
            ]),
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_charge_amount)
        await callback.answer()
        
    elif action == "msg":
        await state.update_data(direct_msg_target_id=target_uid)
        await callback.message.edit_text(
            "✉️ پیام مورد نظر خود را جهت ارسال مستقیم به کاربر بنویسید:\n"
            "_(از قالب بندی استاندارد Markdown پشتیبانی می‌شود)_",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 لغو", callback_data="btn_admin_panel")]
            ]),
            parse_mode="Markdown"
        )
        await state.set_state(AdminStates.waiting_for_direct_message)
        await callback.answer()

@router.message(AdminStates.waiting_for_direct_message)
async def process_direct_message_send(message: Message, state: FSMContext):
    """Sends custom typed administrative message directly to user."""
    state_data = await state.get_data()
    target_uid = state_data["direct_msg_target_id"]
    msg_text = message.text.strip()
    
    await state.clear()
    
    user_banner = (
        "✉️ **پیام جدیدی از مدیریت دریافت شد:**\n\n"
        f"{msg_text}"
    )
    
    try:
        await bot.send_message(chat_id=target_uid, text=user_banner, parse_mode="Markdown")
        await message.reply(
            f"✅ پیام مستقیم شما با موفقیت برای کاربر ({target_uid}) ارسال گردید.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
            ])
        )
    except Exception as e:
        await message.reply(f"❌ خطا در ارسال پیام مستقیم: {e}")

# ---------------------------------------------------------------------------
# 11.8 Manual User Recharge Flow (Fallback wrapper logic matching database interface)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_charge_user")
async def adm_charge_user_callback(callback: CallbackQuery, state: FSMContext):
    """Tolls lookup panel to safely configure balances."""
    await adm_user_panel_search(callback, state)

@router.message(AdminStates.waiting_for_charge_amount)
async def adm_process_charge_amount(message: Message, state: FSMContext):
    """Performs database transaction updating user balance value locally."""
    amount_str = message.text.strip()
    try:
        amount = float(amount_str)
    except ValueError:
        return await message.reply("❌ خطا: لطفاً مقدار عددی معتبری وارد کنید.")
        
    state_data = await state.get_data()
    target_uid = state_data["charge_target_id"]
    
    with SessionLocal() as db:
        user = db.query(DBUser).filter(DBUser.telegram_id == target_uid).first()
        user.balance += amount
        
        tx = DBTransaction(
            user_id=user.id,
            type="ChargeByAdmin",
            amount=amount,
            status="success",
            description=f"تغییر تراز دستی توسط مدیریت: {amount:,} تومان"
        )
        db.add(tx)
        db.commit()
        new_balance = user.balance
        
    await message.reply(
        f"✅ عملیات با موفقیت اعمال شد.\n\n"
        f"تغییرات: **{amount:+,}** تومان\n"
        f"موجودی نهایی کاربر: **{int(new_balance):,}** تومان",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
        ])
    )
    
    try:
        status_word = "شارژ" if amount > 0 else "کسر"
        await bot.send_message(
            chat_id=target_uid,
            text=f"🔔 **گزارش تغییر موجودی حساب**\n\nمبلغ **{int(abs(amount)):,}** تومان از حساب شما **{status_word}** شد.\nموجودی جدید: **{int(new_balance):,}** تومان"
        )
    except Exception:
        pass
        
    await state.clear()

# ---------------------------------------------------------------------------
# 11.9 Broadcast System
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_broadcast_mode_select")
async def adm_broadcast_mode_select(callback: CallbackQuery, state: FSMContext):
    """Offers choice between forward or raw copy mode for global communications."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 روش اول: کپی مستقیم (Copy)", callback_data="set_broad_copy")],
        [InlineKeyboardButton(text="🔄 روش دوم: فوروارد مستقیم (Forward)", callback_data="set_broad_forward")],
        [InlineKeyboardButton(text="🔙 لغو", callback_data="btn_admin_panel")]
    ])
    
    await callback.message.edit_text(
        "📢 **انتخاب شیوه ارسال پیام همگانی:**\n\n"
        "▫️ **روش کپی:** متن یا فایل ارسالی شما مستقیماً با نام ربات فرستاده می‌شود.\n\n"
        "▫️ **روش فوروارد:** پیام منتخب شما از کانال یا گروه فوروارد می‌شود. (برای نگهداشتن شکلک‌های ویژه، پیوست‌ها و قالب‌بندی‌های پریمیوم مناسب‌تر است)",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_broadcast_mode)
    await callback.answer()

@router.callback_query(F.data.startswith("set_broad_"), AdminStates.waiting_for_broadcast_mode)
async def process_broad_mode_set(callback: CallbackQuery, state: FSMContext):
    """Saves selected transmission mechanism and prompts the message content."""
    mode = "copy" if callback.data == "set_broad_copy" else "forward"
    await state.update_data(broadcast_send_mode=mode)
    
    await callback.message.edit_text(
        f"📥 لطفاً پیام خود را ارسال کنید (این پیام با روش **{mode.upper()}** برای تمام اعضا فرستاده خواهد شد):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 لغو", callback_data="btn_admin_panel", style="danger")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback.answer()

@router.message(AdminStates.waiting_for_broadcast_msg)
async def capture_broadcast_message(message: Message, state: FSMContext):
    """Registers source parameters and requests ultimate deployment authorization."""
    state_data = await state.get_data()
    mode = state_data["broadcast_send_mode"]
    
    with SessionLocal() as db:
        target_count = db.query(DBUser).filter(DBUser.is_active == True).count()
        
    eta_seconds = int(target_count * 0.05)
    
    await state.update_data(
        src_msg_id=message.message_id,
        src_chat_id=message.chat.id,
        target_pool_count=target_count
    )
    
    preview_txt = (
        "⚠️ **تاییدیه نهایی ارسال پیام همگانی**\n\n"
        f"▫️ تعداد گیرندگان فعال: **{target_count}** کاربر\n"
        f"▫️ شیوه ارسال: **{mode.upper()}**\n"
        f"▫️ زمان تقریبی فرآیند (ETA): ~**{eta_seconds}** ثانیه\n\n"
        "آیا برای شروع ارسال همگانی اطمینان دارید؟"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و ارسال عمومی", callback_data="adm_confirm_broadcast_go", style="success"),
            InlineKeyboardButton(text="❌ انصراف", callback_data="btn_admin_panel", style="danger")
        ]
    ])
    
    await message.reply(preview_txt, reply_markup=kb, parse_mode="Markdown")
    await state.set_state(AdminStates.waiting_for_broadcast_confirm)

@router.callback_query(F.data == "adm_confirm_broadcast_go", AdminStates.waiting_for_broadcast_confirm)
async def execute_global_broadcast(callback: CallbackQuery, state: FSMContext):
    """Triggers global background sending sequence with rate limits and active filtering."""
    state_data = await state.get_data()
    mode = state_data["broadcast_send_mode"]
    src_msg_id = state_data["src_msg_id"]
    src_chat_id = state_data["src_chat_id"]
    
    await callback.message.edit_text("⏳ فرآیند ارسال پیام همگانی آغاز شد. گزارش نهایی به زودی ارسال می‌شود...")
    
    with SessionLocal() as db:
        users = db.query(DBUser).filter(DBUser.is_active == True).all()
        
    success_count = 0
    failed_count = 0
    
    for u in users:
        try:
            if mode == "copy":
                await bot.copy_message(
                    chat_id=u.telegram_id,
                    from_chat_id=src_chat_id,
                    message_id=src_msg_id
                )
            else:
                await bot.forward_message(
                    chat_id=u.telegram_id,
                    from_chat_id=src_chat_id,
                    message_id=src_msg_id
                )
            success_count += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            try:
                if mode == "copy":
                    await bot.copy_message(chat_id=u.telegram_id, from_chat_id=src_chat_id, message_id=src_msg_id)
                else:
                    await bot.forward_message(chat_id=u.telegram_id, from_chat_id=src_chat_id, message_id=src_msg_id)
                success_count += 1
            except Exception:
                failed_count += 1
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            failed_count += 1
            with SessionLocal() as db:
                db_user = db.query(DBUser).filter(DBUser.telegram_id == u.telegram_id).first()
                if db_user:
                    db_user.is_active = False
                    db.commit()
            logger.info(f"User {u.telegram_id} marked inactive due to block/deletion.")
        except Exception as e:
            failed_count += 1
            logger.error(f"Error broadcasting to {u.telegram_id}: {e}")
            
    report_txt = (
        "📢 **گزارش پایانی کمپین پیام همگانی**\n\n"
        f"✅ ارسال موفقیت‌آمیز: **{success_count}** کاربر\n"
        f"❌ ناموفق / مسدود شده: **{failed_count}** کاربر\n\n"
        "ℹ️ کاربرانی که ربات را مسدود یا اکانت خود را دیلیت کرده‌اند، برای کاهش بار پردازش در دفعات بعدی غیرفعال شدند."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ])
    
    await callback.message.reply(report_txt, reply_markup=kb, parse_mode="Markdown")
    await state.clear()
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.10 Paginated User List View (2 Columns)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("adm_view_users_"))
async def adm_view_users_callback(callback: CallbackQuery):
    """Renders local user records using modular offset paging."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    page = int(callback.data.split("_")[3])
    limit = 5
    offset = page * limit
    
    with SessionLocal() as db:
        total_users = db.query(DBUser).count()
        users = db.query(DBUser).order_by(desc(DBUser.id)).offset(offset).limit(limit).all()
        
    txt = "👥 **لیست کاربران دیتابیس (صفحه‌بندی شده):**\n\n"
    for u in users:
        with SessionLocal() as db:
            rank, _ = calculate_user_rank(db, u.id)
        status_symbol = "🟢" if u.is_active else "🔴"
        ban_text = " [ مسدود شده ]" if u.is_banned else ""
        txt += f"👤 {status_symbol} [{u.first_name or 'Unknown'}](tg://user?id={u.telegram_id}) (`{u.telegram_id}`){ban_text}\n"
        txt += f"▫️ رتبه: **{rank}**\n"
        txt += f"▫️ تراز حساب: **{int(u.balance):,}** تومان\n"
        txt += f"▫️ پیوستن: {u.joined_at.strftime('%Y-%m-%d %H:%M')}\n\n"
            
    kb_nav = []
    if page > 0:
        kb_nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"adm_view_users_{page - 1}"))
    if offset + limit < total_users:
        kb_nav.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"adm_view_users_{page + 1}"))
        
    kb = [kb_nav] if kb_nav else []
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")])
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.11 Paginated Services List View (2 Columns)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("adm_view_services_"))
async def adm_view_services_callback(callback: CallbackQuery):
    """Renders modular list of localized service registrations with offsets."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    page = int(callback.data.split("_")[3])
    limit = 5
    offset = page * limit
    
    with SessionLocal() as db:
        total_srv = db.query(DBService).count()
        services = db.query(DBService).order_by(desc(DBService.id)).offset(offset).limit(limit).all()
        
    txt = "🛠 **لیست سرویس‌های خریداری شده:**\n\n"
    for s in services:
        txt += f"🖥 سرویس: **{s.name}** (ID: {s.service_id})\n"
        txt += f"▫️ آیدی خریدار: `{s.user_id}`\n"
        txt += f"▫️ کلید UUID:\n`{s.uuid}`\n"
        txt += f"▫️ وضعیت: {s.status}\n\n"
        
    kb_nav = []
    if page > 0:
        kb_nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"adm_view_services_{page - 1}"))
    if offset + limit < total_srv:
        kb_nav.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"adm_view_services_{page + 1}"))
        
    kb = [kb_nav] if kb_nav else []
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")])
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.12 Paginated Transactions List View (2 Columns)
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("adm_view_txs_"))
async def adm_view_txs_callback(callback: CallbackQuery):
    """Loads and lists financial transaction ledgers with incremental pages."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    page = int(callback.data.split("_")[3])
    limit = 5
    offset = page * limit
    
    with SessionLocal() as db:
        total_txs = db.query(DBTransaction).count()
        transactions = db.query(DBTransaction).order_by(desc(DBTransaction.id)).offset(offset).limit(limit).all()
        
    txt = "💰 **گزارش تراکنش‌های مالی اخیر:**\n\n"
    for t in transactions:
        sign = "+" if t.amount > 0 else ""
        txt += f"🔋 تراکنش: **{t.type}** (ID: {t.id})\n"
        txt += f"▫️ مبلغ: **{sign}{int(t.amount):,}** تومان\n"
        txt += f"▫️ وضعیت تراکنش: **{t.status}**\n"
        txt += f"▫️ شرح: {t.description or '-'}\n"
        txt += f"▫️ تاریخ: {t.date.strftime('%Y-%m-%d %H:%M')}\n\n"
        
    kb_nav = []
    if page > 0:
        kb_nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"adm_view_txs_{page - 1}"))
    if offset + limit < total_txs:
        kb_nav.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"adm_view_txs_{page + 1}"))
        
    kb = [kb_nav] if kb_nav else []
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")])
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.13 Pending Receipt Verification View
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_admin_review_pending")
async def admin_review_pending_callback(callback: CallbackQuery):
    """Loads first active pending receipt photo and attaches verification inline."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    with SessionLocal() as db:
        tx = db.query(DBTransaction).filter(DBTransaction.status == "pending").first()
        if not tx:
            return await callback.message.edit_text("✅ تمام فیش‌های واریزی بررسی شده‌اند و در حال حاضر فیش جدیدی موجود نیست.", reply_markup=back_to_menu_keyboard())
            
        user = db.query(DBUser).get(tx.user_id)
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ تایید و افزایش موجودی", callback_data=f"tx_approve_{tx.id}", style="success"),
            InlineKeyboardButton(text="❌ رد رسید پرداخت", callback_data=f"tx_reject_{tx.id}", style="danger")
        ],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ])
    
    if tx.receipt_image_id:
        await bot.send_photo(
            chat_id=callback.from_user.id,
            photo=tx.receipt_image_id,
            caption=f"👤 کاربر: {user.first_name or ''} ({user.telegram_id})\n💵 مبلغ درخواستی: **{tx.amount:,}** تومان\n\nآیا این رسید معتبر است؟",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(
            f"👤 کاربر: {user.first_name or ''} ({user.telegram_id})\n"
            f"💵 مبلغ: **{tx.amount:,}** تومان\n"
            f"ℹ️ توضیحات: {tx.description or 'ندارد'}\n"
            f"🔑 هش تراکنش: `{tx.tx_hash or 'ندارد'}`\n\n"
            "آیا مایل به تایید این واریزی بدون فیش تصویری هستید؟",
            reply_markup=kb,
            parse_mode="Markdown"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("tx_"))
async def admin_decision_callback(callback: CallbackQuery):
    """Updates selected receipt evaluation state (accept/deny) and alerts user."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    parts = callback.data.split("_")
    action = parts[1]
    tx_id = int(parts[2])
    
    with SessionLocal() as db:
        tx = db.query(DBTransaction).get(tx_id)
        if not tx or tx.status != "pending":
            return await callback.answer("⚠️ این فیش قبلاً تعیین تکلیف شده است.", show_alert=True)
            
        user = db.query(DBUser).get(tx.user_id)
        
        if action == "approve":
            tx.status = "success"
            user.balance += tx.amount
            db.commit()
            
            await callback.answer("✅ تراکنش با موفقیت تایید شد و موجودی کاربر افزایش یافت.", show_alert=True)
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"✅ **...واریز کارت به کارت شما تایید شد!**\n\nمبلغ **{int(tx.amount):,}** تومان به کیف پول شما افزوده شد.\nموجودی فعلی شما: **{int(user.balance):,}** تومان"
                )
            except Exception:
                pass
            
            try:
                await callback.message.edit_caption(caption=f"✅ رسید به مبلغ {int(tx.amount):,} تومان توسط ادمین **تایید** شد.")
            except Exception:
                await callback.message.edit_text(text=f"✅ رسید به مبلغ {int(tx.amount):,} تومان توسط ادمین **تایید** شد.")

            for admin_id in config["ADMIN_IDS"]:
                if admin_id != callback.from_user.id:
                    try:
                        await bot.send_message(chat_id=admin_id, text=f"💰 افزایش تراز تایید شده: کاربر {user.telegram_id} مبلغ {tx.amount:,} تومان دریافت کرد.")
                    except Exception: pass
        else:
            tx.status = "rejected"
            db.commit()
            
            await callback.answer("❌ تراکنش رد شد.", show_alert=True)
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"❌ **تراکنش واریز شما تایید نشد!**\n\nدرخواست شارژ به مبلغ **{int(tx.amount):,}** تومان رد شد. در صورت نیاز با پشتیبانی در ارتباط باشید."
                )
            except Exception:
                pass
                
            try:
                await callback.message.edit_caption(caption=f"❌ رسید به مبلغ {int(tx.amount):,} تومان توسط ادمین **رد** شد.")
            except Exception:
                await callback.message.edit_text(text=f"❌ رسید به مبلغ {int(tx.amount):,} تومان توسط ادمین **رد** شد.")

# ---------------------------------------------------------------------------
# 12. Automated Scheduled Tasks (Backups)
# ---------------------------------------------------------------------------
async def backup_scheduler():
    """Periodically archives database schema and sends SQLite file to active admins."""
    while True:
        if config.get("BACKUP_ENABLED"):
            interval_seconds = config.get("BACKUP_INTERVAL_HOURS", 12) * 3600
            await asyncio.sleep(interval_seconds)
            
            db_file_path = "reseller_bot.db"
            if os.path.exists(db_file_path):
                print("[Backup System] Creating and sending automatic database backup to admins...")
                for admin_id in config["ADMIN_IDS"]:
                    try:
                        backup_file = FSInputFile(
                            path=db_file_path,
                            filename=f"backup_reseller_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        )
                        await bot.send_document(
                            chat_id=admin_id,
                            document=backup_file,
                            caption=f"📂 **پشتیبان‌گیری خودکار پایگاه داده**\n📅 تاریخ ارسال: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    except Exception as e:
                        print(f"[Backup System] Error sending backup to admin {admin_id}: {e}")
        else:
            await asyncio.sleep(3600)

# ---------------------------------------------------------------------------
# 13. Main Execution Entrypoint
# ---------------------------------------------------------------------------
async def main():
    """Primary asynchronous orchestration loop starting background cron and bot daemon."""
    print("Application daemon is ready. Starting polling services...")
    asyncio.create_task(backup_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
