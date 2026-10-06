"""HTTP boundary for image build releases."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .image_release import ImageReleasePipeline, UploadRequest, UploadResult
from .infrai_storage import InfraiStorage


def create_app() -> FastAPI:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("INFRAI_API_KEY is required")

    bucket = os.environ.get("INFRAI_IMAGE_BUCKET", "devtools-image-releases")
    storage = InfraiStorage(api_key)
    pipeline = ImageReleasePipeline(storage=storage, bucket=bucket)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        storage.create_bucket(bucket)
        yield

    app = FastAPI(title="Developer Tools Image Release", lifespan=lifespan)

    @app.post("/uploads", response_model=UploadResult)
    def upload(request: UploadRequest) -> UploadResult:
        return pipeline.publish(request)

    return app


app = create_app()
