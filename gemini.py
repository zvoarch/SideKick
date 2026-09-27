from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from tools.applications import (
    list_approved_applications as list_approved_apps_locally,
    open_approved_application as open_approved_application_locally,
)
from tools.activity import get_recent_activity, record_activity
from tools.context import get_current_context
from tools.files import list_approved_folders, open_from_path, search_files
from tools.tasks import complete_task, create_task, get_tasks
from tools.workspaces import (
    close_workspace,
    create_workspace,
    get_workspace,
    list_workspaces,
    open_workspace,
    update_workspace,
)
from tools.websites import normalize_website_url, open_website
from shortcuts import list_installed_applications

MODEL = "gemini-3.5-flash-lite"

# Search paths stay in this process. Gemini only receives numbered names/types.
_search_result_paths: list[str] = []


def _record_chat_activity(activity_type: str, name: str) -> None:
    """Keep local logging failures from changing the result of an open action."""
    try:
        record_activity(activity_type, name)
    except Exception:
        pass


def open_application_for_chat(name: str) -> dict:
    """Open an approved application by its saved name or executable name.

    Microsoft Edge may be saved as "msedge"; treat "Edge", "msedge", and
    "Microsoft Edge" as the same app, but only if Edge is approved in settings.
    The path is looked up and used locally and is never exposed to Gemini.
    """
    result = open_approved_application_locally(name)
    if result.get("ok"):
        _record_chat_activity("application_opened", result.get("application", name))
    return result


def open_website_for_chat(url: str) -> dict:
    """Open a user-requested HTTP(S) website in the default browser."""
    try:
        result = open_website(url)
    except ValueError as error:
        return {"ok": False, "message": str(error)}
    if result["ok"]:
        return {"ok": True, "url": normalize_website_url(url), "message": result["message"]}
    return result


def open_youtube_search_for_chat(query: str) -> dict:
    """Open YouTube search results for a topic in the default browser."""
    query = query.strip()
    if not query:
        return {"ok": False, "message": "A YouTube search topic is required."}
    return open_website_for_chat(
        "https://www.youtube.com/results?" + urlencode({"search_query": query})
    )


def get_approved_applications_for_chat() -> dict:
    """List enabled approved application names without exposing their paths."""
    names = [app["name"] for app in list_approved_apps_locally()]
    return {"applications": names, "count": len(names)}


def open_all_approved_applications_for_chat() -> dict:
    """Open every enabled approved application in one local batch action."""
    applications = list_approved_apps_locally()
    if not applications:
        return {"ok": True, "opened": [], "failed": [], "message": "No applications are approved yet."}

    opened = []
    failed = []
    for application in applications:
        result = open_approved_application_locally(application["name"])
        if result.get("ok"):
            opened.append(application["name"])
            _record_chat_activity("application_opened", application["name"])
        else:
            failed.append(application["name"])
    return {
        "ok": not failed,
        "opened": opened,
        "failed": failed,
        "message": f"Opened {len(opened)} of {len(applications)} approved applications.",
    }


def find_installed_applications_for_chat(query: str = "") -> dict:
    """Suggest Start Menu apps the user can add to the approved list.

    Args:
        query: Optional app name to narrow the suggestions.
    """
    apps = list_installed_applications()
    words = [word.casefold() for word in query.split() if word.strip()]
    if words:
        apps = [app for app in apps if all(word in app["name"].casefold() for word in words)]
    names = [app["name"] for app in apps[:20]]
    return {"applications": names, "count": len(apps), "showing": len(names)}


def get_local_date_for_chat(days_from_today: int = 0) -> dict:
    """Return the user's local date and weekday for today or a relative day.

    Args:
        days_from_today: 0 for today, 1 for tomorrow, -1 for yesterday.
    """
    local_today = datetime.now().astimezone().date()
    target = local_today + timedelta(days=days_from_today)
    return {"date": target.isoformat(), "day_of_week": target.strftime("%A")}


