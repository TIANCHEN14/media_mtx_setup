# Local MediaMTX Video Gateway Operations

For a complete FFmpeg walkthrough, see [Adding an SRT Stream to the Local MediaMTX Broker](ADDING_SRT_STREAM.md).

For recording retention and object-storage archiving, see [Archiving MediaMTX Recordings to S3-Compatible Storage](S3_RECORDING_ARCHIVE.md).

## A. How to interface with MediaMTX

MediaMTX has separate interfaces for media and administration. Replace `PI_IP` with the Raspberry Pi's LAN address.

| Interface | Address | Purpose |
|---|---|---|
| Gateway UI | `http://PI_IP:8000/` | Select and view registered streams |
| Gateway OpenAPI | `http://PI_IP:8000/docs` | Try gateway calls in a browser |
| Gateway stream API | `http://PI_IP:8000/streams` | Discover streams and playback URLs |
| HLS | `http://PI_IP:8888/camera01/index.m3u8` | Compatible HTTP playback |
| HLS player | `http://PI_IP:8888/camera01` | MediaMTX browser player |
| WebRTC player | `http://PI_IP:8889/camera01` | Low-latency browser playback |
| WHEP | `http://PI_IP:8889/camera01/whep` | WebRTC client integration |
| RTSP | `rtsp://PI_IP:8554/camera01` | VLC, FFmpeg, or another media server |
| Control API | `http://127.0.0.1:9997/v3/paths/list` | Private path and connection status |
| Metrics | `http://127.0.0.1:9998/metrics` | Private Prometheus metrics |

This source uses a 500 ms LL-HLS part duration. Its audio packet timing caused MediaMTX to vary the 200 ms default, which can break playback on Apple clients; the larger fixed value trades a small amount of latency for stable segments.

Common gateway calls:

```bash
curl http://PI_IP:8000/streams
curl http://PI_IP:8000/streams/camera01
curl http://PI_IP:8000/streams/camera01/playback
curl http://PI_IP:8000/streams/camera01/health
```

Use `http://PI_IP:8000/docs` to inspect and execute the OpenAPI contract. The same endpoints are also available under `/api`, for example `/api/streams`.

MediaMTX's Control API is intentionally bound to `127.0.0.1`. Run this on the Pi when diagnosing the broker:

```bash
curl http://127.0.0.1:9997/v3/paths/list
curl http://127.0.0.1:9998/metrics
```

View service logs:

```bash
journalctl --user -u mediamtx-local -f
journalctl --user -u video-gateway -f
```

## B. Setup process from zero to finished

### 1. Prepare the Pi

Use a 64-bit Raspberry Pi OS installation. Confirm that the Pi can reach the RTSP server:

```bash
ip route get 10.20.20.1
./scripts/check-source.sh
```

The configured source currently provides 1280x720 H.264 at 30 fps with AAC and Opus audio. MediaMTX can route this without video transcoding.

### 2. Bootstrap the repository

From this repository:

```bash
./scripts/bootstrap.sh
```

The script downloads pinned MediaMTX `1.21.0` for the current CPU architecture, verifies its SHA-256 checksum, creates `.venv`, and installs the gateway dependencies.

Put the upstream RTSP address in the generated private configuration:

```bash
nano config/local.env
```

Use this format:

```bash
RTSP_SOURCE_URL='rtsp://user:password@camera-host:554/path'
```

`config/local.env` is excluded from Git. The launch script passes it to MediaMTX as a configuration override, keeping credentials and stream tokens out of repository history.

### 3. Install and start services

```bash
./scripts/install-user-services.sh
```

The script installs two user-level systemd services. User lingering must be enabled for services to start at boot without an interactive login:

```bash
loginctl show-user "$USER" -p Linger
sudo loginctl enable-linger "$USER"
```

Check them:

```bash
systemctl --user status mediamtx-local video-gateway
./scripts/smoke-test.sh
```

### 4. Open the application

Find the Pi address:

```bash
hostname -I
```

From another LAN machine, open `http://PI_IP:8000`. Select WebRTC for low latency or HLS for compatibility.

### 5. Change configuration

Edit `config/mediamtx.yml` for media sources and `config/streams.json` for application metadata. Apply changes with:

```bash
systemctl --user restart mediamtx-local video-gateway
```

### 6. Validate completion

The setup is finished when:

1. `systemctl --user` reports both services active.
2. `/healthz` reports that MediaMTX is reachable.
3. `/streams/camera01/health` reports `online`.
4. HLS returns an M3U8 playlist.
5. WebRTC plays from another device on the LAN.

