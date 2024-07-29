"""
Decode RT+ payload strings into metadata dictionaries using a provided
RT string. Used as a sanity check for RT+ tagging and to pass values to
the preview queue.

Author: Mason Daugherty <@mdrxy>
Version: 1.0.0
Last Modified: 2025-03-23

Changelog:
    - 1.0.0 (2025-03-23): Initial release.
"""

from config import ARTIST_TAG, TITLE_TAG


def decode_rt_plus(rt_plus_payload: str, text: str) -> dict:
    """
    Decode an RT+ payload into a metadata dictionary.
    Expected payload format (excluding the final two values):
        <content_type_1>,
        <start_pos_1>,
        <length_1>,
        <content_type_2>,
        <start_pos_2>,
        <length_2>

    Example:
        decode_rt_plus("ARTIST_TAG,0,5,TITLE_TAG,8,10,0,0", "Queen -
            Radio Gaga") -> {'artist': 'Queen', 'title': 'Radio Gaga'}
    """
    tags = rt_plus_payload.split(",")[:-2]
    if len(tags) != 6:
        raise ValueError("Invalid RT+ payload: incorrect number of tags")

    try:
        payloads = {
            tags[0]: (int(tags[1]), int(tags[2])),
            tags[3]: (int(tags[4]), int(tags[5])),
        }
    except (ValueError, IndexError) as exc:
        raise ValueError("Invalid RT+ payload: numeric conversion failed") from exc

    # Recognize that there may be a tag missing (in the case of a
    # truncated TEXT value), and handle it accordingly.
    if ARTIST_TAG not in payloads:
        payloads[ARTIST_TAG] = (0, 0)
    if TITLE_TAG not in payloads:
        payloads[TITLE_TAG] = (0, 0)

    artist_start, artist_length = payloads[ARTIST_TAG]
    title_start, title_length = payloads[TITLE_TAG]

    return {
        "artist": text[artist_start : artist_start + artist_length] or "",
        "title": text[title_start : title_start + title_length] or "",
    }
