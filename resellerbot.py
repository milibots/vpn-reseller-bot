# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import json
import re
import urllib.parse
from datetime import datetime

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

import logging
from logging.handlers import RotatingFileHandler
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, FSInputFile
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, desc
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from colorama import init, Fore, Style
from rich.console import Console
from rich.panel import Panel
import getpass

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

def create_systemd_service(venv_python_path):
    """Generates and configures a systemd daemon service for background execution."""
    current_user = getpass.getuser()
    current_dir = os.getcwd()
    service_content = f"""[Unit]
Description=Reseller Telegram Bot Service
After=network.target

[Service]
Type=simple
User={current_user}
WorkingDirectory={current_dir}
ExecStart={venv_python_path} resellerbot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
    local_service_path = "resellerbot.service"
    try:
        with open(local_service_path, "w", encoding="utf-8") as f:
            f.write(service_content)
        console.print(f"[green]✔ Systemd service unit drafted locally at: {local_service_path}[/green]")
        
        systemd_path = "/etc/systemd/system/resellerbot.service"
        if os.getuid == 0 or os.path.exists("/etc/systemd/system/"):
            subprocess.check_call(["sudo", "cp", local_service_path, systemd_path])
            subprocess.check_call(["sudo", "systemctl", "daemon-reload"])
            console.print(Panel(
                f"[bold green]Systemd service created successfully![/bold green]\n\n"
                f"To manage your bot in the background, run:\n"
                f"  [cyan]sudo systemctl enable resellerbot[/cyan]\n"
                f"  [cyan]sudo systemctl start resellerbot[/cyan]\n"
                f"  [cyan]sudo systemctl status resellerbot[/cyan]",
                title="Systemd Installer"
            ))
    except Exception as e:
        console.print(f"[yellow]⚠ Could not automatically write to {systemd_path} due to permission restrictions.[/yellow]")
        console.print(f"You can manually complete this setup by running:\n  [cyan]sudo cp {local_service_path} /etc/systemd/system/ && sudo systemctl daemon-reload[/cyan]")

def load_or_create_config():
    """Initializes and saves the setup configuration parameters dynamically."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
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

    backup_choice = input(f"{Fore.CYAN}7. Enable automatic DB backups? (y/n) [default: n]: {Style.RESET_ALL}").strip().lower()
    backup_enabled = (backup_choice == 'y' or backup_choice == 'yes')
    
    backup_interval = 12
    if backup_enabled:
        backup_interval_input = input(f"{Fore.CYAN}8. Backup interval in hours [default: 12]: {Style.RESET_ALL}").strip()
        if backup_interval_input.isdigit():
            backup_interval = int(backup_interval_input)

    config_data = {
        "BOT_TOKEN": bot_token,
        "ADMIN_IDS": admin_ids,
        "API_KEY": api_key,
        "API_BASE_URL": api_base_url,
        "CARD_NUMBER": card_number or "6037997900000000",
        "CARD_HOLDER": card_holder or "Administrator",
        "BACKUP_ENABLED": backup_enabled,
        "BACKUP_INTERVAL_HOURS": backup_interval
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)
    
    console.print("[green]✔ Configuration written successfully.[/green]")

    service_choice = input(f"{Fore.CYAN}9. Would you like to create a systemctl service unit? (y/n): {Style.RESET_ALL}").strip().lower()
    if service_choice == 'y' or service_choice == 'yes':
        if os.name == "nt":
            venv_python = os.path.join(os.getcwd(), ".venv", "Scripts", "python.exe")
        else:
            venv_python = os.path.join(os.getcwd(), ".venv", "bin", "python")
        create_systemd_service(venv_python)

    return config_data

config = load_or_create_config()

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

Base.metadata.create_all(bind=engine)

