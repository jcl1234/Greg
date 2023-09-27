import json
import os
import platform
import openai
import subprocess
from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

console = Console()


###########################################################################################################
# Config
###########################################################################################################


CONFIG_LOCATION = os.path.expanduser("~/.config/greg.json")

# Defaults
config = {
    "OPENAI_API_KEY": None,
    "GPT_MODEL": "gpt-4",
    "SYSTEM_PLATFORM": platform.platform(),
    "SYSTEM_SHELL": "bash",
    "SYSTEM_EDITOR": "VS Code"
}

if not os.path.exists(CONFIG_LOCATION):
    console.print(f"Could not find {CONFIG_LOCATION}. Configuring now (you can always reconfigure this manually).\n", style="#A0A0A0")
    # Allow user to configure
    for key, val in config.items():
        if not val:
            new_val = Prompt.ask(f"{key}", console=console)
            config[key] = new_val
    # Write config file
    with open(CONFIG_LOCATION, 'w') as f:
        json.dump(config, f, indent=4)


with open(CONFIG_LOCATION) as f:
    config = json.load(f)

# GPT config
OPENAI_API_KEY = config.get("OPENAI_API_KEY")
GPT_MODEL = config.get("GPT_MODEL")

# System config
SYSTEM_PLATFORM = config.get("SYSTEM_PLATFORM")
SYSTEM_SHELL = config.get("SYSTEM_SHELL")
SYSTEM_EDITOR = config.get("SYSTEM_EDITOR")


###########################################################################################################
# OpenAI functionality
###########################################################################################################


openai.api_key = OPENAI_API_KEY


def create_conversation(prompt):
    return [{"role": "system", "content": prompt}]


def put_user_message(conversation, msg):
    conversation.append({"role": "user", "content": msg})


def put_system_message(conversation, msg):
    conversation.append({"role": "system", "content": msg})


# Second return value is True if command
def gen_assistant_response_and_print(conversation, style="#FFFFFF", prefix=""):
    completion = openai.ChatCompletion.create(model=GPT_MODEL, messages=conversation, temperature=0.2, stream=True)
    conversation.append({"role": "assistant", "content": ""})
    is_cmd = None
    for res in completion:
        delta = res.choices[0]["delta"]
        delta_content = delta["content"] if delta else ""
        conversation[-1]["content"] += delta_content
        if is_cmd is None and len(conversation[-1]["content"]) > 0:
            if conversation[-1]["content"][0] == "!":
                # Command detected, change style
                is_cmd = True
                style = "#8080FF"
                prefix = ""
            elif conversation[-1]["content"][0] != "!":
                is_cmd = False
                console.print(prefix, end="", style=style)
        if not is_cmd:
            if prefix:
                delta_content = delta_content.replace("\n", f"\n{prefix}")
            console.print(delta_content, end="", style=style)
    if not is_cmd:
        print("")
    return conversation[-1]["content"]


###########################################################################################################
# Greg
###########################################################################################################


prompt = f"""
You are Greg, a helpful assitant.
You will answer the user in the most helpful possible way.
You have access to multiple commands that allow you to interact with the system.
You cannot mix commands and text in the same response. Commands must be standalone responses.

Example 1:
    system: "Entering chat mode"
    user: "Analyze <file> for me"
    assistant: "!term"
    system: "Entering terminal mode"
    assistant: "cat <file>"
    system: "[TERMINAL] <file contents>"
    assistant: "!chat"
    system: "Entering chat mode"
    assistant: "Here's my analysis of <file> ..."
    user: "Thanks!"


Terminal guidelines:
    - Don't tell the user what you're about to do in the terminal. JUST DO IT.
    - The user can see terminal output.
    - Don't reiterate terminal output in chat mode.
    - Emphasis: DON"T REITERATE TERMINAL OUTPUT IN CHAT MODE. THE USER CAN SEE THE TERMINAL.
        - For example:
            - user: "ls"
            - assistant: *causes terminal to output files*
            - assistant: *DOESN"T LIST FILES IN CHAT MODE*

# Commands:

---
## !chat

This command puts you in "chat" mode.
You start out in this mode.
Use this mode to communicate with the user.

---
## !term

This command puts you in "terminal" mode.
Anything you type while in terminal mode will direct to the users terminal. Do NOT output any text that will be an invalid terminal command.
When you enter a terminal command, you will receive the output from the users terminal (beginning with [TERMINAL])
Type the "!term" again to exit terminal mode.

You use feedback from the terminal to inform your next terminal executions and / or your response to the user.
If a terminal command fails, try not to run the same command again.
Exit terminal mode and request user intervention if necessary.

Try to remain in terminal mode, don't switch back to chat to explain things to the user.
If you need to explain a command, make sure it's commented out with '#' while in terminal mode.

Abilities:
    - You can generate files, and can do anything that a terminal can do.
    - You can access the web. Use curl or any other terminal util.
    - If performing a task requires a library, you can check if the user has the library and use it yourself. For example converting PDF to text.
---

User's machine specifications:
- Operating system: {SYSTEM_PLATFORM}
- Shell: {SYSTEM_SHELL}
- Editor: {SYSTEM_EDITOR}
"""

# Ctrl-C handler
import signal
def sig_interrupt_handler(signal, frame):
    subprocess.run("clear")
    exit()
signal.signal(signal.SIGINT, sig_interrupt_handler)

conversation = create_conversation(prompt)
put_system_message(conversation, "Entering chat mode")

MODES = {
    "chat": {"name": "chat", "style": "#80F080"},
    "term": {"name": "terminal", "style": "#00FF00", "prefix": "$ "}
}

subprocess.run("clear")

gpt_msg = None
mode = MODES["chat"]
first_input = True
while True:
    # Process GPT CMD
    if gpt_msg and len(gpt_msg) > 0 and gpt_msg[0] == "!":
        cmd = gpt_msg[1:]
        system_response = ""
        if cmd in MODES:
            # Valid CMD
            mode = MODES[cmd]
            system_response = f"Entering {mode['name']} mode"
            put_system_message(conversation, system_response)
            console.print(Markdown(f"---"))
            console.print(f"[{system_response}]", style="#404040")
        else:
            # Invalid CMD
            system_response = f"\"!{cmd}\" is not a valid command"
            put_system_message(conversation, system_response)
            console.print(f"<System>: {system_response}", style="#FF0000")
    else:
        match mode["name"]:
            case "chat":
                # Gather and store user input
                first_input = False
                user_msg = Prompt.ask("[bold blue]>[/]", console=console)
                put_user_message(conversation, user_msg)

            case "terminal":
                if gpt_msg:
                    # Run terminal command
                    p = subprocess.Popen(gpt_msg, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, err = p.communicate()
                    console_output = ""
                    if out:
                        console_output += out.decode('utf-8')
                    if err:
                        console_output += " " + err.decode('utf-8')

                    # Store and print terminal response
                    put_system_message(conversation, f"[TERMINAL] {console_output}")
                    if console_output.strip():
                        print("")
                        console.print(Markdown(f"```bash\n{console_output}", code_theme="github-dark", justify="center"))

            case _:
                pass

    # Generate and print gpt response
    print("")
    style = mode.get("style", "#FFFFFF")
    prefix = mode.get("prefix", "")
    gpt_msg = gen_assistant_response_and_print(conversation, prefix=prefix, style=style)
    print("")
