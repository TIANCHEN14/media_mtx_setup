# Archiving MediaMTX Recordings to S3-Compatible Storage

MediaMTX records to a normal filesystem. To use AWS S3, MinIO, Wasabi, Backblaze B2, Cloudflare R2, or another S3-compatible service, record locally first and upload each completed segment with `rclone`.

```text
Live stream
    |
    v
MediaMTX local recording
    |
    | completed segment
    v
rclone upload
    |
    v
S3-compatible bucket
```

Local staging protects the active recording from temporary network or object-storage failures. It is safer than using an S3 FUSE mount as the active MediaMTX recording directory.

## 1. Install rclone

On the Raspberry Pi:

```bash
sudo apt-get update
sudo apt-get install -y rclone
rclone version
```

The MediaMTX user service runs as the current Linux user, so configure `rclone` under the same account.

## 2. Configure the S3 endpoint

Start the interactive configuration:

```bash
rclone config
```

Create a remote named `video-s3`:

```text
n) New remote
name> video-s3
Storage> s3
```

For a non-AWS S3 service, select `Other` as the provider. Supply the values given by the storage service:

- Access key ID
- Secret access key
- Region, when required
- S3 API endpoint
- Bucket ACL preference

Example endpoints:

```text
AWS:   https://s3.us-east-1.amazonaws.com
MinIO: http://10.20.20.50:9000
```

Do not put S3 credentials in this Git repository or in `mediamtx.yml`. By default, `rclone` keeps them in the current user's private configuration.

Confirm access and create the destination bucket if necessary:

```bash
rclone lsd video-s3:
rclone mkdir video-s3:video-recordings
rclone lsd video-s3:video-recordings
```

## 3. Enable local recording and playback

The following is an example MediaMTX configuration. It is not enabled in the current lab configuration by default.

```yaml
playback: true
playbackAddress: :9996

pathDefaults:
  record: false
  recordPath: ./recordings/%path/%Y-%m-%d_%H-%M-%S-%f
  recordFormat: fmp4
  recordPartDuration: 1s
  recordSegmentDuration: 1m
  recordDeleteAfter: 1h

paths:
  camera01:
    source: publisher
    record: true

  remote_srt:
    source: publisher
    record: true
```

This configuration:

- Records only paths with `record: true`.
- Uses browser-friendly fragmented MP4.
- Finalizes one recording segment per minute.
- Keeps a one-hour local VCR window.
- Enables the MediaMTX recording playback API on TCP port `9996`.

The startup script continues to replace the `camera01` source with the private RTSP source from `config/local.env`.

Validate before restarting:

```bash
./bin/mediamtx --validate-conf=config/mediamtx.yml
systemctl --user restart mediamtx-local
```

## 4. Upload completed segments

Add this setting under `pathDefaults`:

```yaml
pathDefaults:
  runOnRecordSegmentComplete: >
    rclone copy
    "$MTX_SEGMENT_PATH"
    "video-s3:video-recordings/$MTX_PATH/"
```

MediaMTX provides these hook variables:

- `MTX_PATH`: the MediaMTX path, such as `camera01`.
- `MTX_SEGMENT_PATH`: the completed local recording file.
- `MTX_SEGMENT_DURATION`: the duration of the completed segment.

The example preserves a separate S3 prefix for each stream:

```text
video-recordings/
  camera01/
  remote_srt/
  car01/
  car02/
```

Use `rclone copy` when MediaMTX should retain a local VCR window. When `recordDeleteAfter` expires, MediaMTX deletes the local copy; the S3 object remains.

## 5. Copy versus move

### Keep a local VCR window

Recommended configuration:

```yaml
recordDeleteAfter: 1h
runOnRecordSegmentComplete: >
  rclone copy
  "$MTX_SEGMENT_PATH"
  "video-s3:video-recordings/$MTX_PATH/"
```

This provides recent playback through MediaMTX and permanent storage in S3.

### Remove local files immediately

To minimize local storage:

