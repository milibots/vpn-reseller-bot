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
import html
import random
import string
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

def setup_environment_and_install_dependencies():
    is_venv = sys.prefix != sys.base_prefix
    if not is_venv:
        venv_dir = os.path.join(os.getcwd(), ".venv")
        if not os.path.exists(venv_dir):
            try:
                subprocess.check_call([sys.executable, "-m", "venv", ".venv"])
            except Exception:
                sys.exit(1)
        
        if os.name == "nt":
            venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        else:
            venv_python = os.path.join(venv_dir, "bin", "python")
            
        try:
            subprocess.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
            subprocess.check_call([venv_python, "-m", "pip", "install", "aiogram==3.12.0", "sqlalchemy==2.0.23", "requests==2.31.0", "colorama==0.4.6", "rich==13.7.0"])
        except Exception:
            sys.exit(1)
            
        os.execv(venv_python, [venv_python] + sys.argv)

setup_environment_and_install_dependencies()

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

def escape_md(text: str) -> str:
    if not text:
        return ""
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", str(text))

def escape_md_code(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("\\", "\\\\").replace("`", "\\`")

DEFAULT_TEXTS = {
    "welcome_text": "🌟 سلام *{first_name}* عزیز، به ربات هوشمند {bot_first_name} خوش آمدید\\.\n\n📊 رتبه کاربری شما: *{rank_name}*\nموجودی فعلی شما: *{balance}* تومان\n\nلطفاً جهت خرید یا مدیریت اشتراک‌های خود از دکمه‌های زیر استفاده کنید\\.",
    "main_menu_text": "🌟 منوی اصلی سیستم\n\n📊 سطح کاربری شما: *{rank_name}*\nموجودی کیف پول شما: *{balance}* تومان",
    "support_text": "📞 *ارتباط با پشتیبانی*\n\nدر صورت بروز هرگونه مشکل یا داشتن سوال درباره خرید و فعال‌سازی سرویس‌ها، با آیدی پشتیبانی در ارتباط باشید\\.",
    "wallet_text": "💳 *کیف پول حساب کاربری*\n\nموجودی فعلی شما: *{balance}* تومان\n\nجهت شارژ حساب خود می‌توانید از دکمه زیر اقدام نمایید\\.",
    "card_payment_instructions": "🧾 *درخواست واریز کارت به کارت*\n\n💵 مبلغ قابل پرداخت: *{amount}* تومان\n\n💳 شماره کارت جهت واریز:\n`{card_number}`\n\n👤 به نام:\n*{card_holder}*\n\n⚠️ لطفاً پس از انتقال وجه، تصویر فیش یا رسید واریزی خود را در همین بخش ارسال کنید\\.",
    "crypto_payment_instructions": "💎 *پرداخت با رمزارز {asset}*\n\n📍 لطفاً مبلغ مورد نظر خود را به آدرس زیر واریز نمایید:\n\n`{address}`\n\n⚠️ توجه: پس از تکمیل انتقال، لطفا کد پیگیری \\(TXID / Hash\\) یا عکس رسید پرداخت خود را در همین بخش ارسال نمایید\\.",
    "maintenance_text": "🔧 *ربات در حال حاضر در وضعیت بروزرسانی قرار دارد*\n\nدر این لحظه امکان ارائه خدمات وجود ندارد\\. لطفاً بعداً تلاش کنید یا با پشتیبانی در ارتباط باشید\\.",
    "shop_closed_text": "⚠️ *فروشگاه موقتاً تعطیل است*\n\nامکان ثبت سفارش جدید در حال حاضر وجود ندارد\\. از صبر و شکیبایی شما سپاسگزاریم\\.",
    "purchase_success_text": "🎉 *خرید شما با موفقیت انجام شد\\!*\n\n🔗 *لینک اشتراک اختصاصی:*\n`{sub_link}`\n\n",
    "insufficient_balance_text": "❌ *موجودی حساب شما کافی نیست\\!*\n\nقیمت پلن: *{price}* تومان\nموجودی شما: *{balance}* تومان\n\nلطفاً ابتدا حساب خود را شارژ کنید\\."
}

def load_or_create_texts():
    if os.path.exists(TEXTS_PATH):
        try:
            with open(TEXTS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
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
    with open(TEXTS_PATH, "w", encoding="utf-8") as f:
        json.dump(bot_texts, f, indent=4, ensure_ascii=False)

def load_or_create_config():
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
    
    return config_data

config = load_or_create_config()

def save_config_file():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

DATABASE_URL = "sqlite:///reseller_bot.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class DBUser(Base):
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
    alert_50d = Column(Boolean, default=False)
    alert_1d = Column(Boolean, default=False)
    alert_50p = Column(Boolean, default=False)
    alert_80p = Column(Boolean, default=False)
    alert_90p = Column(Boolean, default=False)
    alert_100p = Column(Boolean, default=False)

class DBTransaction(Base):
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
    __tablename__ = "plan_overrides"
    plan_id = Column(Integer, primary_key=True)
    custom_title = Column(String, nullable=True)
    custom_price = Column(Float, nullable=True)
    is_hidden = Column(Boolean, default=False)

class DBDiscountCode(Base):
    __tablename__ = "discount_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    discount_type = Column(String)
    value = Column(Float)
    usage_limit = Column(Integer, default=1)
    used_count = Column(Integer, default=0)
    expiry_date = Column(DateTime, nullable=True)
    specific_user_id = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)

Base.metadata.create_all(bind=engine)

def execute_db_migrations():
    inspector = inspect(engine)
    with engine.connect() as conn:
        columns = [col["name"] for col in inspector.get_columns("users")]
        if "is_active" not in columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1"))
                conn.commit()
            except Exception: pass

        if "is_banned" not in columns:
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception: pass

        columns_tx = [col["name"] for col in inspector.get_columns("transactions")]
        if "tx_hash" not in columns_tx:
            try:
                conn.execute(text("ALTER TABLE transactions ADD COLUMN tx_hash VARCHAR(255) NULL"))
                conn.commit()
            except Exception: pass

        columns_po = [col["name"] for col in inspector.get_columns("plan_overrides")]
        if "is_hidden" not in columns_po:
            try:
                conn.execute(text("ALTER TABLE plan_overrides ADD COLUMN is_hidden BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception: pass

        columns_srv = [col["name"] for col in inspector.get_columns("services")]
        for col_name in ["alert_50d", "alert_1d", "alert_50p", "alert_80p", "alert_90p", "alert_100p"]:
            if col_name not in columns_srv:
                try:
                    conn.execute(text(f"ALTER TABLE services ADD COLUMN {col_name} BOOLEAN DEFAULT 0"))
                    conn.commit()
                except Exception: pass

        if not inspector.has_table("discount_codes"):
            try:
                DBDiscountCode.__table__.create(engine)
            except Exception: pass

execute_db_migrations()

def get_or_create_db_user(session, tg_user):
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

async def safe_reply(message: Message, text: str, reply_markup=None, parse_mode="MarkdownV2"):
    try:
        return await message.reply(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            return await message.reply(text, reply_markup=reply_markup, parse_mode=None)
        raise e

async def safe_edit(message: Message, text: str, reply_markup=None, parse_mode="MarkdownV2"):
    try:
        return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        if "can't parse entities" in str(e).lower():
            return await message.edit_text(text, reply_markup=reply_markup, parse_mode=None)
        raise e

class ResellerAPI:
    def __init__(self):
        self.base_url = config["API_BASE_URL"].rstrip("/")
        self.headers = {"X-API-Key": config["API_KEY"]}

    def get_balance(self):
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/balance", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_balance error: {e}")
        return None

    def get_plans(self):
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/plans", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_plans error: {e}")
        return None

    def buy_service(self, plan_id, name, client_id):
        try:
            payload = {"plan_id": int(plan_id), "name": name, "reseller_client_id": int(client_id)}
            r = requests.post(f"{self.base_url}/ma/api/v1/buy", json=payload, headers=self.headers, timeout=20)
            return r.json(), r.status_code
        except Exception as e:
            logger.error(f"API buy_service error: {e}")
            return {"error": str(e)}, 500

    def get_service_details(self, service_id):
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/services/{service_id}", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_service_details error: {e}")
        return None

    def get_client_services(self, client_id):
        try:
            r = requests.get(f"{self.base_url}/ma/api/v1/services/client/{client_id}", headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API get_client_services error: {e}")
        return None

    def toggle_service(self, service_id, action):
        try:
            payload = {"service_ids": [int(service_id)], "action": action}
            r = requests.post(f"{self.base_url}/ma/api/v1/services/toggle", json=payload, headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API toggle_service error: {e}")
        return None

    def renew_service(self, service_id, plan_id):
        try:
            payload = {"service_id": int(service_id), "plan_id": int(plan_id)}
            r = requests.post(f"{self.base_url}/ma/api/v1/services/renew", json=payload, headers=self.headers, timeout=20)
            return r.json(), r.status_code
        except Exception as e:
            logger.error(f"API renew_service error: {e}")
            return {"error": str(e)}, 500

    def extend_gb(self, service_id, gb):
        try:
            payload = {"service_id": int(service_id), "gb": float(gb)}
            r = requests.post(f"{self.base_url}/ma/api/v1/services/extend-gb", json=payload, headers=self.headers, timeout=20)
            return r.json(), r.status_code
        except Exception as e:
            logger.error(f"API extend_gb error: {e}")
            return {"error": str(e)}, 500

    def update_brand(self, brand_data):
        try:
            r = requests.post(f"{self.base_url}/ma/api/reseller/update-brand", json=brand_data, headers=self.headers, timeout=10)
            if r.status_code == 200: return r.json()
        except Exception as e:
            logger.error(f"API update_brand error: {e}")
        return None

api = ResellerAPI()

bot = Bot(token=config["BOT_TOKEN"])
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

class Form(StatesGroup):
    waiting_for_charge_amount = State()
    waiting_for_receipt = State()
    waiting_for_crypto_receipt = State()
    waiting_for_service_name = State()
    waiting_for_discount_code_input = State()
    waiting_for_extend_gb_amount = State()
    
class AdminStates(StatesGroup):
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
    waiting_for_config_json_upload = State()
    waiting_for_gift_amount = State()
    waiting_for_dc_code = State()
    waiting_for_dc_type = State()
    waiting_for_dc_value = State()
    waiting_for_dc_limit = State()
    waiting_for_dc_expiry = State()
    waiting_for_dc_user_restriction = State()
    
    # Sub branding configuration workflow
    waiting_for_brand_label = State()
    waiting_for_brand_logo = State()
    waiting_for_brand_theme_color = State()
    waiting_for_brand_bg_color = State()
    waiting_for_brand_text_color = State()
    waiting_for_brand_bg_image = State()
    waiting_for_brand_support_text = State()

class CustomSecurityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        
        is_admin = user.id in config["ADMIN_IDS"]

        if config.get("MAINTENANCE_MODE") and not is_admin:
            maint_txt = bot_texts.get("maintenance_text", DEFAULT_TEXTS["maintenance_text"])
            if isinstance(event, Message):
                await event.reply(maint_txt, parse_mode="MarkdownV2")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ ربات موقتاً به دلیل بروزرسانی از دسترس خارج است.", show_alert=True)
            return

        with SessionLocal() as db:
            db_user = db.query(DBUser).filter(DBUser.telegram_id == user.id).first()
            if db_user and db_user.is_banned:
                ban_txt = "❌ *دسترسی شما به ربات مسدود شده است.*\n\nدر صورت وجود سوال یا مشکل با پشتیبانی در ارتباط باشید."
                if isinstance(event, Message):
                    await event.reply(ban_txt, parse_mode="MarkdownV2")
                elif isinstance(event, CallbackQuery):
                    await event.answer("❌ حساب شما مسدود شده است.", show_alert=True)
                return

        if is_admin:
            return await handler(event, data)
            
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
                    "⚠️ *جهت استفاده از خدمات ربات، ابتدا باید عضو کانال ما شوید:*\n\n"
                    "لطفاً با دکمه زیر وارد کانال شده و دکمه تایید را فشار دهید."
                )
                if isinstance(event, Message):
                    await event.reply(msg_text, reply_markup=kb, parse_mode="MarkdownV2")
                elif isinstance(event, CallbackQuery):
                    await event.message.edit_text(msg_text, reply_markup=kb, parse_mode="MarkdownV2")
                    await event.answer()
                return
        return await handler(event, data)

dp.message.outer_middleware(CustomSecurityMiddleware())
dp.callback_query.outer_middleware(CustomSecurityMiddleware())

def main_menu_keyboard(tg_id):
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")]
    ])

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    bot_info = await bot.get_me()
    with SessionLocal() as db:
        user = get_or_create_db_user(db, message.from_user)
        rank_name, _ = calculate_user_rank(db, user.id)
        raw_welcome_txt = bot_texts.get("welcome_text", DEFAULT_TEXTS["welcome_text"])
        welcome_txt = raw_welcome_txt.format(
            first_name=escape_md(user.first_name or ''),
            rank_name=escape_md(rank_name),
            balance=escape_md(f"{int(user.balance):,}"),
            bot_first_name=escape_md(bot_info.first_name),
            bot_username=escape_md(bot_info.username)
        )
        
        banner_url = config.get("WELCOME_BANNER_URL")
        if banner_url:
            try:
                await message.answer_photo(
                    photo=banner_url,
                    caption=welcome_txt,
                    reply_markup=main_menu_keyboard(message.from_user.id),
                    parse_mode="MarkdownV2"
                )
                return
            except Exception: pass

        await safe_reply(message, welcome_txt, reply_markup=main_menu_keyboard(message.from_user.id), parse_mode="MarkdownV2")

