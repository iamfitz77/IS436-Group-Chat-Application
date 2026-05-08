"""
server_gui.py - Chat Server with a Graphical User Interface (GUI)
==================================================================
IS 436 Group Project - Basic Chat Application
Team: Fitzgerald Afari-Minta, Noel, KJ, Brandon, Shamar

HOW TO RUN:
    python src/server_gui.py <port>
    Example: python src/server_gui.py 5000

WHAT THIS FILE DOES:
    This file does everything server.py does (accepts connections, handles
    multiple clients, broadcasts messages, logs chats) BUT instead of
    running in a plain black terminal, it opens a real graphical window.

    The window has:
        - A header bar showing the port and how many clients are online
        - A scrollable chat area showing all messages with color-coded names
        - A sidebar listing every connected client with a green dot
        - A text input box and a SEND button at the bottom

HOW THIS DIFFERS FROM server.py:
    server.py uses:      print()  to display messages
                         input()  to read typed messages
    server_gui.py uses:  Tkinter widgets (ScrolledText, Entry, Button) instead

    The socket and threading logic is IDENTICAL — only the display layer changed.

IMPORTANT CONCEPT — THREADS AND THE GUI:
    Tkinter (the GUI library) has one strict rule:
        ALL changes to the GUI MUST happen on the MAIN thread.
    But our networking code runs on BACKGROUND threads (so the window does not freeze).
    To safely update the GUI from a background thread, we use:
        self.root.after(0, lambda: some_gui_function())
    This schedules the GUI update to run on the main thread as soon as possible.

NOTE: Uses ONLY Python built-in libraries. Tkinter comes pre-installed with Python.
      AI assistance (Claude) was used — disclosed per academic integrity policy.
"""

# ══════════════════════════════════════════════════════════════
# SECTION 1: IMPORTS
# ══════════════════════════════════════════════════════════════

import socket       # Lets us create network connections (TCP sockets)
                    # This is the same socket library used in server.py

import threading    # Lets us run multiple tasks at the same time (multithreading)
                    # We need this so the GUI stays responsive while handling clients

import sys          # Gives us access to sys.argv (command-line arguments)
                    # and sys.exit() to stop the program with an error code

import datetime     # Used to get the current date and time for timestamps

import os           # Used for os.path.abspath() to show the full path to the log file

import tkinter as tk
# Tkinter is Python's built-in GUI (Graphical User Interface) library.
# It lets us create windows, buttons, text boxes, labels, etc.
# We import it as "tk" so we can write tk.Button, tk.Label, etc. instead of
# tkinter.Button, tkinter.Label — just shorter to type.

from tkinter import scrolledtext
# ScrolledText is a special Tkinter widget — it's a text area that automatically
# includes a scrollbar on the right side. Perfect for a chat window where
# messages pile up and you need to scroll up to read older ones.

from tkinter import font as tkfont
# This lets us create custom Font objects with specific family, size, and weight.
# Example: tkfont.Font(family="Consolas", size=12, weight="bold")
# Without this, we would be limited to Tkinter's default fonts.


# ══════════════════════════════════════════════════════════════
# SECTION 2: COLOR PALETTE
# ══════════════════════════════════════════════════════════════

# We define ALL colors in one dictionary at the top of the file.
# Why? Because if you ever want to change the theme, you only edit this one place
# instead of hunting through hundreds of lines of code.
#
# Colors are written as "hex codes" — the # symbol followed by 6 characters.
# Each pair of characters represents Red, Green, Blue intensity (00=none, ff=full).
# Example: "#f97316" = high red (f9), medium green (73), low blue (16) = orange

COLORS = {
    # ── Background colors (darkest to lightest) ──
    "bg_dark":        "#0d1117",  # Very dark navy — the main window background
    "bg_medium":      "#161b22",  # Slightly lighter — used for the header and sidebar
    "bg_light":       "#21262d",  # Even lighter — used for the input text box

    # ── Orange accent colors ──
    "accent_orange":  "#f97316",  # Bright orange — used for titles, buttons, highlights
    "accent_dim":     "#c2410c",  # Darker orange — used for hover states and dividers

    # ── Text colors ──
    "text_primary":   "#f0f6fc",  # Nearly white — main readable text
    "text_secondary": "#8b949e",  # Medium gray — timestamps, hints, less important text
    "text_system":    "#f97316",  # Orange — system announcements (join/leave messages)

    # ── UI element colors ──
    "border":         "#30363d",  # Dark gray — thin lines separating sections
    "online_dot":     "#22c55e",  # Green — the dot next to connected client names
}

# These 8 colors are assigned to clients in order.
# Client #1 gets index 0 (Blue), Client #2 gets index 1 (Green), etc.
# If there are more than 8 clients, the colors repeat (cycle) using modulo math.
USERNAME_COLORS = [
    "#60a5fa",  # Blue
    "#34d399",  # Emerald green
    "#a78bfa",  # Purple
    "#f472b6",  # Pink
    "#facc15",  # Yellow
    "#2dd4bf",  # Teal
    "#fb923c",  # Light orange
    "#e879f9",  # Magenta
]


# ══════════════════════════════════════════════════════════════
# SECTION 3: GLOBAL STATE
# These variables are shared and accessible from anywhere in this file,
# including inside threads. "Global" means they are not locked inside
# any one function or class.
# ══════════════════════════════════════════════════════════════

