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

# Storage file for collections
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

        # 1. Base State: Typing just "gp" lists all collections
        if not argument.strip():
            if not groups:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name="No collections found",
                        description="Add a command: 'gp group1 echo \"Hello\"'",
                        on_enter=DoNothingAction()
                    )
                ])
            
            for group_name in groups.keys():
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"📁 Collection: {group_name}",
                    description=f"Contains {len(groups[group_name])} saved items. Click to expand.",
                    # Fills query with 'gp group1' to expand this group
                    on_enter=SetUserQueryAction(f"{keyword} {group_name}")
                ))
            return RenderResultListAction(items)

        # Parse out arguments
        bits = argument.strip().split(maxsplit=1)
        group_name = bits[0]
        command_payload = bits[1] if len(bits) > 1 else None

        # 2. Expanded State: "gp group1" lists all commands under it
        if group_name in groups and not command_payload:
            for cmd in groups[group_name]:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=cmd,
                    description="Click to copy this command into the main search bar",
                    # KEY FIX: This replaces the entire Ulauncher input box with your command!
                    on_enter=SetUserQueryAction(cmd)
                ))
                
                # Management option right below the item to delete it if needed
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"❌ Remove: {cmd}",
                    description="Delete this command string from collection",
                    on_enter=SetUserQueryAction(f"{keyword} remove_cmd {group_name} {cmd}")
                ))
            return RenderResultListAction(items)

        # 3. Action Handler: Removing an item
        if group_name == "remove_cmd":
            sub_bits = bits[1].split(maxsplit=1)
            target_group, target_cmd = sub_bits[0], sub_bits[1]
            if target_group in groups and target_cmd in groups[target_group]:
                groups[target_group].remove(target_cmd)
                save_groups(groups)
            return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Command Removed!", on_enter=SetUserQueryAction(f"{keyword} {target_group}"))])

        # 4. Adding State: "gp group1 echo 'test'"
        if command_payload:
            is_new = group_name not in groups
            items.append(ExtensionResultItem(
                icon=DEFAULT_ICON,
                name=f"➕ {'Create & ' if is_new else ''}Save to '{group_name}'",
                description=f"Will save: {command_payload}",
                on_enter=SetUserQueryAction(f"{keyword} commit_cmd {group_name} {command_payload}")
            ))
            return RenderResultListAction(items)

        if group_name == "commit_cmd":
            sub_bits = bits[1].split(maxsplit=1)
            target_group, target_cmd = sub_bits[0], sub_bits[1]
            if target_group not in groups:
                groups[target_group] = []
            if target_cmd not in groups[target_group]:
                groups[target_group].append(target_cmd)
                save_groups(groups)
            return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Saved!", on_enter=SetUserQueryAction(f"{keyword} {target_group}"))])

        return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Unknown collection state", on_enter=DoNothingAction())])


if __name__ == '__main__':
    InteractiveGroupExtension().run()