"""
Video transcoding module for media file conversion.

This module provides functions for transcoding video files to formats
compatible with Plex and various devices, especially Apple TVs.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Optional

import ffmpeg

from .constants import TRANSCODE_SETTINGS

logger = logging.getLogger(__name__)


class TranscodingError(Exception):
    """Exception for transcoding failures."""

    pass


class VideoInfo:
    """Container for video file information."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.duration: Optional[float] = None
        self.size: int = 0
        self.video_codec: Optional[str] = None
        self.audio_codec: Optional[str] = None
        self.audio_channels: Optional[int] = None
        self.width: Optional[int] = None
        self.height: Optional[int] = None
        self.bitrate: Optional[int] = None
        self.is_already_compatible: bool = False

        self._probe()

    def _probe(self) -> None:
        """Probe the video file to extract metadata."""
        try:
            if ffmpeg is not None:
                probe = ffmpeg.probe(str(self.filepath))
                self._parse_ffmpeg_probe(probe)
            else:
                self._probe_with_ffprobe()
        except Exception as e:
            logger.error(f"Failed to probe video file {self.filepath}: {e}")
            raise TranscodingError(f"Failed to probe video file: {e}")

    def _parse_ffmpeg_probe(self, probe: Dict) -> None:
        """Parse ffmpeg probe data."""
        # Get format info
        format_info = probe.get("format", {})
        self.duration = float(format_info.get("duration", 0))
        self.size = int(format_info.get("size", 0))
        self.bitrate = int(format_info.get("bit_rate", 0))

        # Get stream info
        streams = probe.get("streams", [])
        for stream in streams:
            codec_type = stream.get("codec_type")

            if codec_type == "video":
                self.video_codec = stream.get("codec_name")
                self.width = int(stream.get("width", 0))
                self.height = int(stream.get("height", 0))

            elif codec_type == "audio":
                self.audio_codec = stream.get("codec_name")
                self.audio_channels = int(stream.get("channels", 0))

        self._check_compatibility()

    def _probe_with_ffprobe(self) -> None:
        """Probe using ffprobe command line tool."""
        cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(self.filepath)]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                raise TranscodingError(f"ffprobe failed: {result.stderr}")

            probe_data = json.loads(result.stdout)
            self._parse_ffmpeg_probe(probe_data)

        except subprocess.TimeoutExpired:
            raise TranscodingError("ffprobe timed out")
        except json.JSONDecodeError as e:
            raise TranscodingError(f"Failed to parse ffprobe output: {e}")

    def _check_compatibility(self) -> None:
        """Check if the video is already compatible with target devices."""
        # Check video codec compatibility
        video_compatible = self.video_codec in ["h264", "avc"]

        # Check audio codec compatibility
        audio_compatible = self.audio_codec in ["aac", "mp3"] and (
                self.audio_channels is not None and self.audio_channels <= 2
        )

        self.is_already_compatible = video_compatible and audio_compatible


def needs_transcoding(video_info: VideoInfo) -> bool:
    """Determine if a video file needs transcoding."""
    return not video_info.is_already_compatible


def estimate_transcoding_time(video_info: VideoInfo) -> float:
    """Estimate transcoding time based on video duration and settings."""
    if not video_info.duration:
        return 0.0

    # Rough estimate: transcoding takes about 1.5x real-time
    # This would be calibrated based on actual performance
    return video_info.duration * 1.5


def get_transcode_output_path(input_path: Path) -> Path:
    """Generate output path for transcoded file."""
    # Change extension to .mp4 for transcoded files
    return input_path.with_suffix(".mp4")


