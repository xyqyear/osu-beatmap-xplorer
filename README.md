# OSU Beatmaps Scraper and API

## Overview

This project is a web application that interacts with the OSU API to retrieve information about OSU Beatmaps and stores the data in a SQLite database. Additionally, it exposes an API endpoint for retrieving random beatmaps from the collected data.

The application is designed to be run continuously, with a regular update mechanism that pulls new data from the OSU API every hour, ensuring the database stays up to date with the latest available beatmaps. The application also checks for duplicates before storing the data, reducing unnecessary data storage and retrieval.

## Key Features

1. **Scraping OSU API**: The application authenticates and communicates with the OSU API to fetch details about the beatmaps.

2. **Storing Data**: Fetched data is stored in a SQLite database for persistence. The application uses a structured data model that includes relevant information about the beatmaps.

3. **Periodic Updates**: The application automatically re-fetches data from the OSU API every hour to update the database with any new beatmaps that have been added.

4. **Exposing API**: The application provides a RESTful API that returns a set of random beatmaps from the database. The number of beatmaps to be returned can be specified in the request.

## Running the Application

To run this application, make sure you have Python 3.11 and Poetry installed. Then, install the dependencies using Poetry:

```bash
poetry install --no-dev
```

Please note that this script requires a config.yml file in the same directory containing OSU client_id and client_secret for authenticating with the OSU API. Example config file:

```yaml
client_id: <client_id>
client_secret: <client_secret>
```

Once the dependencies are installed, you can run the application using the following command:

```bash
poetry run serve
```

## Accessing the API

Once the application is running, you can access the API by sending a GET request to `http://localhost/random_beatmaps/<num_beatmaps>`, where `<num_beatmaps>` is the number of random beatmaps you want to retrieve.

You can also add filters to your request with the filter_string query parameter. This parameter takes a comma-separated list of filter criteria, which follow the format `<field><operator><value>`. The `<field>` is the name of the field you want to filter by, `<operator>` is the comparison operator, and `<value>` is the value you want to compare the field against.

Supported operators are:

- = for exact equality,
- \> for greater than,
- < for less than,
- \>= for greater than or equal to,
- <= for less than or equal to,
- ~ for text field contains.

Here are some examples of filter_string:

`mode_int=0,difficulty_rating>5,difficulty_rating<6,text~"maimai"` will retrieve beatmaps with mode_int exactly 0, difficulty_rating between 5 and 6, and any text field contains "maimai".

`bpm>=180` will retrieve beatmaps with bpm greater than or equal to 180.

`text~"pop"` will retrieve beatmaps where any of the text fields (artist, artist_unicode, creator, source, tags) contains the word "pop".

An example API call with filtering might look like:

```url
http://localhost/random_beatmaps/50?filter_string=bpm>=180,text~"pop"
```

## TODO

- [x] basic functionality
- [x] use aiosqlite instead of sqlite3 so that database interactions are async and don't block the event loop
- [x] don't crash the program when retry limit is reached
- [x] add filtering options to the API
- [ ] mitigate SQL injection attacks

---

\* README is partially generated by GPT4.
