"""
server.py - Chat Application Server
====================================
IS 436 Group Project - Basic Chat Application
Team: Fitzgerald Afari-Minta, Noel, KJ, Brandon, Shamar

HOW TO RUN:
    python server.py <port>
    Example: python server.py 5000

WHAT THIS FILE DOES:
    This is the "host" of the chat. Think of it like a telephone exchange —
    it sits in the middle, accepts incoming calls (connections), and routes
    messages between everyone.

NOTE: This file uses ONLY Python built-in libraries (no pip installs needed).
      AI assistance (Claude) was used in writing this code — disclosed per
      academic integrity requirements.
"""

# ─────────────────────────────────────────────
# IMPORTS — built-in Python libraries only
# ─────────────────────────────────────────────

import socket       # The core library for network communication (sending/receiving data over a network)
import threading    # Lets us run multiple things at the same time (one thread per connected client)
import sys          # Gives us access to command-line arguments (sys.argv) and sys.exit()
import datetime     # Used to generate timestamps on messages
import os           # Used for file path operations when logging chat to a file


# ─────────────────────────────────────────────
# GLOBAL STATE — shared data across threads
# ─────────────────────────────────────────────

# A list that will hold every connected client.
# Each entry will be a dictionary: { "socket": ..., "id": ..., "address": ... }
# We use a list so we can loop through all clients and broadcast messages to everyone.
connected_clients = []

# A lock is like a "talking stick" — when one thread is modifying `connected_clients`,
# it holds the lock so no other thread accidentally modifies the list at the same time.
# Without this, two threads could try to add/remove a client simultaneously and corrupt the list.
clients_lock = threading.Lock()

# A simple counter to give each client a unique ID number (Client #1, Client #2, etc.)
client_id_counter = 0

# The name of the log file where all chat messages will be saved (bonus: Chat Logging feature)
LOG_FILE = "chat_log.txt"


# ─────────────────────────────────────────────
# HELPER FUNCTION: log_message
# ─────────────────────────────────────────────

def log_message(message):
    """
    Saves a message to the chat log file AND prints it to the server console.

    Why log to a file?
        So the server admin can review what was said even after the program closes.
        This is the "Chat Logging" bonus feature.

    Parameters:
        message (str): The text to log (e.g., "[10:30:01] Client #1: Hello!")
    """
    # Print to the server's terminal window so the admin can see messages live
    print(message)

    # Also write the same message to the log file
    # "a" mode = "append" — adds to the end of the file without deleting old content
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")  # \n adds a newline after each message


# ─────────────────────────────────────────────
# HELPER FUNCTION: get_timestamp
# ─────────────────────────────────────────────

def get_timestamp():
    """
    Returns the current time as a formatted string like "[14:05:32]".

    This is the "Timestamps" bonus feature — every message shows when it was sent.

    Returns:
        str: Current time formatted as [HH:MM:SS]
    """
    now = datetime.datetime.now()          # Get the current date and time
    return now.strftime("[%H:%M:%S]")      # Format it as hours:minutes:seconds


# ─────────────────────────────────────────────
# HELPER FUNCTION: broadcast
# ─────────────────────────────────────────────

def broadcast(message, sender_socket=None):
    """
    Sends a message to EVERY connected client (except optionally the sender).

    This is what makes it a true "chat room" — when one person speaks,
    everyone hears it. This is the "Multiple Clients" bonus feature.

    Parameters:
        message (str):              The text to send to all clients
        sender_socket (socket):     If provided, we skip sending back to the
                                    person who sent it (they already see their own message)
    """
    # Encode the string into bytes. Networks transmit raw bytes, not text strings.
    # UTF-8 encoding handles special characters (accents, emojis, etc.)
    encoded_message = message.encode("utf-8")

    # We need to lock the list before reading it to avoid threading issues
    with clients_lock:
        # Loop through every client currently connected
        for client in connected_clients:
            # Skip the sender (they don't need to receive their own message back)
            if client["socket"] != sender_socket:
                try:
                    # Send the encoded bytes to this client's socket
                    client["socket"].send(encoded_message)
                except Exception:
                    # If sending fails (client disconnected suddenly), just skip them
                    # They'll be cleaned up when their thread notices the connection dropped
                    pass


