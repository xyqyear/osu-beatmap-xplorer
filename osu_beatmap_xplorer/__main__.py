import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime
from functools import partial

import aiosqlite
import yaml
from aiohttp import ClientResponseError, ClientSession, web

logging.basicConfig(level=logging.INFO)

working_dir = os.environ.get("OSU_WORKING_DIR")
if working_dir:
    os.chdir(working_dir)

HOST = os.environ.get("OSU_HOST")
if not HOST:
    HOST = "localhost"
PORT = os.environ.get("OSU_PORT")
if not PORT:
    PORT = 80
elif PORT.isdigit():
    PORT = int(PORT)
else:
    logging.error("OSU_PORT must be an integer")
    exit(1)

DB_NAME = "beatmaps.db"


def date_string_to_timestamp(data_string):
    return datetime.strptime(data_string, "%Y-%m-%dT%H:%M:%SZ").timestamp()


async def post(session, url, headers, data):
    async with session.post(url, headers=headers, data=data) as response:
        response.raise_for_status()
        return await response.json()


async def get(session, url, headers):
    async with session.get(url, headers=headers) as response:
        response.raise_for_status()
        return await response.json()


async def try_request(session, mode, url, headers, data=None):
    retry_wait = 1
    while True:
        try:
            if mode == "post":
                return await post(session, url, headers, data)
            elif mode == "get":
                return await get(session, url, headers)
        except Exception as e:
            logging.warning(e)
            logging.warning(f"Retrying after {retry_wait} seconds")
            await asyncio.sleep(retry_wait)
            retry_wait *= 2


async def authenticate(session, client_id, client_secret):
    url = "https://osu.ppy.sh/oauth/token"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "public",
    }

    json_response = await try_request(session, "post", url, headers, data)

    return json_response


async def search_beatmaps(session, access_token, cursor_string=None):
    url = "https://osu.ppy.sh/api/v2/beatmapsets/search/"
    headers = {"Accept": "application/json", "Authorization": f"Bearer {access_token}"}

    if cursor_string:
        url += f"?s=ranked&cursor_string={cursor_string}"

    json_response = await try_request(session, "get", url, headers)

    return json_response