def get_or_create_db_user(session, tg_user):
    """Fetches a user profile from SQLite, or creates a new entry if not existing."""
    user = session.query(DBUser).filter(DBUser.telegram_id == tg_user.id).first()
    if not user:
        user = DBUser(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            joined_at=datetime.utcnow()
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user

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
    waiting_for_service_name = State()
    
class AdminStates(StatesGroup):
    """FSM states group for restricted administrative procedures."""
    waiting_for_broadcast = State()
    waiting_for_charge_userid = State()
    waiting_for_charge_amount = State()

# ---------------------------------------------------------------------------
# 5. Keyboards with New Telegram 10.0 Styles (Primary, Success, Danger)
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
# 6. Basic User Messages & Handlers (Persian interface for users)
# ---------------------------------------------------------------------------
@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    """Welcomes new/existing users and shows current wallet status."""
    await state.clear()
    with SessionLocal() as db:
        user = get_or_create_db_user(db, message.from_user)
        welcome_txt = (
            f"🌟 سلام **{user.first_name or ''}** عزیز، به تحریم‌شکن شَب‌راه خوش آمدید.\n\n"
            f"موجودی فعلی شما: **{int(user.balance):,}** تومان\n\n"
            "لطفاً جهت خرید یا مدیریت اشتراک‌های خود از دکمه‌های زیر استفاده کنید."
        )
        await message.reply(welcome_txt, reply_markup=main_menu_keyboard(message.from_user.id), parse_mode="Markdown")

@router.callback_query(F.data == "btn_main_menu")
async def main_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Restores primary inline navigation when callback action is triggered."""
    await state.clear()
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        welcome_txt = (
            f"🌟 منوی اصلی سیستم\n\n"
            f"موجودی کیف پول شما: **{int(user.balance):,}** تومان"
        )
        await callback.message.edit_text(welcome_txt, reply_markup=main_menu_keyboard(callback.from_user.id))
        await callback.answer()

@router.callback_query(F.data == "btn_support")
async def support_callback(callback: CallbackQuery):
    """Displays localized customer service and support details."""
    support_txt = (
        "📞 **ارتباط با پشتیبانی**\n\n"
        "در صورت بروز هرگونه مشکل یا داشتن سوال درباره خرید و فعال‌سازی سرویس‌ها، با آیدی پشتیبانی در ارتباط باشید."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ارسال پیام به پشتیبانی", url="https://t.me/frewgdscew")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
    ])
    await callback.message.edit_text(support_txt, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()

# ---------------------------------------------------------------------------
# 7. Financial & Deposit Processing
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_wallet")
async def wallet_callback(callback: CallbackQuery):
    """Shows user balance inside a localized credit view card."""
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        txt = (
            "💳 **کیف پول حساب کاربری**\n\n"
            f"موجودی فعلی شما: **{int(user.balance):,}** تومان\n\n"
            "جهت شارژ حساب خود می‌توانید از دکمه زیر اقدام نمایید."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏧 افزایش موجودی (کارت به کارت)", callback_data="btn_charge_wallet", style="success")],
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
    
    payment_txt = (
        "🧾 **درخواست واریز کارت به کارت**\n\n"
        f"💵 مبلغ قابل پرداخت: **{amount:,}** تومان\n\n"
        f"💳 شماره کارت جهت واریز:\n`{config['CARD_NUMBER']}`\n\n"
        f"👤 به نام:\n**{config['CARD_HOLDER']}**\n\n"
        "⚠️ لطفاً پس از انتقال وجه، تصویر فیش یا رسید واریزی خود را در همین بخش ارسال کنید."
    )
    await message.reply(payment_txt, reply_markup=back_to_menu_keyboard(), parse_mode="Markdown")
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
# 8. Purchase Flow with Premium Styles
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_buy_service")
async def buy_service_callback(callback: CallbackQuery, state: FSMContext):
    """Fetches plans and structures dynamic buy option inline keyboard."""
    await state.clear()
    await callback.message.edit_text("⏳ در حال دریافت لیست پلن‌ها از سرور...")
    
    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.message.edit_text("❌ خطا در ارتباط با سرور یا دریافت اطلاعات پلن‌ها. لطفا مجدداً تلاش کنید.", reply_markup=back_to_menu_keyboard())
        
    plans = plans_data.get("plans", [])
    if not plans:
        return await callback.message.edit_text("🛒 در حال حاضر پلن فعالی جهت فروش موجود نیست.", reply_markup=back_to_menu_keyboard())
        
    kb = []
    for p in plans:
        btn_txt = f"📦 {p['title']} - {int(p['price']):,} ت"
        kb.append([InlineKeyboardButton(text=btn_txt, callback_data=f"buy_plan_{p['id']}_{int(p['price'])}")])
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")])
    
    await callback.message.edit_text("🛒 لطفاً یکی از پلن‌های زیر را جهت خرید انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("buy_plan_"))
async def buy_plan_callback(callback: CallbackQuery, state: FSMContext):
    """Evaluates checkout affordability and requests custom service descriptor."""
    parts = callback.data.split("_")
    plan_id = int(parts[2])
    price = int(parts[3])
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        if user.balance < price:
            insufficient_txt = (
                f"❌ **موجودی حساب شما کافی نیست!**\n\n"
                f"قیمت پلن: **{price:,}** تومان\n"
                f"موجودی شما: **{int(user.balance):,}** تومان\n\n"
                "لطفاً ابتدا حساب خود را شارژ کنید."
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 افزایش موجودی حساب", callback_data="btn_charge_wallet", style="success")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_buy_service")]
            ])
            return await callback.message.edit_text(insufficient_txt, reply_markup=kb, parse_mode="Markdown")
            
    await state.update_data(buy_plan_id=plan_id, buy_price=price)
    await callback.message.edit_text(
        "✏️ لطفاً یک نام کوتاه انگلیسی (فقط حروف و اعداد بین ۳ تا ۱۲ کاراکتر) برای سرویس خود وارد کنید:\n\nمثال: `myvpn`",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_for_service_name)
    await callback.answer()

@router.message(Form.waiting_for_service_name)
async def process_service_name(message: Message, state: FSMContext):
    """Validates specified name format and displays confirmation invoice."""
    name = message.text.strip()
    if not re.match(r"^[a-zA-Z0-9]{3,12}$", name):
        return await message.reply("❌ خطا: نام سرویس فقط باید شامل حروف انگلیسی و اعداد بین ۳ تا ۱۲ کاراکتر باشد. مجدداً ارسال کنید:")
        
    state_data = await state.get_data()
    plan_id = state_data["buy_plan_id"]
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
    """Requests account creation and balance deduction, then returns the credential URL."""
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
            success_txt = (
                "🎉 **خرید شما با موفقیت انجام شد!**\n\n"
                f"🔗 **لینک اشتراک اختصاصی:**\n`{sub_link}`\n\n"
                "کانفیگ‌های شما صادر شد. می‌توانید از دکمه زیر برای باز کردن مستقیم پنل خود استفاده کنید:"
            )
            
            kb_list = [
                [InlineKeyboardButton(text="📋 کپی سریع لینک اشتراک", copy_text={"text": sub_link}, style="success")],
                [InlineKeyboardButton(text="🔗 باز کردن حساب کاربری (مینی‌اپ)", url=sub_link, style="primary")],
                [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")]
            ]
            
            await callback.message.edit_text(success_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="Markdown")

            admin_msg = (
                f"🔔 **New Purchase Report**\n\n"
                f"👤 Buyer: {user.first_name or 'Unknown'} ({user.telegram_id})\n"
                f"📦 Plan: (ID: {plan_id})\n"
                f"🖥 Service Name: `{name}`\n"
                f"💵 Cost: **{price:,}** Tomans\n"
                f"🔑 UUID: `{res_data.get('uuid')}`"
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
# 9. Services List & Dynamic Clipboard Configs
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
    for s in services:
        kb.append([InlineKeyboardButton(text=f"📡 {s.name or 'سرویس'} | {s.status}", callback_data=f"srv_view_{s.id}")])
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")])
    
    await callback.message.edit_text("🌐 لیست سرویس‌های ثبت شده شما:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("srv_view_"))
async def srv_view_callback(callback: CallbackQuery):
    """Presents detailed subscription analytics and native 10.0 copy actions."""
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
            [InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data=f"srv_view_{srv.id}", style="primary")],
            [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="btn_my_services")]
        ]
        return await callback.message.edit_text(detail_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
        
    status = details.get("status", "active")
    total_gb = details.get("traffic_total_gb", 0)
    used_gb = details.get("traffic_used_gb", 0)
    remain_gb = max(0.0, total_gb - used_gb)
    expire_date = details.get("expire_date") or "نامحدود"
    sub_url = details.get("sub_url") or srv.sub_url
    configs_list = details.get("configs", [])
    
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
        [InlineKeyboardButton(text="📋 کپی لینک اشتراک", copy_text={"text": sub_url}, style="success")],
        [InlineKeyboardButton(text="📸 دریافت کد QR", callback_data=f"srv_qr_{srv_id}", style="primary")]
    ]
    
    if configs_list:
        for index, cfg in enumerate(configs_list[:2]):
            proto_label = "VLESS" if "vless://" in cfg else "VMESS" if "vmess://" in cfg else "Config"
            kb.append([InlineKeyboardButton(text=f"📋 کپی کانفیگ {proto_label} {index+1}", copy_text={"text": cfg}, style="primary")])
            
    kb.append([InlineKeyboardButton(text="🔄 تمدید سرویس", callback_data=f"srv_renew_{srv_id}", style="success")])
    toggle_txt = "🔴 غیرفعال کردن سرویس" if status == "active" else "🟢 فعال کردن سرویس"
    kb.append([InlineKeyboardButton(text=toggle_txt, callback_data=f"srv_toggle_{srv_id}", style="danger")])
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="btn_my_services")])
    
    await callback.message.edit_text(detail_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data.startswith("srv_toggle_"))
async def srv_toggle_callback(callback: CallbackQuery):
    """Processes toggle state instruction and applies active switch on panel."""
    srv_id = int(callback.data.split("_")[2])
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    action = "disable" if srv.status == "active" else "enable"
    await callback.message.edit_text("⏳ در حال ارسال دستور به سرور...")
    
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
    
    await callback.message.edit_text("⏳ در حال تولید کد QR...")
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
            await callback.answer("❌ خطا در تولید عکس کد QR.", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ خطا: {e}", show_alert=True)

@router.callback_query(F.data.startswith("srv_renew_"))
async def srv_renew_callback(callback: CallbackQuery):
    """Queries and renders list of selectable renewal plans for active service."""
    srv_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("⏳ در حال دریافت لیست پلن‌های تمدید...")
    
    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.answer("❌ خطا در دریافت پلن‌ها.", show_alert=True)
        
    plans = plans_data.get("plans", [])
    kb = []
    for p in plans:
        kb.append([InlineKeyboardButton(text=f"🔄 تمدید با {p['title']} - {int(p['price']):,} ت", callback_data=f"renew_confirm_{srv_id}_{p['id']}_{int(p['price'])}")])
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"srv_view_{srv_id}")])
    
    await callback.message.edit_text("🔄 یکی از پلن‌های زیر را جهت تمدید این سرویس انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("renew_confirm_"))
async def renew_confirm_callback(callback: CallbackQuery):
    """Processes final renewal payment, deducts local balance, and registers state."""
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
            f"🔄 **Service Renewal Report**\n\n"
            f"👤 User: {db_user.first_name or 'Unknown'} ({db_user.telegram_id})\n"
            f"🖥 Service: `{srv.name}` (ID: {srv.service_id})\n"
            f"💵 Cost: **{price:,}** Tomans"
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
# 10. Admin Panel Functions (Broadcasting, Pagination, Custom Charge)
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
        
    txt = (
        "⚙️ **پنل مدیریت ربات فروشگاهی نماینده**\n\n"
        f"👥 کل کاربران عضو شده: **{total_users}** کاربر\n"
        f"⏳ فیش‌های در انتظار بررسی: **{len(pending_txs)}** عدد\n"
    )
    
    kb = [
        [InlineKeyboardButton(text="📢 ارسال پیام همگانی (Broadcast)", callback_data="adm_broadcast", style="primary")],
        [InlineKeyboardButton(text="👥 لیست کاربران دیتابیس", callback_data="adm_view_users_0"), InlineKeyboardButton(text="🛠 لیست سرویس‌ها", callback_data="adm_view_services_0")],
        [InlineKeyboardButton(text="💰 لیست تراکنش‌ها", callback_data="adm_view_txs_0"), InlineKeyboardButton(text="💳 تغییر دستی موجودی", callback_data="adm_charge_user")],
        [InlineKeyboardButton(text="🔌 استعلام موجودی وب‌سرویس اصلی", callback_data="adm_central_bal", style="primary")],
    ]
    if pending_txs:
        kb.insert(0, [InlineKeyboardButton(text="✍️ بررسی فیش‌های در انتظار", callback_data="btn_admin_review_pending", style="success")])
        
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")])
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await callback.answer()

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

@router.callback_query(F.data == "adm_charge_user")
async def adm_charge_user_callback(callback: CallbackQuery, state: FSMContext):
    """Prompts target user Telegram identifier to process manual ledger changes."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "✏️ لطفاً آیدی عددی تلگرام کاربر هدف را وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 لغو", callback_data="btn_admin_panel", style="danger")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_charge_userid)
    await callback.answer()

@router.message(AdminStates.waiting_for_charge_userid)
async def adm_process_charge_userid(message: Message, state: FSMContext):
    """Validates Telegram User ID existence and requests credit/deduction value."""
    uid_str = message.text.strip()
    if not uid_str.isdigit():
        return await message.reply("❌ خطا: لطفاً آیدی تلگرام را به صورت عددی معتبر وارد کنید.")
        
    target_uid = int(uid_str)
    with SessionLocal() as db:
        user = db.query(DBUser).filter(DBUser.telegram_id == target_uid).first()
        if not user:
            return await message.reply("❌ خطا: کاربر مورد نظر در پایگاه داده ربات یافت نشد.")
            
    await state.update_data(charge_target_id=target_uid)
    await message.reply(
        f"👤 کاربر انتخاب شد: **{user.first_name or 'نامشخص'}**\n\n"
        "✏️ حالا مبلغ تغییر تراز را به **تومان** وارد کنید:\n"
        "_(جهت افزایش موجودی عدد مثبت مانند 50000 و جهت کسر موجودی عدد منفی مانند -20000 وارد کنید)_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 لغو عملیات", callback_data="btn_admin_panel", style="danger")]
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(AdminStates.waiting_for_charge_amount)

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

