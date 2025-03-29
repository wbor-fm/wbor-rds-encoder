"""
Functions for cleaning up music metadata fields (artist, album, track)
using `music-metadata-filter`.
"""

from music_metadata_filter.filters import make_spotify_filter

# Use opinionated Spotify filter because it's pretty balanced
metadata_filter = make_spotify_filter()


def clean_metadata_field(field_type: str, value: str) -> str:
    """
    Cleans up a single metadata field (artist, album, track) using music-metadata-filter.
    """
    if field_type not in ("artist", "album", "track"):
        raise ValueError(f"Unsupported field_type: {field_type}")
    return metadata_filter.filter_field(field_type, value).strip()
