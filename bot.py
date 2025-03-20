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

# Matrix-Anmeldedaten
MATRIX_SERVER = ""
USERNAME = "botport"
PASSWORD = ""
ROOMS_TO_JOIN = []  # Leer lassen, um in Räume nur auf Einladung beizutreten

# KI-API-Konfiguration
AI_API_URL = "https://api.anthropic.com/v1/messages"  # Claude API Endpoint
AI_API_KEY = ""

# Konfigurationsdatei für geplante Nachrichten
CONFIG_FILE = "bot_config.json"

# Globale Variablen
client = None
rooms = {}
processed_events = set()

# Konfiguration laden
def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        # Standardkonfiguration erstellen
        default_config = {
            "scheduled_messages": [],
            "joined_rooms": []
        }
        save_config(default_config)
        return default_config

# Konfiguration speichern
def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

# KI-Antwort mit Claude von Anthropic generieren
def get_ai_response(message):
    headers = {
        "x-api-key": AI_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    data = {
        "model": "claude-3-sonnet-20240229",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": message
            }
        ]
    }
    
    try:
        response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data)
        if response.status_code == 200:
            response_json = response.json()
            return response_json.get("content", [{}])[0].get("text", "Keine Antwort erhalten.")
        else:
            return f"Fehler bei der API-Anfrage: Status {response.status_code}, {response.text}"
    except Exception as e:
        return f"Fehler bei der KI-Anfrage: {str(e)}"

# Audio-Transkription
# Audio-Transkription mit pydub
def transcribe_audio(audio_url):
    # Audio von URL herunterladen
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_file:
        response = requests.get(audio_url)
        temp_file.write(response.content)
        temp_file_path = temp_file.name
    
    try:
        # Konvertiere Audio zu WAV Format mit pydub
        from pydub import AudioSegment
        
        # Installiere zuerst pydub: pip install pydub
        sound = AudioSegment.from_file(temp_file_path, format="ogg")
        
        wav_temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav_temp_path = wav_temp_file.name
        wav_temp_file.close()
        
        sound.export(wav_temp_path, format="wav")
        
        # Audio in Text umwandeln
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_temp_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="de-DE")
            return text
    except Exception as e:
        return f"Transkription fehlgeschlagen: {str(e)}"
    finally:
        # Temporäre Dateien aufräumen
        os.unlink(temp_file_path)
        if 'wav_temp_path' in locals():
            try:
                os.unlink(wav_temp_path)
            except:
                pass

# Geplante Nachricht hinzufügen
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

# Nachricht senden
def send_scheduled_message(message_data):
    room_id = message_data["room_id"]
    message = message_data["message"]
    
    if room_id not in rooms:
        try:
            rooms[room_id] = client.join_room(room_id)
        except Exception as e:
            print(f"Konnte Raum nicht beitreten: {str(e)}")
            return
    
    rooms[room_id].send_text(f"[Geplante Nachricht] {message}")
    
    # Für nicht-wiederholende Nachrichten
    if not message_data["repeat"]:
        config = load_config()
        config["scheduled_messages"] = [m for m in config["scheduled_messages"] if m["id"] != message_data["id"]]
        save_config(config)
        # Alle Jobs mit diesem Tag entfernen
        schedule.clear(f"once_{message_data['id']}")

# Nachricht planen
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
        # Einmalige Ausführung
        now = datetime.datetime.now()
        target_time = now.replace(hour=hour, minute=minute, second=0)
        if target_time < now:
            target_time = target_time + datetime.timedelta(days=1)
        
        delay = (target_time - now).total_seconds()
        if delay > 0:
            schedule.every(delay).seconds.do(send_scheduled_message, message_data).tag(f"once_{message_data['id']}")

