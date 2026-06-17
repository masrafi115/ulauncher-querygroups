import logging
import json
import difflib
from pathlib import Path

from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction

logger = logging.getLogger(__name__)

GROUPS_FILE = Path("~/.config/ulauncher/collections_storage.json").expanduser()
DEFAULT_ICON = "images/icon.png" 

def load_groups():
    if not GROUPS_FILE.exists():
        GROUPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GROUPS_FILE, "w") as f:
            json.dump({}, f)
        return {}
    try:
        with open(GROUPS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_groups(groups):
    with open(GROUPS_FILE, "w") as f:
        json.dump(groups, f, indent=4)


class InteractiveGroupExtension(Extension):
    def __init__(self):
        super(InteractiveGroupExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        keyword = event.get_keyword()
        argument = event.get_argument() or ""
        groups = load_groups()
        items = []

        raw_args = argument.strip()

        # -----------------------------------------------------------------
        # Intercept Internal State Hooks
        # -----------------------------------------------------------------
        if raw_args.startswith("commit_action "):
            payload = raw_args[14:].strip()
            bits = payload.split(maxsplit=2)
            if len(bits) >= 2:
                target_group, action_type = bits[0], bits[1]
                remaining_data = bits[2] if len(bits) == 3 else ""
                
                if action_type == "add":
                    if target_group not in groups:
                        groups[target_group] = []
                    # Only add if data is provided; allows creating empty groups too
                    if remaining_data and remaining_data not in groups[target_group]:
                        groups[target_group].append(remaining_data)
                    save_groups(groups)
                
                elif action_type == "delete" and remaining_data:
                    if target_group in groups and remaining_data in groups[target_group]:
                        groups[target_group].remove(remaining_data)
                    save_groups(groups)

                elif action_type == "update":
                    if "->" in remaining_data:
                        old_cmd, new_cmd = [x.strip() for x in remaining_data.split("->", 1)]
                        if target_group in groups and old_cmd in groups[target_group]:
                            idx = groups[target_group].index(old_cmd)
                            groups[target_group][idx] = new_cmd
                            save_groups(groups)

                return RenderResultListAction([
                    ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name="✨ Operation Complete!",
                        description="Press Enter to open your collection.",
                        on_enter=SetUserQueryAction(f"{keyword} {target_group}")
                    )
                ])

        # 1. Base State: Typing just "gp" or filtering existing groups
        bits = raw_args.split(maxsplit=1)
        group_name = bits[0] if raw_args else ""
        sub_query = bits[1].strip() if len(bits) > 1 else ""

        if not sub_query and (group_name not in groups or not raw_args):
            # Filter groups list based on what user typed so far
            existing_groups = list(groups.keys())
            matched_groups = [g for g in existing_groups if group_name.lower() in g.lower()] if group_name else existing_groups

            for g_name in matched_groups:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"📁 Collection: {g_name}",
                    description=f"Contains {len(groups[g_name])} items.",
                    on_enter=SetUserQueryAction(f"{keyword} {g_name}")
                ))

            # NEW FEATURE: If what they typed doesn't exactly match an existing group, show "Add New Group"
            if group_name and group_name not in groups:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"✨ Create New Collection: '{group_name}'",
                    description=f"Press Enter to initialize a new group named '{group_name}'",
                    on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} add")
                ))

            return RenderResultListAction(items)

        # 2. Group Exists: View, Fuzzy Search, or Apply Actions inside it
        if group_name in groups:
            
            # Scenario A: Inline Edit/Delete action using "->"
            if "->" in sub_query:
                old_part, new_part = [x.strip() for x in sub_query.split("->", 1)]
                matches = difflib.get_close_matches(old_part, groups[group_name], n=1, cutoff=0.3)
                if matches:
                    target_cmd = matches[0]
                    if not new_part:
                        items.append(ExtensionResultItem(
                            icon=DEFAULT_ICON,
                            name=f"🗑️ Delete command: '{target_cmd}'",
                            description="Press Enter to completely remove this command",
                            on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} delete {target_cmd}")
                        ))
                    else:
                        items.append(ExtensionResultItem(
                            icon=DEFAULT_ICON,
                            name=f"📝 Update to: '{new_part}'",
                            description=f"Modifying original command: '{target_cmd}'",
                            on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} update {target_cmd} -> {new_part}")
                        ))
                    return RenderResultListAction(items)

            # Scenario B: Ordinary browsing / Fuzzy searching within the group
            saved_commands = groups[group_name]
            
            if sub_query:
                matched_cmds = difflib.get_close_matches(sub_query, saved_commands, n=10, cutoff=0.1)
                if not matched_cmds:
                    matched_cmds = [c for c in saved_commands if sub_query.lower() in c.lower()]
            else:
                matched_cmds = saved_commands

            for cmd in matched_cmds:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=cmd,
                    description="👉 Click to drop this command into your search bar",
                    on_enter=SetUserQueryAction(cmd)
                ))

            # Scenario C: If user types a brand new item phrase, offer to append it
            if sub_query and sub_query not in saved_commands and "->" not in sub_query:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"➕ Add to group: '{sub_query}'",
                    description=f"Append this entry into collection '{group_name}'",
                    on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} add {sub_query}")
                ))

            return RenderResultListAction(items)

        return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Unknown state", on_enter=DoNothingAction())])


if __name__ == '__main__':
    KeywordQueryEventListener.__module__ = '__main__' # Safeguard for Ulauncher environment imports
    InteractiveGroupExtension().run()
