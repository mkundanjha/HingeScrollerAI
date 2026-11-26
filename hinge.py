#!/usr/bin/env python3
"""Hinge helper over adb. No installs on the phone, no Skip taps.

  hinge.py next                      read current profile, number each screen,
                                     save map of prompts -> screen number
  hinge.py send "<prompt key>" "<text>"
                                     jump to the screen holding that prompt, tap its
                                     like button once, type the text. YOU tap Send.
"""
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

STATE = Path(__file__).parent / "state" / "current.json"
NOISE = {
    "Undo last skip", "More", "Dating preferences", "Signals filter, Off",
    "Age filter options", "Height filter options", "Dating intentions filter options",
    "Discover", "Standouts", "Likes You", "Matches", "Profile Hub", "Unmute video",
    "Like", "Like photo", "Like prompt", "Like photo prompt", "Like video",
}
SAFE_TOP, SAFE_BOTTOM = 300, 1950  # keep like buttons away from header and bottom bar


def adb(*args):
    return subprocess.run(["adb", *args], capture_output=True, text=True).stdout


def screen_size():
    m = re.findall(r"(\d+)x(\d+)", adb("shell", "wm", "size"))
    return int(m[-1][0]), int(m[-1][1])


def dump():
    """UI text dump; retries because uiautomator sometimes returns nothing mid-animation."""
    for attempt in range(5):
        raw = adb("exec-out", "uiautomator", "dump", "/dev/tty")
        end = raw.rfind("</hierarchy>")
        if end != -1:
            try:
                root = ET.fromstring(raw[: end + len("</hierarchy>")])
            except ET.ParseError:
                root = None
            if root is not None:
                nodes = []
                for n in root.iter("node"):
                    d = (n.get("content-desc") or n.get("text") or "").strip()
                    b = re.findall(r"\d+", n.get("bounds", ""))
                    if d and len(b) == 4:
                        nodes.append((d, tuple(map(int, b))))
                return nodes
        time.sleep(1.0 + attempt * 0.5)
    sys.exit("FAIL: phone returned no UI dump after 5 tries (screen off, locked, or video busy?)")


def interesting(nodes):
    return [d for d, _ in nodes
            if d not in NOISE and not d.startswith(("Skip ", "Elapsed time"))]


def signature(nodes):
    return sorted(set(interesting(nodes)))


def position(nodes):
    """Text AND on-screen position of every element. Unlike signature(), this changes when
    we scroll past photos whose labels are all identical, so it's what detects 'end reached'."""
    return sorted((d, b) for d, b in nodes
                  if d not in NOISE and not d.startswith(("Skip ", "Elapsed time")))


