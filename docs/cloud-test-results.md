# Cloud test results (2026-11-05)

Google Cloud project `project-d700a81d-3de2-4a93-8cf`, region `us-east1`.
Extraction job: 4 vCPU, 8 GiB per task.

## Results

| Test | Result | Key numbers |
|---|---|---|
| Delete with "Also delete PDFs" | Pass | Refused while extracting (409). After: PDF gone from bucket, project 404 |
| COT5407, 14 Rise courses, 31 Kaltura videos | Pass | 3 min 23 s from Extract to last row done. 14/14 tasks succeeded, 0 warnings |
| Suture, 10 YouTube videos | **Fail, reported as Done** | 0 of 10 videos processed. PDF 0.22 MB, 0 transcripts, 0 frames (5.1 MB locally) |
| PCC, 17 Articulate-hosted videos | **Partial** | Finished in 6 min 31 s, 11.65 MB, 248 frames. Whisper failed on all 15 uncaptioned videos |

## COT5407 output (for the poster)

- 535 pages, about 148,000 tokens of text, 284 video frames (all with OCR text),
  278 transcript blocks, 28.4 MB in total. No Rise filler text in any PDF.
- Per task: 29 s to 128 s. Sum of task time 722 s, wall time about 200 s,
  so about 3.6x faster than running the same tasks one after another.
- Queue wait before tasks start varies: about 15 s to 2 min (seen 2026-11-05).

## Cost

Estimate only: rates are from memory, not confirmed from Google's pricing page
(about $0.000018 per vCPU-second, $0.000002 per GiB-second, so about $0.000088
per second for one task). Check the billing report before quoting these.

| Run | Task seconds | Estimated cost |
|---|---|---|
| COT5407, 14 courses | 722 | about $0.06 |
| PCC | 366 | about $0.03 |
| Suture (videos failed) | 57 | under $0.01 |

These runs may also fall inside the monthly free tier.

## Problems found

1. **YouTube blocks downloads from Google Cloud.** Captions, audio and video all
   fail for every YouTube video in the job. yt-dlp's message points to passing
   cookies, which is how it reports YouTube's sign-in check. The same course
   works from a Mac. (`U8tKeMLl5p4` separately has been removed from YouTube.)
2. **A row says Done when its videos failed.** Suture shows Done with a green
   pill although no video content was extracted. Users can't tell without
   opening the PDF. The row needs a "Done with problems" state and a count.
3. **Whisper is broken in the cloud image.** All 15 calls fail with
   `open() got an unexpected keyword argument 'metadata_errors'`.
   faster-whisper 1.2.1 passes that argument to `av.open`; the image installs
   the latest PyAV, while the Mac has av 18.1.0 and works. (av 19 is the likely
   cause; the fix is to pin `av<19` and redeploy.) No PCC transcript was lost
   this time, because those 15 videos are music-only, but any uploaded video
   with speech and no captions would silently lose its transcript.

## Fix status (re-tested 2026-11-05)

| Problem | Status | Evidence |
|---|---|---|
| Whisper | **Fixed** by pinning `av<19` | PCC: 0 `metadata_errors`, 0 transcript failures, 17 of 17 videos, 7 min 18 s |
| False Done | **Fixed** | Suture now shows Done with problems, listing all 10 videos |
| YouTube | **Works through the local runner** | See below. Cookie support also exists (`deploy/set-youtube-cookies.sh`) but was never tried |

## Local runner for YouTube (tested 2026-11-05)

Courses with YouTube videos skip the Cloud Run job. They wait in Firestore until
`python runner.py --project <id>` picks them up on a machine on an ordinary
network, and the PDF goes to the same bucket folder.

Suture, clicked through the cloud app and run on a MacBook on campus Wi-Fi:

- No cookies or YouTube account used. Started 30 s after Extract (the polling
  interval), finished in 4 min 33 s, no Cloud Run job started.
- 9 of 10 videos processed. 78 pages, 5.14 MB, about 32,000 tokens, 117 transcript
  blocks, 122 frames: matches the earlier local result.
- The row correctly showed Done with problems, for the one removed video
  (`U8tKeMLl5p4`).
- YouTube still returned HTTP 429 on one caption request; that video went on to
  Whisper. Heavier use could hit more limits.

### Runner failure tests (2026-11-05)

All on the real system with Suture, downloads cached.

| Situation | Result |
|---|---|
| Runner off at Extract | Row waits, status reports offline after about 90 s. Picked up 76 s after starting the runner, finished normally |
| `kill -9` mid-course | Row stays Running, status reports offline. After restart the course reruns from the start and finishes, 1 problem as expected |
| Ctrl+C mid-course | Clean exit (code 0), course stays queued, reruns after restart and finishes |
| Text-only on a YouTube course | Goes to the cloud job, not the runner, 22 s, 0.22 MB |

A cached Suture rerun took about 3 minutes. An interrupted course restarts from
the beginning rather than resuming.

## Not proven yet

- **Auto-start:** `deploy/install-runner-mac.sh` is written but not yet run, so
  start at login, restart after a crash and iCloud Drive access are untested.
- **Runner on an always-on machine:** so far only tested on a laptop, started by
  hand, which has to stay awake. Courses wait while it's off.
- **Several YouTube courses in a row:** only one has been run.
- **Permission:** USF hasn't been asked about downloading YouTube videos this way.
- **Memory with heavy speech:** PCC peaked at about 22% of 8 GiB with Whisper
  running, but its videos are mostly music, so little speech was transcribed.
- **AICC:** no PDF has been loaded into it yet.

## Takeaways

- Kaltura and Articulate-hosted courses work well in the cloud; YouTube doesn't.
- Fix options for YouTube: run YouTube courses locally and upload the PDFs, pass
  cookies (fragile, ties it to one account), or use a non-datacenter network.
- Check PDF contents, not just the status, until problem 2 is fixed.