# ─────────────────────────────────────────────
# CORE FUNCTION: handle_client
# ─────────────────────────────────────────────

def handle_client(client_socket, client_address, client_id):
    """
    This function runs in its own THREAD for each connected client.

    Think of it like a dedicated phone operator for one caller —
    while this function is running for Client #1, another copy of it
    is running simultaneously for Client #2, Client #3, etc.

    Parameters:
        client_socket (socket): The socket object for this specific client connection
        client_address (tuple): The client's (IP address, port number), e.g. ('127.0.0.1', 54321)
        client_id (int):        The unique ID number assigned to this client
    """

    # Build the display name we'll use for this client in all messages
    # e.g. "Client #3"
    client_name = f"Client #{client_id}"

    # Let the server console know someone connected
    log_message(f"{get_timestamp()} [SERVER] {client_name} connected from {client_address}")

    # Send a welcome message directly to this specific client (not broadcast to everyone)
    # This message only goes to the newly connected client
    welcome = (
        f"Welcome to the IS 436 Chat Server, {client_name}!\n"
        f"  - Type a message and press Enter to send.\n"
        f"  - Type 'exit' to disconnect gracefully.\n"
    )
    try:
        client_socket.send(welcome.encode("utf-8"))
    except Exception as e:
        log_message(f"{get_timestamp()} [SERVER] Could not send welcome to {client_name}: {e}")

    # Announce to the whole chat room that someone new joined
    broadcast(f"{get_timestamp()} [SERVER] {client_name} has joined the chat!", sender_socket=None)

    # ── Main message loop for this client ──────────────────────────────────────
    # This loop keeps running, waiting for messages from this client,
    # until they disconnect or type "exit"
    while True:
        try:
            # recv() = "receive" — waits (blocks) until data arrives from the client
            # 1024 = maximum number of bytes to receive at once (1 KB is plenty for a chat message)
            raw_data = client_socket.recv(1024)

            # If recv() returns empty bytes (b""), the client closed the connection abruptly
            if not raw_data:
                log_message(f"{get_timestamp()} [SERVER] {client_name} disconnected (connection lost).")
                break  # Exit the loop — we're done with this client

            # Decode the raw bytes back into a readable Python string
            message_text = raw_data.decode("utf-8").strip()  # .strip() removes leading/trailing whitespace

            # Check if the client typed "exit" to leave gracefully
            if message_text.lower() == "exit":
                log_message(f"{get_timestamp()} [SERVER] {client_name} has left the chat.")
                # Send a goodbye message back to the client before closing
                client_socket.send("You have disconnected. Goodbye!".encode("utf-8"))
                break  # Exit the loop cleanly

            # Format the message with a timestamp and the sender's name
            # e.g. "[14:05:32] Client #2: Hello everyone!"
            formatted = f"{get_timestamp()} {client_name}: {message_text}"

            # Log it to the file and print it on the server console
            log_message(formatted)

            # Broadcast this message to ALL other connected clients
            broadcast(formatted, sender_socket=client_socket)

        except ConnectionResetError:
            # This happens on Windows when a client disconnects without saying goodbye
            log_message(f"{get_timestamp()} [SERVER] {client_name} disconnected unexpectedly.")
            break

        except Exception as e:
            # Catch any other unexpected errors so the server doesn't crash
            log_message(f"{get_timestamp()} [SERVER] Error with {client_name}: {e}")
            break

    # ── Cleanup after client disconnects ───────────────────────────────────────

    # Remove this client from our list of connected clients
    with clients_lock:
        # Filter the list to keep everyone EXCEPT this client
        connected_clients[:] = [c for c in connected_clients if c["socket"] != client_socket]

    # Notify the rest of the chat room
    broadcast(f"{get_timestamp()} [SERVER] {client_name} has left the chat.")

    # Close the socket to free up system resources
    client_socket.close()


# ─────────────────────────────────────────────
# CORE FUNCTION: start_server
# ─────────────────────────────────────────────

