# Adding an SRT Stream to the Local MediaMTX Broker

This guide explains how to send a video file, RTSP feed, or existing SRT stream from another machine to the Raspberry Pi with FFmpeg.

The resulting flow is:

```text
Video file, RTSP camera, or existing SRT stream
                  |
                  | FFmpeg / MPEG-TS over SRT
                  v
        Raspberry Pi UDP port 8890
                  |
                  v
          MediaMTX path remote_srt
             |       |       |
             v       v       v
            HLS   WebRTC    RTSP
```

The Pi currently has these LAN addresses:

```text
10.20.20.193
10.20.22.195
```

Use the address reachable from the sending machine. The examples below use `10.20.20.193`.

## 1. Check FFmpeg on the sending machine

Confirm that FFmpeg includes SRT input and output support:

```bash
ffmpeg -protocols | grep srt
```

You should see `srt` in both protocol sections. Confirm basic routing to the Pi:

```bash
ping 10.20.20.193
```

SRT uses UDP, so ping only verifies basic IP connectivity.

## 2. Enable SRT on the Pi

On the Pi, open `config/mediamtx.yml`:

```bash
cd /home/tchen/Documents/codex_workspace/media_mtx_setup
nano config/mediamtx.yml
```

Change:

```yaml
srt: false
```

to:

```yaml
srt: true
srtAddress: :8890
```

Add a publisher path under `paths`:

```yaml
paths:
  camera01:
    source: publisher
    rtspTransport: tcp
    sourceOnDemand: false

  remote_srt:
    source: publisher
```

The startup script continues to replace the `camera01` source with the private RTSP URL from `config/local.env`. The `remote_srt` path waits for an external publisher.

Validate and apply the configuration:

```bash
./bin/mediamtx --validate-conf=config/mediamtx.yml
systemctl --user restart mediamtx-local
ss -lunp | grep 8890
```

The final command should show MediaMTX listening on UDP port `8890`.

## 3. Register the stream with the gateway

Add an entry to the JSON array in `config/streams.json`:

```json
{
  "stream_id": "remote_srt",
  "display_name": "Remote SRT Feed",
  "event_id": "local-test",
  "source_type": "srt",
  "mediamtx_path": "remote_srt",
  "primary_protocol": "webrtc",
  "fallback_protocol": "hls",
  "latency_target_ms": 1200
}
```

Remember to put a comma between this object and the preceding object. The gateway loads the registry on each request, so it does not need to be restarted.

Confirm that the new stream appears as offline while no publisher is connected:

```bash
curl http://127.0.0.1:8000/streams
```

## 4. Publish a video file

Run this on the sending machine to loop a file and encode it as H.264 video with optional AAC audio:

```bash
ffmpeg \
  -re \
  -stream_loop -1 \
  -i video.mp4 \
  -map 0:v:0 \
  -map 0:a:0? \
  -c:v libx264 \
  -preset veryfast \
  -tune zerolatency \
  -pix_fmt yuv420p \
  -g 60 \
  -c:a aac \
  -b:a 128k \
  -ar 48000 \
  -f mpegts \
  "srt://10.20.20.193:8890?streamid=publish:remote_srt&pkt_size=1316&latency=200000"
```

Important options:

- `-re` reads the file at normal playback speed.
- `-stream_loop -1` loops the file indefinitely.
- `-map 0:a:0?` uses audio when available without failing when it is absent.
- `-g 60` produces a keyframe about every two seconds for 30 fps video.
- `latency=200000` gives SRT approximately 200 ms of latency for retransmissions.
- `streamid=publish:remote_srt` selects the MediaMTX path.
- The SRT URL is quoted because its query string contains shell control characters.

Stop publishing with `Ctrl+C`.

## 5. Copy compatible streams without transcoding

Inspect the source codecs:

```bash
ffprobe \
  -v error \
  -show_entries stream=codec_type,codec_name,width,height,r_frame_rate \
  -of json \
  video.mp4
```

