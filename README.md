# Desktop-Companion-App
Desktop companion buddy that notifies you of live updates and an everyday helper for day to day tasks

## Google Calendar setup

Calendar access is read-only and requests only a bounded date range from the primary calendar:

- `today`: local midnight today through local midnight tomorrow
- `week`: this Monday through next Monday
- `month`: the first day of this month through the first day of next month

Each request returns at most 100 events and sends Gemini only the event title, start/end, and all-day flag. It does not fetch descriptions, attendees, or event links.

To connect Google Calendar:

1. Install project packages with `python -m pip install -r requirements.txt`.
2. In Google Cloud Console, enable the Google Calendar API and create an OAuth client with application type **Desktop app**.
3. Download the OAuth client JSON and save it in the project root as `credentials.json`. This file is ignored by Git.
4. Ask the companion about today's, this week's, or this month's schedule. On first use, a Google sign-in/consent window opens. The read-only token is stored under `%LOCALAPPDATA%\Desktop-Companion-App\google_calendar_token.json`.

If `credentials.json` is missing, other chat tools continue to work and Gemini reports that Calendar is not connected.