# A list of dictionaries — one entry per connected client.
# Each entry looks like: { "socket": <socket obj>, "id": 1, "address": ("192.168.1.2", 54321) }
connected_clients = []

# A threading Lock — think of it as a "talking stick".
# When one thread wants to modify connected_clients, it must acquire the lock first.
# If another thread already holds the lock, the second thread WAITS until it is released.
# This prevents two threads from modifying the list at the same time (which would corrupt it).
clients_lock = threading.Lock()

# A counter that goes up by 1 each time a new client connects.
# Used to give each client a unique ID: Client #1, Client #2, etc.
client_id_counter = 0

# The filename for the chat log.
# All messages are appended to this file as the chat happens (Chat Logging bonus feature).
LOG_FILE = "chat_log.txt"


# ══════════════════════════════════════════════════════════════
# SECTION 4: HELPER FUNCTIONS
# Small reusable functions used throughout the file.
# ══════════════════════════════════════════════════════════════

def get_timestamp():
    """
    Returns the current date and time as a neatly formatted string.

    Example output: [2026-05-06 02:35:10 PM]

    How strftime() works:
        strftime() = "string format time" — converts a datetime object into a string.
        Each % code is replaced with part of the date/time:
            %Y = 4-digit year        -> 2026
            %m = month as 2 digits   -> 05
            %d = day as 2 digits     -> 06
            %I = hour (12-hr clock)  -> 02
            %M = minutes             -> 35
            %S = seconds             -> 10
            %p = AM or PM            -> PM

    Returns:
        str: Formatted timestamp string like "[2026-05-06 02:35:10 PM]"
    """
    now = datetime.datetime.now()                   # Get the current moment in time
    return now.strftime("[%Y-%m-%d %I:%M:%S %p]")  # Format it as a readable string


def get_username_color(client_id):
    """
    Returns a hex color string for a given client ID.

    Why do we need this?
        Each client's name is displayed in a unique color so it is easy to tell
        who said what at a glance — similar to how Slack or Discord color usernames.

    How it works:
        We have 8 colors in USERNAME_COLORS (indices 0-7).
        We use modulo (%) to wrap around if the client ID is larger than 8.
        Example:
            Client #1  -> (1-1) % 8 = 0 -> Blue
            Client #2  -> (2-1) % 8 = 1 -> Green
            Client #9  -> (9-1) % 8 = 0 -> Blue again (cycles back)

    Parameters:
        client_id (int): The client's unique ID number (1, 2, 3, ...)

    Returns:
        str: A hex color code like "#60a5fa"
    """
    return USERNAME_COLORS[(client_id - 1) % len(USERNAME_COLORS)]


# ══════════════════════════════════════════════════════════════
# SECTION 5: THE MAIN GUI CLASS
# ══════════════════════════════════════════════════════════════

