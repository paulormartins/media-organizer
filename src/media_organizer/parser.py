from __future__ import annotations

import re
from pathlib import Path

from .models import Plan, PlanStatus


VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".m4v",
    ".wmv",
    ".ts",
    ".webm",
}

YEAR_RE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})(?!\d)"
)

EPISODE_RE = re.compile(
    r"(?i)\bS(\d{1,2})E(\d{1,3})(?:E(\d{1,3}))?\b"
)

NOISE_PATTERNS = [
    r"\b(?:2160p|1080p|720p|576p|480p|4k)\b",
    r"\b(?:uhd|bluray|blu-ray|blurayrip|brrip|bdrip|webrip|web-rip|web-dl|webdl|web|hdtv|dvdrip|hdrip|remux)\b",
    r"\b(?:x264|x265|h\.?264|h\.?265|hevc|avc|av1|10bit|8bit)\b",
    r"\b(?:hdr10\+?|hdr|dolby[ ._-]?vision|dv)\b",
    r"\b(?:aac(?:2|5)?(?:\.?0|\.?1)?|ac3|eac3|ddp?5\.?1|dts(?:-hd)?|truehd|atmos|mp3)\b",
    r"\b(?:proper|repack|extended|unrated|remastered|imax|hybrid)\b",
    r"\b(?:multi|dual[ ._-]?audio|dualleg|dublado|legendado|subbed|dubbed|commentary)\b",
    r"\b(?:yify|yts|rarbg|eztv|ettv|galaxyrg|tgx|amzn|pcok)\b",
]


def _split_camel_case(value: str) -> str:
    value = re.sub(
        r"(?<=[a-zá-ÿ])(?=[A-ZÁ-Ý])",
        " ",
        value,
    )

    return re.sub(
        r"(?<=[A-ZÁ-Ý])(?=[A-ZÁ-Ý][a-zá-ÿ])",
        " ",
        value,
    )


def _format_word(
    word: str,
    is_first: bool,
) -> str:
    small_words = {
        "a",
        "an",
        "and",
        "as",
        "at",
        "but",
        "by",
        "for",
        "in",
        "of",
        "on",
        "or",
        "the",
        "to",
    }

    if "-" in word:
        parts = word.split("-")

        return "-".join(
            _format_word(
                part,
                is_first or index == 0,
            )
            for index, part in enumerate(parts)
        )

    lowered = word.lower()

    if word.isupper() and len(word) <= 4:
        return word

    if not is_first and lowered in small_words:
        return lowered

    return lowered[:1].upper() + lowered[1:]


def _title_case(value: str) -> str:
    words = value.split()

    return " ".join(
        _format_word(
            word,
            index == 0,
        )
        for index, word in enumerate(words)
    )


def clean_title(value: str) -> str:
    value = _split_camel_case(value)

    value = re.sub(
        r"[\[\{].*?[\]\}]",
        " ",
        value,
    )

    value = re.sub(
        r"[._]+",
        " ",
        value,
    )

    for pattern in NOISE_PATTERNS:
        value = re.sub(
            pattern,
            " ",
            value,
            flags=re.IGNORECASE,
        )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip(" -_.()[]{}")

    return _title_case(value)


def plan_movie(
    source: Path,
    destination_root: Path,
) -> Plan:
    year_match = YEAR_RE.search(source.stem)

    if not year_match:
        return Plan(
            source=source,
            destination=source,
            media_type="movie",
            title="",
            status=PlanStatus.UNKNOWN,
            reason="Movie year not found",
        )

    year = year_match.group(1)

    raw_title = source.stem[
        : year_match.start()
    ].rstrip(" -_.([")

    title = clean_title(raw_title)

    if not title:
        return Plan(
            source=source,
            destination=source,
            media_type="movie",
            title="",
            year=year,
            status=PlanStatus.UNKNOWN,
            reason="Movie title not found",
        )

    base_name = f"{title} ({year})"

    destination = (
        destination_root
        / base_name
        / f"{base_name}{source.suffix.lower()}"
    )

    return Plan(
        source=source,
        destination=destination,
        media_type="movie",
        title=title,
        year=year,
        status=PlanStatus.READY,
    )


def plan_episode(
    source: Path,
    destination_root: Path,
) -> Plan:
    episode_match = EPISODE_RE.search(
        source.stem
    )

    if not episode_match:
        return Plan(
            source=source,
            destination=source,
            media_type="series",
            title="",
            status=PlanStatus.UNKNOWN,
            reason="Episode pattern SxxEyy not found",
        )

    season = int(
        episode_match.group(1)
    )

    episode = int(
        episode_match.group(2)
    )

    second_episode = (
        int(episode_match.group(3))
        if episode_match.group(3)
        else None
    )

    raw_title = source.stem[
        : episode_match.start()
    ].rstrip(" -_.([")

    title = clean_title(raw_title)

    if not title:
        return Plan(
            source=source,
            destination=source,
            media_type="series",
            title="",
            season=season,
            episode=episode,
            status=PlanStatus.UNKNOWN,
            reason="Series title not found",
        )

    episode_code = (
        f"S{season:02d}"
        f"E{episode:02d}"
    )

    if second_episode is not None:
        episode_code += (
            f"E{second_episode:02d}"
        )

    destination = (
        destination_root
        / title
        / f"Season {season:02d}"
        / (
            f"{title} - "
            f"{episode_code}"
            f"{source.suffix.lower()}"
        )
    )

    return Plan(
        source=source,
        destination=destination,
        media_type="series",
        title=title,
        season=season,
        episode=episode,
        status=PlanStatus.READY,
    )