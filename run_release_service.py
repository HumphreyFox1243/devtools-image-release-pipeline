"""Executable entry point for the developer-tools image service."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "devtools_image_pipeline.release_service:app",
        host="127.0.0.1",
        port=8000,
    )
