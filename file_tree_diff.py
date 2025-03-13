import os
import re
import json
import argparse

def parse_tree(tree_str):
    """
    Parse a tree-like string (e.g. output from "tree /F") into a nested dictionary.
    
    The algorithm:
      1. The first non-blank line is taken as the root.
      2. For each subsequent line, determine its depth by counting the leading
         characters (spaces and vertical bars '│') before the connector ("├── " or "└── ").
         We assume each indent level corresponds to 4 characters.
      3. Remove the connector and extra spaces to extract the name.
      4. If the name ends with '/', it is treated as a folder (stored as a dict) with the slash removed.
         Otherwise, it’s a file (stored with value None).
      5. A stack is used to keep track of the current branch.
    """
    lines = [line.rstrip() for line in tree_str.splitlines() if line.strip()]
    if not lines:
        return {}
    
    # The first line is the root folder. Remove any leading/trailing slashes.
    root_line = lines[0].strip()
    root = root_line.strip("/")
    tree = {root: {}}
    
    # Stack holds tuples: (current_depth, current_dict)
    stack = [(0, tree[root])]
    
    for line in lines[1:]:
        # Determine indent level by matching leading spaces and vertical bars.
        indent_match = re.match(r'^([ │]+)', line)
        indent_str = indent_match.group(1) if indent_match else ""
        level = len(indent_str) // 4  # assume each level = 4 characters
        
        # Remove the indent and connector (either "├── " or "└── ")
        line_without_indent = re.sub(r'^[ │]*(├── |└── )', '', line)
        name = line_without_indent.strip()
        
        # Check if it's a folder (ends with "/")
        if name.endswith("/"):
            is_folder = True
            name = name.rstrip("/")
        else:
            is_folder = False
        
        # Pop the stack until we reach the correct parent level (level-1 relative to this line).
        while stack and stack[-1][0] >= level + 1:
            stack.pop()
        parent = stack[-1][1] if stack else tree[root]
        if is_folder:
            parent[name] = {}
            stack.append((level + 1, parent[name]))
        else:
            parent[name] = None
    return tree

def build_actual_tree(folder):
    """
    Walk through the given folder and build a nested dictionary structure.
    Folder keys are stored as folder names (without trailing '/').
    Files are stored as keys with a value of None.
    
    If the folder does not exist, a warning is printed and an empty dictionary is returned,
    so that the diff will report all baseline items as missing.
    """
    if not os.path.exists(folder):
        print(f"Warning: Folder '{folder}' does not exist. Treating it as empty.")
        return {}
    
    tree = {}
    for root, dirs, files in os.walk(folder):
        rel_path = os.path.relpath(root, folder)
        if rel_path == ".":
            current_node = tree
        else:
            parts = rel_path.split(os.sep)
            current_node = tree
            for part in parts:
                current_node = current_node.setdefault(part, {})
        for d in sorted(dirs):
            current_node[d] = {}
        for f in sorted(files):
            current_node[f] = None
    folder_name = os.path.basename(os.path.abspath(folder))
    return {folder_name: tree}

def diff_trees(baseline, actual):
    """
    Recursively compute the diff between two nested dictionary trees.
    
    Returns a dictionary mapping names to tuples:
       (marker, children)
    where marker is:
       "-" if the item is in the baseline but missing in actual,
       "+" if the item is extra in actual,
       ""  if the item is present in both (only included if children differ).
       
    Files (value None) are compared directly.
    """
    diff = {}
    all_keys = set(baseline.keys()).union(actual.keys())
    for key in sorted(all_keys):
        in_base = key in baseline
        in_act = key in actual
        if in_base and not in_act:
            diff[key] = ("-", baseline[key])
        elif in_act and not in_base:
            diff[key] = ("+", actual[key])
        else:
            base_val = baseline[key]
            act_val = actual[key]
            if isinstance(base_val, dict) and isinstance(act_val, dict):
                child_diff = diff_trees(base_val, act_val)
                if child_diff:
                    diff[key] = ("", child_diff)
            # If both are files (None), then they match.
    return diff

def print_diff(diff, prefix=""):
    """
    Print the diff tree in a tree-like format.
    The marker is appended after the item name, e.g.:
      exceptions.py   (-)
    
    This function checks that each diff item is a tuple before unpacking.
    """
    if not diff:
        return
    items = list(diff.items())
    count = len(items)
    for idx, item in enumerate(items):
        if not isinstance(item[1], tuple):
            continue
        name, (marker, children) = item
        connector = "└── " if idx == count - 1 else "├── "
        marker_str = f"   ({marker})" if marker else ""
        print(prefix + connector + name + marker_str)
        if isinstance(children, dict) and children:
            extension = "    " if idx == count - 1 else "│   "
            print_diff(children, prefix + extension)

def main():
    parser = argparse.ArgumentParser(
        description="Parse baseline.txt, build an actual folder tree, and compute the differences."
    )
    parser.add_argument("--baseline", required=True,
                        help="Path to the baseline file (tree output).")
    parser.add_argument("--folder", required=True,
                        help="Path to the actual folder to scan.")
    args = parser.parse_args()
    
    # Determine the baseline structure:
    if os.path.isfile(args.baseline):
        try:
            with open(args.baseline, "r", encoding="utf-8") as f:
                baseline_text = f.read()
            baseline_tree = parse_tree(baseline_text)
        except Exception as e:
            print(f"Error reading baseline file: {e}")
            return
    elif os.path.isdir(args.baseline):
        baseline_tree = build_actual_tree(args.baseline)
    else:
        print("Error: Baseline argument must be a valid file or folder path.")
        return
    
    # Build the actual folder tree.
    if os.path.isdir(args.folder):
        actual_tree = build_actual_tree(args.folder)
    else:
        print("Error: The folder argument must be a valid folder path.")
        return
            
    # Compute the differences.
    diff = diff_trees(baseline_tree, actual_tree)
    
    
    # Optionally, print the parsed trees.
    print("Baseline Tree:")
    print(json.dumps(baseline_tree, indent=4))
    print("\nActual Tree:")
    print(json.dumps(actual_tree, indent=4))
    # Print instructions.
    print("\n---------------------------------------------------")    
    print("Instructions to Interpret Differences:")
    print("- Items appended with '(-)' indicate that the item is present in the baseline but missing in the actual folder.")
    print("- Items appended with '(+)' indicate that the item is extra in the actual folder (i.e. not present in the baseline).")
    print("- Items without a marker are either matching or are folders that only show differences within their children.")
    print("---------------------------------------------------\n")
    print("\nDifferences:")
    print_diff(diff)

if __name__ == "__main__":
    main()