def items(nodes):
    """Prompts on this screen with their like-button centre."""
    out = []
    for d, (x1, y1, x2, y2) in nodes:
        m = re.match(r"(Photo prompt|Prompt): (.*?)(?:\. Answer:|$)", d)
        if not m:
            continue
        want = "Like photo prompt" if m.group(1) == "Photo prompt" else "Like prompt"
        for d2, (a1, b1, a2, b2) in nodes:
            if d2 == want and b1 >= y1 and b2 <= y2:
                out.append({"key": m.group(2), "full": d[:120], "bounds": [x1, y1, x2, y2],
                            "like": [(a1 + a2) // 2, (b1 + b2) // 2]})
                break
    return out


def swipe(frac_from, frac_to, ms=400):
    w, h = screen_size()
    adb("shell", "input", "swipe", str(w // 2), str(int(h * frac_from)),
        str(w // 2), str(int(h * frac_to)), str(ms))
    time.sleep(1.2)


def fwd():
    swipe(0.70, 0.35)


def back():
    swipe(0.35, 0.70)


def go_top():
    """Swipe back until the screen stops changing, i.e. we are at the top of the profile."""
    prev = None
    for _ in range(16):
        pos = position(dump())
        if pos == prev:
            return
        prev = pos
        back()


def cmd_next():
    go_top()  # always start from the top so screen numbers are consistent
    screens, prev, shown = [], None, set()
    for i in range(1, 15):
        nodes = dump()
        sig = signature(nodes)
        pos = position(nodes)
        if pos == prev:  # nothing moved at all: really the end
            print("[end of profile]")
            break
        screens.append({"n": i, "items": items(nodes), "sig": sig})
        for line in interesting(nodes):  # print each line once -> fewer tokens
            if line not in shown:
                shown.add(line)
                print(line)
        prev = pos
        fwd()
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(screens, ensure_ascii=False, indent=1))
    index = {s["n"]: [it["key"] for it in s["items"]] for s in screens if s["items"]}
    print("\n[screen map]", json.dumps(index, ensure_ascii=False))


def cmd_send(key, text):
    if re.search(r"[\"\\$`&;<>|()%]", text):
        sys.exit("FAIL: text has characters adb can't type safely: \" \\ $ ` & ; < > | ( ) %")
    screens = json.loads(STATE.read_text())
    cands = [(s["n"], it) for s in screens for it in s["items"] if key.lower() in it["key"].lower()]
    if not cands:
        sys.exit(f"FAIL: no prompt matching '{key}' in the last 'next' map")
    # judge by the like BUTTON (not the whole prompt box); prefer the most central one
    mid = screen_size()[1] // 2
    ok = [c for c in cands if SAFE_TOP <= c[1]["like"][1] <= SAFE_BOTTOM]
    n, _ = min(ok or cands, key=lambda c: abs(c[1]["like"][1] - mid))

    def locate(nodes=None):
        for it in items(dump() if nodes is None else nodes):
            if key.lower() in it["key"].lower() and SAFE_TOP <= it["like"][1] <= SAFE_BOTTOM:
                return it["like"]
        return None

    def try_tap(nodes, where):
        """If the prompt's like button is visible AND stable (two reads), tap it and type."""
        a = locate(nodes)
        if not a:
            return False
        time.sleep(1.5)
        if locate() != a:
            return False
        adb("shell", "input", "tap", str(a[0]), str(a[1]))
        time.sleep(1.8)
        adb("shell", f'input text "{text.replace(" ", "%s")}"')
        print(f"OK: tapped like on '{key}' ({where}) at {a} and typed the text. "
              "Check the box, then tap Send yourself.")
        return True

    # Directional walk: find which recorded screen we are on, then swipe the shorter way toward
    # the target screen n, checking the live screen after every swipe. Ambiguous matches (screens
    # with identical text) resolve to the one closest to n; a wrong guess only costs a swipe.
    sigs = {s["n"]: s["sig"] for s in screens}
    prev_sig = None
    for step in range(14):
        nodes = dump()
        if try_tap(nodes, f"directional, step {step}"):
            return
        sig = signature(nodes)
        pos = position(nodes)
        if pos == prev_sig:  # swipe changed nothing: hit an end, so fall back to go-to-top
            break
        prev_sig = pos
        match = [k for k, v in sigs.items() if v == sig]
        if not match:  # screen not in the map: we're lost, fall back
            break
        cur = min(match, key=lambda k: abs(k - n))
        if cur > n:
            back()
        elif cur < n:
            fwd()
        else:  # on the target screen but not tappable yet: nudge down a little and re-check
            fwd()

    # Fallback: go to the top (checking every step), then down toward screen n.
    top_sig = screens[0]["sig"]
    for step in range(16):
        nodes = dump()
        if try_tap(nodes, f"scrolling up, step {step}"):
            return
        if signature(nodes) == top_sig:
            break
        back()
    else:
        sys.exit("FAIL: couldn't get back to the top of the profile; nothing tapped")
    # Phase 2: from the top, down toward the recorded screen number.
    for step in range(1, n + 2):
        fwd()
        if try_tap(dump(), f"scrolling down, screen ~{step + 1}"):
            return
    sys.exit(f"FAIL: prompt '{key}' never became visible and stable (expected near screen {n}); nothing tapped")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "next":
        cmd_next()
    elif len(sys.argv) == 4 and sys.argv[1] == "send":
        cmd_send(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