@router.callback_query(F.data == "btn_main_menu")
async def main_menu_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    bot_info = await bot.get_me()
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        rank_name, _ = calculate_user_rank(db, user.id)
        raw_menu_txt = bot_texts.get("main_menu_text", DEFAULT_TEXTS["main_menu_text"])
        welcome_txt = raw_menu_txt.format(
            rank_name=escape_md(rank_name),
            balance=escape_md(f"{int(user.balance):,}"),
            bot_first_name=escape_md(bot_info.first_name),
            bot_username=escape_md(bot_info.username)
        )
        
        banner_url = config.get("WELCOME_BANNER_URL")
        if banner_url:
            try:
                await callback.message.delete()
            except Exception: pass
            try:
                await callback.message.answer_photo(
                    photo=banner_url,
                    caption=welcome_txt,
                    reply_markup=main_menu_keyboard(callback.from_user.id),
                    parse_mode="MarkdownV2"
                )
                return
            except Exception: pass
        await safe_edit(callback.message, welcome_txt, reply_markup=main_menu_keyboard(callback.from_user.id), parse_mode="MarkdownV2")

@router.callback_query(F.data == "btn_support")
async def support_callback(callback: CallbackQuery):
    support_user = config.get("SUPPORT_USERNAME", "@rnilaad").replace("@", "")
    support_txt = bot_texts.get("support_text", DEFAULT_TEXTS["support_text"])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 ارسال پیام به پشتیبانی", url=f"https://t.me/{support_user}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
    ])
    await safe_edit(callback.message, support_txt, reply_markup=kb, parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data == "btn_wallet")
async def wallet_callback(callback: CallbackQuery):
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        raw_wallet_txt = bot_texts.get("wallet_text", DEFAULT_TEXTS["wallet_text"])
        txt = raw_wallet_txt.format(balance=escape_md(f"{int(user.balance):,}"))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏧 افزایش موجودی (کارت به کارت)", callback_data="btn_charge_wallet", style="success")],
            [InlineKeyboardButton(text="💎 شارژ با ارز دیجیتال (Crypto)", callback_data="btn_charge_crypto", style="success")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
        ])
        await safe_edit(callback.message, txt, reply_markup=kb, parse_mode="MarkdownV2")
        await callback.answer()

@router.callback_query(F.data == "btn_charge_wallet")
async def charge_wallet_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ لطفاً مبلغ مورد نظر خود را برای شارژ حساب به *تومان* وارد کنید \\(به صورت عدد انگلیسی\\):",
        reply_markup=back_to_menu_keyboard(),
        parse_mode="MarkdownV2"
    )
    await state.set_state(Form.waiting_for_charge_amount)
    await callback.answer()

@router.message(Form.waiting_for_charge_amount)
async def process_charge_amount(message: Message, state: FSMContext):
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
        amount=escape_md(f"{amount:,}"),
        card_number=escape_md(card_num),
        card_holder=escape_md(card_holder_name)
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 کپی شماره کارت", copy_text={"text": card_num}, style="success")],
        [InlineKeyboardButton(text="📋 کپی نام دارنده کارت", copy_text={"text": card_holder_name}, style="primary")],
        [InlineKeyboardButton(text="📋 کپی مبلغ (تومان)", copy_text={"text": str(amount)}, style="primary")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_main_menu")]
    ])
    
    await safe_reply(message, payment_txt, reply_markup=kb, parse_mode="MarkdownV2")
    await state.set_state(Form.waiting_for_receipt)

@router.message(Form.waiting_for_receipt, F.photo)
async def process_receipt_photo(message: Message, state: FSMContext):
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

    await message.reply("✅ رسید شما با موفقیت ثبت شد و در انتظار تایید مدیریت قرار گرفت\\. به محض بررسی وضعیت آن به شما اطلاع داده خواهد شد\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
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
                caption=f"⚡️ *رسید پرداخت جدید دریافت شد*\n\n👤 کاربر: {escape_md(message.from_user.first_name)} \\({message.from_user.id}\\)\n💵 مبلغ: *{escape_md(f'{amount:,}')}* تومان\n\nآیا این رسید را تایید می‌کنید؟",
                reply_markup=admin_markup,
                parse_mode="MarkdownV2"
            )
        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")

@router.callback_query(F.data == "btn_charge_crypto")
async def charge_crypto_callback(callback: CallbackQuery):
    kb = []
    if config.get("TON_ADDRESS"):
        kb.append([InlineKeyboardButton(text="💎 شبکه TON", callback_data="cry_TON")])
    if config.get("USDT_ADDRESS"):
        kb.append([InlineKeyboardButton(text="💵 شبکه USDT (TRC-20)", callback_data="cry_USDT")])
    if config.get("TRX_ADDRESS"):
        kb.append([InlineKeyboardButton(text="🔴 شبکه TRX", callback_data="cry_TRX")])
        
    if not kb:
        return await callback.answer("⚠️ در حال حاضر هیچ درگاه پرداخت رمزارزی توسط مدیریت ثبت نشده است\\.", show_alert=True)
        
    kb.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_wallet")])
    await callback.message.edit_text("⚙️ لطفاً رمزارز مورد نظر خود را جهت واریز وجه انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("cry_"))
async def process_crypto_asset(callback: CallbackQuery, state: FSMContext):
    asset = callback.data.split("_")[1]
    addr_key = f"{asset}_ADDRESS"
    address = config.get(addr_key, "")
    
    if not address:
        return await callback.answer("❌ آدرس این کیف پول پیکربندی نشده است\\.", show_alert=True)
        
    await state.update_data(crypto_asset=asset, crypto_address=address)
    
    raw_instructions = bot_texts.get("crypto_payment_instructions", DEFAULT_TEXTS["crypto_payment_instructions"])
    crypto_instructions = raw_instructions.format(
        asset=escape_md(asset),
        address=escape_md(address)
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 کپی آدرس کیف پول", copy_text={"text": address}, style="success")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_charge_crypto")]
    ])
    
    await safe_edit(callback.message, crypto_instructions, reply_markup=kb, parse_mode="MarkdownV2")
    await state.set_state(Form.waiting_for_crypto_receipt)
    await callback.answer()

