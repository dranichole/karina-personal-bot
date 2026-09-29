# Karina Personal Desktop AI
```
Note: Project is still undergoing development, some features may not work as expected.
```

This project contains helper tools for Karina, your local desktop AI agent.

## First tool: open_app

Use this script to launch Windows applications by friendly name.

### Supported apps
- notepad
- calculator
- cmd
- powershell
- explorer
- edge
- chrome
- google chrome
- firefox
- vlc
- visual studio code
- code
- word
- excel
- powerpoint
- spotify

### Run from command line
```powershell
cd C:\Users\Alexandra\Documents\Code\karina_ai_agent
python open_app.py notepad
```

### List supported apps
```powershell
python open_app.py --list
```

### Use from Python
```python
from open_app import open_app
print(open_app('notepad'))
```

## Fuzzy matching

Karina uses fuzzy matching so you do not need exact names for apps and audio devices.

- App names like `chorme` or `visual code` are matched against known apps.
- Audio device names like `headset` match partial device labels such as `Logitech G733 Wireless Headset`.
- Numeric indices also work for audio devices (for example, `select audio device 2`).
- When a match is ambiguous or not found, Karina suggests the closest options.

## Local Chatbot: Karina

A simple local chatbot is included so you can talk to Karina directly.

### Run the chatbot
```powershell
python karina_chat.py
```
### Run the UI
```powershell
python karina_gui.py
```
### Example commands
- `open notepad`
- `launch chrome`
- `list apps`
- `list audio devices`
- `select audio device default`
- `current audio device`
- `take a snapshot`
- `list files in C:\Users\Alexandra\Documents`
- `open file C:\Users\Alexandra\Documents\example.txt`
- `list windows`
- `list monitors`
- `focus chrome`
- `maximize notepad`
- `minimize spotify`
- `move chrome to monitor 2`
- `snap edge to left`
- `close window notepad`
- `close Karina`
- `I'm done, close this`
- `llm status`
- `help`
- `exit`

## Voice input

The Karina GUI supports offline voice commands via the microphone button next to Send.

### Setup
1. Install dependencies:
```powershell
pip install -r requirements.txt
```
2. Download a Vosk speech model (for example, `vosk-model-small-en-us-0.15`) from https://alphacephei.com/vosk/models
3. Either:
   - Extract the model folder into this project directory (name must start with `vosk-model-`), or
   - Set the `KARINA_VOSK_MODEL` environment variable to the model folder path

### Using the mic button
- **Short click**: toggle recording on/off
- **Hold (>300 ms)**: record while the button is held, then transcribe on release

Use the **Mic input** dropdown at the top of the window to choose which microphone Karina listens to. The choice is saved.

Enable **Wake word** in Settings to say `hey Karina` followed by a command.

## Window management

Karina can manage open windows across multiple monitors (Windows only).

- `list windows` — show open window titles
- `list monitors` — show connected displays
- `focus <window>` — bring a window to the front
- `maximize / minimize / restore <window>`
- `move <window> to monitor <n>` — move a window to another display
- `snap <window> to left|right|top|bottom` — snap a window to half the screen
- `close window <name>` — close a specific window

Window names use the same fuzzy matching as apps and audio devices.

## Local LLM chat

Known commands still run immediately through Karina's parsers. Anything else is sent to a local model so you can ask in plain language. The model can call the same desktop tools (open apps, move windows, switch audio devices, and so on).

On launch, Karina:
1. Uses a local server if one is already running (Ollama or LM Studio)
2. Otherwise starts `ollama serve` if Ollama is installed
3. Downloads `llama3.2` automatically the first time (or `KARINA_LLM_MODEL` if set)

You do not need to run `ollama pull` or `ollama serve` yourself. Ollama still has to be installed once from https://ollama.com/download because the model runtime is too large to ship inside Karina.exe.

Optional environment variables:
- `KARINA_LLM_BASE_URL` — skip auto-discovery and use this OpenAI-compatible URL
- `KARINA_LLM_MODEL` — default `llama3.2`
- `KARINA_LLM_API_KEY` — only needed if your local server requires one

Check with:
```
llm status
```

If Ollama is missing, Karina still handles the command list.

## Build a Windows .exe

```powershell
cd C:\Users\Alexandra\Documents\Code\karina_ai_agent
.\build_exe.ps1
```

This creates `dist\Karina\Karina.exe`. The packaged app:
- starts Ollama and pulls the default model on first run
- includes the Vosk voice model if `vosk-model-small-en-us-0.15` is in the project folder
- shows a status bar for model download progress
- supports Up/Down arrow command history in the input box

## Desktop extras

- **Mic input dropdown** — choose the capture device used for the Mic button and wake word
- **Settings** — fuzzy-match threshold, TTS, wake word, and confirm-before-close
- **TTS** — Karina can speak replies (pyttsx3, offline)
- **Wake word** — optional `hey Karina` listener
- **System tray** — closing the window hides to tray; **Ctrl+Shift+K** shows it again
- **Chat timestamps and colors** — user vs Karina
- **Plugins** — add `plugins/*.py` with a `register(registry)` function (see `plugins/time_plugin.py`)

## Dependencies

Install optional features with:
```powershell
pip install -r requirements.txt
```

`requirements.txt` includes:
- `sounddevice` — audio device listing/selection and voice recording
- `vosk` — offline speech-to-text
- `opencv-python` — webcam snapshots
- `pywin32` — window and monitor management (Windows)
- `pyttsx3` — spoken replies
- `pystray` and `pillow` — system tray icon

## Next step

Karina now includes the original command set plus fuzzy matching, voice, window management, local LLM chat, Ollama auto-start, a Windows exe, TTS, tray/hotkey, wake word, plugins, and a microphone picker.
The next step is Odysseus integration: a built-in Karina MCP tool has been added to Odysseus so you can use Karina commands from the Odysseus tool interface.
