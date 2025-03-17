from matrix_client.client import MatrixClient
import speech_recognition as sr
import requests
import json
import schedule
import time
import os
import tempfile
import datetime
import pytz
import threading

MATRIX_SERVER = ""
USERNAME = "toolbot"
PASSWORD = ""
ROOMS_TO_JOIN = []

AI_API_URL = ""
AI_API_KEY = ""

CONFIG_FILE = "bot_config.json"

client = None
rooms = {}
processed_events = set()

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        default_config = {
            "scheduled_messages": [],
            "joined_rooms": []
        }
        save_config(default_config)
        return default_config

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def get_ai_response(message):
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "prompt": message,
        "max_tokens": 150
    }
    try:
        response = requests.post(AI_API_URL, headers=headers, json=data)
        response_json = response.json()
        return response_json.get("text", "No response received.")
    except Exception as e:
        return f"Error with AI request: {str(e)}"

def transcribe_audio(audio_url):
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
        response = requests.get(audio_url)
        temp_file.write(response.content)
        temp_file_path = temp_file.name
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(temp_file_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="de-DE")
            return text
    except Exception as e:
        return f"Transcription failed: {str(e)}"
    finally:
        os.unlink(temp_file_path)

def add_scheduled_message(room_id, message, schedule_time, repeat=None):
    config = load_config()
    message_id = len(config["scheduled_messages"])
    new_message = {
        "id": message_id,
        "room_id": room_id,
        "message": message,
        "schedule_time": schedule_time,
        "repeat": repeat
    }
    config["scheduled_messages"].append(new_message)
    save_config(config)
    schedule_message(new_message)
    return message_id

def send_scheduled_message(message_data):
    room_id = message_data["room_id"]
    message = message_data["message"]
    if room_id not in rooms:
        try:
            rooms[room_id] = client.join_room(room_id)
        except Exception as e:
            print(f"Could not join room: {str(e)}")
            return
    rooms[room_id].send_text(f"[Scheduled Message] {message}")
    if not message_data["repeat"]:
        config = load_config()
        config["scheduled_messages"] = [m for m in config["scheduled_messages"] if m["id"] != message_data["id"]]
        save_config(config)
        schedule.clear(f"once_{message_data['id']}")

def schedule_message(message_data):
    schedule_time = message_data["schedule_time"]
    time_parts = schedule_time.split(":")
    hour, minute = int(time_parts[0]), int(time_parts[1])
    if message_data["repeat"] == "daily":
        schedule.every().day.at(schedule_time).do(send_scheduled_message, message_data).tag(f"daily_{message_data['id']}")
    elif message_data["repeat"] == "weekdays":
        schedule.every().monday.at(schedule_time).do(send_scheduled_message, message_data).tag(f"weekday_{message_data['id']}")
        schedule.every().tuesday.at(schedule_time).do(send_scheduled_message, message_data).tag(f"weekday_{message_data['id']}")
        schedule.every().wednesday.at(schedule_time).do(send_scheduled_message, message_data).tag(f"weekday_{message_data['id']}")
        schedule.every().thursday.at(schedule_time).do(send_scheduled_message, message_data).tag(f"weekday_{message_data['id']}")
        schedule.every().friday.at(schedule_time).do(send_scheduled_message, message_data).tag(f"weekday_{message_data['id']}")
    elif message_data["repeat"] == "weekly":
        schedule.every().week.at(schedule_time).do(send_scheduled_message, message_data).tag(f"weekly_{message_data['id']}")
    else:
        now = datetime.datetime.now()
        target_time = now.replace(hour=hour, minute=minute, second=0)
        if target_time < now:
            target_time = target_time + datetime.timedelta(days=1)
        delay = (target_time - now).total_seconds()
        if delay > 0:
            schedule.every(delay).seconds.do(send_scheduled_message, message_data).tag(f"once_{message_data['id']}")

