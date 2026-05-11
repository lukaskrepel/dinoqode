Dinoqode Project — Summary

### What the project does
A Raspberry Pi reads QR codes via camera, translates them into Sonos commands using `node-sonos-http-api` (port 5005). `qrgen.py` generates printable cards with QR codes and artwork; `qrplay.py` runs on the Pi and handles the scanned codes.

Changes made to the local project (`/Users/lukas/GitHub/dinoqode`)

**`qrgen.py`**
- Added `--sonos-hostname` flag to auto-fetch playlist/favorite artwork from the Sonos HTTP API at generation time. Use: `python3 qrgen.py --input lukas_albums.txt --sonos-hostname raspberrypi.local`
- `get_sonos_artwork()` tries all matching entries by name and skips expired/unreachable URLs (Apple Music signed URLs expire in 24h; Spotify CDN URLs are stable)
- Removed "von" and "Album" label prefixes from card HTML
- Removed music service logos (applemusic, spotify, etc.) from card HTML and output directory
- All German strings translated to English

**`qrplay.py`**
- Removed auto-pause on startup — previously caused music to stop every time the service restarted
- Switched from calling `zbarcam` binary directly to launching `zbarcam_wrapper.py`
- All German strings translated to English (spoken phrases, default room name)

**`zbarcam_wrapper.py`** *(new file, synced from Pi)*
- Replaces the old `zbarcam` binary with `picamera2` + `pyzbar` + `cv2`
- Wrapped in a retry loop — camera crashes now self-recover without killing `qrplay.py`

**`lukas_albums.txt`**
- Uncommented all entries
- Fixed `playlist:Ontbijt` → `favorite:Ontbijt` (it lives under Sonos favorites, not playlists)
- Fixed artwork URL for Kinderen Voor Kinderen album (was stale)
- Fixed broken `png.icons8.com` URL for Keuken room command
- Added iTunes lookup tip in comment: `https://itunes.apple.com/lookup?id=ALBUM_ID`

**`basic_commands.txt`** and **`example.txt`**
- All German card labels translated to English

**`dinoqode.service`** *(new file)*
- Tracks the Pi's systemd service config for version control

---

### Pi (`raspberrypi.local`, user `lukas`, `/home/lukas/Developer/dinoqode`)

- `dinoqode.service` and `node-sonos-http-api.service` are both enabled and start on boot automatically
- Updated `dinoqode.service` with `Restart=always` and `StartLimitIntervalSec=0` — the service now restarts indefinitely after crashes instead of giving up after 5 attempts
- Deployed updated `qrplay.py` and `zbarcam_wrapper.py` to the Pi

---

### Known Sonos rooms
`Keuken` (default), `Slaapkamer`, `Woonkamer` — all visible to node-sonos-http-api.

### Generating cards
```/dev/null/example.sh#L1-1
python3 qrgen.py --input lukas_albums.txt --sonos-hostname raspberrypi.local
```
Output goes to `out/index.html`. Open in browser and hold cards up to the Pi camera.
Changes made to the local project (`/Users/lukas/GitHub/dinoqode`)

**`qrgen.py`**
- Added `--sonos-hostname` flag to auto-fetch playlist/favorite artwork from the Sonos HTTP API at generation time. Use: `python3 qrgen.py --input lukas_albums.txt --sonos-hostname raspberrypi.local`
- `get_sonos_artwork()` tries all matching entries by name and skips expired/unreachable URLs (Apple Music signed URLs expire in 24h; Spotify CDN URLs are stable)
- Removed "von" and "Album" label prefixes from card HTML
- Removed music service logos (applemusic, spotify, etc.) from card HTML and output directory
- All German strings translated to English

**`qrplay.py`**
- Removed auto-pause on startup — previously caused music to stop every time the service restarted
- Switched from calling `zbarcam` binary directly to launching `zbarcam_wrapper.py`
- All German strings translated to English (spoken phrases, default room name)

**`zbarcam_wrapper.py`** *(new file, synced from Pi)*
- Replaces the old `zbarcam` binary with `picamera2` + `pyzbar` + `cv2`
- Wrapped in a retry loop — camera crashes now self-recover without killing `qrplay.py`

**`lukas_albums.txt`**
- Uncommented all entries
- Fixed `playlist:Ontbijt` → `favorite:Ontbijt` (it lives under Sonos favorites, not playlists)
- Fixed artwork URL for Kinderen Voor Kinderen album (was stale)
- Fixed broken `png.icons8.com` URL for Keuken room command
- Added iTunes lookup tip in comment: `https://itunes.apple.com/lookup?id=ALBUM_ID`

**`basic_commands.txt`** and **`example.txt`**
- All German card labels translated to English

**`dinoqode.service`** *(new file)*
- Tracks the Pi's systemd service config for version control

---

### Pi (`raspberrypi.local`, user `lukas`, `/home/lukas/Developer/dinoqode`)

- `dinoqode.service` and `node-sonos-http-api.service` are both enabled and start on boot automatically
- Updated `dinoqode.service` with `Restart=always` and `StartLimitIntervalSec=0` — the service now restarts indefinitely after crashes instead of giving up after 5 attempts
- Deployed updated `qrplay.py` and `zbarcam_wrapper.py` to the Pi

---

### Known Sonos rooms
`Keuken` (default), `Slaapkamer`, `Woonkamer` — all visible to node-sonos-http-api.

### Generating cards
```/dev/null/example.sh#L1-1
python3 qrgen.py --input lukas_albums.txt --sonos-hostname raspberrypi.local
```
Output goes to `out/index.html`. Open in browser and hold cards up to the Pi camera.
