"""
client_gui.py - Chat Client with a Graphical User Interface (GUI)
==================================================================
IS 436 Group Project - Basic Chat Application
Team: Fitzgerald Afari-Minta, Noel, KJ, Brandon, Shamar

HOW TO RUN:
    Same machine:       python src/client_gui.py <port>
    Different machine:  python src/client_gui.py <server-ip> <port>

    Examples:
        python src/client_gui.py 5000
        python src/client_gui.py 192.168.1.45 5000

    (The server must already be running before you launch the client)

WHAT THIS FILE DOES:
    This file does everything client.py does (connects to the server,
    sends and receives messages) BUT instead of using the plain terminal,
    it opens a real graphical window.

    When launched, it first shows a small popup asking for your display name.
    Then it opens the main chat window showing:
        - A header with your name and connection status
        - A scrollable chat area with color-coded messages
        - A text input box and SEND button at the bottom

HOW THIS DIFFERS FROM client.py:
    client.py uses:      print()  to display received messages
                         input()  to read what you type
    client_gui.py uses:  Tkinter widgets (ScrolledText, Entry, Button) instead

    The socket and threading logic is IDENTICAL — only the display layer changed.

IMPORTANT CONCEPT — WHY TWO THREADS:
    The client needs to do two things simultaneously:
        1. Wait for messages arriving from the server (could happen any time)
        2. Let you type and send messages
    These cannot both run on the same thread because recv() BLOCKS —
    it just sits and waits. So:
        Main thread     -> runs the Tkinter GUI (keeps window alive)
        Receive thread  -> runs _receive_loop() in the background

    GUI updates from the receive thread use self.root.after() to safely
    pass work back to the main thread (Tkinter's strict threading requirement).

NOTE: Uses ONLY Python built-in libraries. Tkinter is included with Python.
      AI assistance (Claude) was used — disclosed per academic integrity policy.
"""

# ══════════════════════════════════════════════════════════════
# SECTION 1: IMPORTS
# ══════════════════════════════════════════════════════════════

import socket       # Network communication — connects us to the server
                    # Same library as in client.py

import threading    # Lets the receive loop run in the background
                    # while the main thread handles the GUI

import sys          # sys.argv for command-line arguments, sys.exit() to stop on errors

import datetime     # Used to generate timestamps on outgoing messages

import tkinter as tk
# Tkinter = Python's built-in Graphical User Interface library.
# Lets us create real windows with buttons, text boxes, labels, etc.
# Imported as "tk" for shorter syntax: tk.Button, tk.Label, etc.

from tkinter import scrolledtext
# ScrolledText = a text area widget that includes a scrollbar automatically.
# Perfect for a chat window where messages accumulate and you scroll up to read them.

from tkinter import font as tkfont
# Lets us create Font objects with specific: family (typeface), size, weight (bold/normal).

from tkinter import simpledialog
# simpledialog.askstring() shows a small popup box asking the user to type something.
# We use this to ask for the user's display name before opening the main chat window.


# ══════════════════════════════════════════════════════════════
# SECTION 2: COLOR PALETTE
# Same dark navy + orange theme as server_gui.py for visual consistency.
# ══════════════════════════════════════════════════════════════

# All colors defined in one place — easy to update the whole theme in one edit.
# Hex color format: "#RRGGBB" where RR=red, GG=green, BB=blue (00=none, ff=maximum)
COLORS = {
    # ── Background colors ──
    "bg_dark":        "#0d1117",  # Very dark navy — main window background
    "bg_medium":      "#161b22",  # Slightly lighter — header and input bar background
    "bg_light":       "#21262d",  # Lighter still — text input box background

    # ── Message colors ──
    "bg_bubble_self": "#e8600a",  # Dark orange — your own message label color
    "bg_bubble_other":"#1f2937",  # Dark blue-gray — other people's messages

    # ── Orange accent colors ──
    "accent_orange":  "#f97316",  # Bright orange — titles, buttons, your own label
    "accent_dim":     "#c2410c",  # Darker orange — hover states, dividers

    # ── Text colors ──
    "text_primary":   "#f0f6fc",  # Near-white — regular readable text
    "text_secondary": "#8b949e",  # Medium gray — timestamps, status text
    "text_system":    "#f97316",  # Orange — system announcements (join/leave)

    # ── UI detail colors ──
    "border":         "#30363d",  # Dark gray — thin separating lines
    "online_dot":     "#22c55e",  # Green — "connected" status dot
    "disconnected":   "#ef4444",  # Red — "disconnected" status
}

