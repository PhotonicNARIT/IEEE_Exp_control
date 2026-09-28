# Experiment Control: Red Pitaya Multi-Channel Signal Sequencer

A two-part control system for generating timed, multi-channel analog and digital
output sequences on a [Red Pitaya](https://www.redpitaya.com/) board. A desktop GUI
is used to design a sequence of output steps; the sequence is sent over TCP/IP to a
server running on the Red Pitaya, which drives the board's real analog and digital
outputs with precise per-sample timing.

This repository accompanies an IEEE publication describing the system. It contains
the full source for both the desktop application and the board-side server.

## System overview

The software is split into two cooperating programs that communicate over a plain
TCP socket:

- **`WD/` (Windows Desktop client)** — a PySide6 (Qt6) GUI application. The user
  defines a sequence of steps: for each analog output channel, a waveform shape
  (constant, linear ramp up, linear ramp down) with amplitude and offset; for each
  digital pin, a logic level (high/low). Pressing **Run** packages the full sequence
  as JSON and sends it to the board.
- **`RP/` (Red Pitaya server)** — a TCP server intended to run directly on the Red
  Pitaya board. It receives a sequence, validates it, and executes it sample-by-
  sample on the board's real analog and digital outputs in a background thread, so
  the server keeps responding to `stop`/`ping` requests while a sequence is running.
- **`Qt_Designer/`** — the Qt Designer `.ui` source files that the GUI's generated
  code (`WD_GUI.py`, `WD_Setup.py`) is compiled from. You only need these if you want
  to modify the GUI layout itself.

### Communication protocol

Client and server exchange length-prefixed JSON messages over TCP:

```
[4 bytes: payload length, big-endian unsigned int]
[payload: UTF-8 JSON]
```

Supported commands (sent by the client as `{"cmd": "..."}`): `connect`,
`disconnect`, `poweroff`, `run`, `stop`, `ping`. The server responds to `ping` with
`pong`, which the client also uses to detect when a running sequence has finished.

By default the server listens on **port 5000** on all network interfaces.

### Repository structure

```
Qt_Designer/
  Main_GUI.ui                  Main window layout (Qt Designer source)
  Edit_signal_profile_GUI.ui   Per-step signal editor dialog layout
RP/
  RP_TCP_Server.py             Entry point: opens the TCP server on the board
  RP_Command_handler.py        Dispatches incoming commands to the control layer
  RP_Control_program.py        Run/stop state machine, runs generation on a thread
  RP_Create_signal.py          Builds output waveforms and drives the Red Pitaya pins
WD/
  WD_GUI_main.py                Entry point: application logic and main window
  WD_GUI.py                     Generated UI code for the main window
  WD_Setup.py                   Generated UI code for the signal-profile editor
  WD_TCP_Client.py              TCP socket handling (connect/send/receive framing)
  WD_command_send.py            Builds and sends individual commands to the server
```

## Hardware requirements

- A Red Pitaya board, reachable over TCP/IP from the machine running the GUI.
- The board side uses the official Red Pitaya `rp` Python API, which ships with the
  Red Pitaya OS image — it does not need to be installed separately, but the server
  must be run on the board itself (or another environment where that API is
  available).
- Outputs used: 4 slow analog outputs (`AOUT_0`–`AOUT_3`) and 22 digital GPIO pins,
  split into two banks (`GPIO_n`, `GPIO_p`).
- Any host reachable by hostname or IP address works; Red Pitaya boards typically
  advertise themselves as `rp-xxxxxx.local` via mDNS, where `xxxxxx` is derived from
  the board's MAC address — check your own board for its exact address.

## Software requirements

- Python 3 on the machine running the GUI (the `WD/` side).
- Python dependencies for the GUI, listed in `requirements.txt`:

  ```
  pip install -r requirements.txt
  ```

  This installs `PySide6`, `pyqtgraph`, and `numpy`.
- No additional Python packages need to be installed on the Red Pitaya itself; the
  `RP/` scripts only depend on the standard library and the board's built-in `rp`
  API.

## Running it

### 1. Board side (Red Pitaya)

Copy the contents of `RP/` onto the Red Pitaya, then run the server:

```
python RP_TCP_Server.py
```

The server listens on port 5000 and prints connection activity to the console. Note
that the `poweroff` command shuts the board down via the operating system's
`poweroff` command — use it deliberately.

### 2. Desktop side (GUI)

Before running the GUI for the first time, create an `Output` folder next to
`WD_GUI_main.py` — the application writes a session log file there on exit
(`Output/Log_file_<timestamp>.txt`) and will fail to save the log if the folder does
not already exist.

Then, from the `WD/` folder:

```
python WD_GUI_main.py
```

In the GUI, enter the Red Pitaya's hostname or IP address and connect. Once
connected, build a sequence by configuring each analog/digital pin's steps, then
press **Run** to send the sequence to the board. Use **Stop** to halt a running
sequence.

## Citation

If you use this software in your work, please cite:

```
[Authors]. "[Paper title]." [Conference / Journal], [Year]. DOI: [DOI]
```

## License

This project is released under the MIT License. See [LICENSE](LICENSE) for details.