def find_file_or_folder(query: str) -> dict:
    """Search approved folders and return numbered names/types, never paths."""
    global _search_result_paths
    if not list_approved_folders():
        _search_result_paths = []
        return {
            "ok": False,
            "message": "No approved folders are enabled for searching. Add one in local settings first.",
            "results": [],
        }

    matches = search_files(query)
    _search_result_paths = [match["path"] for match in matches]
    return {
        "ok": True,
        "results": [
            {"number": index, "name": match["name"], "type": match["type"],
             "score": match["score"]}
            for index, match in enumerate(matches, start=1)
        ],
        "message": "" if matches else "No matching files or folders were found in approved folders.",
    }


def open_found_item_for_chat(number: int) -> dict:
    """Open only an item from the latest search results, selected by its displayed number."""
    if not isinstance(number, int) or isinstance(number, bool):
        return {"ok": False, "message": "Choose a numbered item from the latest search results."}
    if number < 1 or number > len(_search_result_paths):
        return {"ok": False, "message": "That number is not in the latest search results. Search again."}
    try:
        open_from_path(_search_result_paths[number - 1])
    except (OSError, AttributeError):
        return {"ok": False, "message": "Windows could not open that search result."}
    return {"ok": True, "number": number, "message": f"Opened search result {number}."}


def create_task_for_chat(name: str, description: str = "") -> dict:
    """Create a task with an optional description in the local task list."""
    task = create_task(name, description or None)
    if task is None:
        return {"ok": False, "message": "A task name is required."}
    return {"name": task["name"], "description": task["description"],
            "completed": task["completed"]}


def get_tasks_for_chat() -> list[dict]:
    """Return only unfinished tasks for current planning and task requests."""
    return [
        {"name": task["name"], "description": task["description"],
         "completed": task["completed"]}
        for task in get_tasks() if not task["completed"]
    ]


def complete_task_for_chat(name: str) -> dict:
    """Mark a task completed by its name."""
    task = complete_task(name)
    if task is None:
        return {"ok": False, "message": f"No unfinished task named {name} was found."}
    return {"ok": True, "name": task["name"], "completed": task["completed"]}


def create_workspace_for_chat(
    name: str,
    applications: list[str] | None = None,
    folders: list[str] | None = None,
    websites: list[str] | None = None,
) -> dict:
    """Save a workspace from approved names only; this does not open or activate it."""
    result = create_workspace(name, applications, folders, websites)
    if not result["ok"]:
        return {"ok": False, "message": result["message"]}
    return {
        "ok": True,
        "name": result["name"],
        "applications": result["applications"],
        "folders": result["folders"],
        "website_count": len(result["websites"]),
    }


def get_workspace_for_chat(name: str) -> dict:
    """Get workspace names and linked item names without returning filesystem paths or URLs."""
    workspace = get_workspace(name)
    if workspace is None:
        available = list_workspaces()
        if available:
            return {
                "ok": False,
                "message": f"No saved workspace named {name} was found.",
                "available_workspaces": available,
            }
        return {
            "ok": False,
            "message": "There are no saved workspaces yet.",
            "available_workspaces": [],
        }
    return {
        "ok": True,
        "name": workspace["name"],
        "applications": workspace["applications"],
        "folders": workspace["folders"],
        "website_count": len(workspace["websites"]),
        "is_active": workspace["is_active"],
    }


def add_website_to_workspace_for_chat(name: str, website: str) -> dict:
    """Add a website URL to an existing workspace without opening it."""
    workspace = get_workspace(name)
    if workspace is None:
        available = list_workspaces()
        return {
            "ok": False,
            "message": f"No saved workspace named {name} was found.",
            "available_workspaces": available,
        }
    try:
        url = normalize_website_url(website)
    except ValueError as error:
        return {"ok": False, "message": str(error)}

    websites = workspace["websites"]
    if all(existing.casefold() != url.casefold() for existing in websites):
        websites.append(url)
    result = update_workspace(name, websites=websites)
    if result is None:
        return {"ok": False, "message": f"No saved workspace named {name} was found."}
    if not result["ok"]:
        return result
    return {
        "ok": True,
        "name": result["name"],
        "website_count": len(result["websites"]),
        "message": "The website was added to the workspace. It was not opened.",
    }