# 8 colors for different users. Assigned based on the sender's name
# so the same person always gets the same color throughout the conversation.
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
# SECTION 3: HELPER FUNCTION
# ══════════════════════════════════════════════════════════════

def get_timestamp():
    """
    Returns the current date and time as a formatted string.

    Example output: [2026-05-06 02:35:10 PM]

    strftime() format codes used:
        %Y = 4-digit year        e.g. 2026
        %m = 2-digit month       e.g. 05
        %d = 2-digit day         e.g. 06
        %I = 12-hour hour        e.g. 02
        %M = minutes             e.g. 35
        %S = seconds             e.g. 10
        %p = AM or PM            e.g. PM

    Returns:
        str: Formatted timestamp like "[2026-05-06 02:35:10 PM]"
    """
    now = datetime.datetime.now()
    return now.strftime("[%Y-%m-%d %I:%M:%S %p]")


# ══════════════════════════════════════════════════════════════
# SECTION 4: THE MAIN CLIENT GUI CLASS
# ══════════════════════════════════════════════════════════════

class ClientGUI:
    """
    This class manages the entire client-side chat window.

    WHAT IS A CLASS?
        A class is a blueprint. ClientGUI(host, port) creates one running instance
        of that blueprint — our actual chat window with all its parts.

    WHAT IS "self"?
        "self" refers to this specific instance. All shared data is stored on self:
            self.root          = the Tkinter main window
            self.host          = the server IP address to connect to
            self.port          = the server port number
            self.username      = the display name chosen at startup
            self.client_socket = the network socket connected to the server
            self.stop_event    = a flag used to tell the receive thread to stop

    THREAD MODEL:
        Main thread     -> runs the Tkinter event loop (keeps the window alive)
        Connect thread  -> connects to the server socket (runs _connect in background)
        Receive thread  -> runs _receive_loop() — waits for incoming messages continuously

        Rule: ALL GUI updates (inserting text, changing labels) MUST happen on the main thread.
              The receive thread schedules GUI updates using self.root.after().
    """

    def __init__(self, host, port):
        """
        The constructor — runs automatically when we create a ClientGUI object.

        Steps in order:
            1. Save host and port
            2. Create a threading Event to signal threads to stop
            3. Create the Tkinter window
            4. Ask the user for their display name (popup dialog)
            5. Build all visual widgets (header, chat area, input bar)
            6. Start connecting to the server in a background thread
            7. Start the Tkinter main loop (keeps window open)

        Parameters:
            host (str): IP address of the server.
                        "127.0.0.1" = same machine (localhost)
                        "192.168.x.x" = server on another device on the same WiFi
            port (int): TCP port number the server is listening on
        """
        self.host = host
        self.port = port
        self.client_socket = None   # Will be set once connected

        # threading.Event() is a thread-safe flag with two states: set or not set.
        # stop_event.set()     = signal "please stop"
        # stop_event.is_set()  = check if we should stop
        # We use this to tell the receive thread to exit cleanly when the user closes the window.
        self.stop_event = threading.Event()

        # ── Create the main Tkinter window ─────────────────────────────────────
        self.root = tk.Tk()
        self.root.title(f"IS436 Chat Client — {host}:{port}")
        self.root.geometry("800x620")       # Initial window size: 800 x 620 pixels
        self.root.minsize(600, 450)         # Minimum resize limit
        self.root.configure(bg=COLORS["bg_dark"])

        # When the user clicks the X to close the window, call our on_close() method
        # instead of immediately terminating. This lets us disconnect from the server first.
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ── Ask for a display name ─────────────────────────────────────────────
        # simpledialog.askstring() shows a small popup dialog with a text input.
        # The user types their name and clicks OK. If they cancel or leave it blank,
        # we default to "Anonymous".
        # parent=self.root ensures the popup appears centered over our main window.
        raw_name = simpledialog.askstring(
            "Display Name",                 # Title bar text of the popup
            "Enter your display name:",     # The prompt text shown in the popup
            parent=self.root                # Center popup over the main window
        )
        # Use the name if provided, otherwise fall back to "Anonymous"
        self.username = raw_name.strip() if raw_name and raw_name.strip() else "Anonymous"

        # Update the window title bar to include the chosen username
        self.root.title(f"IS436 Chat — {self.username} @ {host}:{port}")

        # ── Build the visual layout ────────────────────────────────────────────
        self._build_ui()

        # ── Connect to the server in a background thread ───────────────────────
        # We connect in a background thread so the window doesn't freeze
        # while we wait for the connection to establish.
        # daemon=True = auto-kill this thread when the window closes
        connect_thread = threading.Thread(target=self._connect, daemon=True)
        connect_thread.start()

        # ── Start the Tkinter event loop ───────────────────────────────────────
        # mainloop() keeps the window open and responsive.
        # It processes user events (clicks, key presses) and redraws the window.
        # It blocks here until the window is closed.
        self.root.mainloop()

    # ──────────────────────────────────────────────────────────
    # _build_ui: Creates all visual widgets
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        """
        Builds the entire visual layout of the client window.

        TKINTER LAYOUT REMINDER:
            .pack(side=tk.TOP)               -> attach to the top
            .pack(side=tk.BOTTOM)            -> attach to the bottom
            .pack(fill=tk.X)                 -> stretch to fill full width
            .pack(fill=tk.BOTH, expand=True) -> fill all available space

        WINDOW LAYOUT:
            +----------------------------------------------+
            |               HEADER BAR                     |
            +----------------------------------------------+
            |                                              |
            |              CHAT AREA                       |
            |         (scrollable message history)         |
            |                                              |
            +----------------------------------------------+
            |              INPUT BAR                       |
            |  [type your message here...    ] [ SEND ]    |
            +----------------------------------------------+
        """

        # ── FONTS ─────────────────────────────────────────────────────────────
        self.font_header    = tkfont.Font(family="Consolas", size=13, weight="bold")
        self.font_message   = tkfont.Font(family="Consolas", size=11)
        self.font_timestamp = tkfont.Font(family="Consolas", size=9)
        self.font_username  = tkfont.Font(family="Consolas", size=11, weight="bold")
        self.font_input     = tkfont.Font(family="Consolas", size=12)

        # ── HEADER BAR ────────────────────────────────────────────────────────
        # A colored Frame that spans the full width at the top of the window
        header_frame = tk.Frame(
            self.root,
            bg=COLORS["bg_medium"],
            height=55
        )
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)  # Prevent shrinking below height=55

        # A thin 3px orange accent line placed at the absolute top of the window
        # .place(x=0, y=0) = top-left corner, relwidth=1 = full window width
        tk.Frame(self.root, bg=COLORS["accent_orange"], height=3).place(x=0, y=0, relwidth=1)

        # App title on the left side of the header
        tk.Label(
            header_frame,
            text="IS436 CHAT",
            font=self.font_header,
            bg=COLORS["bg_medium"],
            fg=COLORS["accent_orange"],
            padx=20
        ).pack(side=tk.LEFT, pady=12)

        # Show the user's chosen display name
        tk.Label(
            header_frame,
            text=f"You: {self.username}",
            font=tkfont.Font(family="Consolas", size=10),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],
            padx=10
        ).pack(side=tk.LEFT, pady=12)

        # Connection status label on the RIGHT side.
        # Saved as self.status_label so we can update it later:
        #   "CONNECTING..."  -> shown while connecting
        #   "CONNECTED"      -> shown after successful connection (green)
        #   "DISCONNECTED"   -> shown if connection drops (red)
        self.status_label = tk.Label(
            header_frame,
            text="CONNECTING...",
            font=tkfont.Font(family="Consolas", size=10),
            bg=COLORS["bg_medium"],
            fg=COLORS["text_secondary"],
            padx=20
        )
        self.status_label.pack(side=tk.RIGHT, pady=12)

        # ── CHAT AREA ──────────────────────────────────────────────────────────
        # ScrolledText: a multi-line read-only text display with a scrollbar.
        # state=tk.DISABLED = read-only. We unlock it briefly to insert messages.
        self.chat_area = scrolledtext.ScrolledText(
            self.root,
            state=tk.DISABLED,          # Read-only
            wrap=tk.WORD,               # Wrap at word boundaries, not mid-word
            bg=COLORS["bg_dark"],
            fg=COLORS["text_primary"],
            font=self.font_message,
            borderwidth=0,
            highlightthickness=0,
            padx=15,                    # Left/right internal padding
            pady=15,                    # Top/bottom internal padding
            spacing3=8,                 # 8px extra gap after each line/paragraph
        )
        self.chat_area.pack(fill=tk.BOTH, expand=True)

        # ── TEXT TAGS ─────────────────────────────────────────────────────────
        # Tags apply specific styles to specific pieces of inserted text.
        # Think of them as inline CSS classes.

        # Small gray text for timestamps shown next to each message
        self.chat_area.tag_configure("timestamp",
            foreground=COLORS["text_secondary"],
            font=self.font_timestamp)

        # Bold orange label for YOUR OWN messages ("YourName (You)")
        self.chat_area.tag_configure("self_name",
            foreground=COLORS["accent_orange"],
            font=self.font_username)

        # White indented body text for your own messages
        self.chat_area.tag_configure("self_msg",
            foreground=COLORS["text_primary"],
            font=self.font_message,
            lmargin1=20,    # Indent first line 20px from left
            lmargin2=20)    # Keep wrapped lines indented too

        # Bold orange label for messages from the SERVER HOST admin
        self.chat_area.tag_configure("server_name",
            foreground=COLORS["accent_orange"],
            font=self.font_username)

        # White indented body for server host message content
        self.chat_area.tag_configure("server_msg",
            foreground=COLORS["text_primary"],
            font=self.font_message,
            lmargin1=20,
            lmargin2=20)

        # Centered italic orange text for system announcements
        # (join/leave notices, connection status messages)
        self.chat_area.tag_configure("system",
            foreground=COLORS["text_system"],
            font=tkfont.Font(family="Consolas", size=10, slant="italic"),
            justify=tk.CENTER)

        # ── INPUT BAR (bottom) ─────────────────────────────────────────────────
        # Pack order matters when using side=BOTTOM:
        # The LAST item packed ends up at the very bottom.
        # So we pack input_frame first, then the 1px separator.

        input_frame = tk.Frame(
            self.root,
            bg=COLORS["bg_medium"],
            pady=12,
            padx=15
        )
        input_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # 1px gray line separating the chat area from the input bar
        tk.Frame(self.root, bg=COLORS["border"], height=1).pack(fill=tk.X, side=tk.BOTTOM)

        # Single-line text entry box for typing messages
        # state=tk.DISABLED = locked until we successfully connect to the server
        # (so you can not try to send before connecting)
        self.input_box = tk.Entry(
            input_frame,
            font=self.font_input,
            bg=COLORS["bg_light"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent_orange"],  # Blinking cursor color = orange
            relief=tk.FLAT,
            bd=0,
            highlightthickness=2,
            highlightbackground=COLORS["border"],      # Gray outline when not focused
            highlightcolor=COLORS["accent_orange"],    # Orange outline when focused
            state=tk.DISABLED,                         # Locked until connected
        )
        # ipady=10 = 10px internal vertical padding (makes the box taller)
        # padx=(0, 10) = 10px gap between input box and the Send button
        self.input_box.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 10))

        # Pressing Enter in the input box triggers _send_message().
        # lambda event: is needed because .bind() always passes an event object,
        # but _send_message() takes no parameters — the lambda absorbs it.
        self.input_box.bind("<Return>", lambda e: self._send_message())

        # SEND button — disabled until connected, just like the input box
        self.send_btn = tk.Button(
            input_frame,
            text="SEND",
            font=tkfont.Font(family="Consolas", size=11, weight="bold"),
            bg=COLORS["accent_orange"],             # Orange button
            fg=COLORS["bg_dark"],                   # Dark text on orange background
            activebackground=COLORS["accent_dim"],  # Slightly darker when clicked
            activeforeground=COLORS["text_primary"],
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=8,
            cursor="hand2",                         # Pointer cursor on hover
            command=self._send_message,
            state=tk.DISABLED                       # Locked until connected
        )
        self.send_btn.pack(side=tk.RIGHT)

    # ──────────────────────────────────────────────────────────
    # _append_message: Adds a message to the chat window
    # ──────────────────────────────────────────────────────────

    def _append_message(self, sender, message, msg_type="other"):
        """
        Inserts a message into the scrollable chat area with appropriate styling.

        THREADING RULE:
            This method MUST be called from the MAIN thread.
            When called from the receive thread, wrap it like this:
                self.root.after(0, lambda: self._append_message(sender, msg, type))
            self.root.after(0, func) safely schedules func on the main thread.

        HOW EACH MESSAGE IS BUILT:
            We insert multiple pieces of text, each with a different style tag.

            Your own message example:
                1. Insert blank line (spacing between messages)
                2. Insert "  Fitzgerald (You)  " with "self_name" tag (orange bold)
                3. Insert "[2026-05-06 02:35 PM]" with "timestamp" tag (small gray)
                4. Insert "  Hello everyone!" with "self_msg" tag (white indented)

            Other person's message example:
                1. Insert blank line
                2. Insert "  Client #1  " with their color tag
                3. Insert timestamp
                4. Insert message body

        Parameters:
            sender (str):    The display name shown above the message.
                             Examples: "Fitzgerald (You)", "CLIENT #1", "SERVER HOST"
            message (str):   The message content to display.
            msg_type (str):  Controls the visual style:
                               "self"   -> orange label (your own messages)
                               "server" -> orange label (from server admin)
                               "other"  -> uniquely colored label (from other clients)
                               "system" -> centered italic (join/leave/status notices)
        """

        # Temporarily unlock the text widget so we can insert new text.
        # Normally DISABLED (read-only) to prevent the user from editing chat history.
        self.chat_area.configure(state=tk.NORMAL)

        timestamp = get_timestamp()

        if msg_type == "system":
            # System notices: centered italic orange text
            # Example: "Connected to server!" or "Disconnected from server."
            self.chat_area.insert(tk.END, f"\n  {message}\n", "system")

        elif msg_type in ("self", "server"):
            # Your own messages OR messages from the server host
            # Both use the orange label style for visual consistency
            self.chat_area.insert(tk.END, f"\n")                           # Blank spacer
            self.chat_area.insert(tk.END, f"  {sender}  ", "self_name")   # Orange bold label
            self.chat_area.insert(tk.END, f"{timestamp}\n", "timestamp")  # Small gray time
            self.chat_area.insert(tk.END, f"  {message}\n", "self_msg")   # White body text

        else:
            # Messages from other clients in the chat
            # Each sender gets a consistent color based on their name

            # Pick a color by summing the ASCII values of the sender's name characters,
            # then using modulo (%) to pick from our 8 available colors.
            # Example: "Client #1" -> sum of char codes -> index 0-7 -> one of our colors
            # Using the name (not just a counter) means the same person always gets
            # the same color, even across reconnections.
            color_index = sum(ord(c) for c in sender) % len(USERNAME_COLORS)
            color = USERNAME_COLORS[color_index]

            # Create a uniquely named tag for this sender's username color.
            # Tag name example: "user_Client #1"
            # tag_configure() creates the tag if it doesn't exist, or updates it if it does.
            tag_name = f"user_{sender}"
            self.chat_area.tag_configure(tag_name,
                foreground=color,
                font=self.font_username)

            # A separate tag for this sender's message body text
            msg_tag = f"msg_{sender}"
            self.chat_area.tag_configure(msg_tag,
                foreground=COLORS["text_primary"],
                font=self.font_message,
                lmargin1=20,    # Indent message body 20px from the left
                lmargin2=20)    # Keep wrapped lines indented

            self.chat_area.insert(tk.END, f"\n")                           # Blank spacer
            self.chat_area.insert(tk.END, f"  {sender}  ", tag_name)      # Colored username
            self.chat_area.insert(tk.END, f"{timestamp}\n", "timestamp")  # Gray timestamp
            self.chat_area.insert(tk.END, f"  {message}\n", msg_tag)      # White body

        # Scroll to the bottom so the newest message is always visible.
        # see(tk.END) = scroll until the last character in the widget is in view.
        self.chat_area.see(tk.END)

        # Lock the widget again — back to read-only mode
        self.chat_area.configure(state=tk.DISABLED)

    # ──────────────────────────────────────────────────────────
    # _connect: Connects to the server (runs in background thread)
    # ──────────────────────────────────────────────────────────

    def _connect(self):
        """
        Runs in a background thread — creates a socket and connects to the server.

        WHY a background thread?
            socket.connect() can take a moment (especially over a network).
            If we ran this on the main thread, the window would freeze while
            we waited for the connection to establish. A background thread keeps
            the window responsive with a "CONNECTING..." status.

        After a successful connection:
            - Updates the status label to "CONNECTED" (green)
            - Enables the input box and Send button
            - Starts the receive loop to listen for incoming messages

        On failure:
            - Shows an error message in the chat area
            - Updates the status label to "DISCONNECTED" (red)
        """
        try:
            # Create a new TCP socket (same type as on the server side)
            # AF_INET = IPv4 addresses, SOCK_STREAM = TCP protocol
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            # connect() initiates the TCP connection to the server.
            # This BLOCKS until either the connection succeeds or fails.
            # (host, port) = the server's IP address and port number
            self.client_socket.connect((self.host, self.port))

            # ── Connection succeeded! Update the GUI ───────────────────────────
            # We must update GUI widgets on the main thread.
            # self.root.after(0, func) schedules func on the main thread ASAP.

            # Update status label to green "CONNECTED"
            self.root.after(0, lambda: self.status_label.configure(
                text=f"CONNECTED  {self.host}:{self.port}",
                fg=COLORS["online_dot"]     # Green color for connected state
            ))

            # Unlock the input box so the user can start typing
            self.root.after(0, lambda: self.input_box.configure(state=tk.NORMAL))

            # Unlock the Send button
            self.root.after(0, lambda: self.send_btn.configure(state=tk.NORMAL))

            # Move keyboard focus to the input box so the user can type immediately
            self.root.after(0, lambda: self.input_box.focus())

            # ── Start the receive loop ─────────────────────────────────────────
            # _receive_loop() runs right here in this same background thread.
            # It blocks in a recv() loop forever, processing incoming messages.
            self._receive_loop()

        except ConnectionRefusedError:
            # The server is not running, or nothing is listening on that port.
            # "Connection refused" = the server actively rejected our connection attempt.
            self.root.after(0, lambda: self._append_message(
                "", f"Could not connect to {self.host}:{self.port}. Is the server running?",
                msg_type="system"
            ))
            self.root.after(0, lambda: self.status_label.configure(
                text="DISCONNECTED",
                fg=COLORS["disconnected"]   # Red for disconnected state
            ))

        except Exception as e:
            # Any other connection error (network unreachable, timeout, etc.)
            self.root.after(0, lambda err=e: self._append_message(
                "", f"Connection error: {err}", msg_type="system"
            ))

    # ──────────────────────────────────────────────────────────
    # _receive_loop: Listens for incoming messages (runs in background thread)
    # ──────────────────────────────────────────────────────────

    def _receive_loop(self):
        """
        Runs in a background thread — continuously waits for messages from the server
        and passes them to the chat display.

        WHY a separate thread?
            socket.recv() is BLOCKING — it does nothing until data arrives.
            If this ran on the main thread, the window would freeze while waiting.
            In a background thread, it can sit and wait all day without affecting the GUI.

        HOW IT WORKS:
            Loop forever:
                1. Wait (block) for data from the server
                2. If empty bytes returned -> server disconnected -> break loop
                3. Decode bytes to string
                4. Parse and display the message in the chat window
                5. Repeat

        Stops when:
            - stop_event is set (user closed the window and called on_close())
            - Server closes the connection (recv returns empty bytes)
            - A network error occurs
        """
        # Keep looping until told to stop
        while not self.stop_event.is_set():
            try:
                # recv(1024) waits (blocks) for up to 1024 bytes from the server.
                # 1024 bytes = 1 KB — more than enough for any chat message.
                # This call just sits here doing nothing until data arrives.
                raw_data = self.client_socket.recv(1024)

                # recv() returns empty bytes b"" when the server closes the connection
                if not raw_data:
                    # Schedule the GUI update on the main thread
                    self.root.after(0, lambda: self._append_message(
                        "", "Disconnected from server.", msg_type="system"
                    ))
                    self.root.after(0, lambda: self.status_label.configure(
                        text="DISCONNECTED", fg=COLORS["disconnected"]
                    ))
                    break  # Exit the receive loop

                # Decode the received bytes back into a readable string
                # .strip() removes any trailing whitespace or newline characters
                message = raw_data.decode("utf-8").strip()

                # Parse the message and display it appropriately in the GUI
                self._display_incoming(message)

            except OSError:
                # OSError happens when the socket is closed externally
                # (e.g., on_close() called self.client_socket.close())
                # If stop_event is already set, this is expected — we are shutting down
                if not self.stop_event.is_set():
                    self.root.after(0, lambda: self._append_message(
                        "", "Connection lost.", msg_type="system"
                    ))
                break

            except Exception as e:
                # Catch any other network error so the app does not crash
                if not self.stop_event.is_set():
                    self.root.after(0, lambda err=e: self._append_message(
                        "", f"Error: {err}", msg_type="system"
                    ))
                break

    # ──────────────────────────────────────────────────────────
    # _display_incoming: Parses and displays a received message
    # ──────────────────────────────────────────────────────────

    def _display_incoming(self, raw_message):
        """
        Parses a raw message string received from the server and routes it
        to the correct visual style in the chat window.

        WHY do we need to parse?
            The server sends messages as formatted strings like:
                "[2026-05-06 02:35:10 PM] Client #1: Hello!"
                "[2026-05-06 02:35:10 PM] [SERVER HOST]: Hi all"
                "[2026-05-06 02:35:10 PM] [SERVER] Client #1 has joined the chat!"
            We need to identify WHAT KIND of message it is so we can display it
            with the right style (system = centered italic, server = orange label, etc.)

        MESSAGE TYPES WE HANDLE:
            1. "[SERVER]" without "HOST" -> system announcement (join/leave/shutdown)
            2. "[SERVER HOST]:"          -> message from the server admin
            3. "Client #N: ..."          -> message from another client
            4. Welcome message or other  -> displayed as system message

        Parameters:
            raw_message (str): The complete message string received from the server
        """

        # CASE 1: System announcements from the server
        # "[SERVER]" messages are join/leave/shutdown notices — not chat messages
        # We check that "HOST" is NOT in the message to avoid matching "[SERVER HOST]:"
        if "[SERVER]" in raw_message and "HOST" not in raw_message:
            # Strip the timestamp prefix for cleaner display.
            # raw_message example: "[2026-05-06 02:35 PM] [SERVER] Client #1 has joined!"
            # After split on "] ": ["[2026-05-06 02:35 PM", "[SERVER] Client #1 has joined!"]
            parts = raw_message.split("] ", 1)  # Split into at most 2 pieces at the first "] "
            text = parts[-1].replace("[SERVER]", "").strip()  # Remove "[SERVER]" prefix
            self.root.after(0, lambda t=text: self._append_message("", t, msg_type="system"))

        # CASE 2: Message from the server admin (SERVER HOST)
        elif "[SERVER HOST]:" in raw_message:
            # Split on "[SERVER HOST]: " to separate the prefix from the message content
            parts = raw_message.split("[SERVER HOST]: ", 1)
            content = parts[1] if len(parts) > 1 else raw_message
            self.root.after(0, lambda c=content: self._append_message(
                "SERVER HOST", c, msg_type="server"
            ))

        # CASE 3: Regular chat message from another client
        # Format: "[timestamp] Client #N: message content"
        elif ": " in raw_message:
            try:
                # Skip past the timestamp by splitting on "] " (the end of the timestamp)
                # raw_message: "[2026-05-06 02:35 PM] Client #1: Hello!"
                # after_timestamp: "Client #1: Hello!"
                after_timestamp = raw_message.split("] ", 1)[1] if "] " in raw_message else raw_message

                # Split on the first ": " to separate sender name from message content
                # "Client #1: Hello!" -> sender="Client #1", content="Hello!"
                sender, content = after_timestamp.split(": ", 1)
                sender = sender.strip()

                # Default argument values (s=sender, c=content) capture current variable values.
                # Without this, the lambda might use stale values if the loop runs again first.
                self.root.after(0, lambda s=sender, c=content: self._append_message(
                    s, c, msg_type="other"
                ))
            except Exception:
                # If parsing fails for any reason, just show the raw message as a system notice
                self.root.after(0, lambda m=raw_message: self._append_message(
                    "", m, msg_type="system"
                ))

        # CASE 4: Welcome message or anything else we did not specifically handle
        else:
            self.root.after(0, lambda m=raw_message: self._append_message(
                "", m, msg_type="system"
            ))

    # ──────────────────────────────────────────────────────────
    # _send_message: Sends the user's typed message
    # ──────────────────────────────────────────────────────────

    def _send_message(self):
        """
        Called when the user clicks SEND or presses Enter in the input box.

        Steps:
            1. Read the text from the input box (.get())
            2. If empty, do nothing (return early)
            3. Clear the input box (.delete())
            4. Display the message in your OWN chat window immediately
               (no need to wait for the server to echo it back)
            5. Send the message to the server over the socket
               (the server will broadcast it to everyone else)

        NOTE about the message format we send:
            We prefix with "[username] " so the server can show who sent it.
            Example sent bytes: "[Fitzgerald] Hello everyone!"
            The server wraps this in a timestamp and broadcasts:
            "[2026-05-06 02:35:10 PM] Client #1: [Fitzgerald] Hello everyone!"
        """
        # Make sure we have an active connection before trying to send
        if not self.client_socket:
            return

        # Read what the user typed and remove surrounding whitespace
        message_text = self.input_box.get().strip()

        # Do nothing if the input is empty
        if not message_text:
            return

        # Clear the input box after reading so it is ready for the next message
        self.input_box.delete(0, tk.END)

        # Show your own message in the chat window immediately.
        # We display it locally right away — no network round-trip needed for your own messages.
        # "Fitzgerald (You)" tells you which messages are yours when scrolling back
        self._append_message(f"{self.username} (You)", message_text, msg_type="self")

        # Send the message to the server.
        # The server will receive it, format it with a timestamp, and broadcast
        # it to everyone else in the chat room.
        try:
            # Include the username in the message so the server knows who sent it
            full_message = f"[{self.username}] {message_text}"
            # .encode("utf-8") converts the string to bytes for network transmission
            self.client_socket.send(full_message.encode("utf-8"))

        except BrokenPipeError:
            # BrokenPipeError = the server closed the connection while we tried to send
            self._append_message("", "Connection to server was lost.", msg_type="system")
            self.stop_event.set()   # Signal the receive loop to stop too

        except Exception as e:
            # Catch any other send error
            self._append_message("", f"Failed to send: {e}", msg_type="system")
            self.stop_event.set()

    # ──────────────────────────────────────────────────────────
    # on_close: Graceful shutdown when the X button is clicked
    # ──────────────────────────────────────────────────────────

    def on_close(self):
        """
        Called automatically when the user clicks the X to close the window.

        WHY handle this manually?
            Without this, closing the window would leave the server hanging —
            it would not know the client disconnected, which could cause errors.

            With this handler:
                1. Set the stop_event flag so the receive thread knows to exit
                2. Send "exit" to the server so it can announce our departure
                3. Close the socket cleanly to free the OS network resource
                4. Destroy the Tkinter window and end the program
        """
        # Signal all background threads to stop their loops
        self.stop_event.set()

        # Close the network connection cleanly
        if self.client_socket:
            try:
                # Send "exit" to tell the server we're leaving gracefully.
                # The server will broadcast "Client #N has left the chat." to everyone.
                self.client_socket.send("exit".encode("utf-8"))
                self.client_socket.close()
            except Exception:
                pass  # If the connection is already dead, that is fine

        # Destroy the Tkinter window.
        # This ends mainloop() in __init__ and the program exits.
        self.root.destroy()


