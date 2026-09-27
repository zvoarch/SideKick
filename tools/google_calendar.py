"""Read a bounded time window from the user's primary Google Calendar."""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal

from .database import APP_DATA_DIR

CalendarPeriod = Literal["today", "week", "month"]
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENT_CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = APP_DATA_DIR / "google_calendar_token.json"
MAX_EVENTS = 100
PAGE_SIZE = 50


def is_calendar_connected() -> bool:
    """Return whether a usable saved Calendar authorization is present."""
    if not TOKEN_PATH.is_file():
        return False
    try:
        from google.oauth2.credentials import Credentials

        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_PATH), [CALENDAR_SCOPE]
        )
        return credentials.valid or bool(credentials.refresh_token)
    except (ImportError, ValueError, OSError):
        return False


class CalendarSetupError(RuntimeError):
    """Raised when Google Calendar has not been configured or authorized."""


class CalendarRequestError(RuntimeError):
    """Raised when Google Calendar cannot return the requested events."""


def _period_bounds(period: CalendarPeriod) -> tuple[datetime, datetime]:
    today = date.today()
    if period == "today":
        start_day, end_day = today, today + timedelta(days=1)
    elif period == "week":
        start_day = today - timedelta(days=today.weekday())
        end_day = start_day + timedelta(days=7)
    elif period == "month":
        start_day = today.replace(day=1)
        if start_day.month == 12:
            end_day = date(start_day.year + 1, 1, 1)
        else:
            end_day = date(start_day.year, start_day.month + 1, 1)
    else:
        raise ValueError("Calendar period must be today, week, or month.")

    # Convert each local midnight separately so daylight-saving changes are respected.
    start = datetime.combine(start_day, time.min).astimezone()
    end = datetime.combine(end_day, time.min).astimezone()
    return start, end


def _get_credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as error:
        raise CalendarSetupError(
            "Google Calendar packages are missing. Install the project's requirements first."
        ) from error

    credentials = None
    if TOKEN_PATH.exists():
        try:
            credentials = Credentials.from_authorized_user_file(
                str(TOKEN_PATH), [CALENDAR_SCOPE]
            )
        except (ValueError, OSError):
            credentials = None

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception as error:
            raise CalendarSetupError(
                "Google Calendar authorization expired. Remove the saved calendar token and reconnect."
            ) from error
    elif not credentials or not credentials.valid:
        if not CLIENT_CREDENTIALS_PATH.is_file():
            raise CalendarSetupError(
                "Google Calendar is not connected yet. Add a Google Desktop OAuth file named "
                "credentials.json to the project folder, then ask for calendar access again."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_CREDENTIALS_PATH), [CALENDAR_SCOPE]
            )
            credentials = flow.run_local_server(port=0)
        except Exception as error:
            raise CalendarSetupError(
                "Google Calendar authorization did not complete. Check the Desktop OAuth setup and try again."
            ) from error

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def get_calendar_events(period: CalendarPeriod) -> dict:
    """Fetch at most 100 primary-calendar events within the requested local date range."""
    if period not in {"today", "week", "month"}:
        raise ValueError("Calendar period must be today, week, or month.")

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as error:
        raise CalendarSetupError(
            "Google Calendar packages are missing. Install the project's requirements first."
        ) from error

    start, end = _period_bounds(period)
    try:
        service = build("calendar", "v3", credentials=_get_credentials(), cache_discovery=False)
        events = []
        page_token = None
        while len(events) < MAX_EVENTS:
            response = service.events().list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                fields="nextPageToken,items(summary,start,end)",
                maxResults=min(PAGE_SIZE, MAX_EVENTS - len(events)),
                pageToken=page_token,
            ).execute()
            events.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except CalendarSetupError:
        raise
    except HttpError as error:
        raise CalendarRequestError(
            "Google Calendar could not return events. Check the connection and Calendar API setup."
        ) from error
    except Exception as error:
        raise CalendarRequestError(
            "Google Calendar could not be reached. Check the connection and try again."
        ) from error

    result_events = []
    for event in events[:MAX_EVENTS]:
        start_value = event.get("start", {})
        end_value = event.get("end", {})
        result_events.append({
            "title": event.get("summary") or "(No title)",
            "start": start_value.get("dateTime", start_value.get("date")),
            "end": end_value.get("dateTime", end_value.get("date")),
            "all_day": "date" in start_value and "dateTime" not in start_value,
        })

    return {
        "period": period,
        "start": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "events": result_events,
        "message": "No events are scheduled for this period." if not result_events else "",
        "truncated": len(events) >= MAX_EVENTS,
    }