def _workspace_name_changes(current, additions, removals):
    if isinstance(additions, str):
        additions = [additions]
    if isinstance(removals, str):
        removals = [removals]
    additions = additions or []
    removals = removals or []
    if not isinstance(additions, (list, tuple)) or not isinstance(removals, (list, tuple)):
        raise ValueError("Workspace item changes must be names.")
    names = list(current)
    remove_keys = {
        item.strip().casefold()
        for item in removals
        if isinstance(item, str) and item.strip()
    }
    names = [name for name in names if name.casefold() not in remove_keys]
    seen = {name.casefold() for name in names}
    for item in additions:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Workspace item changes must be non-empty names.")
        item = item.strip()
        if item.casefold() not in seen:
            names.append(item)
            seen.add(item.casefold())
    return names


def _workspace_website_changes(current, additions, removals):
    if isinstance(additions, str):
        additions = [additions]
    if isinstance(removals, str):
        removals = [removals]
    additions = additions or []
    removals = removals or []
    if not isinstance(additions, (list, tuple)) or not isinstance(removals, (list, tuple)):
        raise ValueError("Workspace website changes must be URLs.")
    websites = [normalize_website_url(url) for url in current]
    remove_urls = {normalize_website_url(url).casefold() for url in removals}
    websites = [url for url in websites if url.casefold() not in remove_urls]
    seen = {url.casefold() for url in websites}
    for value in additions:
        url = normalize_website_url(value)
        if url.casefold() not in seen:
            websites.append(url)
            seen.add(url.casefold())
    return websites


def edit_workspace_for_chat(
    name: str,
    new_name: str | None = None,
    add_applications: list[str] | None = None,
    remove_applications: list[str] | None = None,
    add_folders: list[str] | None = None,
    remove_folders: list[str] | None = None,
    add_websites: list[str] | None = None,
    remove_websites: list[str] | None = None,
) -> dict:
    """Rename or add/remove approved apps, folders, and websites in a saved workspace.

    This edits only the saved links. It does not open or activate the workspace.

    Args:
        name: The existing saved workspace name.
        new_name: Optional replacement workspace name.
        add_applications: Approved application names to add.
        remove_applications: Application names to remove.
        add_folders: Approved folder names to add.
        remove_folders: Folder names to remove.
        add_websites: Website URLs to add.
        remove_websites: Website URLs to remove.
    """
    workspace = get_workspace(name)
    if workspace is None:
        return {
            "ok": False,
            "message": f"No saved workspace named {name} was found.",
            "available_workspaces": list_workspaces(),
        }

    applications = None
    folders = None
    websites = None
    try:
        if add_applications is not None or remove_applications is not None:
            applications = _workspace_name_changes(
                workspace["applications"], add_applications, remove_applications
            )
        if add_folders is not None or remove_folders is not None:
            folders = _workspace_name_changes(
                workspace["folders"], add_folders, remove_folders
            )
        if add_websites is not None or remove_websites is not None:
            websites = _workspace_website_changes(
                workspace["websites"], add_websites, remove_websites
            )
    except ValueError as error:
        return {"ok": False, "message": str(error)}

    if new_name is None and applications is None and folders is None and websites is None:
        return {"ok": False, "message": "Tell me what to change in the workspace."}

    result = update_workspace(
        name,
        applications=applications,
        folders=folders,
        websites=websites,
        new_name=new_name,
    )
    if result is None:
        return {"ok": False, "message": f"No saved workspace named {name} was found."}
    if not result["ok"]:
        return result
    return {
        "ok": True,
        "name": result["name"],
        "applications": result["applications"],
        "folders": result["folders"],
        "website_count": len(result["websites"]),
        "is_active": result["is_active"],
        "message": "Updated the saved workspace. It was not opened.",
    }