# ══════════════════════════════════════════════════════════════
# SECTION 5: ENTRY POINT
# This block only runs when you execute this file directly.
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    sys.argv is a list of everything on the command line.

    Examples:
        python src/client_gui.py 5000
            sys.argv = ["src/client_gui.py", "5000"]
            -> connect to localhost (127.0.0.1) port 5000

        python src/client_gui.py 192.168.1.45 5000
            sys.argv = ["src/client_gui.py", "192.168.1.45", "5000"]
            -> connect to 192.168.1.45 port 5000 (different device on same WiFi)
    """

    if len(sys.argv) == 2:
        # Only port provided -> connect to the same machine (localhost)
        # "127.0.0.1" is the loopback address — always means "this computer"
        server_host = "127.0.0.1"
        port_arg = sys.argv[1]

    elif len(sys.argv) == 3:
        # IP address AND port provided -> connect to a different device
        server_host = sys.argv[1]
        port_arg = sys.argv[2]

    else:
        # Wrong number of arguments — show usage instructions
        print("Usage:")
        print("  Same machine:      python src/client_gui.py <port>")
        print("  Different device:  python src/client_gui.py <server-ip> <port>")
        print("Examples:")
        print("  python src/client_gui.py 5000")
        print("  python src/client_gui.py 192.168.1.45 5000")
        sys.exit(1)

    # Try converting the port argument from string to integer
    # int("5000") = 5000   int("abc") raises ValueError
    try:
        port_number = int(port_arg)
    except ValueError:
        print(f"Error: '{port_arg}' is not a valid port number. Please enter an integer.")
        sys.exit(1)

    # Validate the port is in the allowed range (project requirement: 1025-65535)
    # Ports 0-1024 are reserved for system services and require admin privileges
    if not (1025 <= port_number <= 65535):
        print(f"Error: Port must be between 1025 and 65535.")
        sys.exit(1)

    # All validation passed — create the ClientGUI object.
    # This triggers __init__ which:
    #   1. Creates the window
    #   2. Shows the name dialog
    #   3. Builds the layout
    #   4. Connects to the server in a background thread
    #   5. Calls mainloop() which blocks until the window is closed
    ClientGUI(server_host, port_number)