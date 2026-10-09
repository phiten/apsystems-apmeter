# Changelog

## 0.2.0

### Added
- Fast power values over the meter's local TCP port 3333 (the channel the EZHI uses for "Local Control"). Total power and L1-L3 are read about every second (default 1 s, minimum 0.5 s) over one persistent connection.
- Hybrid operation: the existing power sensors (`Power`, `Power L1`-`L3`) use the port-3333 values while a valid frame is less than 10 s old and fall back to HTTP otherwise. A `source` attribute shows `tcp` or `http`. Entity IDs are unchanged.
- Invalid frames (wrong length, checksum or meter ID) are dropped and counted; the connection is rebuilt with a 1-30 s backoff.
- Config flow and new options: fast power on/off (default on), port (3333) and interval. Saving reads one frame and checks the meter ID against the device; on failure a clear message is shown and HTTP-only operation stays possible.
- Options flow for the HTTP poll interval and the port-3333 settings.
- Zeroconf discovery (`_http._tcp.local.`, `company=apsystems`) suggests the meter's IP and updates it if it changes.
- pytest suite for the protocol module with a fake meter on 127.0.0.1.

### Changed
- While port 3333 delivers values, HTTP is polled at least every 15 s instead of the configured interval. Voltage, current, power factor and energy still come from HTTP.

### Security
- Port 3333 is unencrypted and has no login. It is meant for the local network only; Home Assistant and the meter must reach each other on TCP 3333.