@router.message(Form.waiting_for_crypto_receipt)
async def process_crypto_receipt(message: Message, state: FSMContext):
    state_data = await state.get_data()
    asset = state_data["crypto_asset"]
    photo_id = message.photo[-1].file_id if message.photo else None
    tx_hash = message.text.strip() if message.text else None
    
    if not photo_id and not tx_hash:
        return await message.reply("❌ خطا: لطفاً یک فیش تصویری ارسال کنید یا کد پیگیری (TXID) تراکنش را به صورت متنی وارد کنید\\.")
        
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
        
    await message.reply("✅ رسید تراکنش رمزارز شما با موفقیت ثبت شد و جهت بررسی در اختیار مدیریت قرار گرفت\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
    await state.clear()
    
    admin_cap = (
        f"💎 *واریز رمزارز جدید \\({escape_md(asset)}\\)*\n\n"
        f"👤 کاربر: {escape_md(message.from_user.first_name)} \\({message.from_user.id}\\)\n"
        f"🔑 هش تراکنش: `{escape_md_code(tx_hash or 'ارسال نشده')}`\n\n"
        f"جهت تایید این واریزی می‌توانید با تخصیص موجودی دستی از منوی ادمین اقدام نمایید\\."
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
                await bot.send_photo(chat_id=admin_id, photo=photo_id, caption=admin_cap, reply_markup=admin_markup, parse_mode="MarkdownV2")
            else:
                await bot.send_message(chat_id=admin_id, text=admin_cap, reply_markup=admin_markup, parse_mode="MarkdownV2")
        except Exception as e:
            logger.error(f"Error alerting admins for crypto transaction: {e}")

# ---------------------------------------------------------------------------
# 9. Purchase Flow with Premium Styles, Discount Codes & Override Plan Logic
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_buy_service")
async def buy_service_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        closed_txt = bot_texts.get("shop_closed_text", DEFAULT_TEXTS["shop_closed_text"])
        return await safe_edit(callback.message, closed_txt, reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
    await callback.message.edit_text("⏳ در حال دریافت لیست پلن‌ها از سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.message.edit_text("❌ خطا در ارتباط با سرور یا دریافت اطلاعات پلن‌ها\\. لطفا مجدداً تلاش کنید\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
    plans = plans_data.get("plans", [])
    if not plans:
        return await callback.message.edit_text("🛒 در حال حاضر پلن فعالی جهت فروش موجود نیست\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
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
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان ثبت سفارش جدید وجود ندارد\\.", show_alert=True)

    parts = callback.data.split("_")
    plan_id = int(parts[2])
    price = int(parts[3])
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        if user.balance < price:
            raw_insufficient_txt = bot_texts.get("insufficient_balance_text", DEFAULT_TEXTS["insufficient_balance_text"])
            insufficient_txt = raw_insufficient_txt.format(
                price=escape_md(f"{price:,}"),
                balance=escape_md(f"{int(user.balance):,}")
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 افزایش موجودی حساب", callback_data="btn_charge_wallet", style="success")],
                [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_buy_service")]
            ])
            return await safe_edit(callback.message, insufficient_txt, reply_markup=kb, parse_mode="MarkdownV2")
            
    await state.update_data(buy_plan_id=plan_id, buy_price=price)
    
    name_instructions = (
        "✏️ لطفاً یک نام کوتاه انگلیسی \\(فقط حروف و اعداد بین ۳ تا ۱۲ کاراکتر\\) برای سرویس خود وارد کنید:\n\n"
        "مثال: `myvpn`\n\n"
        "🎲 یا می‌توانید از دکمه زیر جهت تولید نام کاملاً تصادفی استفاده کنید\\."
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 تولید نام تصادفی", callback_data="btn_generate_random_name", style="primary")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="btn_buy_service")]
    ])
    
    await callback.message.edit_text(name_instructions, reply_markup=kb, parse_mode="MarkdownV2")
    await state.set_state(Form.waiting_for_service_name)
    await callback.answer()

@router.callback_query(F.data == "btn_generate_random_name", Form.waiting_for_service_name)
async def generate_random_name_callback(callback: CallbackQuery, state: FSMContext):
    rand_name = "v" + "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
    await state.update_data(buy_service_name=rand_name)
    await render_checkout_invoice(callback.message, state)
    await callback.answer()

@router.message(Form.waiting_for_service_name)
async def process_service_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not re.match(r"^[a-zA-Z0-9]{3,12}$", name):
        return await message.reply("❌ خطا: نام سرویس فقط باید شامل حروف انگلیسی و اعداد بین ۳ تا ۱۲ کاراکتر باشد\\. مجدداً ارسال کنید:", parse_mode="MarkdownV2")
        
    await state.update_data(buy_service_name=name)
    await render_checkout_invoice(message, state)

async def render_checkout_invoice(message_to_send: Message, state: FSMContext):
    state_data = await state.get_data()
    name = state_data["buy_service_name"]
    original_price = state_data["buy_price"]
    
    discount_code = state_data.get("applied_discount_code", None)
    discount_amount = 0.0
    
    if discount_code:
        with SessionLocal() as db:
            dc = db.query(DBDiscountCode).filter(DBDiscountCode.code == discount_code).first()
            if dc:
                if dc.discount_type == "percent":
                    discount_amount = original_price * (dc.value / 100.0)
                else:
                    discount_amount = dc.value
                    
    final_price = max(0.0, original_price - discount_amount)
    await state.update_data(buy_final_price=final_price)
    
    confirm_txt = (
        "🧾 *پیش‌فاکتور نهایی خرید سرویس*\n\n"
        f"🖥 نام سرویس: `{escape_md_code(name)}`\n"
        f"💵 قیمت پایه: *{escape_md(f'{int(original_price):,}')}* تومان\n"
    )
    
    if discount_code:
        confirm_txt += (
            f"🎟 کد تخفیف اعمال شده: `{escape_md_code(discount_code)}`\n"
            f"🎁 مقدار کسر شده: *{escape_md(f'{int(discount_amount):,}')}* تومان\n"
        )
        
    confirm_txt += f"\n💳 *مبلغ قابل پرداخت نهایی: {escape_md(f'{int(final_price):,}')} تومان*"
    
    kb = [
        [
            InlineKeyboardButton(text="✅ پرداخت و تایید خرید", callback_data="confirm_buy_final", style="success")
        ],
        [
            InlineKeyboardButton(text="🎟 ثبت کد تخفیف", callback_data="btn_apply_checkout_discount", style="primary"),
            InlineKeyboardButton(text="❌ انصراف", callback_data="btn_main_menu", style="danger")
        ]
    ]
    
    if isinstance(message_to_send, Message):
        await safe_reply(message_to_send, confirm_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    else:
        await safe_edit(message_to_send, confirm_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")

@router.callback_query(F.data == "btn_apply_checkout_discount")
async def btn_apply_checkout_discount_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✏️ لطفاً کد تخفیف خود را وارد کنید \\(به بزرگی و کوچکی حروف دقت کنید\\):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف و بازگشت", callback_data="btn_cancel_discount_application")]
        ]),
        parse_mode="MarkdownV2"
    )
    await state.set_state(Form.waiting_for_discount_code_input)
    await callback.answer()

@router.callback_query(F.data == "btn_cancel_discount_application", Form.waiting_for_discount_code_input)
async def btn_cancel_discount_application_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_service_name)
    await render_checkout_invoice(callback, state)
    await callback.answer()

@router.message(Form.waiting_for_discount_code_input)
async def process_discount_code_input_checkout(message: Message, state: FSMContext):
    code_entered = message.text.strip()
    
    with SessionLocal() as db:
        dc = db.query(DBDiscountCode).filter(
            DBDiscountCode.code == code_entered,
            DBDiscountCode.is_active == True
        ).first()
        
        if not dc:
            return await message.reply("❌ خطا: این کد تخفیف وجود ندارد یا غیرفعال شده است\\. مجددا تلاش کنید یا انصراف دهید:", parse_mode="MarkdownV2")
            
        if dc.expiry_date and dc.expiry_date < datetime.utcnow():
            return await message.reply("❌ خطا: مدت اعتبار این کد تخفیف به پایان رسیده است\\.", parse_mode="MarkdownV2")
            
        if dc.used_count >= dc.usage_limit:
            return await message.reply("❌ خطا: سقف تعداد دفعات استفاده از این کد تخفیف پر شده است\\.", parse_mode="MarkdownV2")
            
        if dc.specific_user_id and dc.specific_user_id != message.from_user.id:
            return await message.reply("❌ خطا: این کد تخفیف مخصوص یک کاربر دیگر طراحی شده است و شما مجاز به استفاده از آن نیستید\\.", parse_mode="MarkdownV2")
            
    await state.update_data(applied_discount_code=dc.code)
    await state.set_state(Form.waiting_for_service_name)
    
    await message.reply(f"✅ کد تخفیف `{escape_md_code(dc.code)}` با موفقیت بر روی فاکتور شما اعمال گردید\\.", parse_mode="MarkdownV2")
    await render_checkout_invoice(message, state)

@router.callback_query(F.data == "confirm_buy_final")
async def confirm_buy_final_callback(callback: CallbackQuery, state: FSMContext):
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان ثبت سفارش جدید وجود ندارد\\.", show_alert=True)

    state_data = await state.get_data()
    plan_id = state_data.get("buy_plan_id")
    name = state_data.get("buy_service_name")
    price = state_data.get("buy_final_price", state_data.get("buy_price"))
    discount_code = state_data.get("applied_discount_code", None)
    
    if not plan_id or not name:
        return await callback.message.edit_text("❌ خطا در بازیابی اطلاعات نشست خرید\\. مجدداً اقدام کنید\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
    await callback.message.edit_text("⏳ در حال برقراری ارتباط با سرور و پیکربندی اکانت\\.\\.\\.", parse_mode="MarkdownV2")
    
    with SessionLocal() as db:
        user = db.query(DBUser).filter(DBUser.telegram_id == callback.from_user.id).first()
        if not user or user.balance < price:
            return await callback.message.edit_text("❌ موجودی حساب شما کافی نیست یا کاربر یافت نشد\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
            
        res_data, status_code = api.buy_service(plan_id, name, callback.from_user.id)
        if status_code == 200 and res_data.get("success"):
            user.balance -= price
            
            if discount_code:
                dc = db.query(DBDiscountCode).filter(DBDiscountCode.code == discount_code).first()
                if dc:
                    dc.used_count += 1
            
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
                description=f"خرید سرویس {name}" + (f" با کد تخفیف {discount_code}" if discount_code else "")
            )
            db.add(tx)
            db.commit()
            
            sub_link = res_data.get("sub_url", "")
            configs_list = res_data.get("configs", [])
            configs_list = [cfg for cfg in configs_list if "/sub/" not in cfg]
            
            raw_success_txt = bot_texts.get("purchase_success_text", DEFAULT_TEXTS["purchase_success_text"])
            success_txt = raw_success_txt.format(sub_link=escape_md_code(sub_link))
            
            if configs_list:
                success_txt += "🔌 *کانفیگ‌های اتصال مستقیم شما:*\n\n"
                for index, cfg in enumerate(configs_list[:3]):
                    success_txt += f"*کانفیگ {index+1}:*\n`{escape_md_code(cfg)}`\n\n"
            
            kb_list = [
                [InlineKeyboardButton(text="📋 کپی سریع لینک اشتراک", copy_text={"text": sub_link}, style="success")],
                [InlineKeyboardButton(text="🔗 باز کردن حساب کاربری (مینی‌اپ)", url=sub_link, style="primary")],
                [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")]
            ]
            
            await safe_edit(callback.message, success_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="MarkdownV2")

            admin_msg = (
                f"🔔 *گزارش خرید سرویس جدید*\n\n"
                f"👤 خریدار: {escape_md(user.first_name or 'نامشخص')} \\({user.telegram_id}\\)\n"
                f"📦 پلن خریداری شده: \\(کد پلن: {plan_id}\\)\n"
                f"🖥 نام سرویس: `{escape_md_code(name)}`\n"
                f"💵 قیمت نهایی: *{escape_md(f'{price:,}')}* تومان\n"
                f"🎟 کد تخفیف اعمال شده: `{escape_md_code(discount_code or 'هیچکدام')}`\n"
                f"🔑 شناسه \\(UUID\\): `{escape_md_code(res_data.get('uuid'))}`"
            )
            for admin_id in config["ADMIN_IDS"]:
                try:
                    await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="MarkdownV2")
                except Exception as e:
                    logger.error(f"Error sending buy report to admin {admin_id}: {e}")
        else:
            err_msg = res_data.get("error", "An error occurred during purchase creation.")
            await callback.message.edit_text(f"❌ *خطا در هنگام ساخت اکانت روی سرور:*\n\n`{escape_md_code(err_msg)}`", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
            
    await state.clear()
    await callback.answer()

# ---------------------------------------------------------------------------
# 10. Services List & Dynamic 2-Row Column Layout Controls
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_my_services")
async def my_services_callback(callback: CallbackQuery):
    """Retrieves client subscriptions and populates active services menu."""
    await callback.message.edit_text("⏳ در حال دریافت لیست سرویس‌های شما از سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        services = db.query(DBService).filter(DBService.user_id == user.id).all()
        
    if not services:
        return await callback.message.edit_text("🌐 شما هیچ سرویس فعالی ثبت نکرده‌اید\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
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
            return await callback.message.edit_text("❌ سرویس مورد نظر در سیستم یافت نشد\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
            
    await callback.message.edit_text("⏳ در حال دریافت جزئیات و ترافیک لحظه‌ای از سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    details = api.get_service_details(srv.service_id)
    if not details or not details.get("success"):
        detail_txt = (
            f"ℹ️ *جزئیات سرویس: {escape_md(srv.name)}*\n\n"
            f"🔑 شناسه \\(UUID\\): `{escape_md_code(srv.uuid)}`\n"
            f"📡 وضعیت: *{escape_md(srv.status)}*\n\n"
            "⚠️ دریافت اطلاعات مصرف حجم لایو از سرور مقدور نبود\\."
        )
        kb = [
            [
                InlineKeyboardButton(text="🔄 تلاش مجدد", callback_data=f"srv_view_{srv.id}", style="primary"),
                InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="btn_my_services")
            ]
        ]
        return await callback.message.edit_text(detail_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
        
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
        f"ℹ️ *مشخصات سرویس: {escape_md(srv.name)}*\n\n"
        f"📊 مصرف ترافیک: *{escape_md(f'{used_gb:.2f}')}* از *{escape_md(f'{total_gb:.2f}')} GB*\n"
        f"🔋 حجم باقیمانده: *{escape_md(f'{remain_gb:.2f}')} GB*\n"
        f"⏳ تاریخ انقضا: *{escape_md(expire_date)}*\n"
        f"📡 وضعیت: *{escape_md(status)}*\n\n"
        f"🔗 *لینک اشتراک:*\n`{escape_md_code(sub_url)}`"
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
        InlineKeyboardButton(text="⚡️ خرید حجم اضافه", callback_data=f"srv_extend_gb_init_{srv_id}", style="primary")
    ])
    kb.append([
        InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="btn_my_services")
    ])
    
    if callback.from_user.id in config["ADMIN_IDS"]:
        toggle_txt = "🔴 غیرفعال کردن سرویس" if status == "active" else "🟢 فعال کردن سرویس"
        kb.append([InlineKeyboardButton(text=toggle_txt, callback_data=f"srv_toggle_{srv_id}", style="danger")])
        
    await safe_edit(callback.message, detail_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data.startswith("srv_toggle_"))
async def srv_toggle_callback(callback: CallbackQuery):
    """Updates active status of a service on the target panel (enable/disable) for admins."""
    if callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("❌ دسترسی غیرمجاز: تنها مدیریت مجاز به قطع موقت سرویس‌ها می‌باشد\\.", show_alert=True)
        
    srv_id = int(callback.data.split("_")[2])
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    action = "disable" if srv.status == "active" else "enable"
    await callback.message.edit_text("⏳ در حال ارسال دستور تغییر وضعیت به سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    res = api.toggle_service(srv.service_id, action)
    if res and res.get("success"):
        await callback.answer("✅ وضعیت سرویس با موفقیت تغییر کرد\\.", show_alert=True)
    else:
        await callback.answer("❌ خطا در تغییر وضعیت سرویس در سرور\\.", show_alert=True)
        
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
    
    await callback.message.edit_text("⏳ در حال تولید کد QR اختصاصی\\.\\.\\.", parse_mode="MarkdownV2")
    try:
        r = requests.get(qr_api_url, timeout=10)
        if r.status_code == 200:
            qr_file = BufferedInputFile(r.content, filename="qrcode.png")
            await callback.message.reply_photo(
                photo=qr_file,
                caption=f"📸 *کد QR لینک اشتراک سرویس: {escape_md(srv.name)}*\n\n`{escape_md_code(qr_data)}`",
                parse_mode="MarkdownV2"
            )
            await callback.message.delete()
        else:
            raise Exception("Non-200 Response from API")
    except Exception as e:
        logger.error(f"Error creating QR code image: {e}")
        await callback.answer("❌ خطا در ایجاد عکس QR Code\\. لینک به صورت متن ارسال شد\\.", show_alert=True)
        await callback.message.reply(f"🔗 *لینک اشتراک شما:*\n\n`{escape_md_code(qr_data)}`", parse_mode="MarkdownV2")

@router.callback_query(F.data.startswith("srv_renew_"))
async def srv_renew_callback(callback: CallbackQuery):
    """Forces renewal only to current service plan to maintain consistent parameters."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        closed_txt = bot_texts.get("shop_closed_text", DEFAULT_TEXTS["shop_closed_text"])
        return await safe_edit(callback.message, closed_txt, reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")

    srv_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("⏳ در حال استعلام مشخصات پلن فعلی از سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv or not srv.plan_id:
            return await callback.message.edit_text("❌ خطا: کد پلن اصلی متصل به این سرویس یافت نشد\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
            
        target_plan_id = srv.plan_id

    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
        return await callback.message.edit_text("❌ خطا in دریافت پلن‌ها از سرور\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
    plans = plans_data.get("plans", [])
    matched_plan = None
    for p in plans:
        if p["id"] == target_plan_id:
            matched_plan = p
            break
            
    if not matched_plan:
        return await callback.message.edit_text("❌ خطا: این پلن دیگر روی سرور اصلی فعال نیست یا امکان تمدید مستقیم آن وجود ندارد\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
        
    with SessionLocal() as db:
        override = db.query(DBPlanOverride).filter(DBPlanOverride.plan_id == matched_plan['id']).first()
        p_title = override.custom_title if (override and override.custom_title) else matched_plan['title']
        p_price = int(override.custom_price) if (override and override.custom_price is not None) else int(matched_plan['price'])

    kb = [
        [InlineKeyboardButton(text=f"🔄 تایید تمدید با {p_title} - {p_price:,} ت", callback_data=f"renew_confirm_{srv_id}_{matched_plan['id']}_{p_price}")],
        [InlineKeyboardButton(text="🔙 انصراف و بازگشت", callback_data=f"srv_view_{srv_id}")]
    ]
    
    await callback.message.edit_text(
        f"🔄 *درخواست تمدید سرویس: {escape_md(srv.name)}*\n\n"
        f"📦 پلن فعلی شما: *{escape_md(p_title)}*\n"
        f"💵 هزینه تمدید دوره: *{escape_md(f'{p_price:,}')}* تومان\n\n"
        "آیا مایل هستید سرویس شما برای یک دوره دیگر تمدید شود؟",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="MarkdownV2"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("renew_confirm_"))
async def renew_confirm_callback(callback: CallbackQuery):
    """Processes final renewal payment, deducts local balance, and registers state."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان تمدید سرویس وجود ندارد\\.", show_alert=True)

    parts = callback.data.split("_")
    srv_id = int(parts[2])
    plan_id = int(parts[3])
    price = int(parts[4])
    
    with SessionLocal() as db:
        user = get_or_create_db_user(db, callback.from_user)
        if user.balance < price:
            return await callback.answer("❌ موجودی حساب شما برای این تمدید کافی نیست\\.", show_alert=True)
            
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    await callback.message.edit_text("⏳ در حال تمدید اشتراک بر روی سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
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
            
        await callback.answer("🎉 سرویس شما با موفقیت تمدید شد\\!", show_alert=True)

        admin_msg = (
            f"🔄 *گزارش تمدید سرویس*\n\n"
            f"👤 کاربر: {escape_md(db_user.first_name or 'نامشخص')} \\({db_user.telegram_id}\\)\n"
            f"🖥 سرویس: `{escape_md(srv.name)}` \\(کد سرویس: {srv.service_id}\\)\n"
            f"💵 هزینه تمدید: *{escape_md(f'{price:,}')}* تومان"
        )
        for admin_id in config["ADMIN_IDS"]:
            try:
                await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="MarkdownV2")
            except Exception as e:
                logger.error(f"Error sending renewal report to admin {admin_id}: {e}")
    else:
        err = res_data.get("error", "Renewal unsuccessful.")
        await callback.answer(f"❌ خطا در تمدید: {err}", show_alert=True)
        
    await srv_view_callback(callback)

# ---------------------------------------------------------------------------
# 10.1 Extend GB Workflow
# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("srv_extend_gb_init_"))
async def srv_extend_gb_init_callback(callback: CallbackQuery, state: FSMContext):
    """Initializes extra traffic purchase sequence."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        closed_txt = bot_texts.get("shop_closed_text", DEFAULT_TEXTS["shop_closed_text"])
        return await safe_edit(callback.message, closed_txt, reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")

    srv_id = int(callback.data.split("_")[4])
    
    await callback.message.edit_text("⏳ در حال استعلام قیمت ترافیک اضافه از سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    plans_data = api.get_plans()
    if not plans_data or not plans_data.get("success"):
         return await callback.message.edit_text("❌ خطا در استعلام مشخصات فنی پلن‌ها\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
         
    plans = plans_data.get("plans", [])
    matched_plan = next((p for p in plans if p["id"] == srv.plan_id), None)
    
    gb_price = matched_plan.get("gb_price", 1000.0) if matched_plan else 1000.0
    await state.update_data(extend_srv_id=srv_id, extend_gb_price=gb_price)
    
    prompt_txt = (
        f"⚡️ *خرید حجم اضافه برای سرویس {escape_md(srv.name)}*\n\n"
        f"💵 قیمت هر گیگابایت ترافیک اضافه: *{escape_md(f'{int(gb_price):,}')}* تومان\n\n"
        "✏️ لطفاً مقدار حجم ترافیک مورد نیاز خود را به *گیگابایت* وارد نمایید \\(به صورت عدد انگلیسی\\):"
    )
    
    await callback.message.edit_text(prompt_txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 انصراف", callback_data=f"srv_view_{srv_id}")]
    ]), parse_mode="MarkdownV2")
    await state.set_state(Form.waiting_for_extend_gb_amount)
    await callback.answer()

@router.message(Form.waiting_for_extend_gb_amount)
async def process_extend_gb_amount(message: Message, state: FSMContext):
    """Calculates price quote based on input volume and renders invoice."""
    amount_str = message.text.strip()
    try:
        gb_amount = float(amount_str)
        if gb_amount <= 0: raise ValueError
    except ValueError:
        return await message.reply("❌ خطا: لطفاً مقدار ترافیک اضافه را به صورت عدد مثبت معتبر \\(انگلیسی\\) وارد نمایید:")
        
    state_data = await state.get_data()
    srv_id = state_data["extend_srv_id"]
    gb_price = state_data["extend_gb_price"]
    
    cost = int(gb_amount * gb_price)
    await state.update_data(extend_gb_amount=gb_amount, extend_cost=cost)
    
    with SessionLocal() as db:
        srv = db.query(DBService).get(srv_id)
        user = get_or_create_db_user(db, message.from_user)
        
    invoice_txt = (
        f"🧾 *پیش‌فاکتور خرید حجم ترافیک اضافه*\n\n"
        f"🖥 نام سرویس: `{escape_md_code(srv.name)}`\n"
        f"⚡️ مقدار حجم اضافه: *{escape_md(f'{gb_amount:.2f}')} GB*\n"
        f"💵 قیمت به ازای هر گیگابایت: *{escape_md(f'{int(gb_price):,}')}* تومان\n\n"
        f"💳 *مجموع هزینه قابل پرداخت: {escape_md(f'{cost:,}')} تومان*\n"
        f"👛 موجودی کیف پول فعلی شما: {escape_md(f'{int(user.balance):,}')} تومان"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ پرداخت و افزایش حجم ترافیک", callback_data="confirm_extend_gb_final", style="success")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data=f"srv_view_{srv_id}", style="danger")]
    ])
    
    await safe_reply(message, invoice_txt, reply_markup=kb, parse_mode="MarkdownV2")

@router.callback_query(F.data == "confirm_extend_gb_final")
async def confirm_extend_gb_final_callback(callback: CallbackQuery, state: FSMContext):
    """Charges user and posts the volume extension directly to central server."""
    if config.get("SHOP_CLOSED") and callback.from_user.id not in config["ADMIN_IDS"]:
        return await callback.answer("⚠️ فروشگاه موقتاً تعطیل است و امکان خرید حجم ترافیک وجود ندارد\\.", show_alert=True)

    state_data = await state.get_data()
    srv_id = state_data.get("extend_srv_id")
    gb_amount = state_data.get("extend_gb_amount")
    cost = state_data.get("extend_cost")
    
    if not srv_id or not gb_amount:
         return await callback.message.edit_text("❌ خطا: اطلاعات نشست خرید منقضی شده است\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
         
    with SessionLocal() as db:
        user = db.query(DBUser).filter(DBUser.telegram_id == callback.from_user.id).first()
        if not user or user.balance < cost:
            return await callback.answer("❌ موجودی حساب شما برای این خرید کافی نیست\\.", show_alert=True)
            
        srv = db.query(DBService).get(srv_id)
        if not srv: return
        
    await callback.message.edit_text("⏳ در حال اعمال حجم ترافیک اضافه بر روی سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    res_data, status_code = api.extend_gb(srv.service_id, gb_amount)
    if status_code == 200 and res_data.get("success"):
        with SessionLocal() as db:
            db_user = db.query(DBUser).filter(DBUser.telegram_id == callback.from_user.id).first()
            db_user.balance -= cost
            
            tx = DBTransaction(
                user_id=db_user.id,
                type="Buy",
                amount=-cost,
                status="success",
                description=f"خرید {gb_amount} گیگابایت حجم اضافه برای سرویس {srv.name}"
            )
            db.add(tx)
            db.commit()
            
        await callback.answer("🎉 حجم اضافه با موفقیت خریداری و به سرویس افزوده شد\\!", show_alert=True)
        
        admin_msg = (
            f"⚡️ *گزارش افزایش حجم سرویس*\n\n"
            f"👤 کاربر: {escape_md(db_user.first_name or 'نامشخص')} \\({db_user.telegram_id}\\)\n"
            f"🖥 سرویس: `{escape_md_code(srv.name)}`\n"
            f"📊 حجم افزوده شده: *{escape_md(f'{gb_amount:.2f}')} GB*\n"
            f"💵 هزینه کسر شده: *{escape_md(f'{cost:,}')}* تومان"
        )
        for admin_id in config["ADMIN_IDS"]:
            try:
                await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="MarkdownV2")
            except Exception as e:
                logger.error(f"Error sending extend-gb report to admin {admin_id}: {e}")
    else:
        err = res_data.get("error", "Failed to extend traffic volume.")
        await callback.answer(f"❌ خطا در اعمال حجم: {err}", show_alert=True)
        
    await state.clear()
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
        
    maint_status = "🔴 فعال \\(تعمیرات\\)" if config.get("MAINTENANCE_MODE") else "🟢 غیرفعال \\(عادی\\)"
    shop_status = "🔴 بسته" if config.get("SHOP_CLOSED") else "🟢 باز"
    
    txt = (
        f"⚙️ *پنل مدیریت ربات فروشگاهی نماینده*\n\n"
        f"👥 کل کاربران عضو شده: *{total_users}* کاربر\n"
        f"⏳ فیش‌های در انتظار بررسی: *{len(pending_txs)}* عدد\n\n"
        f"🔧 وضعیت تعمیرات: *{maint_status}*\n"
        f"🛒 وضعیت فروشگاه: *{shop_status}*"
    )
    
    kb = [
        [
            InlineKeyboardButton(text=f"🔧 تعمیرات: {'غیرفعال' if config.get('MAINTENANCE_MODE') else 'فعال'}", callback_data="adm_toggle_maint"),
            InlineKeyboardButton(text=f"🛒 فروشگاه: {'باز' if config.get('SHOP_CLOSED') else 'بسته'}", callback_data="adm_toggle_shop")
        ],
        [
            InlineKeyboardButton(text="🎨 شخصی‌سازی ظاهر صفحه اشتراک", callback_data="adm_sub_branding_menu", style="primary")
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
            InlineKeyboardButton(text="🎁 هدیه مالی همگانی", callback_data="adm_gift_all_users_init"),
            InlineKeyboardButton(text="🎟 کدهای تخفیف", callback_data="adm_discounts_menu")
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
            InlineKeyboardButton(text="📥 دانلود فایل تنظیمات (Config JSON)", callback_data="adm_download_config_json"),
            InlineKeyboardButton(text="📤 آپلود فایل جدید تنظیمات", callback_data="adm_upload_config_json")
        ],
        [
            InlineKeyboardButton(text="📥 دانلود بکاپ SQL", callback_data="adm_dl_db_sql"),
            InlineKeyboardButton(text="📥 دانلود بکاپ DB", callback_data="adm_dl_db_bin")
        ]
    ]
    if pending_txs:
        kb.insert(0, [InlineKeyboardButton(text="✍️ بررسی فیش‌های در انتظار", callback_data="btn_admin_review_pending", style="success")])
        
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="btn_main_menu")])
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

# ---------------------------------------------------------------------------
# 11.0.1 Sub Branding Configuration Submenu
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_sub_branding_menu")
async def adm_sub_branding_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Renders menu allowing reseller to completely customize dynamic sub page colors/layouts."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    await state.clear()
    
    txt = (
        "🎨 *شخصی‌سازی ظاهر صفحات اشتراک مشترکین*\n\n"
        "با گزینه‌های زیر می‌توانید تم، رنگ‌ها، تصاویر پس‌زمینه و المان‌های صفحه اختصاصی اشتراک مشترکین خود را تغییر دهید\\.\n"
        "این تنظیمات فوراً روی صفحه لایو کاربران اعمال می‌شود\\."
    )
    
    kb = [
        [InlineKeyboardButton(text="✏️ تغییر نام برند تجاری (Label)", callback_data="brand_set_label")],
        [InlineKeyboardButton(text="✏️ تغییر لوگو اختصاصی (آدرس عکس)", callback_data="brand_set_logo")],
        [InlineKeyboardButton(text="✏️ تغییر رنگ تم اصلی (Accent Color)", callback_data="brand_set_theme_color")],
        [InlineKeyboardButton(text="✏️ تغییر رنگ پس‌زمینه (Background Color)", callback_data="brand_set_bg_color")],
        [InlineKeyboardButton(text="✏️ تغییر رنگ متون (Text Color)", callback_data="brand_set_text_color")],
        [InlineKeyboardButton(text="✏️ تغییر عکس بک‌گراند اشتراک (آدرس تصویر)", callback_data="brand_set_bg_image")],
        [InlineKeyboardButton(text="✏️ تغییر متن پشتیبانی سفارشی", callback_data="brand_set_support_text")],
        [
            InlineKeyboardButton(text="🎨 فرم قاب لوگو", callback_data="brand_set_logo_shape_menu"),
            InlineKeyboardButton(text="🔋 نوار مصرف", callback_data="brand_set_progress_style_menu")
        ],
        [
            InlineKeyboardButton(text="✨ افکت تار شدن پس‌زمینه (Blur)", callback_data="brand_toggle_blur"),
            InlineKeyboardButton(text="🔄 ریست به پیش‌فرض", callback_data="brand_reset_defaults_init")
        ],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ]
    
    await safe_edit(callback.message, txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data.startswith("brand_set_"))
async def brand_set_key_callback(callback: CallbackQuery, state: FSMContext):
    """Routes parameter input states based on user brand customization selections."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    key = callback.data.replace("brand_set_", "")
    
    if key == "logo_shape_menu":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="گوشه گرد (Rounded)", callback_data="brand_save_shape_rounded-28px")],
            [InlineKeyboardButton(text="کاملاً گرد (Circular)", callback_data="brand_save_shape_circular")],
            [InlineKeyboardButton(text="زاویه‌دار (Square)", callback_data="brand_save_shape_square")],
            [InlineKeyboardButton(text="بدون نمایش لوگو", callback_data="brand_save_shape_none")],
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_sub_branding_menu")]
        ])
        return await callback.message.edit_text("🖼 *شکل قاب لوگوی اختصاصی برند خود را انتخاب کنید:*", reply_markup=kb, parse_mode="MarkdownV2")
        
    elif key == "progress_style_menu":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="نمودار دایره‌ای (Circular)", callback_data="brand_save_progress_circular")],
            [InlineKeyboardButton(text="نمودار خطی افقی (Linear)", callback_data="brand_save_progress_linear")],
            [InlineKeyboardButton(text="نشانگر متنی ساده (Simple Text)", callback_data="brand_save_progress_simple")],
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_sub_branding_menu")]
        ])
        return await callback.message.edit_text("🔋 *قالب نمایش مصرف ترافیک در صفحه اشتراک را مشخص کنید:*", reply_markup=kb, parse_mode="MarkdownV2")

    await state.update_data(editing_brand_field=key)
    
    prompts = {
        "label": "✏️ نام برند اختصاصی خود را ارسال کنید \\(مثلاً Moon VPN\\):",
        "logo": "✏️ آدرس لینک مستقیم تصویر لوگوی برند خود را بفرستید \\(حتماً با http یا https شروع شود\\):",
        "theme_color": "✏️ کد رنگ هگز \\(HEX\\) تم اصلی یا Accent را بفرستید \\(مثلا `#0A84FF`\\):",
        "bg_color": "✏️ کد رنگ هگز \\(HEX\\) بک‌گراند اشتراک را بفرستید \\(مثلا `#000000`\\):",
        "text_color": "✏️ کد رنگ هگز \\(HEX\\) متون را بفرستید \\(مثلا `#FFFFFF`\\):",
        "bg_image": "✏️ آدرس لینک مستقیم عکس پس‌زمینه صفحات اشتراک را ارسال کنید:",
        "support_text": "✏️ متن راهنمای پشتیبانی دلخواه خود را ارسال کنید تا در زیر جدول مشخصات نمایش داده شود:"
    }
    
    await callback.message.edit_text(prompts[key], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_sub_branding_menu")]
    ]), parse_mode="MarkdownV2")
    
    states_map = {
        "label": AdminStates.waiting_for_brand_label,
        "logo": AdminStates.waiting_for_brand_logo,
        "theme_color": AdminStates.waiting_for_brand_theme_color,
        "bg_color": AdminStates.waiting_for_brand_bg_color,
        "text_color": AdminStates.waiting_for_brand_text_color,
        "bg_image": AdminStates.waiting_for_brand_bg_image,
        "support_text": AdminStates.waiting_for_brand_support_text
    }
    await state.set_state(states_map[key])
    await callback.answer()

