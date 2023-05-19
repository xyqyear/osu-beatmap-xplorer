import asyncio
import logging
import sqlite3
import time
import os

import yaml
from aiohttp import ClientSession, web, ClientResponseError

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
DB_NAME = "beatmaps.db"


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


def create_tables():
    # TODO: use aiosqlite
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute(
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
                     last_updated TEXT,
                     ranked_date TEXT,
                     submitted_date TEXT,
                     tags TEXT)"""
    )

    c.execute(
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
                     last_updated TEXT,
                     mode_int INTEGER,
                     checksum TEXT,
                     FOREIGN KEY (beatmapset_id) REFERENCES beatmapsets (id))"""
    )

    conn.commit()
    conn.close()


def store_beatmapsets(beatmapsets):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

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
            beatmapset["last_updated"],
            beatmapset["ranked_date"],
            beatmapset["submitted_date"],
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
                beatmap["last_updated"],
                beatmap["mode_int"],
                beatmap["checksum"],
            )

            beatmap_rows.append(beatmap_values)

    c.executemany(
        "INSERT OR IGNORE INTO beatmapsets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        beatmapset_rows,
    )

    c.executemany(
        "INSERT OR IGNORE INTO beatmaps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        beatmap_rows,
    )

    conn.commit()
    conn.close()


def beatmapsets_in_db(beatmapsets):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    id_list = [beatmapset["id"] for beatmapset in beatmapsets]

    placeholders = ", ".join("?" * len(id_list))
    c.execute(f"SELECT id FROM beatmapsets WHERE id IN ({placeholders})", id_list)

    ids_in_db = [item[0] for item in c.fetchall()]
    conn.close()

    result = [id_value in ids_in_db for id_value in id_list]

    return result


async def run_scraper(session):
    create_tables()

    with open("config.yml", "r") as f:
        config = yaml.safe_load(f)

    while True:
        logging.info("Authenticating...")

        auth_info = await authenticate(
            session, config["client_id"], config["client_secret"]
        )
        access_token = auth_info["access_token"]
        expires_in = auth_info["expires_in"]
        authenticate_time = time.time()
        cursor_string = None

        logging.info("Scraping...")
        beatmap_count = 0
        while True:
            if time.time() - authenticate_time > expires_in - 600:
                auth_info = await authenticate(
                    session, config["client_id"], config["client_secret"]
                )
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

            exist_in_db = beatmapsets_in_db(beatmapsets)
            num_exist = sum(exist_in_db)

            num_new = len(beatmapsets) - num_exist
            beatmap_count += num_new
            logging.info(f"Scraped {num_new} beatmapsets (total: {beatmap_count})")

            # if there is any beatmapset that already exists in the database,
            # we can stop scraping
            if num_exist > 0:
                logging.info("finished scraping")
                break

            store_beatmapsets(beatmapsets)

            cursor_string = data["cursor_string"]
            if not cursor_string:
                break

            await asyncio.sleep(2)

        # wait for 1 hour
        await asyncio.sleep(3600)


# For the API
async def random_beatmaps(request):
    num_beatmaps = int(request.match_info.get("num_beatmaps", "50"))

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("SELECT * FROM beatmaps ORDER BY RANDOM() LIMIT ?", (num_beatmaps,))

    beatmaps = c.fetchall()
    conn.close()

    return web.json_response(beatmaps)


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
