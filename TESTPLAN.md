# Test Plan: Services, Ping Latency, Device Nicknames/Watched

## 1. HA Services

- [ ] **Developer Tools > Services** — confirm `nwmon.full_scan`, `nwmon.forget_device`, and `nwmon.watch_device` appear with field descriptions
- [ ] Call `nwmon.full_scan` — verify a scan runs and any new devices appear as entities
- [ ] Call `nwmon.forget_device` with a known `device_id` (MAC or IP) — verify the device's entities become unavailable
- [ ] Reload the integration — confirm services still registered; unload all entries — confirm services are removed

## 2. Ping Latency

- [ ] After a scan, check that each device now has a **Ping Latency** sensor (`sensor.nwmon_*_latency`) under its device page showing a value in ms
- [ ] Check the binary sensor attributes — confirm `latency_ms` is present and numeric for online devices
- [ ] Take a device offline (unplug or block) — wait for the offline threshold — confirm the latency sensor goes to **Unknown** and the binary sensor `latency_ms` attribute becomes `None`
- [ ] Bring it back online — confirm latency repopulates on the next check

## 3. Watched Devices

- [ ] Call `nwmon.watch_device` with `device_id` and `watched: true` — verify the binary sensor `watched` attribute is `true`
- [ ] Take that watched device offline — listen in **Developer Tools > Events** for both `nwmon_device_offline` and `nwmon_watched_device_offline` firing
- [ ] Take a non-watched device offline — confirm only `nwmon_device_offline` fires (no watched event)
- [ ] Call `nwmon.watch_device` with `watched: false` — verify the device is no longer watched
- [ ] Restart HA — confirm watched and latency values persist from storage
