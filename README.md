# APmeter SEM test integration

This repository contains a small Home Assistant custom integration for the APsystems APmeter SEM local API.

It is a test implementation, based on the older APsystems EZ1 codebase, but narrowed down to APmeter-only functionality. It is not a fully maintained production integration and may change without notice.

Tested with:
- APsystems APmeter SEM3-WL-2

## Scope

The integration polls the meter locally and exposes the measured values as Home Assistant sensors. It uses two local channels:

- **HTTP (port 80)** for everything: device info, voltage, current, reactive/apparent power, power factor and energy counters.
- **TCP port 3333 (optional, on by default)** for fast power values: total power and L1-L3 about every second.

Supported behavior:
- local HTTP connection to the meter
- fast power values over the meter's local TCP port 3333
- zeroconf discovery (the meter's IP is suggested automatically)
- device info polling
- output data polling
- sensor entities for power, voltage, current, imported/exported energy and power factor
- config flow and options for IP, port, polling interval and the port-3333 channel

Not intended / not implemented:
- inverter control features
- EZ1-specific functionality
- cloud integration
- full long-term maintenance guarantees

## Supported endpoints

The integration calls these endpoints on the meter:
- `http://<ip>:<port>/getDeviceInfo`
- `http://<ip>:<port>/getOutputData`
- `tcp://<ip>:3333` (fast power values, optional)

## Fast power over port 3333

The meter also runs a small TCP server on port 3333. This is the channel the EZHI inverter uses to read the meter in "Local Control" mode. The integration can read it too:

- One persistent connection; each request is the fixed 4-byte request the EZHI sends, each answer a 44-byte frame with L1-L3 and total power in W (positive = grid import).
- Read-only. Nothing else is ever sent, and requests are never faster than every 0.5 s (default 1 s).
- Frames with a wrong length, a wrong checksum or a different meter ID are dropped and never shown as a value.
- On errors the connection is closed and rebuilt with a backoff from 1 s up to 30 s.

The sensors `Power` and `Power L1`-`L3` use the port-3333 values while a valid frame is less than 10 s old, and the HTTP values otherwise. Their `source` attribute shows which one is in use (`tcp` or `http`). Entity IDs do not change. While port 3333 delivers values, the HTTP poll slows down to at least 15 s; voltage, current, power factor and energy keep coming via HTTP.

When you save the settings, the integration reads one frame from port 3333 and checks that the meter ID matches the device. If that fails you get a message and can switch the option off; HTTP keeps working without it.

**Security:** port 3333 is unencrypted and has no login. Anyone on the network can read the power values from it, as with the HTTP API. It is meant for the local network only: do not forward it to the internet. Home Assistant must be able to reach the meter on TCP port 3333 (check firewalls and VLAN rules).

Tested with one SEM3-WL-2 together with a running EZHI (EZHI plus this integration at 0.5 s did not disturb the control loop). Other firmware versions are untested.

## Home Assistant setup

1. Copy the `custom_components/apsystemsSEM` folder into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to Settings → Devices & services → Add integration.
4. Search for `APmeter SEM` and complete the setup.

## Configuration

The setup flow asks for:
- IP address
- Port (default: 80)
- device name
- polling interval in seconds
- fast power via port 3333 (on/off, default on)
- fast power port (default: 3333)
- fast power interval in seconds (default: 1, minimum 0.5, maximum 5)

Polling interval and the port-3333 settings can be changed later under the integration's options.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

The tests cover the port-3333 protocol module (`sem_tcp.py`) against a fake meter on 127.0.0.1 and need no Home Assistant installation.

## Notes

- This is an experimental implementation.
- The project is not guaranteed to be actively maintained.
- Monitoring values are exposed as standard Home Assistant sensors and follow the APmeter device semantics.

## License

MIT
