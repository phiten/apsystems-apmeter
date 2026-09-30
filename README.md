# APmeter SEM test integration

This repository contains a small Home Assistant custom integration for the APsystems APmeter SEM local API.

It is a test implementation, based on the older APsystems EZ1 codebase, but narrowed down to APmeter-only functionality. It is not a fully maintained production integration and may change without notice.

Tested with:
- APsystems APmeter SEM3-WL-2

## Scope

The integration currently focuses on local polling of the device via the APmeter HTTP API and exposing the measured values as Home Assistant sensors.

Supported behavior:
- local HTTP connection to the meter
- device info polling
- output data polling
- sensor entities for power, voltage, current, imported/exported energy and power factor
- config flow for IP, port and polling interval

Not intended / not implemented:
- inverter control features
- EZ1-specific functionality
- cloud integration
- full long-term maintenance guarantees

## Supported endpoints

The integration calls these endpoints on the meter:
- `http://<ip>:<port>/getDeviceInfo`
- `http://<ip>:<port>/getOutputData`

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

## Notes

- This is an experimental implementation.
- The project is not guaranteed to be actively maintained.
- Monitoring values are exposed as standard Home Assistant sensors and follow the APmeter device semantics.

## License

MIT
