"""
Functions for cleaning up music metadata fields (artist, album, track)
using `music-metadata-filter`.
"""

from typing import Literal

from music_metadata_filter import functions
from music_metadata_filter.filter import FilterSet, MetadataFilter
from utils.logging import configure_logging

MetadataFieldType = Literal["artist", "album", "track"]

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


def clean_metadata_field(field_type: MetadataFieldType, value: str) -> str:
    """Clean a single metadata field using music-metadata-filter.

    Args:
        field_type: The type of metadata field to clean.
        value: The metadata field value to clean.

    Returns:
        The cleaned metadata field value.
    """
    logger.debug("Cleaning metadata field: `%s` for `%s`", field_type, value)
    filtered = METADATA_FILTER.filter_field(field_type, value)
    return filtered
