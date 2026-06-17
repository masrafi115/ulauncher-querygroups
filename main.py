import logging
import json
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

        # Clean up any trailing/leading spaces to avoid parsing errors
        raw_args = argument.strip()

        # -----------------------------------------------------------------
        # CRITICAL FIX: Intercept Internal Command Executions Early
        # -----------------------------------------------------------------
        if raw_args.startswith("commit_cmd "):
            # Strip "commit_cmd " out to get the payload
            payload = raw_args[11:].strip()
            bits = payload.split(maxsplit=1)
            if len(bits) == 2:
                target_group, target_cmd = bits[0], bits[1]
                if target_group not in groups:
                    groups[target_group] = []
                if target_cmd not in groups[target_group]:
                    groups[target_group].append(target_cmd)
                    save_groups(groups)
                
                # Success screen! Send user directly back to the clean group view
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name="✅ Saved Successfully!",
                        description=f"Added to '{target_group}'. Press Enter to return.",
                        on_enter=SetUserQueryAction(f"{keyword} {target_group}")
                    )
                ])

        if raw_args.startswith("remove_cmd "):
            payload = raw_args[11:].strip()
            bits = payload.split(maxsplit=1)
            if len(bits) == 2:
                target_group, target_cmd = bits[0], bits[1]
                if target_group in groups and target_cmd in groups[target_group]:
                    groups[target_group].remove(target_cmd)
                    save_groups(groups)
                
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name="🗑️ Command Removed!",
                        description="Press Enter to return.",
                        on_enter=SetUserQueryAction(f"{keyword} {target_group}")
                    )
                ])

        # -----------------------------------------------------------------
        # Standard Parsing Navigation
        # -----------------------------------------------------------------
        
        # 1. Base State: Only typing "gp"
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
                    description=f"Contains {len(groups[group_name])} items. Click to open.",
                    on_enter=SetUserQueryAction(f"{keyword} {group_name}")
                ))
            return RenderResultListAction(items)

        # Split arguments cleanly into target group and text payload
        bits = raw_args.split(maxsplit=1)
        group_name = bits[0]
        command_payload = bits[1] if len(bits) > 1 else None

        # 2. Expanded State: "gp group1" (Viewing existing group data)
        if group_name in groups and not command_payload:
            for cmd in groups[group_name]:
                # Action: Replace input query box entirely with the command to run it
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=cmd,
                    description="👉 Click to copy this command into main search bar",
                    on_enter=SetUserQueryAction(cmd)
                ))
                
                # Management Row: Remove it cleanly
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"❌ Remove: {cmd}",
                    description="Delete this specific command line string",
                    on_enter=SetUserQueryAction(f"{keyword} remove_cmd {group_name} {cmd}")
                ))
            return RenderResultListAction(items)

        # 3. Adding/Creation State: "gp group1 echo 'Demo'"
        if command_payload:
            is_new = group_name not in groups
            items.append(ExtensionResultItem(
                icon=DEFAULT_ICON,
                name=f"➕ {'Create & ' if is_new else ''}Save to '{group_name}'",
                description=f"Will save: {command_payload}",
                # Passes 'commit_cmd' safely to be caught at the top loop next frame
                on_enter=SetUserQueryAction(f"{keyword} commit_cmd {group_name} {command_payload}")
            ))
            return RenderResultListAction(items)

        return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Unknown collection state", on_enter=DoNothingAction())])


if __name__ == '__main__':
    InteractiveGroupExtension().run()
