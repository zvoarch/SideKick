# SideKick

SideKick is a Windows desktop companion with a chat interface powered by the
Google Gemini API. Gemini can chat normally and call SideKick's local tools when
they are useful.

## What it can do

- Open applications that have been approved in SideKick.
- Search approved folders for a file or folder and open a selected result.
- Create, list, and complete tasks.
- Create, view, edit, open, and deactivate workspaces.
- Open websites in the computer's default browser and add websites to
  workspaces.
- Use local context and a limited recent activity history to answer questions
  such as what was opened most recently.

Tool availability can change as the project is developed. Application paths,
folder approvals, tasks, workspaces, and activity records are managed by the
local app and database.

## Where data is stored

The desktop app and its tools run on your computer. Gemini is a Google-hosted
AI service, not a model running locally: chat requires an internet connection
and a Gemini API key. Chat messages and information returned by a tool may be
sent to Gemini so it can answer or choose the next action. SideKick uses local
application and folder settings to perform approved actions; paths are not
needed by Gemini to open an approved application.

SideKick stores data in your Windows user profile:

- SQLite database: `%LOCALAPPDATA%\Desktop-Companion-App\companion.sqlite3`
- Settings and Gemini API key: `%USERPROFILE%\.companion_app\config.json`

The recent activity history records successful application and workspace
opens, with display names and times. It does not record file searches or chat
messages, and entries older than 365 days are removed.

Keep your API key private. Do not commit your local settings, credentials, or
database to a public repository.

## Run from source

With Python installed, run these commands from the project folder:

```sh
python -m pip install -r requirements.txt
python main.py
```

On first launch, open **Settings → General** and enter your Gemini API key.
The key is saved in the app's local settings; no `.env` file is needed.

SideKick currently runs from source with Python; this repository does not
include a packaged executable or installer.

## Project layout

- `main.py` — PySide6 desktop interface.
- `gemini.py` — Gemini chat session, instructions, and function tools.
- `settings_store.py` — local user settings.
- `shortcuts.py` — application shortcut discovery and resolution.
- `tools/` — local application, file, task, workspace, activity, context, and
  database functions.
- `requirements.txt` — Python packages needed to run the app.