## C. Integrating new RTSP, SRT, and WebRTC sources

Every source needs two entries:

1. A MediaMTX path in `config/mediamtx.yml`.
2. Matching metadata in `config/streams.json`.

The `stream_id` and `mediamtx_path` should normally match the MediaMTX path name.

### RTSP pull source

Use this when MediaMTX initiates a connection to a camera or RTSP server:

```yaml
paths:
  shop_camera:
    source: rtsp://user:password@10.20.20.2:554/live
    rtspTransport: tcp
    sourceOnDemand: false
```

URL-encode special characters in usernames and passwords. Prefer TCP initially because it avoids RTP/RTCP firewall and packet-ordering problems. Set `sourceOnDemand: true` when the source should be opened only while someone is watching.

### RTSP publisher

Let an encoder push into a path:

```yaml
paths:
  encoder_rtsp:
    source: publisher
```

Publish with FFmpeg:

```bash
ffmpeg -re -i input.mp4 -c copy -f rtsp rtsp://PI_IP:8554/encoder_rtsp
```

### SRT publisher

First enable SRT globally:

```yaml
srt: true
srtAddress: :8890

paths:
  encoder_srt:
    source: publisher
```

Publish an MPEG-TS stream:

```bash
ffmpeg -re -i input.mp4 -c copy -f mpegts \
  "srt://PI_IP:8890?streamid=publish:encoder_srt&pkt_size=1316"
```

Allow UDP port `8890` through any Pi firewall. An SRT caller publishes to MediaMTX; MediaMTX does not need an individual upstream URL for this mode.

### WebRTC/WHIP publisher

Create a publisher path:

```yaml
paths:
  encoder_webrtc:
    source: publisher
```

Publish from a WHIP-compatible client to:

```text
http://PI_IP:8889/encoder_webrtc/whip
```

For example, an FFmpeg build with WHIP support can use:

```bash
ffmpeg -re -i input.mp4 -c:v libx264 -c:a libopus \
  -f whip http://PI_IP:8889/encoder_webrtc/whip
```

WebRTC clients use TCP `8889` for signaling and UDP `8189` for ICE media. H.264 video and Opus audio are the safest publishing combination.

### Add the registry entry

Append an object to `config/streams.json`:

```json
{
  "stream_id": "shop_camera",
  "display_name": "Shop Camera",
  "event_id": "local-test",
  "source_type": "rtsp",
  "mediamtx_path": "shop_camera",
  "primary_protocol": "webrtc",
  "fallback_protocol": "hls",
  "latency_target_ms": 1000
}
```

Keep the JSON array valid and restart both services. The upstream source address does not belong in this public registry.

## D. Using the system from another machine on the LAN

### 1. Find and verify the Pi address

On the Pi:

```bash
hostname -I
```

On the other machine:

```bash
ping PI_IP
curl http://PI_IP:8000/healthz
curl http://PI_IP:8000/streams
```

### 2. Browser access

Open:

```text
http://PI_IP:8000
```

The gateway automatically constructs playback URLs with the hostname or address used to reach it. If clients reach the Pi through a different stable hostname, set `PUBLIC_HOST` in the gateway service environment and restart it.

### 3. VLC and FFmpeg access

Open this network URL in VLC:

```text
rtsp://PI_IP:8554/camera01
```

Or inspect it remotely:

```bash
ffprobe -rtsp_transport tcp rtsp://PI_IP:8554/camera01
```

### 4. Required LAN ports

| Port | Protocol | Needed for |
|---:|---|---|
| 8000 | TCP | Gateway API, UI, and OpenAPI docs |
| 8888 | TCP | HLS playback |
| 8889 | TCP | WebRTC signaling and built-in player |
| 8189 | UDP | WebRTC media |
| 8554 | TCP | Optional RTSP playback and publishing |
| 8890 | UDP | SRT publishing, only when enabled |

Do not expose `9997` or `9998`; these are local administrative interfaces. If a host firewall is enabled, allow only the needed ports from the local subnet.

### Troubleshooting order

1. Run `./scripts/check-source.sh` on the Pi.
2. Check `systemctl --user status mediamtx-local`.
3. Check `curl http://127.0.0.1:9997/v3/paths/list`.
4. Test `http://PI_IP:8888/camera01` before WebRTC.
5. Check that UDP `8189` is allowed if HLS works but WebRTC does not.
6. Verify that playback URLs returned by `/streams` contain a LAN-reachable Pi address.