def start_server(port):
    """
    Creates the server socket, binds it to a port, and listens for incoming connections.

    This is the "main engine" of the server. It runs forever, accepting new clients
    and spinning up a new thread for each one.

    Parameters:
        port (int): The TCP port number to listen on (validated before this is called)
    """
    global client_id_counter  # We modify the global counter here

    # ── Create the server socket ───────────────────────────────────────────────
    # socket.AF_INET    = use IPv4 addresses (like 192.168.1.1)
    # socket.SOCK_STREAM = use TCP (reliable, ordered delivery — good for chat)
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # SO_REUSEADDR lets us restart the server immediately after closing it.
    # Without this, the OS holds the port "reserved" for ~60 seconds after shutdown,
    # and you'd get "Address already in use" errors.
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # ── Bind the socket to an address and port ─────────────────────────────────
    # ""  means "listen on ALL network interfaces on this machine"
    # port is the number we validated from the command line
    server_socket.bind(("", port))

    # ── Start listening for incoming connections ───────────────────────────────
    # The argument (5) is the "backlog" — how many pending connections to queue
    # before refusing new ones. 5 is a reasonable default.
    server_socket.listen(5)

    print(f"\n{'='*50}")
    print(f"  IS 436 Chat Server started on port {port}")
    print(f"  Chat log will be saved to: {os.path.abspath(LOG_FILE)}")
    print(f"  Waiting for clients to connect...")
    print(f"  Press Ctrl+C to shut down the server.")
    print(f"{'='*50}\n")

    # ── Main accept loop ───────────────────────────────────────────────────────
    # This loop runs forever, waiting for new clients to connect
    try:
        while True:
            # accept() BLOCKS here — the program just waits until a client connects.
            # When a client connects, it returns:
            #   client_socket: a NEW socket object dedicated to that client
            #   client_address: a tuple of (IP, port) for the client
            client_socket, client_address = server_socket.accept()

            # Assign a unique ID to this new client
            client_id_counter += 1
            new_id = client_id_counter

            # Add the new client to our shared list (inside a lock for thread safety)
            with clients_lock:
                connected_clients.append({
                    "socket": client_socket,
                    "id": new_id,
                    "address": client_address
                })

            # Create a new THREAD to handle this client.
            # This means the server can immediately go back to accept() and wait for
            # more clients, while this thread handles Client #N in the background.
            # target = the function to run in this thread
            # args   = the arguments to pass to that function
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, client_address, new_id),
                daemon=True  # daemon=True means the thread auto-closes when the main program exits
            )
            thread.start()  # Kick off the thread — it now runs independently

    except KeyboardInterrupt:
        # Ctrl+C was pressed — shut down gracefully
        print("\n[SERVER] Shutting down server...")

    finally:
        # This block runs whether we exited normally or via Ctrl+C
        # Notify all clients that the server is closing
        broadcast(f"{get_timestamp()} [SERVER] The server is shutting down. Goodbye!")

        # Close all client connections
        with clients_lock:
            for client in connected_clients:
                client["socket"].close()

        # Close the main server socket
        server_socket.close()
        print("[SERVER] Server closed. Goodbye!")


# ─────────────────────────────────────────────
# ENTRY POINT — runs when you execute this file
# ─────────────────────────────────────────────

if __name__ == "__main__":
    """
    sys.argv is a list of command-line arguments.
    When you run:  python server.py 5000
    sys.argv is:   ["server.py", "5000"]
    So sys.argv[0] = "server.py"  (the script name)
       sys.argv[1] = "5000"       (our port argument)
    """

    # Make sure the user provided a port number argument
    if len(sys.argv) != 2:
        print("Usage: python server.py <port>")
        print("Example: python server.py 5000")
        sys.exit(1)  # Exit with error code 1 (non-zero = something went wrong)

    # Try to convert the argument to an integer
    # If the user typed "abc" instead of a number, int() will raise a ValueError
    try:
        port_number = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid integer. Please enter a port number.")
        sys.exit(1)

    # Validate the port range as required by the project spec (1025–65535)
    # Ports 0–1024 are "well-known ports" reserved for system services (HTTP=80, HTTPS=443, etc.)
    if not (1025 <= port_number <= 65535):
        print(f"Error: Port must be between 1025 and 65535. You entered: {port_number}")
        sys.exit(1)

    # All validation passed — start the server!
    start_server(port_number)
