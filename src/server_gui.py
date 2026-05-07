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
    But our networking code runs on BACKGROUND threads (so the window doesn't freeze).
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
# Without this, we'd be limited to Tkinter's default fonts.


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

    # ── Bubble/message background colors ──
    "bg_bubble_self": "#e8600a",  # Dark orange — background for server's own messages
    "bg_bubble_other":"#1f2937",  # Dark gray-blue — background for client messages

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
    "scrollbar":      "#30363d",  # Dark gray — the scrollbar track color
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
# including inside threads. "Global" means they're not locked inside
# any one function or class.
# ══════════════════════════════════════════════════════════════

# A list of dictionaries — one entry per connected client.
# Each entry looks like: { "socket": <socket obj>, "id": 1, "address": ("192.168.1.2", 54321) }
connected_clients = []

# A threading Lock — think of it as a "talking stick" or a bathroom key.
# When one thread wants to read or modify connected_clients, it must "acquire" the lock first.
# If another thread already holds the lock, the second thread WAITS until it's released.
# This prevents two threads from modifying the list at the exact same time (which would corrupt it).
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

    Why do we need this?
        Every chat message is stamped with the exact time it was sent.
        This is the "Timestamps" bonus feature from the project requirements.

    How strftime() works:
        strftime() = "string format time" — converts a datetime object into a string.
        Each % code is replaced with part of the date/time:
            %Y = 4-digit year        → 2026
            %m = month as 2 digits   → 05
            %d = day as 2 digits     → 06
            %I = hour (12-hr clock)  → 02  (use %H for 24-hour)
            %M = minutes             → 35
            %S = seconds             → 10
            %p = AM or PM            → PM

    Returns:
        str: Formatted timestamp string like "[2026-05-06 02:35:10 PM]"
    """
    now = datetime.datetime.now()                    # Get the current moment in time
    return now.strftime("[%Y-%m-%d %I:%M:%S %p]")   # Format it as a readable string


def get_username_color(client_id):
    """
    Returns a hex color string for a given client ID.

    Why do we need this?
        Each client's name is displayed in a unique color so it's easy to tell
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
        "self" refers to the specific instance of the class.
        self.root      = the main window
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

        It does things in this order:
            1. Saves the port number
            2. Creates the Tkinter window
            3. Builds all the visual widgets (header, chat area, sidebar, input bar)
            4. Starts the server networking in a background thread
            5. Starts the Tkinter main loop (keeps window alive and responsive)

        Parameters:
            port (int): The TCP port number this server will listen on
        """
        # Save the port so other methods in this class can access it via self.port
        self.port = port

        # ── Step 1: Create the main window ────────────────────────────────────
        # tk.Tk() creates the root (main) window. Every Tkinter app has exactly one.
        self.root = tk.Tk()

        # Set the text that appears in the window title bar at the top
        self.root.title(f"IS436 Chat Server — Port {port}")

        # Set the initial window size: 900 pixels wide, 650 pixels tall
        self.root.geometry("900x650")

        # Set a minimum size — the user cannot shrink the window smaller than this
        self.root.minsize(700, 500)

        # Set the background color of the entire window to our dark navy color
        self.root.configure(bg=COLORS["bg_dark"])

        # Tell Tkinter what to do when the user clicks the X (close) button.
        # Instead of just closing instantly, we call our on_close() method first
        # so we can disconnect clients gracefully before shutting down.
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ── Step 2: Build the visual layout ───────────────────────────────────
        # This method creates all the widgets: header, chat area, sidebar, input bar
        self._build_ui()

        # ── Step 3: Start the server socket in a background thread ────────────
        # WHY a background thread?
        #   The server accept() call BLOCKS — it just sits and waits for clients.
        #   If we ran this on the main thread, the window would freeze completely.
        #   By running it in a separate thread, the GUI stays responsive.
        # daemon=True means: when the main window closes, kill this thread too
        server_thread = threading.Thread(target=self._start_server, daemon=True)
        server_thread.start()

        # ── Step 4: Start the Tkinter event loop ──────────────────────────────
        # mainloop() hands control to Tkinter. It:
        #   - Keeps the window open
        #   - Listens for user actions (clicks, key presses)
        #   - Redraws the window when needed
        #   - Runs forever until the window is closed
        # Everything after this line only runs AFTER the window closes.
        self.root.mainloop()

    # ──────────────────────────────────────────────────────────
    # _build_ui: Creates and arranges all visual widgets
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        """
        Builds the entire visual layout of the server window.

        TKINTER LAYOUT BASICS:
            Tkinter uses a geometry manager to position widgets.
            We use .pack() which stacks widgets in a direction.

            .pack(side=tk.TOP)              -> stacks from the top down
            .pack(side=tk.BOTTOM)           -> stacks from the bottom up
            .pack(side=tk.LEFT)             -> stacks left to right
            .pack(side=tk.RIGHT)            -> stacks right to left
            .pack(fill=tk.X)                -> stretches the widget to fill horizontally
            .pack(fill=tk.BOTH, expand=True)-> fills all available space

        WIDGET TYPES USED:
            tk.Frame       -> an invisible container for grouping other widgets
            tk.Label       -> displays text (non-editable)
            tk.Entry       -> a single-line text input box (for typing messages)
            tk.Button      -> a clickable button
            ScrolledText   -> a multi-line read-only text area with a scrollbar

        WINDOW LAYOUT:
            +---------------------------------+--------------+
            |           HEADER BAR            |              |
            +---------------------------------|   SIDEBAR    |
            |                                 |  (connected  |
            |         CHAT AREA               |   clients)   |
            |                                 |              |
            +---------------------------------+--------------+
            |                INPUT BAR                        |
            +-------------------------------------------------+
        """

        # ── FONTS ─────────────────────────────────────────────────────────────
        # We define fonts as variables so we can reuse them without repeating ourselves.
        # tkfont.Font() lets us specify: family (typeface), size (in points), weight (bold/normal)
        self.font_header    = tkfont.Font(family="Consolas", size=13, weight="bold")  # Title text
        self.font_message   = tkfont.Font(family="Consolas", size=11)                 # Chat messages
        self.font_timestamp = tkfont.Font(family="Consolas", size=9)                  # Small timestamps
        self.font_username  = tkfont.Font(family="Consolas", size=11, weight="bold")  # Bold usernames
        self.font_input     = tkfont.Font(family="Consolas", size=12)                 # Input box text
        self.font_sidebar   = tkfont.Font(family="Consolas", size=10)                 # Sidebar names

        # ── HEADER BAR ────────────────────────────────────────────────────────
        # tk.Frame is an invisible rectangular box used to group widgets.
        # Here we give it a background color so it becomes a visible colored bar.
        header_frame = tk.Frame(
            self.root,              # Parent: this frame lives inside the root window
            bg=COLORS["bg_medium"], # Slightly lighter than the main dark background
            height=55               # Fixed height of 55 pixels
        )
        # fill=tk.X   -> stretch to fill the full WIDTH of the window
        # side=tk.TOP -> attach to the top of the window
        header_frame.pack(fill=tk.X, side=tk.TOP)

        # pack_propagate(False) prevents the frame from auto-shrinking to fit its contents.
        # Without this, the header would collapse to zero if it had no children yet.
        header_frame.pack_propagate(False)

        # A very thin (3px tall) orange bar placed at the absolute top edge of the window.
        # We use .place() instead of .pack() here because we want pixel-perfect positioning.
        # relwidth=1 means "stretch to 100% of the parent window's width"
        accent_bar = tk.Frame(self.root, bg=COLORS["accent_orange"], height=3)
        accent_bar.place(x=0, y=0, relwidth=1)

        # App title label on the LEFT side of the header
        # tk.Label displays text that the user cannot edit
        tk.Label(
            header_frame,                   # This label lives inside the header frame
            text="IS436 CHAT SERVER",       # The text to display
            font=self.font_header,          # Bold large font
            bg=COLORS["bg_medium"],         # Must match the header background
            fg=COLORS["accent_orange"],     # fg = foreground = text color (orange)
            padx=20                         # 20px of horizontal padding inside the label
        ).pack(side=tk.LEFT, pady=12)       # Attach to left, 12px top/bottom padding

        # Port and status label on the RIGHT side of the header.
        # We save it as self.port_label so we can update it later
        # (e.g. change "WAITING..." to "2 ONLINE" when clients connect).
        self.port_label = tk.Label(
            header_frame,
            text=f"PORT {self.port}  |  WAITING...",
            font=tkfont.Font(family="Consolas", size=10),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],    # Gray — less visually prominent
            padx=20
        )
        self.port_label.pack(side=tk.RIGHT, pady=12)

        # ── MAIN CONTENT AREA ─────────────────────────────────────────────────
        # This frame is a container that holds the chat area AND sidebar side by side.
        # expand=True means it will grow to fill all remaining vertical space
        # after the header and input bar take their share.
        content_frame = tk.Frame(self.root, bg=COLORS["bg_dark"])
        content_frame.pack(fill=tk.BOTH, expand=True)

        # ── CHAT AREA (left side, takes most of the space) ────────────────────
        chat_frame = tk.Frame(content_frame, bg=COLORS["bg_dark"])
        # expand=True + fill=tk.BOTH -> takes all space NOT used by the sidebar
        chat_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ScrolledText is a multi-line text widget with a built-in scrollbar.
        # state=tk.DISABLED makes it read-only so users cannot click and type in it.
        # We temporarily set it to NORMAL when inserting new messages (see _append_message),
        # then set it back to DISABLED so it stays read-only.
        self.chat_area = scrolledtext.ScrolledText(
            chat_frame,
            state=tk.DISABLED,          # Read-only mode — code inserts text, not the user
            wrap=tk.WORD,               # Wrap long lines at word boundaries, not mid-word
            bg=COLORS["bg_dark"],
            fg=COLORS["text_primary"],
            font=self.font_message,
            borderwidth=0,              # No visible border around the widget
            highlightthickness=0,       # No focus highlight ring around the widget
            padx=15,                    # 15px padding on left and right inside the text area
            pady=15,                    # 15px padding on top and bottom inside the text area
            spacing3=8,                 # 8px extra space AFTER each paragraph/line (visual breathing room)
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True)

        # ── TEXT TAGS ─────────────────────────────────────────────────────────
        # Tags let us apply different visual styles to different pieces of text
        # inside the same ScrolledText widget.
        # Think of tags like CSS classes: you define the style once, then apply it by name.
        #
        # tag_configure(name, **options) defines what a tag looks like.
        # When inserting text, the tag name is passed as the 3rd argument:
        #   self.chat_area.insert(tk.END, "hello", "timestamp")
        #   This displays "hello" using the gray small-font "timestamp" style.

        # Small gray text for the time shown next to each message
        self.chat_area.tag_configure("timestamp",
            foreground=COLORS["text_secondary"],
            font=self.font_timestamp)

        # Bold orange label for "SERVER HOST" (the server admin's name)
        self.chat_area.tag_configure("server_name",
            foreground=COLORS["accent_orange"],
            font=self.font_username)

        # White text with left indent for the server's message content
        self.chat_area.tag_configure("server_msg",
            foreground=COLORS["text_primary"],
            font=self.font_message,
            lmargin1=20,    # Left margin for the FIRST line of a paragraph
            lmargin2=20)    # Left margin for CONTINUATION lines (when text wraps)

        # Centered italic orange text for system announcements
        # Examples: "Client #1 has joined" or "Client #2 has left"
        self.chat_area.tag_configure("system",
            foreground=COLORS["text_system"],
            font=tkfont.Font(family="Consolas", size=10, slant="italic"),
            justify=tk.CENTER)

        # Subtle gray for any separator lines
        self.chat_area.tag_configure("separator",
            foreground=COLORS["border"])

        # ── SIDEBAR (right side — shows who is connected) ──────────────────────
        # A fixed-width panel.
        # highlightbackground draws a thin visible border around the entire frame.
        sidebar = tk.Frame(
            content_frame,
            bg=COLORS["bg_medium"],
            width=200,                              # Fixed width — will not resize
            bd=0,
            highlightbackground=COLORS["border"],   # Border color (thin line on left edge)
            highlightthickness=1                    # 1px border
        )
        # fill=tk.Y -> stretch to fill the full HEIGHT of the content area (not width)
        sidebar.pack(side=tk.RIGHT, fill=tk.Y)
        sidebar.pack_propagate(False)   # Lock the sidebar at exactly width=200

        # "CONNECTED" heading at the top of the sidebar
        tk.Label(
            sidebar,
            text="CONNECTED",
            font=tkfont.Font(family="Consolas", size=9, weight="bold"),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],
            pady=12
        ).pack()

        # A thin 1px horizontal orange divider below the heading
        tk.Frame(sidebar, bg=COLORS["accent_dim"], height=1).pack(fill=tk.X, padx=10)

        # This frame will hold the list of client name rows.
        # We save it as self.client_list_frame so _update_client_list() can
        # clear and rebuild its contents every time someone connects or leaves.
        self.client_list_frame = tk.Frame(sidebar, bg=COLORS["bg_medium"])
        self.client_list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Placeholder label shown when nobody is connected yet
        self.no_clients_label = tk.Label(
            self.client_list_frame,
            text="No clients yet",
            font=tkfont.Font(family="Consolas", size=9),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],
            pady=10
        )
        self.no_clients_label.pack()

        # ── INPUT BAR (bottom of the window) ──────────────────────────────────
        # IMPORTANT PACKING ORDER: When using side=tk.BOTTOM, the LAST widget packed
        # ends up at the very bottom. So we pack the input_frame first (it goes to
        # the bottom), then the 1px separator line (which ends up just above it).

        input_frame = tk.Frame(
            self.root,
            bg=COLORS["bg_medium"],
            pady=12,    # Vertical internal padding
            padx=15     # Horizontal internal padding
        )
        input_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # 1px gray separator line between the chat area and the input bar
        tk.Frame(self.root, bg=COLORS["border"], height=1).pack(fill=tk.X, side=tk.BOTTOM)

        # Single-line text entry box where the server admin types messages
        # tk.Entry is the standard Tkinter single-line input field
        self.input_box = tk.Entry(
            input_frame,
            font=self.font_input,
            bg=COLORS["bg_light"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent_orange"],  # The blinking text cursor is orange
            relief=tk.FLAT,                 # No raised/sunken 3D border effect
            bd=0,
            highlightthickness=2,           # Draw a colored 2px outline around the box
            highlightbackground=COLORS["border"],      # Outline color when NOT focused (gray)
            highlightcolor=COLORS["accent_orange"],    # Outline color when focused (orange glow)
        )
        # ipady=10 adds 10px vertical internal padding making the input taller
        # padx=(0, 10) adds 10px gap on the RIGHT between the input and the Send button
        self.input_box.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 10))

        # Bind the Enter/Return key to call _send_message()
        # .bind("<Return>", handler) means: when Enter is pressed, call handler
        # lambda event: ... is needed because .bind() passes an event object,
        # but _send_message() takes no arguments. The lambda absorbs the event param.
        self.input_box.bind("<Return>", lambda event: self._send_message())

        # SEND button — orange background with dark text
        # command=self._send_message tells Tkinter to call this function when clicked
        self.send_btn = tk.Button(
            input_frame,
            text="SEND",
            font=tkfont.Font(family="Consolas", size=11, weight="bold"),
            bg=COLORS["accent_orange"],             # Orange button background
            fg=COLORS["bg_dark"],                   # Dark text on top of orange
            activebackground=COLORS["accent_dim"],  # Slightly darker orange when mouse is held down
            activeforeground=COLORS["text_primary"],
            relief=tk.FLAT,
            bd=0,
            padx=20,                # 20px horizontal padding makes the button wide
            pady=8,
            cursor="hand2",         # Show a pointer (hand) cursor when hovering over the button
            command=self._send_message
        )
        self.send_btn.pack(side=tk.RIGHT)

    # ──────────────────────────────────────────────────────────
    # _append_message: Adds a message to the chat display
    # ──────────────────────────────────────────────────────────

    def _append_message(self, sender, message, msg_type="client", client_id=None):
        """
        Inserts a new message into the scrollable chat area with styling.

        IMPORTANT THREADING RULE:
            This method MUST be called from the MAIN thread.
            If calling from a background (network) thread, wrap it like this:
                self.root.after(0, lambda: self._append_message(sender, msg, ...))
            self.root.after(0, func) schedules func to run on the main thread
            at the very next available moment (0ms delay = as soon as possible).

        HOW WE BUILD EACH MESSAGE:
            We insert multiple pieces of text in sequence, each with its own tag.
            Example for a client message:
                1. Insert a blank line (spacing)
                2. Insert "  Client #1  " with tag "client_1" (colored bold username)
                3. Insert "[2026-05-06 02:35 PM]" with tag "timestamp" (small gray)
                4. Insert "  Hello world" with tag "msg_1" (white indented body)

        Parameters:
            sender (str):     The display name shown above the message.
                              Examples: "Client #1", "SERVER HOST"
            message (str):    The actual message content to display.
            msg_type (str):   Controls the visual style of the message:
                                "server"  -> orange SERVER HOST label (your own messages)
                                "client"  -> uniquely colored username (from clients)
                                "system"  -> centered italic orange (join/leave notices)
            client_id (int):  The client's ID number — used to pick their username color.
                              Only needed when msg_type="client".
        """

        # Temporarily unlock the text widget so code can insert text into it.
        # Normally it's DISABLED (read-only) so users can not click and type in it.
        self.chat_area.configure(state=tk.NORMAL)

        timestamp = get_timestamp()  # Current time for the timestamp label

        if msg_type == "system":
            # System announcements — centered italic orange text
            # Examples: "Client #2 has joined the chat!" or "Server started on port 5000"
            # tk.END means "append to the very end of all existing text"
            self.chat_area.insert(tk.END, f"\n  {message}\n", "system")

        elif msg_type == "server":
            # The server admin's own messages — shown with orange "SERVER HOST" label
            self.chat_area.insert(tk.END, f"\n")                           # Blank line for spacing
            self.chat_area.insert(tk.END, f"  {sender}  ", "server_name") # Bold orange name
            self.chat_area.insert(tk.END, f"{timestamp}\n", "timestamp")  # Small gray timestamp
            self.chat_area.insert(tk.END, f"  {message}\n", "server_msg") # White message body

        else:
            # Messages received from connected clients
            # Each client gets a unique color based on their ID

            # Look up this client's assigned color (cycles through 8 colors)
            color = get_username_color(client_id) if client_id else COLORS["text_primary"]

            # Create a tag for this specific client's username color.
            # We generate the tag name dynamically: "client_1", "client_2", etc.
            # tag_configure() either creates a new tag or updates an existing one.
            tag_name = f"client_{client_id}"
            self.chat_area.tag_configure(tag_name,
                foreground=color,
                font=self.font_username)

            # A separate tag for this client's message body
            msg_tag = f"msg_{client_id}"
            self.chat_area.tag_configure(msg_tag,
                foreground=COLORS["text_primary"],
                font=self.font_message,
                lmargin1=20,    # Indent the message 20px from the left edge
                lmargin2=20)    # Keep wrapped continuation lines indented too

            self.chat_area.insert(tk.END, f"\n")                           # Blank spacer
            self.chat_area.insert(tk.END, f"  {sender}  ", tag_name)      # Colored bold username
            self.chat_area.insert(tk.END, f"{timestamp}\n", "timestamp")  # Gray timestamp
            self.chat_area.insert(tk.END, f"  {message}\n", msg_tag)      # White message body

        # Auto-scroll to the bottom so the newest message is always visible.
        # see(tk.END) tells the widget to scroll until the last character is visible.
        self.chat_area.see(tk.END)

        # Re-lock the text widget — back to read-only so users can not edit the chat history
        self.chat_area.configure(state=tk.DISABLED)

    # ──────────────────────────────────────────────────────────
    # _update_client_list: Refreshes the sidebar panel
    # ──────────────────────────────────────────────────────────

    def _update_client_list(self):
        """
        Clears and rebuilds the sidebar that shows who is currently connected.

        This is called every time a client connects or disconnects so the list
        always reflects the real-time state of the chat room.

        MUST be called on the main thread (it creates and destroys GUI widgets).
        Background threads use: self.root.after(0, self._update_client_list)

        How it works step by step:
            1. Get all child widgets inside self.client_list_frame
            2. Destroy (delete) them all to start fresh
            3. If no clients: show the "No clients yet" placeholder
            4. If clients exist: create one row per client (green dot + colored name)
            5. Update the header label to show the count ("2 ONLINE" or "WAITING...")
        """

        # winfo_children() returns a list of all widgets inside the frame.
        # We destroy() each one to wipe the panel before rebuilding it.
        for widget in self.client_list_frame.winfo_children():
            widget.destroy()

        # Use the lock when reading connected_clients to prevent threading conflicts
        with clients_lock:
            if not connected_clients:
                # Show placeholder when nobody is connected
                tk.Label(
                    self.client_list_frame,
                    text="No clients yet",
                    font=tkfont.Font(family="Consolas", size=9),
                    bg=COLORS["bg_medium"],
                    fg=COLORS["text_secondary"],
                    pady=10
                ).pack()

                # Update the header status back to "WAITING..."
                self.port_label.configure(text=f"PORT {self.port}  |  WAITING...")

            else:
                # Create one row per connected client
                for client in connected_clients:
                    # Each row is a small horizontal frame: [dot] [name]
                    row = tk.Frame(self.client_list_frame, bg=COLORS["bg_medium"])
                    row.pack(fill=tk.X, pady=3)  # pady=3 = small gap between each row

                    # Green online indicator dot
                    tk.Label(
                        row,
                        text="●",
                        font=tkfont.Font(family="Consolas", size=8),
                        bg=COLORS["bg_medium"],
                        fg=COLORS["online_dot"]     # Green color for "online"
                    ).pack(side=tk.LEFT, padx=(0, 5))   # 5px gap between dot and name

                    # Client name in their unique color
                    color = get_username_color(client["id"])
                    tk.Label(
                        row,
                        text=f"Client #{client['id']}",
                        font=self.font_sidebar,
                        bg=COLORS["bg_medium"],
                        fg=color
                    ).pack(side=tk.LEFT)

                # Update header with current client count
                count = len(connected_clients)
                self.port_label.configure(text=f"PORT {self.port}  |  {count} ONLINE")

    # ──────────────────────────────────────────────────────────
    # _send_message: Sends the server admin's typed message
    # ──────────────────────────────────────────────────────────

    def _send_message(self):
        """
        Called when the SEND button is clicked or the Enter key is pressed.

        What it does step by step:
            1. Read text from the input box and strip whitespace
            2. Do nothing if the input is empty
            3. Clear the input box so it's ready for the next message
            4. Format the message with a timestamp
            5. Display it in our own chat window immediately
            6. Save it to the log file
            7. Broadcast it to all connected clients over the network
        """

        # .get() reads the current text in the Entry widget
        # .strip() removes any leading/trailing spaces or newline characters
        message_text = self.input_box.get().strip()

        # If the user just pressed Enter without typing anything, do nothing
        if not message_text:
            return  # return exits the function immediately (early return)

        # Clear the input box after reading it
        # .delete(0, tk.END) deletes characters from position 0 to the end
        self.input_box.delete(0, tk.END)

        # Build the formatted message string used for the log file and network broadcast
        # Example output: "[2026-05-06 02:35:10 PM] [SERVER HOST]: Hello everyone!"
        formatted = f"{get_timestamp()} [SERVER HOST]: {message_text}"

        # Display it in our own chat window (no network needed for our own messages)
        self._append_message("SERVER HOST", message_text, msg_type="server")

        # Save to the chat log file on disk
        self._log_message(formatted)

        # Broadcast to every connected client over the network
        # sender_socket=None means "send to ALL clients, skip nobody"
        self._broadcast(formatted, sender_socket=None)

    # ──────────────────────────────────────────────────────────
    # _log_message: Saves a message to the log file
    # ──────────────────────────────────────────────────────────

    def _log_message(self, message):
        """
        Appends a formatted message string to the chat log file on disk.

        This implements the "Chat Logging" bonus feature from the requirements.
        Every message sent or received is permanently saved here so the server
        admin can review the full conversation history even after the app closes.

        Why append mode ("a") instead of write mode ("w")?
            "w" (write) mode ERASES the file and starts fresh every time.
            "a" (append) mode ADDS to the end of the file without deleting anything.
            We always want to keep the full history, so we use append.

        Parameters:
            message (str): The fully formatted message string to save.
                           Example: "[2026-05-06 02:35:10 PM] Client #1: Hello!"
        """
        # open() opens (or creates) the file.
        # "a" = append mode (add to end, never erase)
        # encoding="utf-8" ensures special characters like accents and emojis are handled
        # The "with" block automatically closes the file when done — no manual f.close() needed
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message + "\n")  # \n = newline character — puts each message on its own line

    # ──────────────────────────────────────────────────────────
    # _broadcast: Sends a message to all connected clients
    # ──────────────────────────────────────────────────────────

    def _broadcast(self, message, sender_socket=None):
        """
        Transmits a message to every connected client over the network.

        WHY skip the sender?
            When Client #1 sends a message, the server receives it and broadcasts
            it to everyone. But Client #1 already knows what they typed — we should
            not send their own message back to them again.
            So we skip sender_socket when looping.
            When sender_socket=None (server admin sent it), everyone receives it.

        HOW network sending works:
            Sockets transmit raw bytes — not strings. So we must convert first:
                "Hello".encode("utf-8") -> b"Hello" (bytes object)
            UTF-8 is a character encoding that supports all languages and emoji.

        Parameters:
            message (str):          The text message to send to all clients.
            sender_socket (socket): The socket of the message's original sender.
                                    This socket will be SKIPPED to avoid echoing.
                                    Pass None to send to ALL clients (no skip).
        """
        # Convert the string to bytes — this is required for socket.send()
        encoded = message.encode("utf-8")

        # Acquire the threading lock before iterating over connected_clients.
        # This prevents another thread from adding/removing a client in the middle
        # of our loop, which could cause a crash or skipped delivery.
        with clients_lock:
            for client in connected_clients:
                # Skip the socket that sent this message (no need to echo it back)
                if client["socket"] != sender_socket:
                    try:
                        client["socket"].send(encoded)
                    except Exception:
                        # If sending fails, the client probably disconnected suddenly.
                        # We silently skip them — their dedicated thread will clean them up.
                        pass

    # ──────────────────────────────────────────────────────────
    # _handle_client: Manages one connected client (runs in its own thread)
    # ──────────────────────────────────────────────────────────

    def _handle_client(self, client_socket, client_address, client_id):
        """
        Handles all incoming messages from a single connected client.

        WHY does this run in its own thread?
            socket.recv() is a BLOCKING call — it just waits indefinitely until
            the client sends something. If all clients shared one thread, Client #2
            would be completely ignored while we sat waiting for Client #1 to speak.
            By giving each client their own thread, they all get handled simultaneously.

        LIFECYCLE (what happens in order):
            1. Show "Client #N connected" system message in the GUI
            2. Refresh the sidebar to add this client's name
            3. Send a personal welcome message to this client only
            4. Broadcast "Client #N has joined the chat!" to everyone
            5. Loop: wait for messages, broadcast them, display them in the GUI
            6. When the client disconnects or types "exit", clean up:
               - Remove from connected_clients list
               - Close their socket
               - Broadcast "Client #N has left the chat."
               - Refresh the sidebar to remove their name

        Parameters:
            client_socket (socket): The socket dedicated to this specific client.
                                    Each client gets their own socket (not the server socket).
            client_address (tuple): The client's IP and port, e.g. ("192.168.1.5", 54321).
            client_id (int):        The unique ID for this client (1, 2, 3, ...).
        """
        client_name = f"Client #{client_id}"

        # ── Notify the GUI that a new client connected ────────────────────────
        # self.root.after(0, func) schedules func to run on the MAIN thread.
        # We CANNOT call GUI functions directly from this background thread —
        # Tkinter requires all GUI updates on the main thread.
        # after(0, ...) means "schedule this for the main thread ASAP (0ms delay)"
        # lambda: ... creates a small anonymous function to wrap the call
        self.root.after(0, lambda: self._append_message(
            "", f"{client_name} connected from {client_address[0]}", msg_type="system"
        ))

        # Refresh the sidebar on the main thread to show the new client's name
        self.root.after(0, self._update_client_list)

        # ── Send welcome message ONLY to this client ───────────────────────────
        # This is a direct send to one socket — it's NOT broadcast to others
        welcome = (
            f"Welcome to IS436 Chat, {client_name}!\n"
            f"  Type a message and press Enter to send.\n"
            f"  Type 'exit' to disconnect gracefully.\n"
        )
        try:
            client_socket.send(welcome.encode("utf-8"))
        except Exception:
            pass  # If this fails, we will catch the disconnection in the loop below

        # ── Announce to the whole room that this client joined ─────────────────
        join_msg = f"{get_timestamp()} [SERVER] {client_name} has joined the chat!"
        self._broadcast(join_msg)   # Send to all other clients via their sockets
        self._log_message(join_msg) # Save to the log file

        # ── Main message receive loop for this client ─────────────────────────
        # Runs continuously until the client disconnects or types "exit"
        while True:
            try:
                # recv(1024) waits (blocks) for data from this client.
                # 1024 = max bytes to receive at once (1 KB — more than enough for chat).
                # This call just sits here doing nothing until the client sends something.
                raw_data = client_socket.recv(1024)

                # recv() returns empty bytes b"" when the client closes the connection
                if not raw_data:
                    break  # Exit the loop — client disconnected

                # Convert bytes back to a readable string
                # .strip() removes whitespace and newline characters from both ends
                message_text = raw_data.decode("utf-8").strip()

                # Did the client type "exit" to leave gracefully?
                if message_text.lower() == "exit":
                    try:
                        # Send a goodbye acknowledgment before closing
                        client_socket.send("You have disconnected. Goodbye!".encode("utf-8"))
                    except Exception:
                        pass
                    break  # Exit the loop cleanly

                # Build the formatted message for the log and broadcast
                # Example: "[2026-05-06 02:35:10 PM] Client #2: Hey everyone!"
                formatted = f"{get_timestamp()} {client_name}: {message_text}"
                self._log_message(formatted)

                # Schedule the GUI update on the main thread.
                # We use default argument values (m=message_text, etc.) to "capture"
                # the current variable values in the lambda. Without this trick,
                # by the time the lambda runs, these variables might have changed
                # (because the loop keeps running and overwriting them).
                self.root.after(0, lambda m=message_text, cid=client_id, cn=client_name:
                    self._append_message(cn, m, msg_type="client", client_id=cid)
                )

                # Broadcast to all other clients (skip this sender's socket)
                self._broadcast(formatted, sender_socket=client_socket)

            except ConnectionResetError:
                # Windows-specific error: client closed the window without typing "exit"
                break

            except Exception:
                # Catch any other unexpected errors so the server does not crash
                break

        # ── Cleanup after this client disconnects ─────────────────────────────

        # Remove this client from the shared connected_clients list.
        # List comprehension keeps all clients EXCEPT the one whose socket matches.
        with clients_lock:
            connected_clients[:] = [c for c in connected_clients if c["socket"] != client_socket]

        # Close the socket to free the OS network resource
        client_socket.close()

        # Notify the chat room that this person left
        leave_msg = f"{get_timestamp()} [SERVER] {client_name} has left the chat."
        self._broadcast(leave_msg)
        self._log_message(leave_msg)

        # Update the GUI: show system message and refresh the sidebar
        self.root.after(0, lambda: self._append_message(
            "", f"{client_name} has left the chat.", msg_type="system"
        ))
        self.root.after(0, self._update_client_list)

    # ──────────────────────────────────────────────────────────
    # _start_server: Creates the server socket and waits for connections
    # ──────────────────────────────────────────────────────────

    def _start_server(self):
        """
        Runs in a background thread — sets up the server socket and loops
        forever accepting new client connections.

        WHY a background thread?
            server_socket.accept() BLOCKS until a client connects.
            If this ran on the main thread, the entire GUI window would freeze.
            A background thread keeps the GUI fully responsive at all times.

        HOW THE SERVER SOCKET LIFECYCLE WORKS:
            socket()     -> create a blank socket object
            setsockopt() -> configure: allow reuse of the port after restart
            bind()       -> attach the socket to our IP address and port number
            listen()     -> start listening (queue up to 5 pending connections)
            accept()     -> BLOCK until a client connects, then return their socket
            Thread()     -> hand the client socket to a dedicated handler thread
            -> repeat accept() for the next client
        """
        global client_id_counter  # We increment this global variable when clients connect

        # ── Create and configure the server socket ────────────────────────────
        # AF_INET     = use IPv4 addresses (the standard x.x.x.x format)
        # SOCK_STREAM = use TCP (reliable ordered delivery — right for chat)
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # SO_REUSEADDR = allow the port to be reused immediately after the server closes.
        # Without this, restarting the server quickly gives "Address already in use"
        # because the OS keeps the port reserved for ~60 seconds after the last use.
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # bind(("", port)) attaches this socket to our chosen port.
        # "" = "listen on ALL network interfaces" (both 127.0.0.1 and the WiFi IP)
        self.server_socket.bind(("", self.port))

        # listen(5) = start accepting connections; queue up to 5 waiting connections
        self.server_socket.listen(5)

        # ── Display startup message in the GUI ────────────────────────────────
        self.root.after(0, lambda: self._append_message(
            "", f"Server started on port {self.port}. Waiting for clients...", msg_type="system"
        ))

        # ── Main accept loop ───────────────────────────────────────────────────
        while True:
            try:
                # accept() BLOCKS here until a client connects.
                # Returns a BRAND NEW socket just for communicating with that one client,
                # plus the client's address as a (ip, port) tuple.
                # The original server_socket stays open to accept more clients.
                client_socket, client_address = self.server_socket.accept()

                # Give this client a unique sequential ID number
                client_id_counter += 1
                new_id = client_id_counter

                # Add the new client to the shared list (inside a lock for safety)
                with clients_lock:
                    connected_clients.append({
                        "socket": client_socket,   # Used to send/receive from this client
                        "id": new_id,              # Their unique number
                        "address": client_address  # Their IP address and port
                    })

                # Start a dedicated thread for this client.
                # target = the function to run in this thread
                # args   = arguments passed to that function (must be a tuple)
                # daemon = True means the thread auto-closes when the main window closes
                t = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, client_address, new_id),
                    daemon=True
                )
                t.start()   # Launch the thread — runs independently from this point

            except Exception:
                # This exception is triggered when on_close() calls self.server_socket.close()
                # while accept() is waiting. That is our signal to stop the accept loop.
                break

    # ──────────────────────────────────────────────────────────
    # on_close: Graceful shutdown when the X button is clicked
    # ──────────────────────────────────────────────────────────

    def on_close(self):
        """
        Called automatically when the user clicks the window's X (close) button.

        WHY do we handle this manually?
            Without this handler, closing the window would:
                - Leave all client TCP connections hanging open (bad)
                - Not notify clients that the server shut down
                - Not write a final entry to the chat log

            With this handler we:
                1. Send a shutdown notice to all connected clients
                2. Log the shutdown
                3. Close all client sockets cleanly
                4. Close the server socket (also stops the accept() loop)
                5. Destroy the Tkinter window and end the program
        """
        shutdown_msg = f"{get_timestamp()} [SERVER] Server is shutting down. Goodbye!"
        self._broadcast(shutdown_msg)    # Notify all connected clients
        self._log_message(shutdown_msg)  # Save to the log file

        # Close every client socket
        with clients_lock:
            for client in connected_clients:
                try:
                    client["socket"].close()
                except Exception:
                    pass  # Already closed is fine

        # Close the main server socket.
        # This will cause the accept() call in _start_server to throw an exception,
        # which breaks out of the loop and ends that background thread.
        try:
            self.server_socket.close()
        except Exception:
            pass

        # Destroy the Tkinter window — this ends mainloop() and the program exits
        self.root.destroy()


# ══════════════════════════════════════════════════════════════
# SECTION 6: ENTRY POINT
# This block only runs when you execute this file directly.
# It will NOT run if this file is imported by another script.
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    sys.argv is a list of everything typed on the command line.

    Example:
        Command:      python src/server_gui.py 5000
        sys.argv:     ["src/server_gui.py", "5000"]
        sys.argv[0]:  "src/server_gui.py"  (the script name — we ignore this)
        sys.argv[1]:  "5000"               (our port argument)

    We expect exactly 2 items: the script name and the port number.
    """

    # Make sure the user provided exactly one argument (the port)
    if len(sys.argv) != 2:
        print("Usage:   python src/server_gui.py <port>")
        print("Example: python src/server_gui.py 5000")
        sys.exit(1)  # Exit with code 1 — non-zero means "something went wrong"

    # Try converting the port argument from a string to an integer.
    # int("5000") = 5000. int("abc") raises ValueError — we catch that below.
    try:
        port_number = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid port number. Please enter an integer.")
        sys.exit(1)

    # Validate the port is in the allowed range (project spec says 1025-65535).
    # Ports 0-1024 are "well-known ports" reserved for system services
    # (HTTP=80, HTTPS=443, SSH=22) and require admin privileges to use.
    if not (1025 <= port_number <= 65535):
        print(f"Error: Port must be between 1025 and 65535. You entered: {port_number}")
        sys.exit(1)

    # All checks passed — create the ServerGUI object.
    # This triggers __init__, which builds the window, starts the server thread,
    # and calls mainloop() which keeps the window open until the user closes it.
    ServerGUI(port_number)