@router.callback_query(F.data.startswith("brand_save_"))
async def brand_save_menu_options(callback: CallbackQuery):
    """Instantly registers select option-based branding custom settings."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    parts = callback.data.split("_")
    field = parts[2]
    val = parts[3]
    
    await callback.message.edit_text("⏳ در حال ثبت و اعمال تنظیمات قالب روی سرور اختصاصی\\.\\.\\.", parse_mode="MarkdownV2")
    
    payload = {
        "initData": "dummy", # API uses reseller authorization based on headers
        field: val
    }
    
    res = api.update_brand(payload)
    if res and res.get("success"):
        await callback.answer("✅ قالب برند با موفقیت به‌روزرسانی شد\\.", show_alert=True)
    else:
        await callback.answer("❌ خطا در ذخیره تنظیمات روی سرور اصلی\\.", show_alert=True)
        
    await adm_sub_branding_menu_callback(callback, FSMContext)

@router.callback_query(F.data == "brand_toggle_blur")
async def brand_toggle_blur_callback(callback: CallbackQuery):
    """Toggles backdrop background blurring effects."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text("⏳ در حال دریافت تنظیمات فعلی پس‌زمینه از سرور\\.\\.\\.", parse_mode="MarkdownV2")
    
    # Quick API fetch to get current state or toggle directly
    plans_data = api.get_plans() # We can get current state or toggle via default payload
    # For robust toggle, we can send a POST directly to update-brand
    # Since we can't easily query single state, we update background_blur to True/False based on toggle.
    # The endpoint accepts "background_blur" as a boolean. We toggle it.
    # We can default toggle it to true/false. To make it seamless, let's send true.
    # Let's send true first, next time they can reset if they want. Or we fallback to simple alert prompt.
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 فعال کردن افکت بلور (Blur: True)", callback_data="brand_save_blur_true")],
        [InlineKeyboardButton(text="🔴 غیرفعال کردن افکت بلور (Blur: False)", callback_data="brand_save_blur_false")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_sub_branding_menu")]
    ])
    await callback.message.edit_text("✨ *تنظیم افکت تار شدن پس‌زمینه (Blur) صفحه اشتراک:*", reply_markup=kb, parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data.startswith("brand_save_blur_"))