async def create_tables():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS beatmapsets (
                        id INTEGER PRIMARY KEY,
                        artist TEXT,
                        artist_unicode TEXT,
                        creator TEXT,
                        source TEXT,
                        spotlight INTEGER,
                        title TEXT,
                        title_unicode TEXT,
                        user_id INTEGER,
                        bpm REAL,
                        last_updated INTEGER,
                        ranked_date INTEGER,
                        submitted_date INTEGER,
                        tags TEXT)"""
        )
        await db.execute(
            """CREATE TABLE IF NOT EXISTS beatmaps (
                        id INTEGER PRIMARY KEY,
                        beatmapset_id INTEGER,
                        difficulty_rating REAL,
                        total_length INTEGER,
                        user_id INTEGER,
                        version TEXT,
                        accuracy REAL,
                        ar REAL,
                        bpm REAL,
                        convert INTEGER,
                        count_circles INTEGER,
                        count_sliders INTEGER,
                        count_spinners INTEGER,
                        cs REAL,
                        drain REAL,
                        hit_length INTEGER,
                        last_updated INTEGER,
                        mode_int INTEGER,
                        checksum TEXT,
                        FOREIGN KEY (beatmapset_id) REFERENCES beatmapsets (id))"""
        )
        await db.commit()


async def store_beatmapsets(beatmapsets):
    beatmapset_rows = list()
    beatmap_rows = list()

    for beatmapset in beatmapsets:
        beatmapset_values = (
            beatmapset["id"],
            beatmapset["artist"],
            beatmapset["artist_unicode"],
            beatmapset["creator"],
            beatmapset["source"],
            int(beatmapset["spotlight"]),
            beatmapset["title"],
            beatmapset["title_unicode"],
            beatmapset["user_id"],
            beatmapset["bpm"],
            date_string_to_timestamp(beatmapset["last_updated"]),
            date_string_to_timestamp(beatmapset["ranked_date"]),
            date_string_to_timestamp(beatmapset["submitted_date"]),
            beatmapset["tags"],
        )
        beatmapset_rows.append(beatmapset_values)

        for beatmap in beatmapset["beatmaps"]:
            beatmap_values = (
                beatmap["id"],
                beatmap["beatmapset_id"],
                beatmap["difficulty_rating"],
                beatmap["total_length"],
                beatmap["user_id"],
                beatmap["version"],
                beatmap["accuracy"],
                beatmap["ar"],
                beatmap["bpm"],
                int(beatmap["convert"]),
                beatmap["count_circles"],
                beatmap["count_sliders"],
                beatmap["count_spinners"],
                beatmap["cs"],
                beatmap["drain"],
                beatmap["hit_length"],
                date_string_to_timestamp(beatmap["last_updated"]),
                beatmap["mode_int"],
                beatmap["checksum"],
            )
            beatmap_rows.append(beatmap_values)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany(
            "INSERT OR IGNORE INTO beatmapsets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            beatmapset_rows,
        )
        await db.executemany(
            "INSERT OR IGNORE INTO beatmaps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            beatmap_rows,
        )
        await db.commit()


async def beatmapsets_in_db(beatmapsets):
    id_list = [beatmapset["id"] for beatmapset in beatmapsets]
    placeholders = ", ".join("?" * len(id_list))

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            f"SELECT id FROM beatmapsets WHERE id IN ({placeholders})", id_list
        ) as cursor:
            ids_in_db = [item[0] for item in await cursor.fetchall()]

    result = [id_value in ids_in_db for id_value in id_list]

    return result


async def run_scraper(session):
    await create_tables()

    if os.path.exists("config.yml"):
        with open("config.yml", "r") as f:
            config = yaml.safe_load(f)
            client_id = config["client_id"]
            client_secret = config["client_secret"]
    else:
        client_id = os.environ["CLIENT_ID"]
        client_secret = os.environ["CLIENT_SECRET"]

        if not client_id or not client_secret:
            logging.error("No config file or environment variables found.")
            exit(1)

    while True:
        logging.info("Authenticating...")

        auth_info = await authenticate(session, client_id, client_secret)
        access_token = auth_info["access_token"]
        expires_in = auth_info["expires_in"]
        authenticate_time = time.time()
        cursor_string = None

        logging.info("Scraping...")
        beatmap_count = 0
        while True:
            if time.time() - authenticate_time > expires_in - 600:
                auth_info = await authenticate(session, client_id, client_secret)
                access_token = auth_info["access_token"]
                expires_in = auth_info["expires_in"]
                authenticate_time = time.time()

            try:
                data = await search_beatmaps(session, access_token, cursor_string)
            except ClientResponseError as e:
                logging.warning(f"ClientResponseError: {e}")
                await asyncio.sleep(10)
                continue
            beatmapsets = data["beatmapsets"]

            exist_in_db = await beatmapsets_in_db(beatmapsets)
            num_exist = sum(exist_in_db)

            num_new = len(beatmapsets) - num_exist
            beatmap_count += num_new
            logging.info(f"Scraped {num_new} beatmapsets (total: {beatmap_count})")

            # if there is any beatmapset that already exists in the database,
            # we can stop scraping
            if num_exist > 0:
                logging.info("finished scraping")
                break

            await store_beatmapsets(beatmapsets)

            cursor_string = data["cursor_string"]
            if not cursor_string:
                break

            await asyncio.sleep(2)

        await asyncio.sleep(3600)


def parse_filter_string(filter_string):
    """
    parse a filter string like
    ```
    mode_int=0,difficulty_rating>5,difficulty_rating<6,text~"maimai"
    ```
    into what build_query() expects
    """
    if not filter_string:
        return []
    filter_items = filter_string.split(",")
    parsed_filter = []

    for item in filter_items:
        if "~" in item:
            type, compare, value = item.partition("~")
            parsed_filter.append(
                {"type": "text", "compare": compare, "value": value.strip('""')}
            )
        else:
            type, compare, value = re.split("(>=|<=|=|>|<)", item)
            parsed_filter.append(
                {
                    "type": type,
                    "compare": compare,
                    "value": int(value) if value.isdigit() else float(value),
                }
            )

    return parsed_filter


def build_query(filters, limit=50):
    """
    filter example:
    [
        {"type": "mode_int", "compare": "=", "value": 0},
        {"type": "difficulty_rating", "compare": ">", "value": 5},
        {"type": "difficulty_rating", "compare": "<", "value": 6},
        {"type": "text", "compare": "~", "value": "maimai"},
    ]
    """
    query = "SELECT * FROM beatmapsets"
    params = []
    text_filter = []

    if filters:
        query += " WHERE id IN (SELECT DISTINCT beatmapset_id FROM beatmaps WHERE "

        for filter_item in filters:
            if filter_item["type"] == "text":
                text_filter.append(filter_item["value"])
            else:
                query += "{} {} ? AND ".format(
                    filter_item["type"], filter_item["compare"]
                )
                params.append(filter_item["value"])

        # remove trailing "AND " and add closing parenthesis
        query = query[:-5] + ")"

        if text_filter:
            query += " AND ("
            for _ in text_filter:
                query += "artist LIKE ? OR artist_unicode LIKE ? OR creator LIKE ? OR source LIKE ? OR tags LIKE ? OR "
                params += ["%" + text + "%" for text in text_filter for _ in range(5)]
            # remove trailing "OR " and add closing parenthesis
            query = query[:-4] + ")"

    # limit and randomness are always applied
    query += " ORDER BY RANDOM() LIMIT ?"
    params.append(limit)

    return query, params


async def random_beatmaps(request):
    num_beatmaps = int(request.match_info.get("num_beatmaps", "50"))
    filter_string = request.rel_url.query.get("filter_string", "")
    query, params = build_query(parse_filter_string(filter_string), num_beatmaps)

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(query, params) as cursor:
            beatmapsets = [
                dict(zip([column[0] for column in cursor.description], row))
                for row in await cursor.fetchall()
            ]

        id_to_beatmapset = {beatmapset["id"]: beatmapset for beatmapset in beatmapsets}
        beatmapset_ids = [beatmapset["id"] for beatmapset in beatmapsets]
        placeholders = ", ".join("?" for _ in beatmapset_ids)

        async with db.execute(
            f"SELECT * FROM beatmaps WHERE beatmapset_id IN ({placeholders})",
            beatmapset_ids,
        ) as cursor:
            beatmaps = [
                dict(zip([desc[0] for desc in cursor.description], beatmap))
                for beatmap in await cursor.fetchall()
            ]

        for beatmap in beatmaps:
            beatmapset_id = beatmap["beatmapset_id"]
            beatmapset = id_to_beatmapset[beatmapset_id]
            beatmapset["beatmaps"] = beatmapset.get("beatmaps", []) + [beatmap]

    return web.json_response(beatmapsets, dumps=partial(json.dumps, ensure_ascii=False))


async def run():
    app = web.Application()
    app.add_routes([web.get("/random_beatmaps/{num_beatmaps}", random_beatmaps)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    async with ClientSession() as session:
        await run_scraper(session)


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
