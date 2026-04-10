# Requirements - Chat Application

## Functional Requirements
1. The system will allow the server to accept a TCP port number as a command-line argument.
2. The system will validate that the port number is an integer between 1025 and 65535.
3. The system will allow the server to listen for a client connection.
4. The system will allow one client to connect to the server.
5. The system will send a welcome message to the client after connection.
6. The system will allow the client to connect using a TCP port.
7. The system will allow the client to send messages to the server.
8. The system will allow the server to send messages to the client.
9. The system will display received messages.
10. The system will allow graceful exit using "exit".

## Non-Functional Requirements
1. The system must be implemented in Python only.
2. The system must use only built-in Python libraries.
3. The system must support at least one server and one client.
4. The system must validate ports before use.
5. The system must allow graceful shutdown without crashing.
6. The code must be clearly commented.
7. The documentation must explain how to run the programs.
