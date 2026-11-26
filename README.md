# HingeScrollerAI

A human-in-the-loop helper that reads Hinge profiles on an Android phone over ADB, so an AI agent can score them and draft openers. It likes a chosen prompt and types a comment on request, but **you always tap Send yourself**. It never taps Skip and installs nothing on the phone.

Hinge may not allow automated use of its app. Use at your own risk, keep a human in the loop, and be honest with the people you talk to.

## Setup
```
sudo apt install -y adb
```
On the phone: Settings > About > tap Build number 7x > Developer options > enable USB debugging. Plug in, accept the prompt, set USB mode to File transfer.

```
adb devices   # should list your phone as "device"
```

Python 3 standard library only; no pip packages and no API key.

## Use
Open a profile in Hinge, then:
```
./next.sh                                   # scroll to top, read the profile, save a screen map
python3 hinge.py send "<prompt key>" "<text>"   # like that prompt and type the comment
```
`next` prints the profile text and a `[screen map]` of prompt keys. `send` jumps to that prompt, taps its like button once, and types your text. Then you check the box and tap Send.

See `AGENTS.md` for how an AI agent should drive this (aliases, safety rules, scoring, opener style, known quirks).

## Notes
- Hinge blocks screenshots (black image), so everything works from the UI text dump. Photos and videos can't be read.
- `state/` holds the last profile's details and is git-ignored. Don't commit it.
