# Local MediaMTX Video Gateway

This repository runs a small livestream lab on a Raspberry Pi:

- MediaMTX pulls an existing RTSP feed and makes it available as HLS, WebRTC, and RTSP.
- A FastAPI gateway provides stream discovery, playback URLs, and health status.
- A browser page at the gateway root provides a simple player and status view.

The configured source is exposed by MediaMTX as `camera01`. The upstream RTSP URL remains inside the server configuration and is never returned by the API.

## Quick start

```bash
./scripts/bootstrap.sh
./scripts/install-user-services.sh
./scripts/smoke-test.sh
```

Open `http://PI_LAN_IP:8000` from another machine on the same network. Find the Pi address with:

```bash
hostname -I
```

Useful commands:

```bash
systemctl --user status mediamtx-local video-gateway
journalctl --user -u mediamtx-local -f
journalctl --user -u video-gateway -f
curl http://127.0.0.1:8000/streams
curl http://127.0.0.1:8000/streams/camera01/health
```

Detailed operating and integration instructions are in [`docs/OPERATIONS.md`](docs/OPERATIONS.md).
