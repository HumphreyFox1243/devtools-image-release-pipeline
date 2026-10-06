import base64
import io

from PIL import Image

from devtools_image_pipeline.image_release import ImageReleasePipeline, UploadRequest


class RecordingStore:
    def __init__(self) -> None:
        self.puts: list[tuple[str, str, str, str]] = []

    def put_image(
        self,
        bucket: str,
        key: str,
        *,
        data_base64: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self.puts.append((bucket, key, data_base64, idempotency_key))
        return {}


def test_landscape_build_image_is_resized_then_published() -> None:
    source = io.BytesIO()
    Image.new("RGB", (1600, 900), "#2563eb").save(source, format="PNG")
    storage = RecordingStore()
    pipeline = ImageReleasePipeline(storage=storage, bucket="release-images")

    result = pipeline.publish(
        UploadRequest(
            build_id="build-2048",
            artifact_name="bundle-report.png",
            image_base64=base64.b64encode(source.getvalue()).decode("ascii"),
            max_edge=800,
        )
    )

    assert result.release_state == "published"
    assert result.object_key.startswith("releases/build-2048/bundle-report-")
    assert result.diagnostics.source_size == "1600x900"
    assert result.diagnostics.output_size == "800x450"
    assert result.diagnostics.resized is True
    assert [event.kind.value for event in result.events] == [
        "build.received",
        "image.resized",
        "release.published",
    ]
    published = base64.b64decode(result.image_base64)
    assert storage.puts == [
        (
            "release-images",
            result.object_key,
            result.image_base64,
            f"image-release-{result.object_key.removesuffix('.png').rsplit('-', 1)[1]}",
        )
    ]
    with Image.open(io.BytesIO(published)) as image:
        assert image.size == (800, 450)