# 10.3 Broadcast System
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    """Sets FSM state to accept custom broad broadcast payload message."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "📢 لطفاً پیام خود را جهت ارسال همگانی بنویسید (از فرمت استاندارد Markdown پشتیبانی می‌شود):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 لغو", callback_data="btn_admin_panel", style="danger")]
        ])
    )
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@router.message(AdminStates.waiting_for_broadcast)
async def adm_process_broadcast(message: Message, state: FSMContext):
    """Loops and sends the formatted broadcast message asynchronously with safety sleep."""
    broadcast_text = message.text
    await state.clear()
    
    with SessionLocal() as db:
        users = db.query(DBUser).all()
        
    sent_msg = await message.reply("⏳ در حال ارسال پیام همگانی به کاربران...")
    
    success_count = 0
    failed_count = 0
    
    for u in users:
        try:
            await bot.send_message(chat_id=u.telegram_id, text=broadcast_text, parse_mode="Markdown")
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed_count += 1
            
    await sent_msg.edit_text(
        f"📢 **گزارش ارسال پیام همگانی:**\n\n"
        f"✅ ارسال موفقیت‌آمیز: **{success_count}** کاربر\n"
        f"❌ ناموفق / مسدود کرده: **{failed_count}** کاربر",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
        ])
    )

# 10.4 Paginated User List View
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
        txt += f"👤 [{u.first_name or 'Unkown'}](tg://user?id={u.telegram_id}) (`{u.telegram_id}`)\n"
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

# 10.5 Paginated Services List View
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

# 10.6 Paginated Transactions List View
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
        txt += f"🧾 تراکنش: **{t.type}** (ID: {t.id})\n"
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

# 10.7 Pending Receipt Verification View
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
    
    await bot.send_photo(
        chat_id=callback.from_user.id,
        photo=tx.receipt_image_id,
        caption=f"👤 کاربر: {user.first_name or ''} ({user.telegram_id})\n💵 مبلغ درخواستی: **{tx.amount:,}** تومان\n\nآیا این رسید معتبر است؟",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await callback.message.delete()
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
                    text=f"✅ **واریز کارت به کارت شما تایید شد!**\n\nمبلغ **{int(tx.amount):,}** تومان به کیف پول شما افزوده شد.\nموجودی فعلی شما: **{int(user.balance):,}** تومان"
                )
            except Exception:
                pass
            
            await callback.message.edit_caption(caption=f"✅ رسید به مبلغ {int(tx.amount):,} تومان توسط ادمین **تایید** شد.")

            for admin_id in config["ADMIN_IDS"]:
                if admin_id != callback.from_user.id:
                    try:
                        await bot.send_message(chat_id=admin_id, text=f"💰 Card Top-up Approved: User {user.telegram_id} got +{tx.amount:,} Tomans.")
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
                
            await callback.message.edit_caption(caption=f"❌ رسید به مبلغ {int(tx.amount):,} تومان توسط ادمین **رد** شد.")

# ---------------------------------------------------------------------------
# 11. Automated Scheduled Tasks (Backups)
# ---------------------------------------------------------------------------
async def backup_scheduler():
    """Periodically archives database schema and sends SQLite file to active admins."""
    while True:
        if config.get("BACKUP_ENABLED"):
            interval_seconds = config.get("BACKUP_INTERVAL_HOURS", 12) * 3600
            await asyncio.sleep(interval_seconds)
            
            db_file_path = "reseller_bot.db"
            if os.path.exists(db_file_path):
                print(f"[Backup System] Creating and sending automatic database backup to admins...")
                for admin_id in config["ADMIN_IDS"]:
                    try:
                        backup_file = FSInputFile(
                            path=db_file_path,
                            filename=f"backup_reseller_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                        )
                        await bot.send_document(
                            chat_id=admin_id,
                            document=backup_file,
                            caption=f"📂 **Automatic Reseller Bot Database Backup**\n📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    except Exception as e:
                        print(f"[Backup System] Error sending backup to admin {admin_id}: {e}")
        else:
            await asyncio.sleep(3600)

# ---------------------------------------------------------------------------
# 12. Main Execution Entrypoint
# ---------------------------------------------------------------------------
async def main():
    """Primary asynchronous orchestration loop starting background cron and bot daemon."""
    print("Application daemon is ready. Starting polling services...")
    asyncio.create_task(backup_scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
