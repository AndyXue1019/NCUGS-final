# A Discord Music Bot with Utility Tools

## Environment Setup

### Requirement
- Python >=3.12
- pip or uv package manager

### Steps

#### 1. Copy .env file
```bash
cp .env.example .env
```

#### 2. Setup virtual environment
Using venv：
```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows
# or
source .venv/bin/activate      # macOS/Linux
```

or using uv：
```bash
uv venv
source .venv/bin/activate
```

#### 3. Install dependencies
Using pip：
```bash
pip install -e .
```

or using uv：
```bash
uv sync
```

#### 4. Install FFmpeg (Required for Music Playback)
FFmpeg is a system dependency required to process audio streams. Install it via your OS package manager:

- **Windows (PowerShell)**:
  ```powershell
  winget install Gyan.FFmpeg
  ```
- **macOS (Homebrew)**:
  ```bash
  brew install ffmpeg
  ```
- **Linux (Ubuntu/Debian)**:
  ```bash
  sudo apt update && sudo apt install ffmpeg
  ```

#### 5. Configuration environment variables
Edit `.env` file, enter the necessary API key and settings: 

```env
BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN"

GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"      # (Optional) Gemini AI
OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"      # (Optional) OpenAI

COMMAND_PREFIX = "%"                         # Discord commend prefix

LOGGING = "True"                             # Enable logging
```

#### 6. Setup YouTube Cookies (Recommended for Music Playback)
To prevent YouTube from blocking the music streaming, it is highly recommended to provide a cookie file:

Export your YouTube cookies using a browser extension (e.g., [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc?pli=1)).

Save the file as yt_cookies.txt in the ./data directory of the project.

### Run the bot
```bash
python main.py
```

## Features
- Discord music playback
- AI integration（only Gemini for now）
- Message event handler
- Administrator commands