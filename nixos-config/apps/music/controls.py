import subprocess

_MPRIS_DEST  = "org.mpris.MediaPlayer2.ShairportSync"
_MPRIS_PATH  = "/org/mpris/MediaPlayer2"
_MPRIS_IFACE = "org.mpris.MediaPlayer2.Player"


def _mpris(method: str):
    subprocess.run(
        [
            "dbus-send", "--session", "--type=method_call",
            f"--dest={_MPRIS_DEST}", _MPRIS_PATH,
            f"{_MPRIS_IFACE}.{method}",
        ],
        capture_output=True,
    )


def play_pause():  _mpris("PlayPause")
def next_track():  _mpris("Next")
def prev_track():  _mpris("Previous")


def volume_up():
    subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
        capture_output=True,
    )


def volume_down():
    subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
        capture_output=True,
    )