def transcode_video(
        input_path: Path,
        output_path: Path,
        settings: Optional[Dict] = None,
        progress_callback: Optional[callable] = None,
) -> bool:
    """
    Transcode a video file using FFmpeg.

    Args:
        input_path: Input video file path
        output_path: Output video file path
        settings: Transcoding settings (uses default if None)
        progress_callback: Callback function for progress updates

    Returns:
        True if transcoding succeeded, False otherwise
    """
    if settings is None:
        settings = TRANSCODE_SETTINGS

    try:
        if ffmpeg is not None:
            return _transcode_with_python_ffmpeg(input_path, output_path, settings, progress_callback)
        else:
            return _transcode_with_ffmpeg_cli(input_path, output_path, settings, progress_callback)

    except Exception as e:
        logger.error(f"Transcoding failed for {input_path}: {e}")
        raise TranscodingError(f"Transcoding failed: {e}")


def _transcode_with_python_ffmpeg(
        input_path: Path,
        output_path: Path,
        settings: Dict,
        progress_callback: Optional[callable],
) -> bool:
    """Transcode using python-ffmpeg library."""
    if ffmpeg is None:
        logger.error("python-ffmpeg library not available")
        return False

    try:
        # Use ffmpeg directly since the python bindings have issues
        return _transcode_with_ffmpeg_cli(input_path, output_path, settings, progress_callback)

    except Exception as e:
        logger.error(f"FFmpeg error: {e}")
        return False


def _transcode_with_ffmpeg_cli(
        input_path: Path,
        output_path: Path,
        settings: Dict,
        progress_callback: Optional[callable],
) -> bool:
    """Transcode using FFmpeg command line interface."""
    cmd = [
        "ffmpeg",
        "-i",
        str(input_path),
        "-c:v",
        settings["video_codec"],
        "-preset",
        settings["preset"],
        "-crf",
        str(settings["crf"]),
        "-c:a",
        settings["audio_codec"],
        "-b:a",
        settings["audio_bitrate"],
        "-ac",
        str(settings["max_audio_channels"]),
        "-y",  # Overwrite output file
        str(output_path),
    ]

    process = None
    try:
        logger.info(f"Starting transcoding: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
        )

        # Monitor progress
        if process.stdout:
            for line in process.stdout:
                if progress_callback:
                    # Parse progress from FFmpeg output (simplified)
                    if "time=" in line:
                        try:
                            time_str = line.split("time=")[1].split()[0]
                            # Convert to seconds and call callback
                            progress_callback(time_str)
                        except (IndexError, ValueError):
                            pass

        return_code = process.wait()

        if return_code == 0:
            logger.info(f"Transcoding completed: {output_path}")
            return True
        else:
            logger.error(f"Transcoding failed with return code {return_code}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Transcoding timed out")
        if process:
            process.kill()
        return False
    except Exception as e:
        logger.error(f"Transcoding error: {e}")
        return False


def validate_transcoded_file(original_path: Path, transcoded_path: Path) -> bool:
    """Validate that a transcoded file is properly formatted."""
    try:
        # Check that output file exists and has reasonable size
        if not transcoded_path.exists():
            return False

        original_size = original_path.stat().st_size
        transcoded_size = transcoded_path.stat().st_size

        # Transcoded file should be at least 10% of original (very rough check)
        if transcoded_size < original_size * 0.1:
            return False

        # Try to probe the transcoded file
        transcoded_info = VideoInfo(transcoded_path)

        # Check that it has video and audio streams
        return transcoded_info.video_codec is not None and transcoded_info.audio_codec is not None

    except Exception as e:
        logger.error(f"Failed to validate transcoded file: {e}")
        return False


def cleanup_transcoding_artifacts(filepath: Path) -> None:
    """Clean up temporary files and artifacts from transcoding."""
    # Remove any temporary files that might have been created
    temp_patterns = [
        filepath.with_suffix(filepath.suffix + ".tmp"),
        filepath.with_suffix(".tmp"),
    ]

    for temp_file in temp_patterns:
        if temp_file.exists():
            try:
                temp_file.unlink()
                logger.debug(f"Cleaned up temporary file: {temp_file}")
            except OSError as e:
                logger.warning(f"Failed to clean up temporary file {temp_file}: {e}")
