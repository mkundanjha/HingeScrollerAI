"""Read the Hinge chat currently on screen and print reply suggestions.
Read-only: it never taps or types anything on the phone."""
import os
import sys
import xml.etree.ElementTree as ET

import subprocess
import uiautomator2 as u2


def screen_text(d):
    """Return visible text nodes in top-to-bottom order."""
    root = ET.fromstring(d.dump_hierarchy())
    items = []
    for node in root.iter("node"):
        text = (node.get("text") or node.get("content-desc") or "").strip()
        if not text:
            continue
        # bounds look like "[x1,y1][x2,y2]"
        b = node.get("bounds", "[0,0][0,0]").replace("][", ",").strip("[]").split(",")
        items.append((int(b[1]), int(b[0]), text))
    items.sort()
    return [t for _, _, t in items]


def main():
    d = u2.connect()  # first adb device
    if d.app_current().get("package", "").lower().find("hinge") == -1:
        print("Warning: Hinge doesn't look like the foreground app.", file=sys.stderr)

    lines = screen_text(d)
    if not lines:
        print("No readable text (screen may be blocked or empty).")
        return
    screen = "\n".join(lines)
    print("--- Screen text ---")
    print(screen)

    prompt = (
        "Below is text scraped from a dating app screen (may include UI "
        "labels). If it's a chat, suggest 3 short, natural, specific "
        "replies in the user's voice. If it's a profile, suggest 3 "
        "openers that reference something concrete. Keep each under "
        "25 words. Reply with only the suggestions.\n\n" + screen
    )
    # Uses your Claude Code login; no API key needed.
    out = subprocess.run(
        ["claude", "-p", "--tools", ""], input=prompt,
        capture_output=True, text=True,
    )
    print("\n--- Suggestions ---")
    print(out.stdout or out.stderr)


if __name__ == "__main__":
    main()
