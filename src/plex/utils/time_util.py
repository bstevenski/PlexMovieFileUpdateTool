from datetime import datetime, timedelta, timezone

from plex.utils.constants import EST_AVG_VIDEO_LENGTH, EST_AVG_SPEED, WORKERS


def get_eta_single_file(video_duration, speed_val, elapsed_seconds):
    remaining_seconds = (video_duration - elapsed_seconds) / speed_val
    return _get_eta_string(remaining_seconds)


def get_eta_total(transcoded_count, staged_count, elapsed_seconds):
    avg_time_per_file = elapsed_seconds / transcoded_count
    remaining_files = staged_count - transcoded_count
    remaining_seconds = avg_time_per_file * remaining_files
    return _get_eta_string(remaining_seconds)


def get_eta_from_start(file_count):
    total_seconds = (file_count * EST_AVG_VIDEO_LENGTH) / (WORKERS * EST_AVG_SPEED)
    return _get_eta_string(total_seconds)


def _get_eta_string(time_in_seconds):
    completion_time = (datetime.now(timezone.utc) + timedelta(
        seconds=time_in_seconds)).strftime("%Y-%m-%d %H:%M:%S")

    eta_hours = int(time_in_seconds // 3600)
    eta_mins = int((time_in_seconds % 3600) // 60)
    eta_secs = int(time_in_seconds % 60)
    if eta_hours > 0:
        formatted_time = f"{eta_hours}h{eta_mins}m{eta_secs}s"
    elif eta_mins > 0:
        formatted_time = f"{eta_mins}m{eta_secs}s"
    else:
        formatted_time = f"{eta_secs}s"

    return f"{completion_time} ({formatted_time})"
