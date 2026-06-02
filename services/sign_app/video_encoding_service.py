"""Video encoding service for normalizing uploads before S3 storage."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


class VideoEncodingError(RuntimeError):
    """Raised when video encoding with ffmpeg fails."""


def _probe_vfrdet(video_path: Path, timeout_seconds: int = 120) -> float | None:
    """Run ffmpeg vfrdet filter and return parsed VFR score when available."""
    cmd = [
        "ffmpeg", "-v", "warning", "-i", str(video_path), 
        "-vf", "vfrdet", "-an", "-f", "null", "-"
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds
        )
        
        if result.returncode != 0:
            print(f"⚠️ vfrdet failed on {video_path.name} (code={result.returncode})")
            return None
            
    except Exception as exc:
        print(f"⚠️ Could not run vfrdet on {video_path.name}: {exc}")
        return None

    match = re.search(r"VFR:([0-9]*\.?[0-9]+)", result.stderr)
    if not match:
        print(f"⚠️ vfrdet score not found in ffmpeg output for {video_path.name}")
        return None

    try:
        return float(match.group(1))
    except ValueError:
        return None


def _get_local_gpu_encoder() -> str:
    """Return the GPU encoder to use for local uploads based on OS."""
    return "h264_videotoolbox" if sys.platform == "darwin" else "h264_nvenc"


def encode_video_cfr_semi_all_intra(input_path: str, timeout_seconds: int = 1800) -> str:
    """
    Encode a raw MP4 to a CFR, semi All-Intra profile using ffmpeg.

    The output is written to a temporary file and then replaces the original
    file so the filename remains unchanged.
    """
    source = Path(input_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Input video not found: {source}")

    output_path = source.with_name(f"{source.stem}_encoded_cfr.mp4")

    source_vfr_score = _probe_vfrdet(source, timeout_seconds=min(timeout_seconds, 120))
    if source_vfr_score is not None:
        print(f"🎯 vfrdet source ({source.name}): {source_vfr_score:.6f}")

    encoder = _get_local_gpu_encoder()
    print(f"🎬 Local encoder selected: {encoder}")

    cmd = ["ffmpeg", "-y", "-i", str(source), "-c:v", encoder]

    if encoder == "h264_videotoolbox":
        cmd.extend(["-b:v", "8M"])
    else:
        cmd.extend(["-preset", "p4", "-cq", "18"])

    cmd.extend([
        "-fps_mode", "cfr", "-g", "10", "-keyint_min", "10",
        "-sc_threshold", "0", "-an", "-movflags", "+faststart",
        str(output_path)
    ])

    try:
        # check=True will raise CalledProcessError if ffmpeg fails
        subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_seconds, check=True
        )
        
    except FileNotFoundError as exc:
        raise VideoEncodingError("ffmpeg is not installed or not available in PATH") from exc
    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)
        raise VideoEncodingError(f"Video encoding timed out after {timeout_seconds} seconds") from exc
    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        stderr_tail = "\n".join(exc.stderr.strip().splitlines()[-20:])
        raise VideoEncodingError(
            f"Video encoding failed with ffmpeg (code={exc.returncode}). Details:\n{stderr_tail}"
        ) from exc
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        raise VideoEncodingError(f"Unexpected ffmpeg execution error: {exc}") from exc

    # Encoding succeeded, probe the new file
    encoded_vfr_score = _probe_vfrdet(output_path, timeout_seconds=min(timeout_seconds, 120))
    if encoded_vfr_score is not None:
        print(f"🎯 vfrdet encoded ({output_path.name}): {encoded_vfr_score:.6f}")

    try:
        output_path.replace(source)
    except OSError as exc:
        output_path.unlink(missing_ok=True)
        raise VideoEncodingError(f"Failed to replace original video: {exc}") from exc

    return str(source)