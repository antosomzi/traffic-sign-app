"""Video encoding service for normalizing uploads before S3 storage."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class VideoEncodingError(RuntimeError):
    """Raised when video encoding with ffmpeg fails."""


def _get_local_gpu_encoder() -> str:
    """Return the GPU encoder to use for local uploads based on OS."""
    if sys.platform == "darwin":
        # Apple Silicon / Intel macOS hardware encoder
        return "h264_videotoolbox"

    # Linux hosts with NVIDIA drivers/toolkit
    return "h264_nvenc"


def encode_video_cfr_semi_all_intra(input_path: str, timeout_seconds: int = 1800) -> str:
    """
    Encode a raw MP4 to a CFR, semi All-Intra profile using ffmpeg.

    The output is written next to the original file with the suffix
    ``_encoded_cfr.mp4`` and returned as an absolute path.

    Args:
        input_path: Absolute or relative path to source video.
        timeout_seconds: Max ffmpeg execution time in seconds.

    Returns:
        Absolute path to encoded output video.

    Raises:
        FileNotFoundError: If input file does not exist.
        VideoEncodingError: If ffmpeg is missing or encoding fails.
    """
    source = Path(input_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input video not found: {source}")

    output_path = source.with_name(f"{source.stem}_encoded_cfr.mp4")

    encoder = _get_local_gpu_encoder()

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:v",
        encoder,
    ]

    if encoder == "h264_videotoolbox":
        # videotoolbox does not support libx264-style CRF/preset flags
        cmd.extend([
            "-b:v",
            "8M",
        ])
    else:
        cmd.extend([
            "-preset",
            "p4",
            "-cq",
            "18",
        ])

    cmd.extend([
        "-fps_mode",
        "cfr",
        "-g",
        "10",
        "-keyint_min",
        "10",
        "-sc_threshold",
        "0",
        "-an",
        "-movflags",
        "+faststart",
        str(output_path),
    ])

    try:
        result = subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise VideoEncodingError("ffmpeg is not installed or not available in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        if output_path.exists():
            try:
                os.remove(output_path)
            except OSError:
                pass
        raise VideoEncodingError(
            f"Video encoding timed out after {timeout_seconds} seconds"
        ) from exc
    except Exception as exc:
        raise VideoEncodingError(f"Unexpected ffmpeg execution error: {exc}") from exc

    if result.returncode != 0:
        if output_path.exists():
            try:
                os.remove(output_path)
            except OSError:
                pass

        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-20:])
        raise VideoEncodingError(
            "Video encoding failed with ffmpeg. "
            f"Return code: {result.returncode}. "
            f"Details:\n{stderr_tail}"
        )

    return str(output_path)
