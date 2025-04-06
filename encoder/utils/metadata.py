"""
Functions for cleaning up music metadata fields (artist, album, track)
using `music-metadata-filter`.
"""

from music_metadata_filter import functions
from music_metadata_filter.filter import FilterSet, MetadataFilter
from utils.logging import configure_logging

logger = configure_logging(__name__)

FILTER_SET: FilterSet = {
    "track": (
        functions.fix_track_suffix,
        functions.remove_feature,
        functions.remove_clean_explicit,
        functions.remove_live,
        functions.remove_reissue,
        functions.remove_remastered,
        functions.remove_version,
        functions.remove_zero_width,
        functions.replace_nbsp,
    ),
    "artist": (
        functions.normalize_feature,
        functions.remove_zero_width,
        functions.replace_nbsp,
    ),
}

METADATA_FILTER = MetadataFilter(FILTER_SET)


def clean_metadata_field(field_type: str, value: str) -> str:
    """
    Cleans up a single metadata field (artist, album, track) using
    music-metadata-filter.
    """
    logger.debug("Cleaning metadata field: `%s` for `%s`", field_type, value)
    if field_type not in ("artist", "album", "track"):
        raise ValueError(f"Unsupported field_type: {field_type}")

    filtered = METADATA_FILTER.filter_field(field_type, value)

    return filtered
