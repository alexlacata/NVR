"""Builds ffmpeg command lines for the two per-camera pipelines.

Supported source protocols: RTSP (the vast majority of IP cameras -
Hikvision, Uniview, Dahua, Axis, Reolink and any ONVIF-compliant camera all
speak it), RTMP, SRT, HTTP/MJPEG, a local USB/V4L2 device, and a synthetic
test pattern. See app/onvif_client.py for ONVIF-based auto-discovery of a
camera's RTSP stream URL.

The two pipelines:

- "record": copies/encodes the stream into fixed-length fragmented-MP4
  segment files on disk (the actual recording, for the hard drive). Keeps
  audio when the source has it.
- "live": copies/encodes the stream into an HLS playlist for near-real-time
  viewing on a phone or computer browser. Video only, deliberately: many IP
  cameras send audio in codecs (e.g. PCMU/PCMA) that browsers cannot decode
  via Media Source Extensions at all, and pulling audio into the live leg
  buys little for a surveillance live view while adding a real compatibility
  risk and extra mobile-data bandwidth. Recordings keep the original audio.

Two independent ffmpeg processes are used per camera (rather than a single
`tee` process) so a real IP camera source is opened twice. Nearly all IP
cameras support several concurrent RTSP sessions, and keeping the two
pipelines independent makes failure handling and restarts much simpler.
Use `live_url` (a camera's lower-resolution substream, if it has one) to
keep the live pipeline lightweight.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.models import Camera, SourceType


@dataclass
class InputSpec:
    pre_args: list[str]
    in_args: list[str]
    video_map: list[str]
    audio_map: Optional[list[str]]
    copy_ok: bool


def _input_spec(source_type: SourceType, url: str) -> InputSpec:
    if source_type == SourceType.rtsp:
        return InputSpec(
            pre_args=["-rtsp_transport", "tcp", "-fflags", "+genpts"],
            in_args=["-i", url],
            video_map=["-map", "0:v:0"],
            audio_map=["-map", "0:a:0?"],
            copy_ok=True,
        )
    if source_type == SourceType.rtmp:
        return InputSpec(
            pre_args=["-fflags", "+genpts"],
            in_args=["-i", url],
            video_map=["-map", "0:v:0"],
            audio_map=["-map", "0:a:0?"],
            copy_ok=True,
        )
    if source_type == SourceType.srt:
        return InputSpec(
            pre_args=["-fflags", "+genpts"],
            in_args=["-i", url],
            video_map=["-map", "0:v:0"],
            audio_map=["-map", "0:a:0?"],
            copy_ok=True,
        )
    if source_type == SourceType.http:
        return InputSpec(
            pre_args=["-fflags", "+genpts"],
            in_args=["-i", url],
            video_map=["-map", "0:v:0"],
            audio_map=None,
            copy_ok=False,
        )
    if source_type == SourceType.usb:
        return InputSpec(
            pre_args=["-f", "v4l2", "-framerate", "25", "-video_size", "1280x720"],
            in_args=["-i", url],
            video_map=["-map", "0:v:0"],
            audio_map=None,
            copy_ok=False,
        )
    if source_type == SourceType.test:
        return InputSpec(
            pre_args=[],
            in_args=[
                "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            ],
            video_map=["-map", "0:v"],
            audio_map=["-map", "1:a"],
            copy_ok=False,
        )
    raise ValueError(f"Unknown source type: {source_type}")


#  h264_v4l2m2m has no software-only concept of a quality preset and
# doesn't support -tune zerolatency - it's a fixed hardware pipeline that
# the driver, not libavcodec, controls. It also needs an explicit bitrate:
# left unset, the driver's own default is low enough to look noticeably
# worse than libx264's default (quality-targeted, not bitrate-targeted)
# behavior, so a cap below applies to it as much as it does to libx264.
_HW_ENCODER_DEFAULT_BITRATE_KBPS = 4000


def _video_codec_args(
    gop_seconds: int,
    max_bitrate_kbps: Optional[int] = None,
    scale: Optional[str] = None,
    hw_encoder: Optional[str] = None,
) -> list[str]:
    if hw_encoder:
        args = [
            "-c:v", hw_encoder,
            "-pix_fmt", "yuv420p",
            "-g", str(gop_seconds * 25),
            "-r", "25",
        ]
    else:
        args = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-g", str(gop_seconds * 25),
            "-r", "25",
        ]
    if scale:
        width, height = scale.split("x")
        args += ["-vf", f"scale={width}:{height}"]
    if max_bitrate_kbps:
        args += [
            "-b:v", f"{max_bitrate_kbps}k",
            "-maxrate", f"{max_bitrate_kbps}k",
            "-bufsize", f"{max_bitrate_kbps * 2}k",
        ]
    elif hw_encoder:
        args += ["-b:v", f"{_HW_ENCODER_DEFAULT_BITRATE_KBPS}k"]
    return args


_AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "96k", "-ar", "44100"]


def build_record_cmd(
    ffmpeg_bin: str,
    camera: Camera,
    out_dir: Path,
    segment_seconds: int,
    hw_encoder: Optional[str] = None,
) -> list[str]:
    spec = _input_spec(camera.source_type, camera.url)
    maps = list(spec.video_map)
    if spec.audio_map:
        maps += spec.audio_map

    if spec.copy_ok:
        codec_args = ["-c", "copy"]
    else:
        codec_args = _video_codec_args(gop_seconds=2, hw_encoder=hw_encoder)
        codec_args += _AUDIO_CODEC_ARGS if spec.audio_map else ["-an"]

    out_pattern = str(out_dir / "%Y-%m-%d_%H-%M-%S.mp4")
    return [
        ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "warning",
        *spec.pre_args,
        *spec.in_args,
        *maps,
        *codec_args,
        "-f", "segment",
        "-segment_time", str(segment_seconds),
        "-segment_format", "mp4",
        "-segment_format_options", "movflags=+frag_keyframe+empty_moov+default_base_moof",
        "-reset_timestamps", "1",
        "-strftime", "1",
        out_pattern,
    ]


def build_live_cmd(
    ffmpeg_bin: str,
    camera: Camera,
    out_dir: Path,
    hls_segment_seconds: int,
    hls_list_size: int,
    hw_encoder: Optional[str] = None,
) -> list[str]:
    url = camera.live_url or camera.url
    spec = _input_spec(camera.source_type, url)

    # A bitrate cap or forced resolution (used to fit the live view through a
    # constrained/metered uplink, e.g. a cellular router) requires
    # re-encoding even when the source could otherwise be stream-copied.
    needs_cap = bool(camera.live_max_bitrate_kbps or camera.live_scale)
    if spec.copy_ok and not needs_cap:
        codec_args = ["-c:v", "copy"]
    else:
        codec_args = _video_codec_args(
            gop_seconds=hls_segment_seconds,
            max_bitrate_kbps=camera.live_max_bitrate_kbps,
            scale=camera.live_scale,
            hw_encoder=hw_encoder,
        )

    playlist = str(out_dir / "stream.m3u8")
    segment_pattern = str(out_dir / "seg_%08d.ts")
    return [
        ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "warning",
        *spec.pre_args,
        *spec.in_args,
        *spec.video_map,
        *codec_args,
        "-f", "hls",
        "-hls_time", str(hls_segment_seconds),
        "-hls_list_size", str(hls_list_size),
        "-hls_flags", "delete_segments+independent_segments",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", segment_pattern,
        playlist,
    ]