async def brand_save_blur_confirmed(callback: CallbackQuery):
    """Submits blurred backdrop configuration setting to master API."""
    val = callback.data.split("_")[3] == "true"
    payload = {"background_blur": val}
    res = api.update_brand(payload)
    if res and res.get("success"):
        await callback.answer("✅ افکت بلور با موفقیت به‌روزرسانی شد\\.", show_alert=True)
    else:
        await callback.answer("❌ خطا در ثبت اطلاعات\\.", show_alert=True)
    await adm_sub_branding_menu_callback(callback, FSMContext)

@router.callback_query(F.data == "brand_reset_defaults_init")
async def brand_reset_defaults_init_callback(callback: CallbackQuery):
    """Confirms restoration of brand parameters back to system default colors."""
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بله، ریست به حالت پیش‌فرض", callback_data="brand_reset_defaults_confirmed")],
        [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_sub_branding_menu")]
    ])
    await callback.message.edit_text(
        "⚠️ *آیا از بازگردانی ظاهر صفحه به حالت پیش‌فرض مطمئن هستید؟*\n\n"
        "این کار تمام کدهای رنگی تم، پس‌زمینه، متن و تصاویر را حذف کرده و قالب پیش‌فرض را فعال می‌کند\\.",
        reply_markup=kb,
        parse_mode="MarkdownV2"
    )
    await callback.answer()

@router.callback_query(F.data == "brand_reset_defaults_confirmed")
async def brand_reset_defaults_confirmed_callback(callback: CallbackQuery):
    """Submits default payload resetting all customizations."""
    payload = {
        "label": "",
        "logo": "",
        "theme_color": "#0a84ff",
        "background_color": "#000000",
        "text_color": "#ffffff",
        "support_text": "",
        "logo_shape": "rounded-28px",
        "progress_style": "circular",
        "background_image_url": "",
        "background_blur": False
    }
    await callback.message.edit_text("⏳ در حال بازگردانی تنظیمات قالب به مقادیر پایه سیستمی\\.\\.\\.", parse_mode="MarkdownV2")
    res = api.update_brand(payload)
    if res and res.get("success"):
        await callback.answer("✅ قالب برند با موفقیت به حالت پیش‌فرض ریست شد\\.", show_alert=True)
    else:
         await callback.answer("❌ خطا در اعمال ریست قالب روی سرور\\.", show_alert=True)
    await adm_sub_branding_menu_callback(callback, FSMContext)

# ---------------------------------------------------------------------------
# State completion handlers for branding fields
# ---------------------------------------------------------------------------
async def save_brand_field_api(message: Message, state: FSMContext, field_key: str, value):
    """Helper function to execute central server sync for brand configuration."""
    payload = {field_key: value}
    await message.reply("⏳ در حال همگام‌سازی و ذخیره‌سازی داده‌های قالب روی سرور اصلی\\.\\.\\.", parse_mode="MarkdownV2")
    
    res = api.update_brand(payload)
    await state.clear()
    
    if res and res.get("success"):
        await message.reply(
            f"✅ ویژگی برند `{escape_md_code(field_key)}` با موفقیت روی سرور اعمال و ذخیره شد\\.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به منوی شخصی‌سازی ظاهر", callback_data="adm_sub_branding_menu")]
            ]),
            parse_mode="MarkdownV2"
        )
    else:
        await message.reply(
            "❌ خطا در ذخیره تنظیمات روی سرور اصلی\\.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به منوی شخصی‌سازی ظاهر", callback_data="adm_sub_branding_menu")]
            ]),
            parse_mode="MarkdownV2"
        )

@router.message(AdminStates.waiting_for_brand_label)
async def process_brand_label(message: Message, state: FSMContext):
    await save_brand_field_api(message, state, "label", message.text.strip())