class ServerGUI:
    """
    This class contains EVERYTHING for the server's graphical window.

    WHAT IS A CLASS?
        A class is like a blueprint. When we write ServerGUI(port_number),
        Python creates one "instance" of this blueprint — our actual running window.

    WHY USE A CLASS HERE?
        The GUI has many parts (window, chat area, input box, sidebar, socket, etc.)
        that all need to talk to each other. Storing them all as "self.something"
        inside a class keeps everything organized and connected.

    WHAT IS "self"?
        "self" refers to this specific instance of the class.
        self.root      = the main Tkinter window
        self.port      = the port number we are listening on
        self.chat_area = the scrollable text widget showing messages
        etc.

    THREAD MODEL:
        Main thread    -> runs the Tkinter GUI event loop (keeps window responsive)
        Server thread  -> runs _start_server() — accepts new client connections
        Client threads -> one per connected client, runs _handle_client()

        Rule: ONLY the main thread can update GUI widgets.
              Background threads schedule GUI updates using self.root.after()
    """

    def __init__(self, port):
        """
        __init__ is the constructor — it runs automatically when we create
        a ServerGUI object. Think of it as the setup function.

        ORDER OF OPERATIONS (very important — do not rearrange):
            1. Save the port number
            2. Create the Tkinter window (tk.Tk())
            3. Configure the window (title, size, colors, close handler)
            4. Build all visual widgets (_build_ui)
            5. Start the server socket in a background thread
            6. Schedule focus on the input box after 100ms
            7. Start the Tkinter main loop — this BLOCKS until window closes

        Parameters:
            port (int): The TCP port number this server will listen on
        """

        # ── 1. Save the port ──────────────────────────────────────────────────
        # We store it on self so every method in this class can access it
        self.port = port

        # ── 2. Create the root window ─────────────────────────────────────────
        # tk.Tk() creates the ONE main window for this application.
        # Every Tkinter app must have exactly one root window.
        self.root = tk.Tk()

        # ── 3. Configure the window ───────────────────────────────────────────

        # Text shown in the title bar at the top of the window
        self.root.title(f"IS436 Chat Server — Port {port}")

        # Initial size: 900 pixels wide, 650 pixels tall
        self.root.geometry("900x650")

        # Minimum resize limit — user cannot shrink the window below this size
        self.root.minsize(700, 500)

        # Background color for the entire window
        self.root.configure(bg=COLORS["bg_dark"])

        # When the user clicks the X button, call our on_close() method FIRST
        # so we can notify clients and close sockets before the program exits.
        # Without this, closing the window would leave client connections hanging.
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ── 4. Build all visual widgets ───────────────────────────────────────
        # _build_ui() creates all the frames, labels, text areas, and buttons.
        # It must run BEFORE the server thread starts, because the server thread
        # updates the GUI and the widgets need to exist before that happens.
        self._build_ui()

        # ── 5. Start the server networking in a background thread ─────────────
        # WHY a background thread?
        #   The server's accept() call BLOCKS — it just sits and waits for clients.
        #   If we ran this on the main thread, the window would freeze completely
        #   and the user could never type anything.
        #   A background thread lets the GUI run normally at the same time.
        #
        # threading.Thread(target=func) creates a thread that will run func().
        # daemon=True means: when the main window closes, kill this thread too.
        #   Without daemon=True, the thread would keep running even after the
        #   window closes, and the program would never fully exit.
        server_thread = threading.Thread(target=self._start_server, daemon=True)
        server_thread.start()  # Launch the thread — _start_server() begins running

        # ── 6. Schedule focus on the input box ───────────────────────────────
        # focus_force() moves keyboard focus to the input box so the user can
        # start typing right away without having to click on it first.
        # We use root.after(100, ...) to wait 100 milliseconds before doing this.
        # Why wait? Because the window needs a moment to fully render before
        # focus_force() will work reliably. 100ms is enough time.
        self.root.after(100, lambda: self.input_box.focus_force())

        # ── 7. Start the Tkinter main loop ────────────────────────────────────
        # mainloop() hands control to Tkinter. It:
        #   - Keeps the window open and visible
        #   - Listens for user actions (mouse clicks, key presses, window resize)
        #   - Redraws widgets whenever they change
        #   - Processes all the self.root.after() callbacks scheduled by threads
        #   - Runs FOREVER until the window is closed
        #
        # IMPORTANT: Everything after this line only runs AFTER the window closes.
        # The program is effectively "paused" here while the window is open.
        self.root.mainloop()

    # ──────────────────────────────────────────────────────────
    # _build_ui: Creates and arranges all visual widgets
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        """
        Builds the entire visual layout of the server window.

        TKINTER LAYOUT SYSTEM — HOW .pack() WORKS:
            Tkinter uses a "geometry manager" to position widgets.
            .pack() stacks widgets against the edges of their parent container.

            .pack(side=tk.TOP)               -> stack against the top edge
            .pack(side=tk.BOTTOM)            -> stack against the bottom edge
            .pack(side=tk.LEFT)              -> stack against the left edge
            .pack(side=tk.RIGHT)             -> stack against the right edge
            .pack(fill=tk.X)                 -> stretch to fill full width
            .pack(fill=tk.Y)                 -> stretch to fill full height
            .pack(fill=tk.BOTH, expand=True) -> fill all remaining space

        IMPORTANT PACKING ORDER FOR side=BOTTOM:
            When packing with side=BOTTOM, widgets stack from the bottom UP.
            The FIRST widget packed with side=BOTTOM ends up at the very bottom.
            So we pack the input bar first, then the separator line above it.

        WIDGET TYPES USED:
            tk.Frame       -> invisible container/box for grouping other widgets
            tk.Label       -> displays static text (user cannot edit it)
            tk.Entry       -> single-line text input field (for typing messages)
            tk.Button      -> clickable button
            ScrolledText   -> multi-line read-only text area with a scrollbar

        FINAL LAYOUT:
            +---------------------------------+--------------+
            |           HEADER BAR            |              |
            +---------------------------------+   SIDEBAR    |
            |                                 |  (who is     |
            |         CHAT AREA               |  connected)  |
            |    (scrollable messages)        |              |
            +---------------------------------+--------------+
            |                INPUT BAR                        |
            |  [ type here...              ]  [  SEND  ]      |
            +-------------------------------------------------+
        """

        # ── FONTS ─────────────────────────────────────────────────────────────
        # Define all fonts once here so they can be reused throughout _build_ui.
        # tkfont.Font() creates a font object with: family, size, weight
        #   family = the typeface name (Consolas is a monospace/coding font)
        #   size   = point size (larger number = bigger text)
        #   weight = "bold" or "normal"
        self.font_header    = tkfont.Font(family="Consolas", size=13, weight="bold")
        self.font_message   = tkfont.Font(family="Consolas", size=11)
        self.font_timestamp = tkfont.Font(family="Consolas", size=9)
        self.font_username  = tkfont.Font(family="Consolas", size=11, weight="bold")
        self.font_input     = tkfont.Font(family="Consolas", size=12)
        self.font_sidebar   = tkfont.Font(family="Consolas", size=10)

        # ── HEADER BAR ────────────────────────────────────────────────────────
        # tk.Frame is an invisible rectangular container.
        # By giving it a background color, it becomes a visible colored bar.
        header_frame = tk.Frame(
            self.root,               # parent: this frame lives directly inside the root window
            bg=COLORS["bg_medium"],  # slightly lighter than the main dark background
            height=55                # fixed at 55 pixels tall
        )
        header_frame.pack(fill=tk.X, side=tk.TOP)  # stretch full width, attach to top

        # pack_propagate(False) stops the frame from auto-shrinking to fit its children.
        # Without this, if children are small, the header would collapse to near-zero height.
        header_frame.pack_propagate(False)

        # A thin 3-pixel orange accent line at the absolute top of the window.
        # We use .place() instead of .pack() here for pixel-perfect positioning.
        # x=0, y=0 = top-left corner of the window
        # relwidth=1 = stretch to 100% of the window width
        tk.Frame(self.root, bg=COLORS["accent_orange"], height=3).place(x=0, y=0, relwidth=1)

        # App title label on the LEFT side of the header
        # tk.Label displays text that the user cannot click into or edit
        tk.Label(
            header_frame,
            text="IS436 CHAT SERVER",
            font=self.font_header,
            bg=COLORS["bg_medium"],      # must match the header frame's background
            fg=COLORS["accent_orange"],  # fg = foreground = the text color
            padx=20                      # 20px horizontal padding inside the label
        ).pack(side=tk.LEFT, pady=12)    # attach to left, 12px top/bottom padding

        # Port + status label on the RIGHT side of the header.
        # Saved as self.port_label so _update_client_list() can change its text later
        # (e.g. from "WAITING..." to "2 ONLINE" when clients connect).
        self.port_label = tk.Label(
            header_frame,
            text=f"PORT {self.port}  |  WAITING...",
            font=tkfont.Font(family="Consolas", size=10),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],  # gray — less visually prominent
            padx=20
        )
        self.port_label.pack(side=tk.RIGHT, pady=12)

        # ── INPUT BAR (bottom of the window) ──────────────────────────────────
        # CRITICAL PACKING ORDER:
        #   Tkinter's pack() allocates space in the ORDER widgets are packed.
        #   The content frame uses expand=True to fill ALL remaining space.
        #   If we pack the content frame first, it takes everything and leaves
        #   no room for the input bar — it disappears off the bottom of the window.
        #
        #   SOLUTION: Pack the input bar FIRST (it claims its space at the bottom),
        #   THEN pack the content frame (it fills whatever space is left over).
        #
        #   Order we pack with side=BOTTOM (first packed = closest to bottom):
        #       1. input_frame  -> sits at the very bottom
        #       2. separator    -> sits just above the input frame

        input_frame = tk.Frame(
            self.root,
            bg=COLORS["bg_medium"],
            pady=12,   # 12px top and bottom internal padding
            padx=15    # 15px left and right internal padding
        )
        input_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # 1px gray separator line between the chat area and the input bar
        tk.Frame(self.root, bg=COLORS["border"], height=1).pack(fill=tk.X, side=tk.BOTTOM)

        # Single-line text input field where the server admin types messages.
        # Saved as self.input_box so _send_message() and focus_force() can access it.
        self.input_box = tk.Entry(
            input_frame,
            font=self.font_input,
            bg=COLORS["bg_light"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent_orange"],  # blinking cursor is orange
            relief=tk.FLAT,               # no raised/sunken 3D border effect
            bd=0,
            highlightthickness=2,         # 2px colored outline around the box
            highlightbackground=COLORS["border"],       # outline when NOT focused (gray)
            highlightcolor=COLORS["accent_orange"],     # outline when focused (orange glow)
        )
        # ipady=10 adds 10px vertical internal padding, making the box taller
        # padx=(0, 10) adds 10px gap on the RIGHT between the box and the SEND button
        self.input_box.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 10))

        # Bind the Enter/Return key to _send_message().
        # lambda event: absorbs the event object that .bind() always passes,
        # since _send_message() takes no parameters.
        self.input_box.bind("<Return>", lambda event: self._send_message())

        # SEND button
        self.send_btn = tk.Button(
            input_frame,
            text="SEND",
            font=tkfont.Font(family="Consolas", size=11, weight="bold"),
            bg=COLORS["accent_orange"],
            fg=COLORS["bg_dark"],
            activebackground=COLORS["accent_dim"],
            activeforeground=COLORS["text_primary"],
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=8,
            cursor="hand2",
            command=self._send_message
        )
        self.send_btn.pack(side=tk.RIGHT)

        # ── MAIN CONTENT AREA ─────────────────────────────────────────────────
        # This frame holds both the CHAT AREA and the SIDEBAR side by side.
        # expand=True means it grows to fill all vertical space not used by the
        # header (top) and input bar (bottom).
        # NOTE: This is packed AFTER the input bar so it only fills the remaining
        # space — it does not push the input bar off screen.
        content_frame = tk.Frame(self.root, bg=COLORS["bg_dark"])
        content_frame.pack(fill=tk.BOTH, expand=True)

        # ── CHAT AREA (left side) ─────────────────────────────────────────────
        chat_frame = tk.Frame(content_frame, bg=COLORS["bg_dark"])
        # expand=True + fill=BOTH means this takes ALL space not used by the sidebar
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ScrolledText is a text widget with a built-in scrollbar.
        # state=tk.DISABLED = read-only. Users cannot click into it and type.
        # We temporarily switch to NORMAL when inserting messages (see _append_message),
        # then switch back to DISABLED to keep it read-only.
        self.chat_area = scrolledtext.ScrolledText(
            chat_frame,
            state=tk.DISABLED,           # read-only
            wrap=tk.WORD,                # wrap long lines at word boundaries, not mid-word
            bg=COLORS["bg_dark"],
            fg=COLORS["text_primary"],
            font=self.font_message,
            borderwidth=0,               # no border around the widget
            highlightthickness=0,        # no focus ring around the widget
            padx=15,                     # 15px left and right internal padding
            pady=15,                     # 15px top and bottom internal padding
            spacing3=8,                  # 8px extra space after each line/paragraph
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True)

        # ── TEXT TAGS ─────────────────────────────────────────────────────────
        # Tags let us style specific pieces of text inside ScrolledText.
        # Think of them like CSS classes — define the style once, apply it by name.
        #
        # HOW TO USE TAGS:
        #   self.chat_area.tag_configure("tagname", foreground="#color", font=...)
        #   defines the style.
        #
        #   self.chat_area.insert(tk.END, "some text", "tagname")
        #   applies that style to "some text" when inserting it.

        # Small gray text — used for the timestamp shown next to each message
        self.chat_area.tag_configure("timestamp",
            foreground=COLORS["text_secondary"],
            font=self.font_timestamp)

        # Bold orange text — used for the "SERVER HOST" label above server messages
        self.chat_area.tag_configure("server_name",
            foreground=COLORS["accent_orange"],
            font=self.font_username)

        # White indented text — used for the body of server messages
        self.chat_area.tag_configure("server_msg",
            foreground=COLORS["text_primary"],
            font=self.font_message,
            lmargin1=20,   # left margin for the first line of a paragraph
            lmargin2=20)   # left margin for continuation lines (when text wraps)

        # Centered italic orange text — used for system announcements
        # Examples: "Client #1 has joined" / "Server started on port 5000"
        self.chat_area.tag_configure("system",
            foreground=COLORS["text_system"],
            font=tkfont.Font(family="Consolas", size=10, slant="italic"),
            justify=tk.CENTER)

        # ── SIDEBAR (right side — shows who is connected) ─────────────────────
        # A fixed-width 200px panel on the right.
        # highlightbackground + highlightthickness draws a thin visible border.
        sidebar = tk.Frame(
            content_frame,
            bg=COLORS["bg_medium"],
            width=200,
            bd=0,
            highlightbackground=COLORS["border"],
            highlightthickness=1
        )
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)  # lock sidebar at exactly width=200

        # "CONNECTED" section heading
        tk.Label(
            sidebar,
            text="CONNECTED",
            font=tkfont.Font(family="Consolas", size=9, weight="bold"),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],
            pady=12
        ).pack()

        # Thin orange horizontal divider line below the heading
        tk.Frame(sidebar, bg=COLORS["accent_dim"], height=1).pack(fill=tk.X, padx=10)

        # This frame holds the list of connected client rows.
        # Saved as self.client_list_frame so _update_client_list() can
        # clear and rebuild it whenever someone connects or disconnects.
        self.client_list_frame = tk.Frame(sidebar, bg=COLORS["bg_medium"])
        self.client_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Placeholder label shown when nobody is connected
        tk.Label(
            self.client_list_frame,
            text="No clients yet",
            font=tkfont.Font(family="Consolas", size=9),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],
            pady=10
        ).pack()



    # ──────────────────────────────────────────────────────────
    # _append_message: Inserts a message into the chat display
    # ──────────────────────────────────────────────────────────

    def _append_message(self, sender, message, msg_type="client", client_id=None):
        """
        Adds a new message to the scrollable chat area with color-coded styling.

        THREADING RULE — VERY IMPORTANT:
            This method MUST only be called from the MAIN thread.
            If you call it from a background thread, Tkinter will crash or glitch.
            Background threads must schedule it like this:
                self.root.after(0, lambda: self._append_message(sender, msg, ...))
            self.root.after(0, func) = "run func on the main thread as soon as possible"

        HOW EACH MESSAGE IS BUILT:
            We insert several pieces of text in sequence, each with its own tag (style).
            Example for a client message:
                Insert "\n"                         (blank line for visual spacing)
                Insert "  Client #1  "              with tag "client_1" (colored bold name)
                Insert "[2026-05-06 02:35:10 PM]\n" with tag "timestamp" (small gray)
                Insert "  Hello everyone!\n"        with tag "msg_1" (white indented body)

        Parameters:
            sender (str):     The display name shown above the message.
                              Examples: "Client #1", "SERVER HOST"
            message (str):    The actual message content to show.
            msg_type (str):   Controls the visual style:
                                "server"  -> orange label (server admin's own messages)
                                "client"  -> colored label (messages from connected clients)
                                "system"  -> centered italic (join/leave/status notices)
            client_id (int):  The client's unique ID — used to pick their username color.
                              Only needed when msg_type="client".
        """

        # Step 1: Temporarily unlock the text widget.
        # Normally DISABLED (read-only) to prevent users from editing chat history.
        # We set to NORMAL just long enough to insert the new message, then lock again.
        self.chat_area.configure(state=tk.NORMAL)

        timestamp = get_timestamp()  # get current date+time string

        if msg_type == "system":
            # System announcements — centered italic orange text
            # tk.END = "insert at the very end of all existing text"
            self.chat_area.insert(tk.END, f"\n  {message}\n", "system")

        elif msg_type == "server":
            # The server admin's own outgoing messages
            self.chat_area.insert(tk.END, "\n")                             # blank spacer line
            self.chat_area.insert(tk.END, f"  {sender}  ", "server_name")  # orange bold name
            self.chat_area.insert(tk.END, f"{timestamp}\n", "timestamp")   # small gray time
            self.chat_area.insert(tk.END, f"  {message}\n", "server_msg")  # white body text

        else:
            # Messages received from a connected client
            # Each client gets a unique color based on their ID number
            color = get_username_color(client_id) if client_id else COLORS["text_primary"]

            # Dynamically create a tag for this client's username color.
            # tag_configure creates the tag if new, or updates it if it already exists.
            # Tag name example: "client_3" for Client #3
            tag_name = f"client_{client_id}"
            self.chat_area.tag_configure(tag_name,
                foreground=color,
                font=self.font_username)

            # A separate tag for this client's message body text
            msg_tag = f"msg_{client_id}"
            self.chat_area.tag_configure(msg_tag,
                foreground=COLORS["text_primary"],
                font=self.font_message,
                lmargin1=20,   # indent 20px from left
                lmargin2=20)   # keep wrapped lines indented too

            self.chat_area.insert(tk.END, "\n")                            # blank spacer
            self.chat_area.insert(tk.END, f"  {sender}  ", tag_name)      # colored bold name
            self.chat_area.insert(tk.END, f"{timestamp}\n", "timestamp")  # gray timestamp
            self.chat_area.insert(tk.END, f"  {message}\n", msg_tag)      # white body text

        # Auto-scroll to the bottom so the newest message is always visible.
        # see(tk.END) scrolls the widget until the very last character is in view.
        self.chat_area.see(tk.END)

        # Step 2: Lock the widget again — back to read-only mode.
        self.chat_area.configure(state=tk.DISABLED)

        # Return focus to the input box so the admin can keep typing without
        # having to click on the input box again after each message appears.
        self.input_box.focus_force()

    # ──────────────────────────────────────────────────────────
    # _update_client_list: Refreshes the sidebar panel
    # ──────────────────────────────────────────────────────────

    def _update_client_list(self):
        """
        Clears and rebuilds the sidebar that shows who is currently connected.

        Called every time a client connects or disconnects so the list always
        reflects the real-time state of the chat room.

        MUST be called on the main thread (it creates and destroys GUI widgets).
        Background threads use: self.root.after(0, self._update_client_list)

        Steps:
            1. Destroy all existing widgets inside self.client_list_frame
            2. If no clients: show "No clients yet" placeholder
            3. If clients: create one row per client (green dot + colored name)
            4. Update the header label ("WAITING..." or "2 ONLINE")
        """

        # winfo_children() returns all widgets inside the frame.
        # We destroy() all of them to wipe the slate clean before rebuilding.
        for widget in self.client_list_frame.winfo_children():
            widget.destroy()

        # Use the lock when reading connected_clients to prevent threading conflicts
        with clients_lock:
            if not connected_clients:
                # Nobody connected — show placeholder
                tk.Label(
                    self.client_list_frame,
                    text="No clients yet",
                    font=tkfont.Font(family="Consolas", size=9),
                    bg=COLORS["bg_medium"],
                    fg=COLORS["text_secondary"],
                    pady=10
                ).pack()
                self.port_label.configure(text=f"PORT {self.port}  |  WAITING...")

            else:
                # One or more clients — show a row for each
                for client in connected_clients:
                    # Each row = a small horizontal frame containing a dot and a name
                    row = tk.Frame(self.client_list_frame, bg=COLORS["bg_medium"])
                    row.pack(fill=tk.X, pady=3)  # 3px gap between rows

                    # Green dot indicating "online"
                    tk.Label(
                        row,
                        text="●",
                        font=tkfont.Font(family="Consolas", size=8),
                        bg=COLORS["bg_medium"],
                        fg=COLORS["online_dot"]
                    ).pack(side=tk.LEFT, padx=(0, 5))

                    # Client name in their unique color
                    color = get_username_color(client["id"])
                    tk.Label(
                        row,
                        text=f"Client #{client['id']}",
                        font=self.font_sidebar,
                        bg=COLORS["bg_medium"],
                        fg=color
                    ).pack(side=tk.LEFT)

                # Update the header with the current client count
                count = len(connected_clients)
                self.port_label.configure(text=f"PORT {self.port}  |  {count} ONLINE")

    # ──────────────────────────────────────────────────────────
    # _send_message: Sends the server admin's typed message
    # ──────────────────────────────────────────────────────────

    def _send_message(self):
        """
        Called when the SEND button is clicked OR the Enter key is pressed.

        Steps:
            1. Read and strip text from the input box
            2. Return early if empty (nothing to send)
            3. Clear the input box
            4. Display the message in our own chat window
            5. Save it to the log file
            6. Broadcast it to all connected clients over the network
            7. Return focus to the input box for the next message
        """

        # .get() reads the current text from the Entry widget
        # .strip() removes any leading/trailing whitespace or accidental newlines
        message_text = self.input_box.get().strip()

        # If the box is empty, do nothing — exit the function early
        if not message_text:
            return

        # Clear the input box so it's ready for the next message
        # .delete(0, tk.END) removes all characters from position 0 to the end
        self.input_box.delete(0, tk.END)

        # Format the message for the log file and network broadcast
        # Example: "[2026-05-06 02:35:10 PM] [SERVER HOST]: Hello everyone!"
        formatted = f"{get_timestamp()} [SERVER HOST]: {message_text}"

        # Display the message in our own chat window immediately
        # (no need to send it over the network to ourselves)
        self._append_message("SERVER HOST", message_text, msg_type="server")

        # Save to the chat log file on disk (Chat Logging bonus feature)
        self._log_message(formatted)

        # Broadcast to all connected clients
        # sender_socket=None means "send to ALL clients, skip nobody"
        self._broadcast(formatted, sender_socket=None)

        # Return keyboard focus to the input box so the admin can keep typing
        self.input_box.focus_force()

    # ──────────────────────────────────────────────────────────
    # _log_message: Saves a message to the log file
    # ──────────────────────────────────────────────────────────

    def _log_message(self, message):
        """
        Appends a formatted message to the chat log file on disk.

        This is the "Chat Logging" bonus feature from the project requirements.
        Every message (sent or received) is permanently saved so the conversation
        can be reviewed even after the app is closed.

        Why "a" (append) mode instead of "w" (write) mode?
            "w" ERASES the file and starts fresh every time it's opened.
            "a" ADDS to the end without deleting existing content.
            We always want the full history, so we use append mode.

        Parameters:
            message (str): The fully formatted message string to save.
                           Example: "[2026-05-06 02:35:10 PM] Client #1: Hello!"
        """
        # "with" automatically closes the file when the block ends — no need for f.close()
        # encoding="utf-8" handles accented characters, emojis, etc.
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message + "\n")  # \n = newline, so each message is on its own line

    # ──────────────────────────────────────────────────────────
    # _broadcast: Sends a message to all connected clients
    # ──────────────────────────────────────────────────────────

    def _broadcast(self, message, sender_socket=None):
        """
        Transmits a message to every connected client over the network.

        WHY skip the sender?
            When Client #1 sends a message, we broadcast it to everyone.
            But Client #1 already knows what they typed — no need to echo it back.
            So we skip sender_socket when looping through clients.
            When sender_socket=None (server admin sent it), we send to ALL clients.

        HOW sending works:
            Sockets transmit raw bytes, not strings.
            We must encode the string first:
                "Hello".encode("utf-8")  ->  b"Hello"  (bytes object)

        Parameters:
            message (str):          The text message to send.
            sender_socket (socket): This socket will be SKIPPED (no echo to sender).
                                    Pass None to send to ALL clients.
        """
        encoded = message.encode("utf-8")  # convert string to bytes for the network

        # Acquire the lock before reading connected_clients.
        # This prevents another thread from modifying the list mid-loop.
        with clients_lock:
            for client in connected_clients:
                if client["socket"] != sender_socket:
                    try:
                        client["socket"].send(encoded)
                    except Exception:
                        # Sending failed — client probably disconnected suddenly.
                        # Skip silently; their dedicated thread will clean them up.
                        pass

    # ──────────────────────────────────────────────────────────
    # _handle_client: Manages one connected client in its own thread
    # ──────────────────────────────────────────────────────────

    def _handle_client(self, client_socket, client_address, client_id):
        """
        Handles all communication with a single connected client.
        Runs in its own background thread — one copy per client.

        WHY its own thread?
            socket.recv() BLOCKS — it waits forever until the client sends something.
            If all clients shared one thread, everyone would be blocked waiting for
            just one client to speak. Each client gets their own thread so they are
            all handled simultaneously.

        LIFECYCLE:
            1. Display "Client #N connected" in the GUI
            2. Refresh the sidebar to show the new client
            3. Send a personal welcome message to just this client
            4. Announce to the whole room that they joined
            5. Loop: receive messages, display them, broadcast them
            6. When they disconnect or type "exit":
               - Remove from connected_clients
               - Close their socket
               - Announce they left
               - Refresh the sidebar

        Parameters:
            client_socket (socket): The socket just for this client.
            client_address (tuple): Their (IP address, port), e.g. ("192.168.1.5", 54321).
            client_id (int):        Their unique number (1, 2, 3, ...).
        """
        client_name = f"Client #{client_id}"

        # ── Notify the GUI ────────────────────────────────────────────────────
        # self.root.after(0, func) schedules func to run on the MAIN thread.
        # We cannot call GUI functions directly from this thread — Tkinter requires
        # all GUI changes on the main thread. after(0, ...) = "do this ASAP".
        self.root.after(0, lambda: self._append_message(
            "", f"{client_name} connected from {client_address[0]}", msg_type="system"
        ))
        self.root.after(0, self._update_client_list)

        # ── Send welcome message to this client only ──────────────────────────
        # This goes directly to their socket, not broadcast to everyone
        welcome = (
            f"Welcome to IS436 Chat, {client_name}!\n"
            f"  Type a message and press Enter to send.\n"
            f"  Type 'exit' to disconnect gracefully.\n"
        )
        try:
            client_socket.send(welcome.encode("utf-8"))
        except Exception:
            pass

        # ── Announce to the whole room ────────────────────────────────────────
        join_msg = f"{get_timestamp()} [SERVER] {client_name} has joined the chat!"
        self._broadcast(join_msg)
        self._log_message(join_msg)

        # ── Main receive loop ─────────────────────────────────────────────────
        while True:
            try:
                # recv(1024) waits (blocks) for up to 1024 bytes from this client.
                # This call does nothing until the client sends something.
                raw_data = client_socket.recv(1024)

                # Empty bytes b"" = client closed the connection
                if not raw_data:
                    break

                # Decode bytes back to a string and strip whitespace
                message_text = raw_data.decode("utf-8").strip()

                # Client typed "exit" — graceful disconnect
                if message_text.lower() == "exit":
                    try:
                        client_socket.send("You have disconnected. Goodbye!".encode("utf-8"))
                    except Exception:
                        pass
                    break

                # Format for the log and broadcast
                formatted = f"{get_timestamp()} {client_name}: {message_text}"
                self._log_message(formatted)

                # Schedule the GUI update on the main thread.
                # We capture current variable values as default args (m=message_text, etc.)
                # to prevent the lambda from using stale values if the loop runs again.
                self.root.after(0, lambda m=message_text, cid=client_id, cn=client_name:
                    self._append_message(cn, m, msg_type="client", client_id=cid)
                )

                # Broadcast to all other clients (skip this sender)
                self._broadcast(formatted, sender_socket=client_socket)

            except ConnectionResetError:
                # Windows: client closed their window without typing "exit"
                break
            except Exception:
                break

        # ── Cleanup ───────────────────────────────────────────────────────────

        # Remove this client from the shared list
        with clients_lock:
            connected_clients[:] = [c for c in connected_clients if c["socket"] != client_socket]

        client_socket.close()  # free the network resource

        leave_msg = f"{get_timestamp()} [SERVER] {client_name} has left the chat."
        self._broadcast(leave_msg)
        self._log_message(leave_msg)

        self.root.after(0, lambda: self._append_message(
            "", f"{client_name} has left the chat.", msg_type="system"
        ))
        self.root.after(0, self._update_client_list)

    # ──────────────────────────────────────────────────────────
    # _start_server: Creates the server socket and accepts connections
    # ──────────────────────────────────────────────────────────

    def _start_server(self):
        """
        Runs in a background thread.
        Creates the server socket and loops forever accepting new clients.

        WHY a background thread?
            accept() BLOCKS until a client connects. Running this on the main
            thread would freeze the GUI window completely.

        SERVER SOCKET LIFECYCLE:
            socket()     -> create a blank socket
            setsockopt() -> allow port reuse after restart
            bind()       -> attach to our port number
            listen()     -> start listening (queue up to 5 pending connections)
            accept()     -> BLOCK until client connects, return their socket
            Thread()     -> hand the client to a dedicated handler thread
            -> repeat accept() for the next client
        """
        global client_id_counter

        # Create the TCP server socket
        # AF_INET = IPv4, SOCK_STREAM = TCP (reliable ordered delivery)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SO_REUSEADDR lets us restart the server immediately after closing it.
        # Without this, the OS holds the port reserved for ~60 seconds after shutdown.
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # bind(("", port)) attaches to our port on ALL network interfaces
        # "" means "any IP address on this machine" (localhost AND WiFi)
        self.server_socket.bind(("", self.port))

        # listen(5) = begin accepting connections; queue up to 5 waiting at once
        self.server_socket.listen(5)

        # Show startup message in the chat area (scheduled on the main thread)
        self.root.after(0, lambda: self._append_message(
            "", f"Server started on port {self.port}. Waiting for clients...", msg_type="system"
        ))

        # ── Accept loop ───────────────────────────────────────────────────────
        while True:
            try:
                # accept() BLOCKS until a client connects.
                # Returns: client_socket (new socket just for this client)
                #          client_address (their IP and port as a tuple)
                client_socket, client_address = self.server_socket.accept()

                client_id_counter += 1
                new_id = client_id_counter

                with clients_lock:
                    connected_clients.append({
                        "socket": client_socket,
                        "id": new_id,
                        "address": client_address
                    })

                # Start a dedicated thread for this client
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address, new_id),
                    daemon=True
                )
                t.start()

            except Exception:
                # server_socket was closed by on_close() — exit the loop
                break

    # ──────────────────────────────────────────────────────────
    # on_close: Graceful shutdown when the X button is clicked
    # ──────────────────────────────────────────────────────────

    def on_close(self):
        """
        Called automatically when the user clicks the X to close the window.

        Handles graceful shutdown:
            1. Broadcast a shutdown notice to all clients
            2. Log the shutdown
            3. Close all client sockets
            4. Close the server socket (stops the accept() loop)
            5. Destroy the Tkinter window
        """
        shutdown_msg = f"{get_timestamp()} [SERVER] Server is shutting down. Goodbye!"
        self._broadcast(shutdown_msg)
        self._log_message(shutdown_msg)

        with clients_lock:
            for client in connected_clients:
                try:
                    client["socket"].close()
                except Exception:
                    pass

        try:
            self.server_socket.close()
        except Exception:
            pass

        self.root.destroy()


# ══════════════════════════════════════════════════════════════
# SECTION 6: ENTRY POINT
# Only runs when you execute: python src/server_gui.py 5000
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    sys.argv example:
        Command:     python src/server_gui.py 5000
        sys.argv:    ["src/server_gui.py", "5000"]
        sys.argv[0]: script name (ignored)
        sys.argv[1]: our port number
    """

    if len(sys.argv) != 2:
        print("Usage:   python src/server_gui.py <port>")
        print("Example: python src/server_gui.py 5000")
        sys.exit(1)

    try:
        port_number = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid port number.")
        sys.exit(1)

    if not (1025 <= port_number <= 65535):
        print(f"Error: Port must be between 1025 and 65535. You entered: {port_number}")
        sys.exit(1)

    # Launch the server GUI — blocks here until the window is closed
    ServerGUI(port_number)