from osu_beatmap_xplorer.__main__ import build_query, create_tables

import pytest


@pytest.mark.asyncio
async def test_build_query():
    await create_tables()

    test_pairs = [
        (
            [
                {"type": "mode_int", "compare": "=", "value": 0},
                {"type": "difficulty_rating", "compare": ">", "value": 5},
                {"type": "difficulty_rating", "compare": "<", "value": 6},
                {"type": "text", "compare": "~", "value": "maimai"},
                {"type": "creator", "compare": "=", "value": "camellia"},
            ],
            (
                "SELECT * FROM beatmapsets WHERE id IN (SELECT DISTINCT beatmapset_id FROM beatmaps WHERE mode_int = ? AND difficulty_rating > ? AND difficulty_rating < ?) AND creator = ? AND (artist LIKE ? OR artist_unicode LIKE ? OR creator LIKE ? OR source LIKE ? OR tags LIKE ?) ORDER BY RANDOM() LIMIT ?",
                [
                    0,
                    5,
                    6,
                    "camellia",
                    "%maimai%",
                    "%maimai%",
                    "%maimai%",
                    "%maimai%",
                    "%maimai%",
                    50,
                ],
            ),
        ),
        (
            [{"type": "mode_int", "compare": "=", "value": 0}],
            (
                "SELECT * FROM beatmapsets WHERE id IN (SELECT DISTINCT beatmapset_id FROM beatmaps WHERE mode_int = ?) ORDER BY RANDOM() LIMIT ?",
                [
                    0,
                    50,
                ],
            ),
        ),
        (
            [
                {"type": "text", "compare": "~", "value": "maimai"},
            ],
            (
                "SELECT * FROM beatmapsets WHERE (artist LIKE ? OR artist_unicode LIKE ? OR creator LIKE ? OR source LIKE ? OR tags LIKE ?) ORDER BY RANDOM() LIMIT ?",
                [
                    "%maimai%",
                    "%maimai%",
                    "%maimai%",
                    "%maimai%",
                    "%maimai%",
                    50,
                ],
            ),
        ),
        (
            [
                {"type": "creator", "compare": "=", "value": "camellia"},
            ],
            (
                "SELECT * FROM beatmapsets WHERE creator = ? ORDER BY RANDOM() LIMIT ?",
                [
                    "camellia",
                    50,
                ],
            ),
        ),
        (
            [
                {"type": "difficulty_rating", "compare": ">", "value": 5},
                {"type": "creator", "compare": "=", "value": "camellia"},
            ],
            (
                "SELECT * FROM beatmapsets WHERE id IN (SELECT DISTINCT beatmapset_id FROM beatmaps WHERE difficulty_rating > ?) AND creator = ? ORDER BY RANDOM() LIMIT ?",
                [
                    5,
                    "camellia",
                    50,
                ],
            ),
        ),
        (
            [
                {"type": "nonexistingfilter", "compare": ">", "value": 5},
            ],
            ValueError("invalid filter type: nonexistingfilter"),
        ),
        (
            [
                {"type": "difficulty_rating", "compare": ">>", "value": 5},
            ],
            ValueError("invalid comparison operator: >>"),
        ),
        ([], ("SELECT * FROM beatmapsets ORDER BY RANDOM() LIMIT ?", [50])),
    ]

    for test_pair in test_pairs:
        if isinstance(test_pair[1], Exception):
            with pytest.raises(type(test_pair[1])) as excinfo:
                assert build_query(test_pair[0])
            assert str(test_pair[1]) == str(excinfo.value)
        else:
            assert build_query(test_pair[0]) == test_pair[1]
