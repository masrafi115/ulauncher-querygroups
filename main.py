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
            # Expecting: group_name action_type data...
            bits = payload.split(maxsplit=2)
            if len(bits) >= 2:
                target_group, action_type = bits[0], bits[1]
                remaining_data = bits[2] if len(bits) == 3 else ""
                
                if action_type == "add" and remaining_data:
                    if target_group not in groups:
                        groups[target_group] = []
                    if remaining_data not in groups[target_group]:
                        groups[target_group].append(remaining_data)
                    save_groups(groups)
                
                elif action_type == "delete" and remaining_data:
                    if target_group in groups and remaining_data in groups[target_group]:
                        groups[target_group].remove(remaining_data)
                    save_groups(groups)

                elif action_type == "update":
                    # Expecting old_cmd -> new_cmd split
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
                        description="Press Enter to return to your collection.",
                        on_enter=SetUserQueryAction(f"{keyword} {target_group}")
                    )
                ])

        # 1. Base State: Typing just "gp" lists collections
        if not raw_args:
            if not groups:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name="No collections found",
                        description="Add a command: 'gp group1 echo \"Demo\"'",
                        on_enter=DoNothingAction()
                    )
                ])
            for group_name in groups.keys():
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"📁 Collection: {group_name}",
                    description=f"Contains {len(groups[group_name])} items.",
                    on_enter=SetUserQueryAction(f"{keyword} {group_name}")
                ))
            return RenderResultListAction(items)

        # Parse main group block
        bits = raw_args.split(maxsplit=1)
        group_name = bits[0]
        sub_query = bits[1].strip() if len(bits) > 1 else ""

        # 2. Group Exists: View, Fuzzy Search, or Apply Actions
        if group_name in groups:
            
            # Scenario A: User is trying an inline Edit/Delete action using "->"
            if "->" in sub_query:
                old_part, new_part = [x.strip() for x in sub_query.split("->", 1)]
                
                # Close match matching to see what command the user wants to target
                matches = difflib.get_close_matches(old_part, groups[group_name], n=1, cutoff=0.3)
                if matches:
                    target_cmd = matches[0]
                    if not new_part: # Leaving the right side empty implies delete
                        items.append(ExtensionResultItem(
                            icon=DEFAULT_ICON,
                            name=f"🗑️ Delete command: '{target_cmd}'",
                            description="Press Enter to completely remove this command",
                            on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} delete {target_cmd}")
                        ))
                    else: # Having a right side implies an update mutation
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
                # Use standard close matching scores to dynamically sort items by relevance
                matched_cmds = difflib.get_close_matches(sub_query, saved_commands, n=10, cutoff=0.1)
                # If fuzzy matching yields nothing, fallback to simple string containment rules
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

            # Scenario C: If the user types a brand new phrase that doesn't match any old item,
            # offer to save it right there as a new entry.
            if sub_query and sub_query not in saved_commands and "->" not in sub_query:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"➕ Save brand new item: '{sub_query}'",
                    description=f"Append this entry into collection '{group_name}'",
                    on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} add {sub_query}")
                ))

            return RenderResultListAction(items)

        # 3. Group doesn't exist yet: Bootstrap initial collection
        if sub_query:
            items.append(ExtensionResultItem(
                icon=DEFAULT_ICON,
                name=f"📂 Create Collection '{group_name}'",
                description=f"Will instantiate collection and add: {sub_query}",
                on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} add {sub_query}")
            ))
            return RenderResultListAction(items)

        return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Unknown state", on_enter=DoNothingAction())])


if __name__ == '__main__':
    InteractiveGroupExtension().run()