```yaml
runOnRecordSegmentComplete: >
  rclone move
  "$MTX_SEGMENT_PATH"
  "video-s3:video-recordings/$MTX_PATH/"
```

After a file moves, the MediaMTX playback API cannot find it locally. A gateway or application must retrieve the older recording from S3. For VCR functionality, prefer `copy` with a short local retention period.

## 6. Choose a segment duration

Uploads begin after a recording segment closes.

| Segment duration | Approximate upload delay | Tradeoff |
|---:|---:|---|
| 10 seconds | 10 seconds | Many objects and API operations |
| 1 minute | 1 minute | Useful starting point for this lab |
| 5 minutes | 5 minutes | Fewer objects and requests |
| 1 hour | 1 hour | Delayed archive and larger recovery loss |

Begin with:

```yaml
recordSegmentDuration: 1m
recordDeleteAfter: 1h
```

Move to five-minute segments when object count matters more than upload delay.

## 7. Required S3 permissions

The upload identity normally needs:

- `s3:ListBucket`
- `s3:PutObject`

Add `s3:GetObject` when the gateway or another service will retrieve recordings. Add `s3:DeleteObject` only when remote retention or cleanup should delete objects.

An example AWS policy is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::video-recordings"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::video-recordings/*"
      ]
    }
  ]
}
```

Replace the bucket name and ARN with values for the actual provider. S3-compatible services may express permissions differently.

## 8. Verify uploads

Watch MediaMTX while a recording segment closes:

```bash
journalctl --user -u mediamtx-local -f
```

List uploaded recordings:

```bash
rclone lsf video-s3:video-recordings/camera01/
```

Copy one object back as a playback test:

```bash
rclone copy \
  video-s3:video-recordings/camera01/RECORDING_FILE.mp4 \
  /tmp/media-recording-test/
```

If uploads fail, run the equivalent `rclone copy` command manually. This separates S3 credentials and connectivity problems from MediaMTX hook problems.

## 9. Play recent local recordings

List available MediaMTX recordings:

```bash
curl "http://127.0.0.1:9996/list?path=camera01"
```

Request a recorded interval:

```text
http://PI_IP:9996/get?path=camera01&start=START_TIME&duration=300&format=mp4
```

The `start` value must be an RFC 3339 timestamp and URL-encoded when necessary. The browser can pause and seek within the returned MP4 interval.

## 10. Expose archived recordings through the gateway

Recent recordings can continue using the MediaMTX playback API. Older recordings require an S3-aware gateway contract, for example:

```http
GET /streams/camera01/recordings
GET /streams/camera01/archive
GET /streams/camera01/archive/{recording_id}/playback
```

The gateway can return short-lived presigned S3 URLs:

```json
{
  "stream_id": "camera01",
  "storage": "s3",
  "start": "2026-09-07T18:30:00Z",
  "duration": 300,
  "playback_url": "https://s3-endpoint/bucket/object?X-Amz-Signature=..."
}
```

This produces a unified model:

```text
MediaMTX local storage = recent VCR window
S3 storage             = long-term archive
FastAPI gateway        = recording catalog and authorized playback URLs
```

## 11. Estimate storage and bandwidth

Approximate recording storage is:

```text
GB per hour = bitrate in Mbps x 0.45
```

| Stream bitrate | Storage per hour | Storage per day |
|---:|---:|---:|
| 2 Mbps | 0.9 GB | 21.6 GB |
| 4 Mbps | 1.8 GB | 43.2 GB |
| 8 Mbps | 3.6 GB | 86.4 GB |

Multiply these values by the number of continuously recorded streams. Upload bandwidth must sustain at least the total incoming recording bitrate, with additional capacity for retries and concurrent viewers.

For more than a short experiment, use a USB SSD for the local recording window instead of repeatedly writing video to the Pi's SD card.

## 12. References

- [MediaMTX recording and remote upload](https://mediamtx.org/docs/features/record)
- [MediaMTX recording playback API](https://mediamtx.org/docs/features/playback)
- [rclone S3 provider configuration](https://rclone.org/s3/)
