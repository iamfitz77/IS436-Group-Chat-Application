"""
client.py - Chat Application Client
=====================================
IS 436 Group Project - Basic Chat Application
Team: Fitzgerald Afari-Minta, Noel, KJ, Brandon, Shamar

HOW TO RUN:
    python client.py <port>
    Example: python client.py 5000
    (The server must already be running on the same port)

WHAT THIS FILE DOES:
    This is the "caller" side of the chat. It connects to the server,
    then lets you send and receive messages simultaneously.

    The tricky part: while you're typing a message, the server might send
    you one at the same time. We handle this using TWO threads:
        Thread 1 (receive_messages): constantly listens for incoming messages
        Thread 2 (main thread):      reads your keyboard input and sends it

NOTE: This file uses ONLY Python built-in libraries (no pip installs needed).
      AI assistance (Claude) was used in writing this code — disclosed per
      academic integrity requirements.
"""

# ─────────────────────────────────────────────
# IMPORTS — built-in Python libraries only
# ─────────────────────────────────────────────

import socket       # Network communication — connects us to the server
import threading    # Lets the receive loop run in the background while we type
import sys          # Access to command-line arguments and sys.exit()
import datetime     # For generating timestamps on outgoing messages


# ─────────────────────────────────────────────
# GLOBAL FLAG — used to signal threads to stop
# ─────────────────────────────────────────────

# This flag acts as a shared "stop sign" between threads.
# When it's True, the receive thread knows to exit its loop.
# We use a threading.Event instead of a plain boolean because
# Event is thread-safe (safe to read/write from multiple threads).
stop_event = threading.Event()


# ─────────────────────────────────────────────
# HELPER FUNCTION: get_timestamp
# ─────────────────────────────────────────────

def get_timestamp():
    """
    Returns the current time as a formatted string like "[14:05:32]".

    Bonus feature: Timestamps — every message shows when it was sent.

    Returns:
        str: Current time formatted as [HH:MM:SS]
    """
    now = datetime.datetime.now()
    return now.strftime("[%H:%M:%S]")


# ─────────────────────────────────────────────
# CORE FUNCTION: receive_messages
# ─────────────────────────────────────────────

def receive_messages(client_socket):
    """
    Runs in a background THREAD — constantly listens for messages from the server.

    This needs to be in its own thread because recv() is a BLOCKING call —
    it just waits and does nothing until data arrives. If we ran this on the
    main thread, we'd be stuck waiting and could never type anything.

    By putting it in a background thread:
        - Main thread: reads your keyboard input
        - This thread: waits for incoming messages at the same time

    Parameters:
        client_socket (socket): The connected socket to the server
    """
    while not stop_event.is_set():  # Keep looping until told to stop
        try:
            # Wait for data to arrive from the server (up to 1024 bytes at once)
            raw_data = client_socket.recv(1024)

            # If we receive empty bytes, the server has closed the connection
            if not raw_data:
                print("\n[CLIENT] Server closed the connection.")
                stop_event.set()  # Signal the main thread to stop too
                break

            # Decode the bytes into a readable string and display it
            message = raw_data.decode("utf-8")
            # \r clears the current input line so the received message appears cleanly
            # (avoids the message appearing mid-way through your typed input)
            print(f"\r{message}")
            print("You: ", end="", flush=True)  # Re-print the input prompt

        except OSError:
            # This happens when the socket is closed while recv() is waiting
            # (e.g., when we call client_socket.close() from the main thread)
            if not stop_event.is_set():
                print("\n[CLIENT] Disconnected from server.")
            break

        except Exception as e:
            if not stop_event.is_set():
                print(f"\n[CLIENT] Error receiving message: {e}")
            break


# ─────────────────────────────────────────────
# CORE FUNCTION: start_client
# ─────────────────────────────────────────────