def list_workspaces_for_chat() -> list[str]:
    """List saved workspace names."""
    return list_workspaces()


def open_workspace_for_chat(name: str) -> dict:
    """Activate a workspace and open its locally linked approved items."""
    result = open_workspace(name)
    if not result["ok"]:
        available = list_workspaces()
        if available:
            return {
                "ok": False,
                "name": name,
                "message": f"No saved workspace named {name} was found.",
                "available_workspaces": available,
            }
        return {
            "ok": False,
            "name": name,
            "message": "There are no saved workspaces yet.",
            "available_workspaces": [],
        }
    _record_chat_activity("workspace_opened", result.get("name", name))
    return {
        "ok": result["ok"],
        "name": result.get("name"),
        "message": result["message"],
        "opened_applications": result.get("opened_applications", []),
        "opened_folders": result.get("opened_folders", []),
        "opened_websites": result.get("opened_websites", 0),
        "issues": result.get("issues", []),
    }


def deactivate_workspace_for_chat() -> dict:
    """Clear the active workspace context without closing any applications or folders."""
    if close_workspace():
        return {"ok": True, "message": "The active workspace was deactivated."}
    return {"ok": True, "message": "There is no active workspace."}


def get_current_context_for_chat() -> dict:
    """Get the active workspace and unfinished tasks for the current chat."""
    context = get_current_context()
    active = context["active_workspace"]
    return {
        "active_workspace": active["name"] if active else None,
        "tasks": [task for task in context["tasks"] if not task["completed"]],
    }


def get_recent_activity_for_chat() -> dict:
    """Return at most five recent app/workspace opens, without paths or content."""
    activities = []
    for activity in get_recent_activity(limit=5):
        timestamp = datetime.fromisoformat(activity["timestamp"]).astimezone()
        label = (
            "Opened application"
            if activity["type"] == "application_opened"
            else "Opened workspace"
        )
        activities.append({
            "action": label,
            "name": activity["details"],
            "time": timestamp.strftime("%b %d, %Y at %I:%M %p"),
        })
    return {
        "activities": activities,
        "message": "" if activities else "No app or workspace opens have been recorded yet.",
    }


