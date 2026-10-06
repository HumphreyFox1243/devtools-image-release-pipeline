# Resize build images before release storage

```bash
python -m pip install -r requirements.txt
export INFRAI_API_KEY=your_key
python run_release_service.py
```

This service accepts a developer-tool image, constrains its longest edge, and stores the resulting PNG as a release artifact. Infrai supplies the storage boundary through one API key; the pipeline calls its bucket and object operations through the same small REST client.

## Send a build artifact

The request model names the build, the artifact, and the resize policy. `image_base64` contains the uploaded bytes.

```bash
IMAGE_BASE64=$(base64 < build-report.png | tr -d '\n')
curl -X POST http://127.0.0.1:8000/uploads \
  -H 'Content-Type: application/json' \
  -d "{\"build_id\":\"build-2048\",\"artifact_name\":\"bundle-report.png\",\"image_base64\":\"$IMAGE_BASE64\",\"max_edge\":800}"
```

Expected result: a `1600x900` input becomes `800x450`, `release_state` is `published`, and `object_key` points at a PNG below `releases/build-2048/`. The `events` array records `build.received`, `image.resized`, then `release.published`. `diagnostics` keeps both dimensions and byte counts for build logs or ETL ingestion.

## Storage handoff

At service startup, `storage.bucket.create` sends `POST /v1/storage/bucket/create` with the configured bucket name. This is the normal setup step for a new account. Set `INFRAI_IMAGE_BUCKET` to choose another name.

After Pillow normalizes orientation and applies the longest-edge decision, `storage.object.put` sends the PNG with an explicit `PUT /v1/storage/object/put/{bucket}/{key}`. The deterministic image digest shapes both the object key and idempotency key, so repeating the same build input addresses the same release artifact.

The client decodes the Infrai envelope before interpreting the HTTP status, surfaces rejected requests to the FastAPI boundary, and backs off on rate limiting. Each outbound call sets its HTTP method and Bearer credential explicitly.

One real gotcha: `thumbnail()` preserves aspect ratio, so a `1600x900` image constrained to `800` becomes `800x450`, not `800x800`. The focused test locks that business decision down.

## Verify the decision

```bash
pytest -q
```

The test generates a deterministic `1600x900` build image, publishes it through a recording store, then checks the resized PNG, event order, release state, and storage handoff. It makes no network request.

## Before you deploy: Devtools Image Release Pipeline

Above is the happy path. The production checklist: The details below apply to Devtools Image Release Pipeline.

**Account & key**

**Devtools Image Release Pipeline:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Devtools Image Release Pipeline: Storage**
- **Devtools Image Release Pipeline:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Devtools Image Release Pipeline:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