# Hilfsfunktion für Befehlsverarbeitung
def parse_command(message):
    parts = message.split(" ", 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""
    return command, args

# Befehlsverarbeitung
def process_command(room, sender, command, args):
    if command == "!help":
        help_text = """**Matrix All-in-One Bot**

**Transkription:**
!transcribe - Transkribiert die letzte Sprachnachricht

**KI-Chat:**
!ai [Nachricht] - Fragt die KI nach einer Antwort

**Geplante Nachrichten:**
!schedule add HH:MM [Nachricht] - Einmalige Nachricht planen
!schedule daily HH:MM [Nachricht] - Tägliche Nachricht planen
!schedule weekly HH:MM [Nachricht] - Wöchentliche Nachricht planen
!schedule weekdays HH:MM [Nachricht] - Nachricht an Wochentagen planen
!schedule list - Geplante Nachrichten anzeigen
!schedule remove [ID] - Geplante Nachricht entfernen

**Sonstiges:**
!help - Diese Hilfe anzeigen
!status - Bot-Status anzeigen"""
        room.send_text(help_text)
        return True
    
    elif command == "!ai":
        # if not args:
        #     room.send_text("Bitte gib eine Nachricht für die KI an.")
        #     return True
        
        # Nachrichten aus dem Raumverlauf abrufen (die letzten 10)
        try:
            from_token = room.prev_batch if hasattr(room, 'prev_batch') else None
            
            if from_token is None:
                # Wenn kein Token verfügbar ist, führe einen Sync durch um einen zu bekommen
                sync_response = client.api.sync(timeout_ms=30000)
                from_token = sync_response['rooms']['join'][room.room_id]['timeline']['prev_batch']
            
            room_events = client.api.get_room_messages(
                room.room_id, 
                from_token, 
                direction='b',  # backwards in time
                limit=10
            )
            
            # Nachrichtenverlauf aus den letzten Nachrichten extrahieren
            message_history = []
            last_user_message = None
            last_user = None
            
            for event in reversed(room_events['chunk']):
                if event['type'] == 'm.room.message' and event['content'].get('msgtype') == 'm.text':
                    # if event['sender'] != client.user_id:  # Keine Bot-Nachrichten
                    message_text = event['content']['body'].strip()
                    if not message_text.startswith("!"):  # Keine Befehle
                        sender_name = event['sender'].split(":")[-2].split("@")[-1]  # Einfache Namensextraktion
                        message_history.append(f"{sender_name}: {message_text}")
                        
                        # Speichere den letzten Nutzer und seine Nachricht
                        if event['sender'] != sender:  # Wenn es nicht vom aktuellen Befehlsgeber ist
                            last_user = sender_name
                            last_user_message = message_text
            
            # Kontext für den KI-Prompt erstellen
            context = "\n".join(message_history[-5:])  # Letzte 5 Nachrichten für Kontext
            
            # KI-Prompt erstellen
            prompt = f"""
    Hier ist ein Auszug aus einer aktuellen Konversation:

    {context}

    Der Nutzer '{last_user}' hat zuletzt geschrieben: "{last_user_message}"

    Bitte antworte im Kontext dieser Konversation und ahme den Sprachstil von '{last_user}' nach. Beziehe dich auf den Inhalt der letzten Nachricht, wenn möglich.

    Anfrage: {args}
    """
            
            room.send_text("Frage KI... (dies kann einen Moment dauern)")
            ai_response = get_ai_response(prompt)
            room.send_text(f"KI-Antwort: {ai_response}")
        
        except Exception as e:
            # Fallback bei Fehler: Normale KI-Anfrage ohne Kontext
            room.send_text("Frage KI... (ohne Konversationskontext)")
            ai_response = get_ai_response(args)
            room.send_text(f"KI-Antwort: {ai_response}")
        
        return True
    
    elif command == "!transcribe":
        room.send_text("Suche nach der letzten Sprachnachricht...")
        try:
            # Nachrichten aus dem Raumverlauf abrufen (die letzten 50)
            # Die direction "b" bedeutet "backwards" (rückwärts in der Zeit)
            from_token = room.prev_batch if hasattr(room, 'prev_batch') else None
            
            if from_token is None:
                # Wenn kein Token verfügbar ist, führe einen Sync durch um einen zu bekommen
                sync_response = client.api.sync(timeout_ms=30000)
                from_token = sync_response['rooms']['join'][room.room_id]['timeline']['prev_batch']
            
            room_events = client.api.get_room_messages(
                room.room_id, 
                from_token, 
                direction='b',  # backwards in time
                limit=50
            )
            
            # Nach Sprachnachrichten suchen
            audio_events = []
            for event in room_events['chunk']:
                if event['type'] == 'm.room.message' and event['content'].get('msgtype') == 'm.audio':
                    audio_events.append(event)
            
            if not audio_events:
                room.send_text("Keine Sprachnachrichten in den letzten 50 Nachrichten gefunden.")
                return True
            
            # Die neueste Sprachnachricht verwenden
            latest_audio = audio_events[0]
            mxc_url = latest_audio['content'].get('url')
            
            if mxc_url:
                # MXC-URL in HTTP-URL umwandeln
                http_url = client.api.get_download_url(mxc_url)
                room.send_text("Transkribiere Sprachnachricht...")
                transcription = transcribe_audio(http_url)
                room.send_text(f"Transkription: {transcription}")
            else:
                room.send_text("Fehler: Keine URL für die Audiodatei gefunden.")
        except Exception as e:
            room.send_text(f"Fehler beim Zugriff auf den Raumverlauf: {str(e)}")
            import traceback
            traceback.print_exc()  # Detaillierteren Fehler in der Konsole ausgeben
        
        return True
    
    elif command == "!status":
        config = load_config()
        active_rooms = len(rooms)
        scheduled_msgs = len(config["scheduled_messages"])
        uptime = time.time() - start_time
        hours, remainder = divmod(uptime, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        status_text = f"""**Bot-Status:**
Bot aktiv seit: {int(hours)}h {int(minutes)}m {int(seconds)}s
Aktive Räume: {active_rooms}
Geplante Nachrichten: {scheduled_msgs}"""
        room.send_text(status_text)
        return True
    
    elif command == "!schedule":
        if not args:
            room.send_text("Bitte gib einen Unterbefehl an. !help für Hilfe.")
            return True
        
        schedule_parts = args.split(" ", 1)
        subcmd = schedule_parts[0].lower()
        subargs = schedule_parts[1] if len(schedule_parts) > 1 else ""
        
        if subcmd == "list":
            config = load_config()
            room_messages = [m for m in config["scheduled_messages"] if m["room_id"] == room.room_id]
            if room_messages:
                message_list = "\n".join([f"ID {m['id']}: {m['schedule_time']} - {m['message'][:30]}..." for m in room_messages])
                room.send_text(f"Geplante Nachrichten:\n{message_list}")
            else:
                room.send_text("Keine geplanten Nachrichten für diesen Raum.")
            return True
        
        elif subcmd == "remove":
            try:
                msg_id = int(subargs)
                config = load_config()
                
                # Prüfen, ob Nachricht existiert
                message = next((m for m in config["scheduled_messages"] if m["id"] == msg_id), None)
                if not message:
                    room.send_text(f"Keine Nachricht mit ID {msg_id} gefunden.")
                    return True
                
                # Prüfen, ob Benutzer berechtigt ist (nur im gleichen Raum)
                if message["room_id"] != room.room_id:
                    room.send_text("Du kannst nur Nachrichten aus diesem Raum entfernen.")
                    return True
                
                # Nachricht entfernen
                config["scheduled_messages"] = [m for m in config["scheduled_messages"] if m["id"] != msg_id]
                save_config(config)
                
                # Alle Jobs mit diesem Tag entfernen
                schedule.clear(f"once_{msg_id}")
                schedule.clear(f"daily_{msg_id}")
                schedule.clear(f"weekly_{msg_id}")
                schedule.clear(f"weekday_{msg_id}")
                
                room.send_text(f"Nachricht mit ID {msg_id} entfernt.")
            except ValueError:
                room.send_text("Bitte gib eine gültige ID an.")
            except Exception as e:
                room.send_text(f"Fehler: {str(e)}")
            return True
        
        elif subcmd in ["add", "daily", "weekly", "weekdays"]:
            repeat = None if subcmd == "add" else subcmd
            
            try:
                time_parts = subargs.split(" ", 1)
                if len(time_parts) != 2:
                    room.send_text("Bitte gib Zeit und Nachricht an.")
                    return True
                
                time_str = time_parts[0]
                msg_text = time_parts[1]
                
                # Zeit validieren
                try:
                    hour, minute = map(int, time_str.split(":"))
                    if not (0 <= hour < 24 and 0 <= minute < 60):
                        raise ValueError()
                except:
                    room.send_text("Bitte gib die Zeit im Format HH:MM an.")
                    return True
                
                # Nachricht planen
                msg_id = add_scheduled_message(room.room_id, msg_text, time_str, repeat)
                
                if repeat:
                    room.send_text(f"{repeat.capitalize()} Nachricht für {time_str} geplant. ID: {msg_id}")
                else:
                    room.send_text(f"Einmalige Nachricht für {time_str} geplant. ID: {msg_id}")
                
            except Exception as e:
                room.send_text(f"Fehler: {str(e)}")
            return True
        
        else:
            room.send_text(f"Unbekannter Unterbefehl: {subcmd}. !help für Hilfe.")
            return True
    
    return False

# Event-Handler für eingehende Nachrichten
def on_message(room, event):
    # Doppelte Events vermeiden
    event_id = event.get('event_id', '')
    if event_id in processed_events:
        return
    processed_events.add(event_id)
    
    # Maximale Anzahl verarbeiteter Events begrenzen
    if len(processed_events) > 1000:
        processed_events.clear()
    
    # Nur Nachrichten verarbeiten
    if event['type'] != "m.room.message":
        return
    
    sender = event['sender']
    
    # Eigene Nachrichten ignorieren
    if sender == client.user_id:
        return
    
    # Nachrichtentyp prüfen
    msg_type = event['content'].get('msgtype', '')
    
    # Textbefehle verarbeiten
    if msg_type == "m.text":
        message = event['content']['body'].strip()
        
        # Auf Befehle prüfen
        if message.startswith("!"):
            command, args = parse_command(message)
            if process_command(room, sender, command, args):
                return
        
        # Bot direkt ansprechen
        if message.startswith(f"@{USERNAME}") or message.startswith(client.user_id):
            # Ansprache entfernen
            user_message = message.replace(f"@{USERNAME}", "").replace(client.user_id, "").strip()
            if user_message:
                room.send_text("Frage KI... (dies kann einen Moment dauern)")
                ai_response = get_ai_response(user_message)
                room.send_text(f"KI-Antwort: {ai_response}")
    
# Sprachnachrichten transkribieren
    elif msg_type == "m.audio":
        # Automatische Transkription, wenn der Bot direkt konfiguriert ist
        auto_transcribe = False  # Auf True setzen für automatische Transkription
        
        if auto_transcribe or any(room.room_id == r_id for r_id in load_config().get("auto_transcribe_rooms", [])):
            mxc_url = event['content'].get('url')
            if mxc_url:
                room.send_text("Transkribiere Sprachnachricht...")
                # MXC-URL in HTTP-URL umwandeln
                http_url = client.api.get_download_url(mxc_url)
                transcription = transcribe_audio(http_url)
                room.send_text(f"Transkription: {transcription}")

# Einladungen annehmen
def on_invite(room_id, state):
    try:
        room = client.join_room(room_id)
        rooms[room_id] = room
        room.add_listener(on_message)
        
        # Raum zur Konfiguration hinzufügen
        config = load_config()
        if room_id not in config["joined_rooms"]:
            config["joined_rooms"].append(room_id)
            save_config(config)
        
        room.send_text("Hallo! Ich bin ein All-in-One Matrix-Bot mit Funktionen für Transkription, KI-Chat und geplante Nachrichten. Schreibe `!help` für eine Liste aller Befehle.")
    except Exception as e:
        print(f"Fehler beim Beitreten zum Raum {room_id}: {str(e)}")

# Alle geplanten Nachrichten laden und planen
def load_all_scheduled_messages():
    config = load_config()
    for message_data in config["scheduled_messages"]:
        schedule_message(message_data)

# Scheduler-Thread
def scheduler_thread():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Hauptfunktion
def main():
    global client, start_time
    
    # Startzeit festhalten
    start_time = time.time()
    
    # Verbindung zur Matrix herstellen
    client = MatrixClient(MATRIX_SERVER)
    token = client.login(username=USERNAME, password=PASSWORD)
    
    # Event-Handler für Einladungen
    client.add_invite_listener(on_invite)
    
    # Bekannten Räumen beitreten
    config = load_config()
    for room_id in config.get("joined_rooms", []):
        try:
            room = client.join_room(room_id)
            rooms[room_id] = room
            room.add_listener(on_message)
        except Exception as e:
            print(f"Fehler beim Beitreten zum Raum {room_id}: {str(e)}")
    
    # Zusätzlichen konfigurierten Räumen beitreten
    for room_id in ROOMS_TO_JOIN:
        if room_id not in rooms:
            try:
                room = client.join_room(room_id)
                rooms[room_id] = room
                room.add_listener(on_message)
                
                # Raum zur Konfiguration hinzufügen
                if room_id not in config["joined_rooms"]:
                    config["joined_rooms"].append(room_id)
                    save_config(config)
            except Exception as e:
                print(f"Fehler beim Beitreten zum Raum {room_id}: {str(e)}")
    
    # Alle geplanten Nachrichten laden
    load_all_scheduled_messages()
    
    # Scheduler-Thread starten
    thread = threading.Thread(target=scheduler_thread, daemon=True)
    thread.start()
    
    print(f"Bot gestartet als {client.user_id}")
    print("Drücke Strg+C zum Beenden")
    
    # Bot starten
    client.start_listener_thread()
    
    # Haupt-Thread aktiv halten
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Bot wird beendet...")
        client.logout()

if __name__ == "__main__":
    main()
