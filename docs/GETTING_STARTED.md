# Getting Started with PCE (no coding experience required)

This guide walks you through installing and using Personal Context Engine
(PCE) on your own computer. You don't need to know how to program. You will
need to type a few commands into a program called **Terminal** (Mac/Linux)
— we'll explain exactly what to type.

It should take about 10-15 minutes.

## What is this, in plain terms?

PCE keeps a private, searchable copy of your own documents and notes —
on your computer only, never uploaded anywhere — so that an AI assistant
you run locally (not a company's cloud service) can actually know about
your projects, preferences, and history instead of starting from zero every
conversation.

Nothing you add to PCE leaves your machine. There's no account to create
and no cloud service involved.

## Before you start

You'll need:

- A Mac or Linux computer. (Windows works too, using [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) — the steps below are the same once you're inside it.)
- About 15 minutes.
- Some folder of your own notes/documents to try it on (optional — a couple of example files are included so you can try PCE without one).

## Step 1: Open Terminal

- **On a Mac:** press `Cmd + Space`, type `Terminal`, press Enter.
- **On Linux:** look for "Terminal" in your applications menu.

A window with a blinking cursor will open. That's where you'll type the
commands below. Type each line exactly as shown, then press Enter, and
wait for it to finish before typing the next one.

## Step 2: Get the PCE code onto your computer

The easiest way: go to <https://github.com/c-ster/PCE>, click the green
**Code** button, then **Download ZIP**. Unzip it — you'll get a folder
named `PCE`.

Then, in Terminal, move into that folder. If you downloaded it normally,
this is usually:

```bash
cd ~/Downloads/PCE
```

(If you know git, `git clone https://github.com/c-ster/PCE.git` and `cd PCE`
works too.)

## Step 3: Install it

Still in Terminal, in that `PCE` folder, run:

```bash
./install.sh
```

This script:

- checks you have a recent-enough version of Python (the programming
  language PCE is written in) and tells you where to get it if not,
- creates a small, self-contained folder inside `PCE` to install into (it
  does not touch anything else on your computer),
- installs PCE into it.

You can open `install.sh` in any text editor first and read exactly what it
does before running it — it's a plain text file, not something mysterious.

If it finishes with "Install verified," you're good. If something goes
wrong, the script will tell you what, and you can [open an issue](https://github.com/c-ster/PCE/issues)
if you're stuck.

## Step 4: Turn PCE on

Every time you open a new Terminal window to use PCE, first run:

```bash
source .venv/bin/activate
```

(This just tells Terminal "use the copy of PCE I installed in this folder."
You'll know it worked because your prompt will start with `(.venv)`.)

Then set up your own private storage, called a **capsule**:

```bash
pce init
```

This creates a folder at `~/.pce` on your computer — that's where all your
information will live, encrypted by nothing but your own computer's normal
file permissions, never sent anywhere.

## Step 5: Add something for PCE to know about

Point PCE at a folder of your own notes (Markdown or plain text files), or
try it with the examples included in this repo:

```bash
pce source add examples/synthetic_profile
```

(To use your own notes instead, replace that path with something like
`~/Documents/my-notes`.)

Then build the search index:

```bash
pce index
```

## Step 6: Search it

```bash
pce search "concise technical preference"
```

You'll probably see **"No matches."** — and that's not a bug. PCE doesn't
trust anything it hasn't been told is safe to use, by default. Try again
with:

```bash
pce search "concise technical preference" --include-unclassified
```

Now you should see a result. In everyday use, instead of typing that flag
every time, you'd mark documents as reviewed once with a command like:

```bash
pce classify <document-id> --sensitivity public
```

(You can find the document id from `pce source inspect <source-id>`, where
`<source-id>` is the id printed when you ran `pce source add`.)

## Step 7 (optional): Connect a local AI model

If you run a local AI model through an app like [Jan](https://jan.ai),
Claude Desktop, or Open WebUI, you can let it search your PCE context. Add
this to that app's settings (the exact place depends on the app — look for
"MCP servers" or "tools"):

```json
{
  "mcpServers": {
    "pce": {
      "command": "pce",
      "args": ["serve-mcp", "--include-unclassified"]
    }
  }
}
```

## Check everything is working

At any point, run:

```bash
pce doctor
```

It checks your setup and tells you what's OK and what still needs
attention.

## What PCE can't do yet

This is an early, actively-developed project. Right now it can store your
documents, search them, and connect to a local AI model. It cannot yet:
remember new facts on its own, notice when your notes contradict each
other, or proactively ask you questions to keep itself up to date. Those
are planned — see the main [README](../README.md) for current status.

## Getting help

- `pce --help` lists every command.
- Something broken? [Open an issue on GitHub](https://github.com/c-ster/PCE/issues).