@router.message(AdminStates.waiting_for_brand_logo)
async def process_brand_logo(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
         return await message.reply("❌ خطا: آدرس تصویر حتما باید با پروتکل معتبر http یا https شروع شود\\. مجددا ارسال کنید:")
    await save_brand_field_api(message, state, "logo", url)

@router.message(AdminStates.waiting_for_brand_theme_color)
async def process_brand_theme_color(message: Message, state: FSMContext):
    color = message.text.strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
         return await message.reply("❌ خطا: فرمت رنگ هگز نامعتبر است\\. حتماً باید شبیه نمونه `#0A84FF` باشد\\. مجدداً ارسال کنید:")
    await save_brand_field_api(message, state, "theme_color", color)

@router.message(AdminStates.waiting_for_brand_bg_color)
async def process_brand_bg_color(message: Message, state: FSMContext):
    color = message.text.strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
         return await message.reply("❌ خطا: فرمت رنگ هگز نامعتبر است\\. حتماً باید شبیه نمونه `#000000` باشد\\. مجدداً ارسال کنید:")
    await save_brand_field_api(message, state, "background_color", color)

@router.message(AdminStates.waiting_for_brand_text_color)
async def process_brand_text_color(message: Message, state: FSMContext):
    color = message.text.strip()
    if not re.match(r"^#[0-9a-fA-F]{6}$", color):
         return await message.reply("❌ خطا: فرمت رنگ هگز نامعتبر است\\. حتماً باید شبیه نمونه `#FFFFFF` باشد\\. مجدداً ارسال کنید:")
    await save_brand_field_api(message, state, "text_color", color)

@router.message(AdminStates.waiting_for_brand_bg_image)
async def process_brand_bg_image(message: Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(("http://", "https://")):
         return await message.reply("❌ خطا: آدرس عکس پس‌زمینه حتماً باید با پروتکل معتبر http یا https شروع شود\\. مجدداً ارسال کنید:")
    await save_brand_field_api(message, state, "background_image_url", url)

@router.message(AdminStates.waiting_for_brand_support_text)
async def process_brand_support_text(message: Message, state: FSMContext):
    await save_brand_field_api(message, state, "support_text", message.text.strip())

# ---------------------------------------------------------------------------
# 11.0.2 Gifting All Users Feature
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_gift_all_users_init")
async def adm_gift_all_users_init(callback: CallbackQuery, state: FSMContext):
    """Prompts administrator to specify gift money credit amount."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "🎁 *سیستم اعطای هدیه مالی به تمام کاربران*\n\n"
        "لطفاً مبلغ مورد نظر جهت شارژ هدیه کیف پول تمام کاربران فعال ربات را به *تومان* وارد کنید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="btn_admin_panel")]
        ]),
        parse_mode="MarkdownV2"
    )
    await state.set_state(AdminStates.waiting_for_gift_amount)
    await callback.answer()

@router.message(AdminStates.waiting_for_gift_amount)
async def process_gift_all_users(message: Message, state: FSMContext):
    """Credits designated gift amounts to all active users with rate limits and progress tracking."""
    amount_str = message.text.strip()
    if not amount_str.isdigit():
        return await message.reply("❌ خطا: لطفاً مقدار را به صورت یک عدد عددی انگلیسی وارد نمایید:")
        
    gift_amount = float(amount_str)
    await state.clear()
    
    with SessionLocal() as db:
        users = db.query(DBUser).filter(DBUser.is_active == True).all()
        
    total_users = len(users)
    if total_users == 0:
        return await message.reply("❌ هیچ کاربر فعالی در سیستم جهت دریافت هدیه یافت نشد\\.", parse_mode="MarkdownV2")
        
    progress_message = await message.reply("⏳ در حال آغاز فرآیند تخصیص اعتبار هدیه به کل کاربران\\.\\.\\.", parse_mode="MarkdownV2")
    
    success_count = 0
    failed_count = 0
    checkpoint = max(1, int(total_users / 10))  # Update admin progress status every 10%
    
    for idx, u in enumerate(users):
        try:
            with SessionLocal() as db:
                db_user = db.query(DBUser).filter(DBUser.telegram_id == u.telegram_id).first()
                db_user.balance += gift_amount
                
                tx = DBTransaction(
                    user_id=db_user.id,
                    type="GiftByAdmin",
                    amount=gift_amount,
                    status="success",
                    description=f"دریافت هدیه همگانی به مبلغ {gift_amount:,} تومان از طرف مدیریت"
                )
                db.add(tx)
                db.commit()
                
            success_count += 1
            
            # Send notification to targeted user asynchronously
            try:
                await bot.send_message(
                    chat_id=u.telegram_id,
                    text=f"🎁 *هدیه جدید دریافت شد\\!*\n\nمبلغ *{escape_md(f'{int(gift_amount):,}')}* تومان هدیه نقدی از طرف مدیریت به کیف پول شما افزوده شد\\.\nموجودی جدید شما: *{escape_md(f'{int(db_user.balance):,}')}* تومان",
                    parse_mode="MarkdownV2"
                )
            except Exception:
                pass
                
            await asyncio.sleep(0.05)  # Enforce strict delay to respect Telegram limits
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            failed_count += 1
        except Exception:
            failed_count += 1
            
        # Update progress every 10% checkpoint completed
        if (idx + 1) % checkpoint == 0 or (idx + 1) == total_users:
            percentage = int(((idx + 1) / total_users) * 100)
            try:
                await progress_message.edit_text(f"⏳ فرآیند اعطای هدیه با موفقیت در جریان است: *{percentage}%*\n\nتعداد کل اعضا: {total_users}\nتعداد پرداخت موفق: {success_count}\nپرداخت ناموفق: {failed_count}", parse_mode="MarkdownV2")
            except Exception:
                pass
                
    await progress_message.reply(
        f"🎁 *پایان گزارش توزیع هدیه مالی همگانی:*\n\n"
        f"✅ توزیع موفقیت‌آمیز: *{success_count}* کاربر\n"
        f"❌ ناموفق / مسدود شده: *{failed_count}* کاربر\n"
        f"💵 کل اعتبار توزیع شده: *{escape_md(f'{int(success_count * gift_amount):,}')}* تومان",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
        ]),
        parse_mode="MarkdownV2"
    )

# ---------------------------------------------------------------------------
# 11.0.3 Discount Codes Panel (Admin Menu)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_discounts_menu")
async def adm_discounts_menu(callback: CallbackQuery, state: FSMContext):
    """Renders promo codes configuration dashboards for administrators."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    await state.clear()
    
    with SessionLocal() as db:
        codes = db.query(DBDiscountCode).all()
        
    txt = "🎟 *پنل مدیریت کدهای تخفیف سیستم*\n\n"
    if not codes:
        txt += "⚠️ در حال حاضر هیچ کد تخفیفی در سیستم ثبت نشده است\\."
    else:
        for c in codes:
            act_symbol = "🟢 فعال" if c.is_active else "🔴 غیرفعال"
            type_label = "درصدی" if c.discount_type == "percent" else "نقدی ثابت"
            val_label = f"{int(c.value)}%" if c.discount_type == "percent" else f"{int(c.value):,} تومان"
            limit_lbl = f"{c.used_count}/{c.usage_limit}"
            usr_restriction = f"مخصوص کاربر {c.specific_user_id}" if c.specific_user_id else "عمومی"
            
            txt += (
                f"🎟 کد: `{escape_md_code(c.code)}` \\({escape_md(act_symbol)}\\)\n"
                f"▫️ نوع: {escape_md(type_label)} | مقدار: *{escape_md(val_label)}*\n"
                f"▫️ استفاده: {escape_md(limit_lbl)} بار | تخصیص: *{escape_md(usr_restriction)}*\n\n"
            )
            
    kb = [
        [InlineKeyboardButton(text="➕ ساخت کد تخفیف جدید", callback_data="adm_discount_create_init")],
        [InlineKeyboardButton(text="❌ حذف یک کد تخفیف", callback_data="adm_discount_delete_init")],
        [InlineKeyboardButton(text="🔙 بازگشت به پنل ادمین", callback_data="btn_admin_panel")]
    ]
    
    await safe_edit(callback.message, txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data == "adm_discount_create_init")
async def adm_discount_create_init(callback: CallbackQuery, state: FSMContext):
    """Launches wizard to configure custom codes."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "🎟 *مرحله ۱:* لطفاً کد تخفیف انحصاری را وارد کنید \\(فقط حروف و اعداد انگلیسی بدون خط فاصله\\):\n\nمثال: `OFF30`",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AdminStates.waiting_for_dc_code)
    await callback.answer()

@router.message(AdminStates.waiting_for_dc_code)
async def process_dc_code_step(message: Message, state: FSMContext):
    """Processes promocode text and asks code type choice."""
    code_str = message.text.strip().upper()
    if not re.match(r"^[A-Z0-9]{3,15}$", code_str):
        return await message.reply("❌ خطا: کد تخفیف فقط باید شامل حروف انگلیسی و اعداد بین ۳ تا ۱۵ کاراکتر باشد\\. مجدداً وارد کنید:", parse_mode="MarkdownV2")
        
    with SessionLocal() as db:
        existing = db.query(DBDiscountCode).filter(DBDiscountCode.code == code_str).first()
        if existing:
            return await message.reply("❌ خطا: این کد تخفیف قبلاً در دیتابیس تعریف شده است\\. لطفا یک کد دیگر وارد کنید:", parse_mode="MarkdownV2")
            
    await state.update_data(new_dc_code=code_str)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎟 درصد کاهش قیمت (Percentage)", callback_data="dc_set_type_percent"),
            InlineKeyboardButton(text="💵 کاهش مبلغ ثابت (Flat Amount)", callback_data="dc_set_type_amount")
        ]
    ])
    await message.reply("🎟 *مرحله ۲:* نوع اعمال تخفیف را مشخص کنید:", reply_markup=kb, parse_mode="MarkdownV2")
    await state.set_state(AdminStates.waiting_for_dc_type)

@router.callback_query(F.data.startswith("dc_set_type_"), AdminStates.waiting_for_dc_type)
async def process_dc_type_step(callback: CallbackQuery, state: FSMContext):
    """Processes discount valuation type."""
    selected_type = "percent" if "percent" in callback.data else "amount"
    await state.update_data(new_dc_type=selected_type)
    
    prompt = (
        "🎟 *مرحله ۳:* درصد تخفیف را به صورت عددی بین ۱ تا ۱۰۰ \\(بدون % و انگلیسی\\) وارد کنید:"
        if selected_type == "percent" else
        "💵 *مرحله ۳:* مبلغ تخفیف نقدی را به *تومان* \\(انگلیسی\\) وارد کنید:"
    )
    await callback.message.edit_text(prompt, parse_mode="MarkdownV2")
    await state.set_state(AdminStates.waiting_for_dc_value)
    await callback.answer()

@router.message(AdminStates.waiting_for_dc_value)
async def process_dc_value_step(message: Message, state: FSMContext):
    """Processes discount absolute values constraints."""
    val_str = message.text.strip()
    if not val_str.isdigit():
        return await message.reply("❌ خطا: لطفاً مقدار را به صورت یک عدد عددی انگلیسی وارد کنید:", parse_mode="MarkdownV2")
        
    val = float(val_str)
    state_data = await state.get_data()
    dc_type = state_data["new_dc_type"]
    
    if dc_type == "percent" and (val < 1 or val > 100):
        return await message.reply("❌ خطا: درصد تخفیف حتماً باید یک عدد صحیح بین ۱ تا ۱۰۰ باشد\\. مجدداً وارد کنید:", parse_mode="MarkdownV2")
        
    await state.update_data(new_dc_value=val)
    await message.reply("🎟 *مرحله ۴:* حداکثر تعداد دفعات مجاز برای استفاده کل کاربران از این کد را به عدد انگلیسی وارد کنید:\n\nمثال: `100`", parse_mode="MarkdownV2")
    await state.set_state(AdminStates.waiting_for_dc_limit)

@router.message(AdminStates.waiting_for_dc_limit)
async def process_dc_limit_step(message: Message, state: FSMContext):
    """Processes total discount usages limit."""
    limit_str = message.text.strip()
    if not limit_str.isdigit():
        return await message.reply("❌ خطا: لطفاً تعداد را به صورت عدد انگلیسی وارد کنید:", parse_mode="MarkdownV2")
        
    limit = int(limit_str)
    if limit < 1:
        return await message.reply("❌ خطا: حداقل تعداد دفعات استفاده باید ۱ باشد\\. مجدداً وارد کنید:", parse_mode="MarkdownV2")
        
    await state.update_data(new_dc_limit=limit)
    await message.reply("🎟 *مرحله ۵:* طول عمر و مدت اعتبار کد تخفیف را به *روز* وارد نمایید \\(مثلا عدد `7` برای اعتبار یک هفته‌ای\\. جهت بی‌محدودیت بودن عدد `0` بفرستید\\):", parse_mode="MarkdownV2")
    await state.set_state(AdminStates.waiting_for_dc_expiry)

@router.message(AdminStates.waiting_for_dc_expiry)
async def process_dc_expiry_step(message: Message, state: FSMContext):
    """Processes discount expiration dates."""
    days_str = message.text.strip()
    if not days_str.isdigit():
        return await message.reply("❌ خطا: طول عمر اعتبار را به صورت عدد عددی انگلیسی وارد کنید:", parse_mode="MarkdownV2")
        
    days = int(days_str)
    await state.update_data(new_dc_expiry_days=days)
    
    await message.reply(
        "🎟 *مرحله ۶:* آیا مایلید این کد تخفیف را مخصوص یک کاربر خاص \\(با آیدی عددی او\\) تعریف کنید؟\n\n"
        "\\_(جهت ساخت کد عمومی عدد `0` را ارسال کنید و در غیر این صورت آیدی عددی تلگرام کاربر هدف را بفرستید\\)_",
        parse_mode="MarkdownV2"
    )
    await state.set_state(AdminStates.waiting_for_dc_user_restriction)

@router.message(AdminStates.waiting_for_dc_user_restriction)
async def process_dc_final_save_step(message: Message, state: FSMContext):
    """Completes and persists newly defined discount codes."""
    user_restrict_str = message.text.strip()
    if not user_restrict_str.isdigit():
        return await message.reply("❌ خطا: لطفاً آیدی عددی معتبر یا عدد ۰ بفرستید:", parse_mode="MarkdownV2")
        
    target_uid = int(user_restrict_str)
    state_data = await state.get_data()
    
    code = state_data["new_dc_code"]
    dc_type = state_data["new_dc_type"]
    val = state_data["new_dc_value"]
    limit = state_data["new_dc_limit"]
    expiry_days = state_data["new_dc_expiry_days"]
    
    expiry_date = None
    if expiry_days > 0:
        expiry_date = datetime.utcnow() + timedelta(days=expiry_days)
        
    specific_user = None
    if target_uid > 0:
        specific_user = target_uid
        
    with SessionLocal() as db:
        new_dc = DBDiscountCode(
            code=code,
            discount_type=dc_type,
            value=val,
            usage_limit=limit,
            expiry_date=expiry_date,
            specific_user_id=specific_user,
            is_active=True
        )
        db.add(new_dc)
        db.commit()
        
    await message.reply(
        f"✅ کد تخفیف `{escape_md_code(code)}` با موفقیت ایجاد و فعال گردید\\.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به منوی کدهای تخفیف", callback_data="adm_discounts_menu")]
        ]),
        parse_mode="MarkdownV2"
    )
    await state.clear()

@router.callback_query(F.data == "adm_discount_delete_init")
async def adm_discount_delete_init(callback: CallbackQuery):
    """Prompts discount code key to process dynamic deletion."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    with SessionLocal() as db:
        codes = db.query(DBDiscountCode).filter(DBDiscountCode.is_active == True).all()
        
    if not codes:
        return await callback.answer("⚠️ در حال حاضر هیچ کد تخفیف فعالی جهت حذف وجود ندارد\\.", show_alert=True)
        
    kb = []
    for c in codes:
        kb.append([InlineKeyboardButton(text=f"❌ حذف کد: {c.code}", callback_data=f"dc_del_{c.id}")])
        
    kb.append([InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_discounts_menu")])
    await callback.message.edit_text("🎟 کد تخفیف مورد نظر جهت حذف و ابطال دائمی را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()

@router.callback_query(F.data.startswith("dc_del_"))
async def process_dc_deletion_confirmed(callback: CallbackQuery):
    """Deletes promotion code entry inside databases."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    dc_id = int(callback.data.split("_")[2])
    with SessionLocal() as db:
        dc = db.query(DBDiscountCode).get(dc_id)
        if dc:
            db.delete(dc)
            db.commit()
            
    await callback.answer("✅ کد تخفیف با موفقیت حذف گردید\\.", show_alert=True)
    await adm_discounts_menu(callback, FSMContext)

# ---------------------------------------------------------------------------
# 11.14 Config JSON Export/Import Settings
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_download_config_json")
async def adm_download_config_json_callback(callback: CallbackQuery):
    """Downloads reseller_config.json raw format to admin."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    try:
        doc = FSInputFile(path=CONFIG_PATH, filename="reseller_config.json")
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 فایل کامل تنظیمات و پیکربندی ربات")
        await callback.answer("✅ فایل پیکربندی ارسال شد\\.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال فایل: {e}", show_alert=True)

@router.callback_query(F.data == "adm_upload_config_json")
async def adm_upload_config_json_callback(callback: CallbackQuery, state: FSMContext):
    """Requests replacement JSON document to overwrite current reseller_config."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "📤 *آپلود مستقیم فایل جدید reseller_config.json*\n\n"
        "لطفاً فایل متنی جدید تنظیمات خود را با پسوند `.json` در همین بخش ارسال نمایید:\n"
        "⚠️ هشدار: قالب کلیدها باید دقیقاً مشابه نمونه اصلی باشد\\.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="btn_admin_panel")]
        ]),
        parse_mode="MarkdownV2"
    )
    await state.set_state(AdminStates.waiting_for_config_json_upload)
    await callback.answer()

@router.message(AdminStates.waiting_for_config_json_upload, F.document)
async def process_config_json_upload_save(message: Message, state: FSMContext):
    """Validates uploaded configuration structure and applies overrides."""
    doc: Document = message.document
    if not doc.file_name.endswith(".json"):
        return await message.reply("❌ خطا: فایل ارسالی باید دارای پسوند معتبر .json باشد\\.", parse_mode="MarkdownV2")
        
    await message.reply("⏳ در حال دریافت و اعتبارسنجی ساختار فایل پیکربندی\\.\\.\\.", parse_mode="MarkdownV2")
    
    try:
        file_info = await bot.get_file(doc.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        content = downloaded_file.read().decode("utf-8")
        parsed_data = json.loads(content)
        
        required_keys = ["BOT_TOKEN", "ADMIN_IDS", "API_KEY", "API_BASE_URL", "CARD_NUMBER", "CARD_HOLDER"]
        missing_keys = [k for k in required_keys if k not in parsed_data]
        if missing_keys:
            return await message.reply(f"❌ خطا در قالب‌بندی: برخی از متغیرهای اصلی پیکربندی در فایل شما یافت نشد\\.\nمتغیرهای مفقود شده: `{escape_md_code(', '.join(missing_keys))}`", parse_mode="MarkdownV2")
            
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=4, ensure_ascii=False)
            
        global config
        config = parsed_data
        
        await state.clear()
        await message.reply(
            "✅ فایل جدید پیکربندی ربات با موفقیت جایگزین شد و تغییرات بلافاصله روی ربات اعمال گردید\\.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
            ]),
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        await message.reply(f"❌ خطا در پردازش یا تجزیه ساختار فایل تنظیمات ارسالی: {e}")

# ---------------------------------------------------------------------------
# Dynamic Configuration Keys Editor
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_edit_config_menu")
async def adm_edit_config_menu(callback: CallbackQuery):
    """Renders keyboard to select and update system config variables."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    txt = (
        "⚙️ *تنظیمات و پیکربندی متغیرهای سیستم*\n\n"
        "یکی از متغیرهای زیر را جهت ویرایش انتخاب کنید:"
    )
    
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
    
    await safe_edit(callback.message, txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data.startswith("cfg_edit_"))
async def adm_cfg_edit_key(callback: CallbackQuery, state: FSMContext):
    """Sets state to collect custom value corresponding to selected setting key."""
    key = callback.data.replace("cfg_edit_", "")
    await state.update_data(editing_config_key=key)
    current_val = config.get(key, "تعریف نشده")
    
    await callback.message.edit_text(
        f"✏️ *ویرایش متغیر: {escape_md(key)}*\n\n"
        f"مقدار فعلی: `{escape_md_code(str(current_val))}`\n\n"
        "لطفاً مقدار جدید را ارسال نمایید:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_edit_config_menu")]
        ]),
        parse_mode="MarkdownV2"
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
            return await message.reply("❌ خطا: آیدی کانال حتما باید به صورت یک عدد علامت‌دار (مانند -100123456789) وارد شود\\.", parse_mode="MarkdownV2")
    else:
        config[key] = val_str
        
    save_config_file()
    await state.clear()
    
    await message.reply(
        f"✅ متغیر `{escape_md_code(key)}` با موفقیت ویرایش گردید و ثبت شد\\.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به منوی تنظیمات", callback_data="adm_edit_config_menu")]
        ]),
        parse_mode="MarkdownV2"
    )