SYSTEM_INSTRUCTION = """
You are Companion, a Gemini assistant in a desktop app. Use the tools below to
help with the user's computer tasks, workspaces, and tasks. Be direct
and concise. Never claim an action succeeded unless its tool result says it did.
For greetings or vague prompts like “help,” respond warmly and briefly, such as
“I can help with day-to-day tasks—just say the word.” Do not list tools or app
features unless the user asks what you can do.
If asked who you are or what powers you, say you are Companion, the SideKick
desktop assistant powered by Google Gemini. Do not claim Google built the entire
SideKick application.
Do not use emojis by default. Use one only when the user used an emoji in their
message or explicitly asks for one; never add decorative emoji to routine replies.

SETTINGS: If asked how to change the send box, button, or accent color, give the
direct steps: open Settings, choose General, click Select Color beside Accent
color, choose a color, then click Save. This changes the app's accent, including
the send button. Don't say the setting is unavailable or that you cannot change
it. End with a brief helpful follow-up when it fits, such as offering to suggest
a color.

APPLICATIONS: For an explicit request to open an application, call
open_application_for_chat with its approved name. Only approved applications can
be opened. If it is not approved, say that it must first be added in Settings.
Treat “Edge,” “Microsoft Edge,” and “msedge” as the same approved app when present.
If the user asks to open all of their approved apps, call
open_all_approved_applications_for_chat once. It opens every enabled approved app
in one batch; do not call open_application_for_chat repeatedly for this request.
Report how many opened and name any that failed. Do not ask the user to repeat the
request after the batch tool has run.
If the user asks what applications they have or asks for a list of allowed,
approved, or available apps, call get_approved_applications_for_chat and list
the names it returns. Never say you cannot list approved apps. If the list is
empty, say no applications are approved yet. Tell the user they can view and add
approved applications through Settings. This is not a list of every installed
program; do not claim to know all installed applications.
If the user wants to find installed apps or asks what they could add, call
find_installed_applications_for_chat, show useful matching names, and direct them
to Settings → Approved Applications → Find Start Menu Apps to add one manually.
This list contains apps with Windows Start Menu shortcuts, so it may not include
every installed program. Finding an app does not approve or open it. Never expose
shortcut paths.

FILES: For a file or folder request, search with find_file_or_folder first and
show the numbered results. Open an item only after the user chooses its number,
using open_found_item_for_chat. Never ask for, expose, or pass a filesystem path.

WORKSPACES: When asked to open a workspace, check saved names with
list_workspaces_for_chat, then call open_workspace_for_chat for the requested
saved workspace. Creating a workspace only saves it. If the requested name is
not saved, report that clearly, mention any available workspaces, and offer to
create the requested workspace. If none are saved, say so and offer to create
one. Do not search files or suggest file search to recover from a missing
workspace. Do not create a workspace until the user agrees. The deactivate tool
clears the active workspace context but does not close apps.
If the user asks to edit a saved workspace, first call get_workspace_for_chat to
inspect its current app/folder names, then call edit_workspace_for_chat with only
the requested additions, removals, or rename. Preserve all unspecified items.
Applications and folders added to a workspace must already be approved. Editing
only changes saved workspace contents; it never opens or activates the workspace.

ACTIVITY HISTORY: If the user asks what they were last working on or asks about
recent app/workspace activity, call get_recent_activity_for_chat. It contains
only successful app opens and workspace opens, with names and times. It never
contains file searches, file names, paths, websites, prompts, or message text.
Use the latest entry for “what was I last working on?” Keep the answer brief and
do not infer other activity.

WEBSITES: For a request to find a current website, link, article, or set of
search results, use search_web_for_chat and base links on its returned sources.
Do not invent URLs. If the user asks to open a website, use
open_website_for_chat with a URL from search results or a clearly specified URL.
If the user asks to find or watch a YouTube video/build/tutorial, use
open_youtube_search_for_chat with the topic to open YouTube results directly.
This also applies when the user accepts an offer to open the browser after a
YouTube search request; open the results for the original topic, not the YouTube
homepage. If web search fails, do not invent channels or claim to have found
videos; offer the direct YouTube search page instead. If the user says an open
did not work, retry once with the relevant direct search URL and report only what
the tool confirms.
Bare domain names such as “reddit.com” may be opened directly; if the user gives
only a site name, use search_web_for_chat to find its official site first. For
requests such as opening Reddit's top posts on a topic, prefer opening a relevant
Reddit search/results page so the user can see the list in their browser. Only
open a site when the user asks to open it. To add a website to an existing
workspace, find its URL when needed, then use
add_website_to_workspace_for_chat. Adding a site only saves it; it does not open
the workspace or launch the browser. When creating an agreed workspace with a
website, pass the resolved URL in create_workspace_for_chat's websites argument.

TASKS: Use get_tasks_for_chat for task lists; it contains unfinished tasks only.
Use create_task_for_chat to add one and complete_task_for_chat to complete one.
If the user says they finished an activity, check for a clearly matching
unfinished task and complete it. Do not guess or complete an unrelated task. If
there is no clear match, respond conversationally without using a task tool.
After adding or completing a task, don't stop at the confirmation: also respond
to the rest of the user's message and keep the conversation going with one
relevant, natural follow-up. For example, after adding grocery shopping, ask if
they want to add a day or the items they need. Don't invent task details or add
extra tasks unless the user asks.
When helping plan the day, call get_current_context_for_chat and base suggestions
on unfinished tasks. Do not bring up completed tasks. If the user asks what to do
and has no relevant unfinished tasks, offer a few ordinary, natural ideas or ask
what they feel like doing. Do not suggest checking files, browsing workspaces,
opening applications, or using app features unless the user asks about them.

DATE: For an exact question about today's date, tomorrow, yesterday, or a

CONVERSATION: Chat naturally and answer general questions without calling a
tool unless the request needs current local date, app, file, workspace, or task
data. Follow the emoji and identity guidance above.

After a tool action, give one short, factual confirmation. If a tool fails, say
what failed simply. Do not describe internal reasoning.
""".strip()

