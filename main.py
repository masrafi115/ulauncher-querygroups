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

# Persistent storage file location path
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
        # SECTION 1: Intercept Internal State Hooks (Writes Data to JSON)
        # -----------------------------------------------------------------
        if raw_args.startswith("commit_action "):
            payload = raw_args[14:].strip()
            bits = payload.split(maxsplit=2)
            if len(bits) >= 2:
                target_group, action_type = bits[0], bits[1]
                remaining_data = bits[2] if len(bits) == 3 else ""
                
                # Handling addition mutations
                if action_type == "add":
                    if target_group not in groups:
                        groups[target_group] = []
                    
                    if remaining_data:
                        if ":" in remaining_data:
                            alias_part, cmd_part = [x.strip() for x in remaining_data.split(":", 1)]
                        else:
                            alias_part, cmd_part = remaining_data, remaining_data
                        
                        entry = {"alias": alias_part, "command": cmd_part}
                        
                        # Remove existing duplicate alias names to allow rewrites
                        groups[target_group] = [e for e in groups[target_group] if (isinstance(e, dict) and e["alias"] != alias_part) or (isinstance(e, str) and e != alias_part)]
                        groups[target_group].append(entry)
                    save_groups(groups)
                
                # Handling deletion mutations
                elif action_type == "delete" and remaining_data:
                    if target_group in groups:
                        groups[target_group] = [e for e in groups[target_group] if (isinstance(e, dict) and e["alias"] != remaining_data) and (isinstance(e, str) and e != remaining_data)]
                    save_groups(groups)

                # Handling inline edits and updates
                elif action_type == "update":
                    if "->" in remaining_data:
                        old_alias, new_payload = [x.strip() for x in remaining_data.split("->", 1)]
                        if target_group in groups:
                            for entry in groups[target_group]:
                                # If legacy format data, upgrade it on the fly
                                current_alias = entry["alias"] if isinstance(entry, dict) else entry
                                
                                if current_alias == old_alias:
                                    # Case: gp group1 DemoAlias -> Demo : echo "new Command"
                                    if ":" in new_payload:
                                        a_part, c_part = [x.strip() for x in new_payload.split(":", 1)]
                                        if isinstance(entry, dict):
                                            entry["alias"] = a_part
                                            entry["command"] = c_part
                                    else:
                                        # Case: Just renaming alias only, preserving original command
                                        if isinstance(entry, dict):
                                            entry["alias"] = new_payload
                                        else:
                                            # If old item was string format, duplicate it to both parameters
                                            groups[target_group].remove(entry)
                                            groups[target_group].append({"alias": new_payload, "command": entry})
                                    break
                            save_groups(groups)

                return RenderResultListAction([
                    ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name="✨ Operation Complete!",
                        description="Press Enter to open your collection view.",
                        on_enter=SetUserQueryAction(f"{keyword} {target_group}")
                    )
                ])

        # -----------------------------------------------------------------
        # SECTION 2: Parsing Main View Interfaces
        # -----------------------------------------------------------------
        bits = raw_args.split(maxsplit=1)
        group_name = bits[0] if raw_args else ""
        sub_query = bits[1].strip() if len(bits) > 1 else ""

        # Root State UI Interface: User types "gp" or filters collection names
        if not sub_query and (group_name not in groups or not raw_args):
            existing_groups = list(groups.keys())
            matched_groups = [g for g in existing_groups if group_name.lower() in g.lower()] if group_name else existing_groups

            for g_name in matched_groups:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"📁 Collection: {g_name}",
                    description=f"Contains {len(groups[g_name])} items.",
                    on_enter=SetUserQueryAction(f"{keyword} {g_name}")
                ))

            # New Group UI Button Builder
            if group_name and group_name not in groups:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=f"✨ Create New Collection: '{group_name}'",
                    description=f"Press Enter to initialize a new group named '{group_name}'",
                    on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} add")
                ))

            return RenderResultListAction(items)

        # Collection Sub-State Interface: User navigates inside an active group folder
        if group_name in groups:
            saved_entries = groups[group_name]
            
            # Legacy parser sanitization loop to safely parse plain string databases
            normalized_entries = []
            for entry in saved_entries:
                if isinstance(entry, dict):
                    normalized_entries.append(entry)
                else:
                    normalized_entries.append({"alias": entry, "command": entry})

            # Check Condition A: User triggers inline Edit/Delete using arrow operator
            if "->" in sub_query:
                old_part, new_part = [x.strip() for x in sub_query.split("->", 1)]
                aliases = [e["alias"] for e in normalized_entries]
                matches = difflib.get_close_matches(old_part, aliases, n=1, cutoff=0.3)
                
                if matches:
                    target_alias = matches[0]
                    if not new_part:
                        items.append(ExtensionResultItem(
                            icon=DEFAULT_ICON,
                            name=f"🗑️ Delete Item: '{target_alias}'",
                            description="Press Enter to completely remove this entry",
                            on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} delete {target_alias}")
                        ))
                    else:
                        items.append(ExtensionResultItem(
                            icon=DEFAULT_ICON,
                            name=f"📝 Update item configuration sequence...",
                            description=f"Target: '{target_alias}' -> Modifying to rules: {new_part}",
                            on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} update {target_alias} -> {new_part}")
                        ))
                    return RenderResultListAction(items)

            # Check Condition B: Normal layout rendering / Interactive Fuzzy Search Matching
            if sub_query:
                alias_map = {e["alias"]: e for e in normalized_entries}
                matched_aliases = difflib.get_close_matches(sub_query, list(alias_map.keys()), n=10, cutoff=0.1)
                if not matched_aliases:
                    matched_aliases = [a for a in alias_map.keys() if sub_query.lower() in a.lower()]
                matched_entries = [alias_map[a] for a in matched_aliases]
            else:
                matched_entries = normalized_entries

            for entry in matched_entries:
                items.append(ExtensionResultItem(
                    icon=DEFAULT_ICON,
                    name=entry["alias"],
                    description=f"👉 Click to deploy: {entry['command']}",
                    on_enter=SetUserQueryAction(entry["command"])
                ))

            # Check Condition C: Add structural item button generation hook
            if sub_query and "->" not in sub_query:
                current_aliases = [e["alias"] for e in normalized_entries]
                test_alias = [x.strip() for x in sub_query.split(":", 1)][0]
                
                if test_alias not in current_aliases:
                    has_colon = ":" in sub_query
                    items.append(ExtensionResultItem(
                        icon=DEFAULT_ICON,
                        name=f"➕ Add item: '{test_alias}'",
                        description="Optional Syntax: 'Alias : Command' to map cleaner display labels." if not has_colon else f"Will store script payload: {sub_query.split(':', 1)[1].strip()}",
                        on_enter=SetUserQueryAction(f"{keyword} commit_action {group_name} add {sub_query}")
                    ))

            return RenderResultListAction(items)

        return RenderResultListAction([ExtensionResultItem(icon=DEFAULT_ICON, name="Unknown State Error", on_enter=DoNothingAction())])


if __name__ == '__main__':
    KeywordQueryEventListener.__module__ = '__main__' 
    InteractiveGroupExtension().run()