# ---------------------------------------------------------------------------
# Dynamic External Texts Localization Manager
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_manage_texts_menu")
async def adm_manage_texts_menu(callback: CallbackQuery, state: FSMContext):
    """Provides complete text manager interface with dynamic file tools."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    await state.clear()
    
    txt = (
        "📝 *مدیریت و ویرایش متون و پیام‌های ربات*\n\n"
        "شما می‌توانید پیام‌های سیستمی ربات را به صورت تکی ویرایش نمایید، "
        "یا کل فایل پیام‌ها را به صورت JSON دانلود و پس از اعمال تغییرات دلخواه، آپلود کنید تا فوراً تغییر کند\\."
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
    
    await safe_edit(callback.message, txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

@router.callback_query(F.data.startswith("txt_edit_"))
async def adm_txt_edit_key(callback: CallbackQuery, state: FSMContext):
    """Sets state to collect custom text string for localized variable."""
    key = callback.data.replace("txt_edit_", "")
    await state.update_data(editing_text_key=key)
    current_val = bot_texts.get(key, DEFAULT_TEXTS.get(key, "تعریف نشده"))
    
    await callback.message.edit_text(
        f"✏️ *ویرایش متن سیستمی: {escape_md(key)}*\n\n"
        f"مقدار فعلی:\n`{escape_md_code(str(current_val))}`\n\n"
        "لطفاً متن جدید را تایپ و ارسال کنید:\n"
        "\\_(دقت کنید متغیرهایی مانند `{balance}`، `{amount}` و... در صورت وجود دست\\-نخورده باقی بمانند\\)_",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_manage_texts_menu")]
        ]),
        parse_mode="MarkdownV2"
    )
    await state.set_state(AdminStates.waiting_for_text_key_value)
    await callback.answer()

@router.message(AdminStates.waiting_for_text_key_value)
async def process_txt_key_value_save(message: Message, state: FSMContext):
    """Saves updated localized string in external texts dictionary storage."""
    state_data = await state.get_data()
    key = state_data["editing_text_key"]
    val_str = message.text.strip()
    
    bot_texts[key] = val_str
    save_texts_file()
    await state.clear()
    
    await message.reply(
        f"✅ پیام مربوط به متغیر `{escape_md_code(key)}` با موفقیت ویرایش و ثبت شد\\.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به مدیریت متون", callback_data="adm_manage_texts_menu")]
        ]),
        parse_mode="MarkdownV2"
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
        await callback.answer("✅ فایل متون ارسال شد\\.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال فایل: {e}", show_alert=True)

@router.callback_query(F.data == "txt_upload_json")
async def txt_upload_json_callback(callback: CallbackQuery, state: FSMContext):
    """Requests replacement JSON document to overwrite current bot_texts."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text(
        "📤 *آپلود مستقیم فایل reseller_texts.json*\n\n"
        "لطفاً فایل متنی جدید خود را با فرمت `.json` و با نام ترجیحی `reseller_texts.json` در همین بخش ارسال نمایید:\n"
        "⚠️ هشدار: ساختار کلیدها باید دقیقاً مشابه نمونه اصلی باشد\\.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="adm_manage_texts_menu")]
        ]),
        parse_mode="MarkdownV2"
    )
    await state.set_state(AdminStates.waiting_for_texts_json_upload)
    await callback.answer()

@router.message(AdminStates.waiting_for_texts_json_upload, F.document)
async def process_texts_json_upload_save(message: Message, state: FSMContext):
    """Validates uploaded texts configuration and overwrites the active dictionary."""
    doc: Document = message.document
    if not doc.file_name.endswith(".json"):
        return await message.reply("❌ خطا: فایل ارسالی باید دارای پسوند معتبر .json باشد\\.", parse_mode="MarkdownV2")
        
    await message.reply("⏳ در حال دریافت و اعتبارسنجی فایل متون\\.\\.\\.", parse_mode="MarkdownV2")
    
    try:
        file_info = await bot.get_file(doc.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        content = downloaded_file.read().decode("utf-8")
        parsed_data = json.loads(content)
        
        missing_keys = [k for k in DEFAULT_TEXTS.keys() if k not in parsed_data]
        if missing_keys:
            return await message.reply(f"❌ خطا در قالب‌بندی: برخی از کلیدهای پیش‌فرض ساختاری ربات در این فایل یافت نشدند\\.\nکلیدهای مفقوده: `{escape_md_code(', '.join(missing_keys))}`", parse_mode="MarkdownV2")
            
        with open(TEXTS_PATH, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=4, ensure_ascii=False)
            
        global bot_texts
        bot_texts = load_or_create_texts()
        
        await state.clear()
        await message.reply(
            "✅ فایل جدید متون با موفقیت جایگزین شد و تغییرات بلافاصله روی ربات اعمال گردید\\.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به مدیریت متون", callback_data="adm_manage_texts_menu")]
            ]),
            parse_mode="MarkdownV2"
        )
    except Exception as e:
        await message.reply(f"❌ خطا در پردازش یا تجزیه ساختار فایل متون ارسالی: {e}")

# ---------------------------------------------------------------------------
# Toggles (Maintenance & Shop Status)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_toggle_maint")
async def adm_toggle_maint(callback: CallbackQuery, state: FSMContext):
    """Toggles active state of Maintenance Mode."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    config["MAINTENANCE_MODE"] = not config.get("MAINTENANCE_MODE", False)
    save_config_file()
    status_word = "فعال" if config["MAINTENANCE_MODE"] else "غیرفعال"
    await callback.answer(f"🔧 وضعیت تعمیرات ربات {status_word} شد\\.", show_alert=True)
    await admin_panel_callback(callback, state)

@router.callback_query(F.data == "adm_toggle_shop")
async def adm_toggle_shop(callback: CallbackQuery, state: FSMContext):
    """Toggles active state of Shop Open/Closed."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    config["SHOP_CLOSED"] = not config.get("SHOP_CLOSED", False)
    save_config_file()
    status_word = "بسته" if config["SHOP_CLOSED"] else "باز"
    await callback.answer(f"🛒 فروشگاه {status_word} شد\\.", show_alert=True)
    await admin_panel_callback(callback, state)

# ---------------------------------------------------------------------------
# Exports and Downloads
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
        await callback.answer("✅ فایل با موفقیت صادر شد\\.")
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
        await callback.answer("✅ فایل با موفقیت صادر شد\\.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال فایل: {e}", show_alert=True)

@router.callback_query(F.data == "adm_dl_db_bin")
async def download_db_binary(callback: CallbackQuery):
    """Packages live database file for direct secure administrative downloads."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    db_file_path = "reseller_bot.db"
    if not os.path.exists(db_file_path):
        return await callback.answer("❌ دیتابیس در مسیر جاری یافت نشد\\.", show_alert=True)
        
    try:
        doc = FSInputFile(path=db_file_path, filename="reseller_bot.db")
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 دیتابیس باینری فعلی سیستم (SQLite)")
        await callback.answer("✅ فایل دیتابیس با موفقیت ارسال شد\\.")
    except Exception as e:
        await callback.answer(f"❌ خطا در ارسال دیتابیس: {e}", show_alert=True)

@router.callback_query(F.data == "adm_dl_db_sql")
async def download_db_sql_dump(callback: CallbackQuery):
    """Produces structured logical SQL export containing DDL/DML statements."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    import sqlite3
    db_file_path = "reseller_bot.db"
    if not os.path.exists(db_file_path):
        return await callback.answer("❌ دیتابیس یافت نشد\\.", show_alert=True)
        
    try:
        conn = sqlite3.connect(db_file_path)
        out = io.StringIO()
        for line in conn.iterdump():
            out.write(line + "\n")
        conn.close()
        
        sql_bytes = out.getvalue().encode("utf-8")
        doc = BufferedInputFile(sql_bytes, filename="reseller_bot_dump.sql")
        
        await bot.send_document(chat_id=callback.from_user.id, document=doc, caption="📂 بکاپ کامل ساختاری و داده‌ای SQL")
        await callback.answer("✅ بکاپ SQL با موفقیت ارسال شد\\.")
    except Exception as e:
        await callback.answer(f"❌ خطا در تولید بکاپ: {e}", show_alert=True)

# ---------------------------------------------------------------------------
# Stats Panel
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_stats")
async def adm_stats_callback(callback: CallbackQuery):
    """Queries and displays local database and central balance diagnostics."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text("⏳ در حال استخراج و تحلیل داده‌های مالی\\.\\.\\.", parse_mode="MarkdownV2")
    
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
        f"📊 *گزارش آمار و فرآیندهای مالی ربات*\n\n"
        f"👥 کل کاربران عضو: *{total_users}* نفر\n"
        f"🛠 کل سرویس‌های فعال: *{total_srv}* عدد\n"
        f"⏳ فیش‌های معلق: *{total_pending}* عدد\n\n"
        f"💳 مجموع موجودی کاربران: *{escape_md(f'{int(user_balances_sum):,}')}* تومان\n"
        f"🔌 اعتبار تایید شده در وب‌سرویس اصلی: *{escape_md(central_bal_text)}*"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل ادمین", callback_data="btn_admin_panel")]
    ])
    await callback.message.edit_text(txt, reply_markup=kb, parse_mode="MarkdownV2")
    await callback.answer()

# ---------------------------------------------------------------------------
# Central API Balance Check
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "adm_central_bal")
async def adm_central_bal_callback(callback: CallbackQuery):
    """Establishes transaction call on master API to query central reseller balance."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    await callback.message.edit_text("⏳ در حال استعلام تراز مالی وب‌سرویس\\.\\.\\.", parse_mode="MarkdownV2")
    res = api.get_balance()
    if res and res.get("success"):
        bal = res.get("balance", 0)
        txt = (
            f"🔌 *موجودی حساب وب‌سرویس نماینده*\n\n"
            f"موجودی فعلی حساب شما در پنل اصلی: *{escape_md(f'{int(bal):,}')}* تومان\n\n"
            "تراکنش‌های خرید مستقیم از این اعتبار کسر می‌شود\\."
        )
    else:
        txt = "❌ دریافت اطلاعات موجودی وب‌سرویس اصلی با خطا مواجه شد\\."
        
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")]
    ])
    await safe_edit(callback.message, txt, reply_markup=kb, parse_mode="MarkdownV2")
    await callback.answer()