def parse_command(message):
    parts = message.split(" ", 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args

def process_command(room, sender, command, args):
    if command == "!help":
        help_text = """**Matrix All-in-One Bot**

**Transcription:**
!transcribe - Transcribe the last voice message

**AI Chat:**
!ai [message] - Query the AI for a response

**Scheduled Messages:**
!schedule add HH:MM [message] - Schedule a one-time message
!schedule daily HH:MM [message] - Schedule a daily message
!schedule weekly HH:MM [message] - Schedule a weekly message
!schedule weekdays HH:MM [message] - Schedule a message on weekdays
!schedule list - Show scheduled messages
!schedule remove [ID] - Remove a scheduled message

**Other:**
!help - Show this help
!status - Show bot status"""
        room.send_text(help_text)
        return True
    elif command == "!ai":
        if not args:
            room.send_text("Please provide a message for the AI.")
            return True
        room.send_text("Querying AI... (this may take a moment)")
        ai_response = get_ai_response(args)
        room.send_text(f"AI Response: {ai_response}")
        return True
    elif command == "!transcribe":
        room.send_text("Looking for the last voice message...")
        room.send_text("Note: Transcription of previous messages requires access to the room history.")
        return True
    elif command == "!status":
        config = load_config()
        active_rooms = len(rooms)
        scheduled_msgs = len(config["scheduled_messages"])
        uptime = time.time() - start_time
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        status_text = f"""**Bot Status:**
Bot active for: {int(hours)}h {int(minutes)}m {int(seconds)}s
Active rooms: {active_rooms}
Scheduled messages: {scheduled_msgs}"""
        room.send_text(status_text)
        return True
    elif command == "!schedule":
        if not args:
            room.send_text("Please provide a subcommand. !help for assistance.")
            return True
        schedule_parts = args.split(" ", 1)
        subcmd = schedule_parts[0].lower()
        subargs = schedule_parts[1] if len(schedule_parts) > 1 else ""
        if subcmd == "list":
            config = load_config()
            room_messages = [m for m in config["scheduled_messages"] if m["room_id"] == room.room_id]
            if room_messages:
                message_list = "\n".join([f"ID {m['id']}: {m['schedule_time']} - {m['message'][:30]}..." for m in room_messages])
                room.send_text(f"Scheduled messages:\n{message_list}")
            else:
                room.send_text("No scheduled messages for this room.")
            return True
        elif subcmd == "remove":
            try:
                msg_id = int(subargs)
                config = load_config()
                message = next((m for m in config["scheduled_messages"] if m["id"] == msg_id), None)
                if not message:
                    room.send_text(f"No message with ID {msg_id} found.")
                    return True
                if message["room_id"] != room.room_id:
                    room.send_text("You can only remove messages from this room.")
                    return True
                config["scheduled_messages"] = [m for m in config["scheduled_messages"] if m["id"] != msg_id]
                save_config(config)
                schedule.clear(f"once_{msg_id}")
                schedule.clear(f"daily_{msg_id}")
                schedule.clear(f"weekly_{msg_id}")
                schedule.clear(f"weekday_{msg_id}")
                room.send_text(f"Message with ID {msg_id} removed.")
            except ValueError:
                room.send_text("Please provide a valid ID.")
            except Exception as e:
                room.send_text(f"Error: {str(e)}")
            return True
        elif subcmd in ["add", "daily", "weekly", "weekdays"]:
            repeat = None if subcmd == "add" else subcmd
            try:
                time_parts = subargs.split(" ", 1)
                if len(time_parts) != 2:
                    room.send_text("Please provide time and message.")
                    return True
                time_str = time_parts[0]
                msg_text = time_parts[1]
                try:
                    hour, minute = map(int, time_str.split(":"))
                    if not (0 <= hour < 24 and 0 <= minute < 60):
                        raise ValueError()
                except:
                    room.send_text("Please provide time in HH:MM format.")
                    return True
                msg_id = add_scheduled_message(room.room_id, msg_text, time_str, repeat)
                if repeat:
                    room.send_text(f"{repeat.capitalize()} message scheduled for {time_str}. ID: {msg_id}")
                else:
                    room.send_text(f"One-time message scheduled for {time_str}. ID: {msg_id}")
            except Exception as e:
                room.send_text(f"Error: {str(e)}")
            return True
        else:
            room.send_text(f"Unknown subcommand: {subcmd}. !help for assistance.")
            return True
    return False

def on_message(room, event):
    event_id = event.get('event_id', '')
    if event_id in processed_events:
        return
    processed_events.add(event_id)
    if len(processed_events) > 1000:
        processed_events.clear()
    if event['type'] != "m.room.message":
        return
    sender = event['sender']
    if sender == client.user_id:
        return
    msg_type = event['content'].get('msgtype', '')
    if msg_type == "m.text":
        message = event['content']['body'].strip()
        if message.startswith("!"):
            command, args = parse_command(message)
            if process_command(room, sender, command, args):
                return
        if message.startswith(f"@{USERNAME}") or message.startswith(client.user_id):
            user_message = message.replace(f"@{USERNAME}", "").replace(client.user_id, "").strip()
            if user_message:
                room.send_text("Querying AI... (this may take a moment)")
                ai_response = get_ai_response(user_message)
                room.send_text(f"AI Response: {ai_response}")
    elif msg_type == "m.audio":
        auto_transcribe = False
        if auto_transcribe or any(room.room_id == r_id for r_id in load_config().get("auto_transcribe_rooms", [])):
            mxc_url = event['content'].get('url')
            if mxc_url:
                room.send_text("Transcribing voice message...")
                http_url = client.api.get_download_url(mxc_url)
                transcription = transcribe_audio(http_url)
                room.send_text(f"Transcription: {transcription}")

def on_invite(room_id, state):
    try:
        room = client.join_room(room_id)
        rooms[room_id] = room
        room.add_listener(on_message)
        config = load_config()
        if room_id not in config["joined_rooms"]:
            config["joined_rooms"].append(room_id)
            save_config(config)
        room.send_text("Hello! I am an All-in-One Matrix bot with features for transcription, AI chat, and scheduled messages. Type `!help` for a list of commands.")
    except Exception as e:
        print(f"Error joining room {room_id}: {str(e)}")

def load_all_scheduled_messages():
    config = load_config()
    for message_data in config["scheduled_messages"]:
        schedule_message(message_data)

def scheduler_thread():
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    global client, start_time
    start_time = time.time()
    client = MatrixClient(MATRIX_SERVER)
    token = client.login(username=USERNAME, password=PASSWORD)
    client.add_invite_listener(on_invite)
    config = load_config()
    for room_id in config.get("joined_rooms", []):
        try:
            room = client.join_room(room_id)
            rooms[room_id] = room
            room.add_listener(on_message)
        except Exception as e:
            print(f"Error joining room {room_id}: {str(e)}")
    for room_id in ROOMS_TO_JOIN:
        if room_id not in rooms:
            try:
                room = client.join_room(room_id)
                rooms[room_id] = room
                room.add_listener(on_message)
                if room_id not in config["joined_rooms"]:
                    config["joined_rooms"].append(room_id)
                    save_config(config)
            except Exception as e:
                print(f"Error joining room {room_id}: {str(e)}")
    load_all_scheduled_messages()
    thread = threading.Thread(target=scheduler_thread, daemon=True)
    thread.start()
    print(f"Bot started as {client.user_id}")
    print("Press Ctrl+C to exit")
    client.start_listener_thread()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Bot is shutting down...")
        client.logout()

if __name__ == "__main__":
    main()