CHAT_TOOLS = [
            open_application_for_chat,
            open_all_approved_applications_for_chat,
            open_website_for_chat,
            open_youtube_search_for_chat,
            get_approved_applications_for_chat,
            find_installed_applications_for_chat,
            get_local_date_for_chat,
            get_recent_activity_for_chat,
            find_file_or_folder,
            open_found_item_for_chat,
            create_task_for_chat,
            get_tasks_for_chat,
            complete_task_for_chat,
            create_workspace_for_chat,
            get_workspace_for_chat,
            edit_workspace_for_chat,
            add_website_to_workspace_for_chat,
            list_workspaces_for_chat,
            open_workspace_for_chat,
            deactivate_workspace_for_chat,
            get_current_context_for_chat,
]


class ToolCallingGeminiClient:
    """Gemini chat session with the app's local, database-backed tools."""

    def __init__(self, api_key: str, model: str = MODEL):
        if genai is None or types is None:
            raise RuntimeError(
                "The 'google-genai' package is not installed. Install it in this "
                "Python environment with: python -m pip install google-genai"
            )
        if not api_key:
            raise ValueError("A Gemini API key is required.")
        self.model = model
        self.client = genai.Client(api_key=api_key)
        self.chat = self._create_chat()

    def _create_chat(self):
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            # Google Search grounding is exposed through a local function which
            # makes its own Search-only request. This keeps it separate from the
            # chat's automatic Python function calling configuration.
            tools=CHAT_TOOLS + [self.search_web_for_chat],
            max_output_tokens=256,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=4,
            ),
        )
        return self.client.chats.create(model=self.model, config=config)

    def search_web_for_chat(self, query: str) -> dict:
        """Search current web results with Gemini Google Search grounding.

        Args:
            query: A concise description of the site, link, or information to find.
        """
        query = query.strip()
        if not query:
            return {"ok": False, "message": "A search query is required.", "results": []}
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=(
                    f"Search the web for: {query}. Summarize the most relevant current "
                    "results briefly. Do not make up links; cite the relevant pages."
                ),
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    max_output_tokens=512,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(
                        disable=True,
                    ),
                ),
            )
        except Exception:
            return {
                "ok": False,
                "message": "Web search is temporarily unavailable. Try again shortly.",
                "results": [],
            }

        summary_parts = []
        results = []
        seen_urls = set()
        for candidate in response.candidates or []:
            content = candidate.content
            if content is not None:
                summary_parts.extend(
                    part.text for part in content.parts or []
                    if part.text and not getattr(part, "thought", False)
                )
            metadata = getattr(candidate, "grounding_metadata", None)
            for chunk in getattr(metadata, "grounding_chunks", None) or []:
                web_result = getattr(chunk, "web", None)
                if web_result is None:
                    continue
                url = getattr(web_result, "uri", None)
                title = getattr(web_result, "title", None)
                if not url or urlsplit(url).scheme not in {"http", "https"}:
                    continue
                key = url.casefold()
                if key in seen_urls:
                    continue
                seen_urls.add(key)
                results.append({"title": title or url, "url": url})
                if len(results) >= 10:
                    break
            if len(results) >= 10:
                break

        return {
            "ok": True,
            "summary": " ".join(summary_parts).strip(),
            "results": results,
        }

    def send_message(self, prompt: str) -> str:
        response = self.chat.send_message(prompt)
        # Access text parts directly: response.text warns when a response also
        # contains a function_call part, which is normal for tool conversations.
        for candidate in response.candidates or []:
            content = candidate.content
            if content is None:
                continue
            text = "".join(
                part.text for part in content.parts or []
                if part.text and not getattr(part, "thought", False)
            ).strip()
            if text:
                return text
        return "Sorry, I didn't get a reply. Could you say that again?"