# ---------------------------------------------------------------------------
# Paginated User List View (2 Columns)
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
        
    txt = "👥 *لیست کاربران دیتابیس \\(صفحه‌بندی شده\\):*\n\n"
    for u in users:
        with SessionLocal() as db:
            rank, _ = calculate_user_rank(db, u.id)
        status_symbol = "🟢" if u.is_active else "🔴"
        ban_text = " \\[ مسدود شده \\]" if u.is_banned else ""
        txt += f"👤 {status_symbol} [{escape_md(u.first_name or 'Unknown')}](tg://user?id={u.telegram_id}) \\(`{u.telegram_id}`\\){ban_text}\n"
        txt += f"▫️ رتبه: *{escape_md(rank)}*\n"
        txt += f"▫️ تراز حساب: *{escape_md(f'{int(u.balance):,}')}* تومان\n"
        txt += f"▫️ پیوستن: {escape_md(u.joined_at.strftime('%Y-%m-%d %H:%M'))}\n\n"
            
    kb_nav = []
    if page > 0:
        kb_nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"adm_view_users_{page - 1}"))
    if offset + limit < total_users:
        kb_nav.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"adm_view_users_{page + 1}"))
        
    kb = [kb_nav] if kb_nav else []
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")])
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

# ---------------------------------------------------------------------------
# Paginated Services List View (2 Columns)
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
        
    txt = "🛠 *لیست سرویس‌های خریداری شده:*\n\n"
    for s in services:
        txt += f"🖥 سرویس: *{escape_md(s.name)}* \\(ID: {s.service_id}\\)\n"
        txt += f"▫️ آیدی خریدار: `{s.user_id}`\n"
        txt += f"▫️ کلید UUID:\n`{escape_md_code(s.uuid)}`\n"
        txt += f"▫️ وضعیت: {escape_md(s.status)}\n\n"
        
    kb_nav = []
    if page > 0:
        kb_nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"adm_view_services_{page - 1}"))
    if offset + limit < total_srv:
        kb_nav.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"adm_view_services_{page + 1}"))
        
    kb = [kb_nav] if kb_nav else []
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")])
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

# ---------------------------------------------------------------------------
# Paginated Transactions List View (2 Columns)
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
        
    txt = "💰 *گزارش تراکنش‌های مالی اخیر:*\n\n"
    for t in transactions:
        sign = "\\+" if t.amount > 0 else ""
        txt += f"🔋 تراکنش: *{escape_md(t.type)}* \\(ID: {t.id}\\)\n"
        txt += f"▫️ مبلغ: *{sign}{escape_md(f'{int(t.amount):,}')}* تومان\n"
        txt += f"▫️ وضعیت تراکنش: *{escape_md(t.status)}*\n"
        txt += f"▫️ شرح: {escape_md(t.description or '-')}\n"
        txt += f"▫️ تاریخ: {escape_md(t.date.strftime('%Y-%m-%d %H:%M'))}\n\n"
        
    kb_nav = []
    if page > 0:
        kb_nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"adm_view_txs_{page - 1}"))
    if offset + limit < total_txs:
        kb_nav.append(InlineKeyboardButton(text="بعدی ➡️", callback_data=f"adm_view_txs_{page + 1}"))
        
    kb = [kb_nav] if kb_nav else []
    kb.append([InlineKeyboardButton(text="🔙 بازگشت به پنل مدیریت", callback_data="btn_admin_panel")])
    
    await callback.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="MarkdownV2")
    await callback.answer()

# ---------------------------------------------------------------------------
# Pending Receipt Verification View
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "btn_admin_review_pending")
async def admin_review_pending_callback(callback: CallbackQuery):
    """Loads first active pending receipt photo and attaches verification inline."""
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    
    with SessionLocal() as db:
        tx = db.query(DBTransaction).filter(DBTransaction.status == "pending").first()
        if not tx:
            return await callback.message.edit_text("✅ تمام فیش‌های واریزی بررسی شده‌اند و در حال حاضر فیش جدیدی موجود نیست\\.", reply_markup=back_to_menu_keyboard(), parse_mode="MarkdownV2")
            
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
            caption=f"👤 کاربر: {escape_md(user.first_name or '')} \\({user.telegram_id}\\)\n💵 مبلغ درخواستی: *{escape_md(f'{tx.amount:,}')}* تومان\n\nآیا این رسید معتبر است؟",
            reply_markup=kb,
            parse_mode="MarkdownV2"
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(
            f"👤 کاربر: {escape_md(user.first_name or '')} \\({user.telegram_id}\\)\n"
            f"💵 مبلغ: *{escape_md(f'{tx.amount:,}')}* تومان\n"
            f"ℹ️ توضیحات: {escape_md(tx.description or 'ندارد')}\n"
            f"🔑 هش تراکنش: `{escape_md_code(tx.tx_hash or 'ندارد')}`\n\n"
            "آیا مایل به تایید این واریزی بدون فیش تصویری هستید؟",
            reply_markup=kb,
            parse_mode="MarkdownV2"
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
            return await callback.answer("⚠️ این فیش قبلاً تعیین تکلیف شده است\\.", show_alert=True)
            
        user = db.query(DBUser).get(tx.user_id)
        
        if action == "approve":
            tx.status = "success"
            user.balance += tx.amount
            db.commit()
            
            await callback.answer("✅ تراکنش با موفقیت تایید شد و موجودی کاربر افزایش یافت\\.", show_alert=True)
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"✅ *...واریز کارت به کارت شما تایید شد\\!*\n\nمبلغ *{escape_md(f'{int(tx.amount):,}')}* تومان به کیف پول شما افزوده شد\\.\nموجودی فعلی شما: *{escape_md(f'{int(user.balance):,}')}* تومان",
                    parse_mode="MarkdownV2"
                )
            except Exception:
                pass
            
            try:
                await callback.message.edit_caption(caption=f"✅ رسید به مبلغ {escape_md(f'{int(tx.amount):,}')} تومان توسط ادمین *تایید* شد\\.", parse_mode="MarkdownV2")
            except Exception:
                await callback.message.edit_text(text=f"✅ رسید به مبلغ {escape_md(f'{int(tx.amount):,}')} تومان توسط ادمین *تایید* شد\\.", parse_mode="MarkdownV2")

            for admin_id in config["ADMIN_IDS"]:
                if admin_id != callback.from_user.id:
                    try:
                        await bot.send_message(chat_id=admin_id, text=f"💰 افزایش تراز تایید شده: کاربر {user.telegram_id} مبلغ {tx.amount:,} تومان دریافت کرد\\.", parse_mode="MarkdownV2")
                    except Exception: pass
        else:
            tx.status = "rejected"
            db.commit()
            
            await callback.answer("❌ تراکنش رد شد\\.", show_alert=True)
            try:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=f"❌ *تراکنش واریز شما تایید نشد\\!*\n\nدرخواست شارژ به مبلغ *{escape_md(f'{int(tx.amount):,}')}* تومان رد شد\\. در صورت نیاز با پشتیبانی در ارتباط باشید\\.",
                    parse_mode="MarkdownV2"
                )
            except Exception:
                pass
                
            try:
                await callback.message.edit_caption(caption=f"❌ رسید به مبلغ {escape_md(f'{int(tx.amount):,}')} تومان توسط ادمین *رد* شد\\.", parse_mode="MarkdownV2")
            except Exception:
                await callback.message.edit_text(text=f"❌ رسید به مبلغ {escape_md(f'{int(tx.amount):,}')} تومان توسط ادمین *رد* شد\\.", parse_mode="MarkdownV2")

# ---------------------------------------------------------------------------
# 12. Automated Scheduled Tasks (Backups & Monitor)
# ---------------------------------------------------------------------------
def parse_days_left(expire_date_str):
    if not expire_date_str or "نامحدود" in expire_date_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return (datetime.strptime(expire_date_str, fmt) - datetime.utcnow()).days
        except ValueError:
            continue
    return None

async def service_usage_monitor():
    while True:
        await asyncio.sleep(1800)
        try:
            with SessionLocal() as db:
                for s in db.query(DBService).all():
                    details = api.get_service_details(s.service_id)
                    if not details or not details.get("success"):
                        continue
                    user = db.query(DBUser).get(s.user_id)
                    if not user:
                        continue
                    total_gb = float(details.get("traffic_total_gb") or 0.0)
                    used_gb = float(details.get("traffic_used_gb") or 0.0)
                    expire_date = details.get("expire_date")
                    sub_url = details.get("sub_url") or s.sub_url
                    pct = (used_gb / total_gb * 100) if total_gb > 0 else 0.0
                    days_left = parse_days_left(expire_date)
                    alerts = []
                    if total_gb > 0 and used_gb >= total_gb and not s.alert_100p:
                        s.alert_100p = True
                        alerts.append(("100p", "🚫 ترافیک سرویس شما به اتمام رسید"))
                    elif pct >= 90 and not s.alert_90p:
                        s.alert_90p = True
                        alerts.append(("90p", "⚠️ ۹۰٪ از حجم ترافیک سرویس مصرف شده است"))
                    elif pct >= 80 and not s.alert_80p:
                        s.alert_80p = True
                        alerts.append(("80p", "⚠️ ۸۰٪ از حجم ترافیک سرویس مصرف شده است"))
                    elif pct >= 50 and not s.alert_50p:
                        s.alert_50p = True
                        alerts.append(("50p", "ℹ️ ۵۰٪ از حجم ترافیک سرویس مصرف شده است"))
                    if days_left is not None:
                        if days_left <= 1 and not s.alert_1d:
                            s.alert_1d = True
                            alerts.append(("1d", "🚨 فقط ۱ روز تا پایان اعتبار سرویس باقی مانده است"))
                        elif days_left <= 50 and not s.alert_50d:
                            s.alert_50d = True
                            alerts.append(("50d", "ℹ️ ۵۰ روز تا پایان اعتبار سرویس باقی مانده است"))
                    if alerts:
                        db.commit()
                        for alert_type, title in alerts:
                            msg_usr = (
                                f"🔔 *{title}*\n\n"
                                f"🖥 نام سرویس: `{escape_md_code(s.name)}`\n"
                                f"📊 مصرف: *{escape_md(f'{used_gb:.2f}')}* از *{escape_md(f'{total_gb:.2f}')} GB*\n"
                                f"⏳ انقضا: *{escape_md(expire_date or 'نامحدود')}*\n"
                                f"🔗 لینک اشتراک:\n`{escape_md_code(sub_url)}`"
                            )
                            kb_usr = InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="🔄 تمدید سریع سرویس", callback_data=f"srv_renew_{s.id}")],
                                [InlineKeyboardButton(text="🛒 خرید سرویس جدید", callback_data="btn_buy_service")]
                            ])
                            try:
                                await bot.send_message(chat_id=user.telegram_id, text=msg_usr, reply_markup=kb_usr, parse_mode="MarkdownV2")
                            except Exception:
                                pass
                            msg_adm = (
                                f"📢 *هشدار مصرف سرویس کاربران*\n\n"
                                f"👤 کاربر: {escape_md(user.first_name or '')} \\({user.telegram_id}\\)\n"
                                f"🖥 سرویس: `{escape_md_code(s.name)}`\n"
                                f"🚨 نوع هشدار: *{escape_md(title)}*\n"
                                f"📊 مصرف: {used_gb:.2f} / {total_gb:.2f} GB\n"
                                f"⏳ انقضا: {expire_date or 'نامحدود'}"
                            )
                            kb_adm = InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="👤 مشاهده پروفایل کاربر", callback_data=f"adm_usr_view_{user.id}")]
                            ])
                            for aid in config["ADMIN_IDS"]:
                                try:
                                    await bot.send_message(chat_id=aid, text=msg_adm, reply_markup=kb_adm, parse_mode="MarkdownV2")
                                except Exception:
                                    pass
        except Exception as ex:
            logger.error(f"Error in monitor: {ex}")

@router.callback_query(F.data.startswith("adm_usr_view_"))
async def adm_usr_view_callback(callback: CallbackQuery):
    if callback.from_user.id not in config["ADMIN_IDS"]: return
    usr_id = int(callback.data.split("_")[3])
    with SessionLocal() as db:
        u = db.query(DBUser).get(usr_id)
        if not u:
            return await callback.answer("کاربر پیدا نشد.", show_alert=True)
        rank, _ = calculate_user_rank(db, u.id)
        txt = (
            f"👤 مشخصات کاربر:\n\n"
            f"آیدی عددی: `{u.telegram_id}`\n"
            f"نام: {escape_md(u.first_name or '')}\n"
            f"نام کاربری: @{escape_md(u.username or '')}\n"
            f"تراز حساب: *{escape_md(f'{int(u.balance):,}')}* تومان\n"
            f"رتبه: {escape_md(rank)}"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="btn_admin_panel")]
        ])
        await safe_edit(callback.message, txt, reply_markup=kb, parse_mode="MarkdownV2")
        await callback.answer()

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
                            caption=f"📂 *پشتیبان‌گیری خودکار پایگاه داده*\n📅 تاریخ ارسال: {escape_md(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}",
                            parse_mode="MarkdownV2"
                        )
                    except Exception as e:
                        print(f"[Backup System] Error sending backup to admin {admin_id}: {e}")
        else:
            await asyncio.sleep(3600)

# ---------------------------------------------------------------------------
# 13. Main Execution Entrypoint
# ---------------------------------------------------------------------------
async def main():
    print("Application daemon is ready. Starting polling services...")
    asyncio.create_task(backup_scheduler())
    asyncio.create_task(service_usage_monitor())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