def start_client(port):
    """
    Connects to the chat server and starts the send/receive loop.

    Parameters:
        port (int): The TCP port number the server is listening on
    """

    # ── Create a client socket ─────────────────────────────────────────────────
    # Same socket type as the server:
    # AF_INET = IPv4,  SOCK_STREAM = TCP
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # ── Connect to the server ──────────────────────────────────────────────────
    # "127.0.0.1" is the "loopback" address — it always means "this same machine".
    # If the server is on a different computer, you'd use its IP address instead.
    # We're using localhost for testing (both server and client on same machine).
    server_address = ("127.0.0.1", port)

    try:
        print(f"[CLIENT] Connecting to server at {server_address[0]}:{server_address[1]}...")
        client_socket.connect(server_address)
        print(f"[CLIENT] Connected!\n")

    except ConnectionRefusedError:
        # The server isn't running, or nothing is listening on that port
        print(f"[CLIENT] Could not connect to server on port {port}.")
        print(f"         Make sure the server is running first:  python server.py {port}")
        sys.exit(1)

    except Exception as e:
        print(f"[CLIENT] Connection error: {e}")
        sys.exit(1)

    # ── Start the background receive thread ───────────────────────────────────
    # This thread will run receive_messages() continuously in the background.
    # daemon=True means it will automatically close when the main program exits.
    receive_thread = threading.Thread(
        target=receive_messages,
        args=(client_socket,),
        daemon=True
    )
    receive_thread.start()

    # ── Main send loop (runs on the main thread) ───────────────────────────────
    # This loop reads your keyboard input and sends it to the server.
    try:
        while not stop_event.is_set():
            # input() waits for the user to type something and press Enter
            # "You: " is just a visual prompt so you know where to type
            user_input = input("You: ")

            # Ignore empty messages (user just pressed Enter without typing)
            if not user_input.strip():
                continue

            # Check if the user wants to exit
            if user_input.strip().lower() == "exit":
                print("[CLIENT] Disconnecting... Goodbye!")
                try:
                    # Send "exit" to the server so it knows we're leaving gracefully
                    client_socket.send("exit".encode("utf-8"))
                except Exception:
                    pass  # Server might already be gone — that's fine
                stop_event.set()  # Tell the receive thread to stop
                break

            # Send the message to the server
            # encode("utf-8") converts the string to bytes for network transmission
            try:
                client_socket.send(user_input.encode("utf-8"))
            except BrokenPipeError:
                # The server closed the connection while we were about to send
                print("\n[CLIENT] Lost connection to server.")
                stop_event.set()
                break
            except Exception as e:
                print(f"\n[CLIENT] Failed to send message: {e}")
                stop_event.set()
                break

    except KeyboardInterrupt:
        # User pressed Ctrl+C — disconnect gracefully
        print("\n[CLIENT] Interrupted. Disconnecting...")
        try:
            client_socket.send("exit".encode("utf-8"))
        except Exception:
            pass
        stop_event.set()

    finally:
        # Always close the socket when we're done, regardless of how we exited
        client_socket.close()
        print("[CLIENT] Connection closed.")


# ─────────────────────────────────────────────
# ENTRY POINT — runs when you execute this file
# ─────────────────────────────────────────────

if __name__ == "__main__":
    """
    sys.argv example:
        Command:   python client.py 5000
        sys.argv:  ["client.py", "5000"]
    """

    # Validate that the user provided exactly one argument (the port number)
    if len(sys.argv) != 2:
        print("Usage: python client.py <port>")
        print("Example: python client.py 5000")
        sys.exit(1)

    # Try converting the argument to an integer
    try:
        port_number = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid port number. Please enter an integer.")
        sys.exit(1)

    # Validate the port is in the allowed range (matching the server's requirement)
    if not (1025 <= port_number <= 65535):
        print(f"Error: Port must be between 1025 and 65535. You entered: {port_number}")
        sys.exit(1)

    # Everything looks good — connect to the server!
    start_client(port_number)