If the source already contains H.264 video and compatible audio, reduce CPU use by copying the encoded tracks:

```bash
ffmpeg \
  -re \
  -stream_loop -1 \
  -i video.mp4 \
  -map 0:v:0 \
  -map 0:a:0? \
  -c copy \
  -f mpegts \
  "srt://10.20.20.193:8890?streamid=publish:remote_srt&pkt_size=1316&latency=200000"
```

Use the transcoding command from the previous section when the source codec is unsuitable for browsers.

## 6. Relay an RTSP source over SRT

This command pulls an RTSP feed on the sending machine and forwards it to MediaMTX:

```bash
ffmpeg \
  -rtsp_transport tcp \
  -i "rtsp://CAMERA_IP:554/path" \
  -map 0:v:0 \
  -map 0:a:0? \
  -c copy \
  -f mpegts \
  "srt://10.20.20.193:8890?streamid=publish:remote_srt&pkt_size=1316&latency=200000"
```

This mode only repackages the encoded stream. If the video is not H.264, replace `-c copy` with:

```bash
-c:v libx264 \
-preset veryfast \
-tune zerolatency \
-pix_fmt yuv420p \
-g 60 \
-c:a aac \
-b:a 128k
```

## 7. Relay an existing SRT stream

If FFmpeg should listen for an upstream SRT sender on the sending machine's UDP port `9001`:

```bash
ffmpeg \
  -i "srt://0.0.0.0:9001?mode=listener&latency=200000" \
  -map 0:v:0 \
  -map 0:a:0? \
  -c copy \
  -f mpegts \
  "srt://10.20.20.193:8890?mode=caller&streamid=publish:remote_srt&pkt_size=1316&latency=200000"
```

If an upstream SRT server is already listening, connect FFmpeg to it as a caller:

```bash
ffmpeg \
  -i "srt://SOURCE_IP:9001?mode=caller&latency=200000" \
  -map 0:v:0 \
  -map 0:a:0? \
  -c copy \
  -f mpegts \
  "srt://10.20.20.193:8890?mode=caller&streamid=publish:remote_srt&pkt_size=1316&latency=200000"
```

Only one program can normally listen on a given UDP port, and only one publisher should own a MediaMTX path at a time.

## 8. Verify the publication

On the Pi, watch MediaMTX while starting FFmpeg:

```bash
journalctl --user -u mediamtx-local -f
```

Check MediaMTX directly:

```bash
curl http://127.0.0.1:9997/v3/paths/list
```

Check the gateway's interpretation:

```bash
curl http://127.0.0.1:8000/streams/remote_srt/health
```

An active publication should return `status: online` and `ready: true`.

## 9. Play the stream

Use these addresses from another machine on the LAN:

| Client | Address |
|---|---|
| Gateway UI | `http://10.20.20.193:8000` |
| WebRTC player | `http://10.20.20.193:8889/remote_srt` |
| HLS player | `http://10.20.20.193:8888/remote_srt` |
| RTSP/VLC | `rtsp://10.20.20.193:8554/remote_srt` |

Read the path as raw SRT with FFplay:

```bash
ffplay "srt://10.20.20.193:8890?streamid=read:remote_srt&latency=200000"
```

## 10. Troubleshooting

If the gateway reports the stream as offline:

1. Confirm MediaMTX is listening with `ss -lunp | grep 8890`.
2. Check FFmpeg's output for SRT connection or codec errors.
3. Confirm the stream ID is exactly `publish:remote_srt`.
4. Inspect recent logs with `journalctl --user -u mediamtx-local -n 100`.
5. If a host firewall is active, allow UDP port `8890` from the local subnet.
6. If MediaMTX accepts the stream but browsers cannot play it, encode video as H.264 and audio as AAC or Opus.

Create separate paths such as `remote_srt_02` and `remote_srt_03` for simultaneous publishers.
