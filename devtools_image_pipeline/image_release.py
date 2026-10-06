"""Domain pipeline: resize a build image, then publish the derived artifact."""

from __future__ import annotations

import base64
import hashlib
import io
import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from PIL import Image, ImageOps
from pydantic import BaseModel, Field, field_validator


class EventKind(str, Enum):
    BUILD_RECEIVED = "build.received"
    IMAGE_RESIZED = "image.resized"
    RELEASE_PUBLISHED = "release.published"


class UploadRequest(BaseModel):
    build_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    artifact_name: str = Field(min_length=1, max_length=120)
    image_base64: str = Field(min_length=1)
    max_edge: int = Field(default=960, ge=64, le=4096)

    @field_validator("artifact_name")
    @classmethod
    def require_image_name(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
            raise ValueError("use letters, digits, dots, underscores, or hyphens")
        return value


class BuildEvent(BaseModel):
    kind: EventKind
    build_id: str
    detail: str


class Diagnostic(BaseModel):
    source_size: str
    output_size: str
    source_bytes: int
    output_bytes: int
    resized: bool


class UploadResult(BaseModel):
    build_id: str
    release_state: str
    object_key: str
    image_base64: str
    diagnostics: Diagnostic
    events: list[BuildEvent]


class ImageStore(Protocol):
    def put_image(
        self,
        bucket: str,
        key: str,
        *,
        data_base64: str,
        idempotency_key: str,
    ) -> dict[str, object]: ...


@dataclass
class ImageReleasePipeline:
    storage: ImageStore
    bucket: str

    def publish(self, request: UploadRequest) -> UploadResult:
        source = base64.b64decode(request.image_base64, validate=True)
        output, source_size, output_size = self._resize(source, request.max_edge)
        digest = hashlib.sha256(output).hexdigest()[:16]
        artifact_stem = request.artifact_name.rsplit(".", 1)[0]
        object_key = f"releases/{request.build_id}/{artifact_stem}-{digest}.png"
        output_base64 = base64.b64encode(output).decode("ascii")

        self.storage.put_image(
            self.bucket,
            object_key,
            data_base64=output_base64,
            idempotency_key=f"image-release-{digest}",
        )

        diagnostics = Diagnostic(
            source_size=f"{source_size[0]}x{source_size[1]}",
            output_size=f"{output_size[0]}x{output_size[1]}",
            source_bytes=len(source),
            output_bytes=len(output),
            resized=source_size != output_size,
        )
        events = [
            BuildEvent(
                kind=EventKind.BUILD_RECEIVED,
                build_id=request.build_id,
                detail=request.artifact_name,
            ),
            BuildEvent(
                kind=EventKind.IMAGE_RESIZED,
                build_id=request.build_id,
                detail=diagnostics.output_size,
            ),
            BuildEvent(
                kind=EventKind.RELEASE_PUBLISHED,
                build_id=request.build_id,
                detail=object_key,
            ),
        ]
        return UploadResult(
            build_id=request.build_id,
            release_state="published",
            object_key=object_key,
            image_base64=output_base64,
            diagnostics=diagnostics,
            events=events,
        )

    @staticmethod
    def _resize(image_bytes: bytes, max_edge: int) -> tuple[bytes, tuple[int, int], tuple[int, int]]:
        with Image.open(io.BytesIO(image_bytes)) as loaded:
            image = ImageOps.exif_transpose(loaded).convert("RGBA")
            source_size = image.size
            image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            output_size = image.size
            stream = io.BytesIO()
            image.save(stream, format="PNG", optimize=True)
        return stream.getvalue(), source_size, output_size
