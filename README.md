# Matrix AI and Scheduling Bot

## Description

This project is an **untested and unmaintained** bot for the Matrix protocol. The bot integrates AI-powered responses, scheduled messages, and speech recognition for transcriptions. It allows users to interact with an AI model, transcribe audio messages, and set scheduled messages in chat rooms.

## Features

- **Matrix Chatbot**: Responds to commands and messages in Matrix rooms
- **AI Integration**: Uses an external AI API to generate responses
- **Audio Transcription**: Converts voice messages to text using speech recognition
- **Scheduled Messages**: Allows scheduling of automated messages with various recurrence options (daily, weekly, weekdays)
- **Command System**: Provides various bot commands for interaction
- **Automatic Room Joining**: Can join invited rooms and keep a persistent configuration

## Installation

### Prerequisites

- Python 3.7+
- Required dependencies:
  ```sh
  pip install matrix-client speechrecognition requests schedule pytz
  ```

### Configuration

1. Set up environment variables or edit the script with:
   - `MATRIX_SERVER`: Your Matrix server URL
   - `USERNAME`: Bot username
   - `PASSWORD`: Bot password
   - `AI_API_URL`: API URL for AI responses
   - `AI_API_KEY`: API key for AI service
2. Create a `bot_config.json` file (or let the bot generate one on the first run):
   ```json
   {
       "scheduled_messages": [],
       "joined_rooms": []
   }
   ```

## Usage

Run the bot with:

```sh
python bot.py
```

### Commands

- `!help` - Display available commands
- `!ai <message>` - Get an AI-generated response
- `!transcribe` - Transcribe the last voice message
- `!schedule add HH:MM <message>` - Schedule a one-time message
- `!schedule daily HH:MM <message>` - Schedule a daily message
- `!schedule weekly HH:MM <message>` - Schedule a weekly message
- `!schedule weekdays HH:MM <message>` - Schedule a message for weekdays
- `!schedule list` - Show scheduled messages
- `!schedule remove <ID>` - Remove a scheduled message
- `!status` - Show bot status

## Notes

- **This project is untested and unmaintained.**
- Use at your own risk.
- The AI response feature relies on an external API, which may require an API key.
- Audio transcription uses Google Speech Recognition, which may require internet access.
- Ensure `bot_config.json` exists and is writable.

## License

This project is provided as-is, without warranty or support.

