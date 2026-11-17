import argparse
import json
import re
from pathlib import Path

import pandas as pd
import pycountry


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "TMDB_all_movies.csv"

DATA_DIR = PROJECT_ROOT / "public" / "data"
COUNTRIES_DIR = DATA_DIR / "countries"

MIN_VOTES = 250
TOP_N = 50


# ============================================================
# Country / Language configuration
# ============================================================

# English-speaking production countries.
#
# These are used only as a language cross-check.
# They do NOT determine the movie's country.
ENGLISH_SPEAKING_COUNTRIES = {
    "US",
    "GB",
    "CA",
    "AU",
    "NZ",
    "IE",
}


# ============================================================
# Country / ISO helpers
# ============================================================


def build_country_map():
    """
    Build a normalized country-name -> ISO_A2 mapping.

    Example:

        United States -> US
        India         -> IN
        France        -> FR
    """

    country_map = {}

    for country in pycountry.countries:

        alpha2 = country.alpha_2

        names = {
            getattr(country, "name", ""),
            getattr(country, "official_name", ""),
            getattr(country, "common_name", ""),
        }

        for name in names:

            if name:
                country_map[name.strip().lower()] = alpha2

    # Common aliases / historical names that may appear in datasets.
    aliases = {
        "usa": "US",
        "u.s.a.": "US",
        "us": "US",
        "united states of america": "US",

        "uk": "GB",
        "u.k.": "GB",
        "united kingdom": "GB",

        "south korea": "KR",
        "republic of korea": "KR",
        "korea, republic of": "KR",

        "north korea": "KP",
        "democratic people's republic of korea": "KP",

        "russia": "RU",
        "russian federation": "RU",

        "iran": "IR",
        "iran, islamic republic of": "IR",

        "venezuela": "VE",
        "venezuela, bolivarian republic of": "VE",

        "bolivia": "BO",
        "bolivia, plurinational state of": "BO",

        "tanzania": "TZ",
        "united republic of tanzania": "TZ",

        "syria": "SY",
        "syrian arab republic": "SY",

        "moldova": "MD",
        "republic of moldova": "MD",

        "laos": "LA",
        "lao people's democratic republic": "LA",

        "brunei": "BN",
        "brunei darussalam": "BN",

        "czech republic": "CZ",
        "czechia": "CZ",

        "myanmar": "MM",
        "burma": "MM",

        "taiwan": "TW",
    }

    country_map.update(aliases)

    return country_map


COUNTRY_MAP = build_country_map()


def country_to_iso(country_name):
    """
    Convert a country name into ISO 3166-1 alpha-2.
    """

    if not country_name:
        return None

    country_name = str(country_name).strip()

    if not country_name:
        return None

    # Already an ISO code.
    if len(country_name) == 2:

        code = country_name.upper()

        try:
            pycountry.countries.get(alpha_2=code)
            return code

        except LookupError:
            pass

    normalized = country_name.lower()

    # Direct lookup from our map.
    if normalized in COUNTRY_MAP:
        return COUNTRY_MAP[normalized]

    # Final pycountry fuzzy lookup.
    try:

        result = pycountry.countries.search_fuzzy(country_name)

        if result:
            return result[0].alpha_2

    except LookupError:
        pass

    return None


# ============================================================
# Production country parser
# ============================================================


def parse_production_countries(value):
    """
    Handle production country data in multiple formats.

    Supported:

        ["United States", "United Kingdom"]

        '["United States", "United Kingdom"]'

        "United States, United Kingdom"

        "United States"

        [{"name": "United States"}, {"name": "France"}]
    """

    # --------------------------------------------------------
    # Already a Python list
    # --------------------------------------------------------

    if isinstance(value, list):

        countries = []

        for item in value:

            if isinstance(item, dict):

                name = (
                    item.get("name")
                    or item.get("country")
                    or item.get("country_name")
                )

                if name:
                    countries.append(str(name))

            elif isinstance(item, str):

                item = item.strip()

                if item:
                    countries.append(item)

        return countries

    # --------------------------------------------------------
    # Missing value
    # --------------------------------------------------------

    if value is None:
        return []

    if not isinstance(value, str) and pd.isna(value):
        return []

    value = str(value).strip()

    if not value:
        return []

    # --------------------------------------------------------
    # JSON-like values
    # --------------------------------------------------------

    try:

        parsed = json.loads(value)

        if isinstance(parsed, list):

            countries = []

            for item in parsed:

                if isinstance(item, dict):

                    name = (
                        item.get("name")
                        or item.get("country")
                        or item.get("country_name")
                    )

                    if name:
                        countries.append(str(name))

                elif isinstance(item, str):

                    item = item.strip()

                    if item:
                        countries.append(item)

            if countries:
                return countries

        elif isinstance(parsed, str):

            return [parsed]

    except (json.JSONDecodeError, TypeError):
        pass

    # --------------------------------------------------------
    # Python-list-like string
    # --------------------------------------------------------

    if value.startswith("[") and value.endswith("]"):

        value = value[1:-1]

        value = value.replace('"', "")
        value = value.replace("'", "")

    # --------------------------------------------------------
    # Comma / pipe / semicolon separated values
    # --------------------------------------------------------

    parts = re.split(r"\s*[,|;]\s*", value)

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


def get_primary_production_country(value):
    """
    Return only the primary production country.

    The first country in production_countries is treated
    as the primary production country.

    Example:

        ["United Kingdom", "United States", "India"]

    becomes:

        "United Kingdom"
    """

    countries = parse_production_countries(value)

    if not countries:
        return None

    return countries[0]


# ============================================================
# Language validation
# ============================================================


def normalize_language(value):
    """
    Normalize original_language values.

    Examples:

        "en"      -> "en"
        "EN"      -> "en"
        "English" -> "en"
    """

    if value is None:
        return ""

    if not isinstance(value, str) and pd.isna(value):
        return ""

    value = str(value).strip().lower()

    language_aliases = {
        "english": "en",
        "eng": "en",

        "hindi": "hi",
        "hin": "hi",

        "telugu": "te",
        "tam": "ta",

        "tamil": "ta",

        "malayalam": "ml",
        "mal": "ml",

        "kannada": "kn",
        "kan": "kn",

        "bengali": "bn",
        "ben": "bn",

        "korean": "ko",
        "kor": "ko",

        "japanese": "ja",
        "jpn": "ja",

        "french": "fr",
        "fra": "fr",
        "fre": "fr",

        "german": "de",
        "deu": "de",
        "ger": "de",

        "spanish": "es",
        "spa": "es",

        "italian": "it",
        "ita": "it",

        "portuguese": "pt",
        "por": "pt",

        "russian": "ru",
        "rus": "ru",

        "chinese": "zh",
        "zho": "zh",
        "chi": "zh",
    }

    return language_aliases.get(value, value)


def language_country_check(
    primary_iso,
    original_language,
    production_countries,
):
    """
    Cross-check the primary production country against
    the movie's original language.

    Important:

    1. Primary production country is authoritative.
    2. Language is only a validation signal.
    3. A sole/primary producer is never rejected simply
       because the movie is in English.
    4. English-language Hollywood/UK productions therefore
       remain associated with their primary producer.
    """

    if not primary_iso:
        return False

    language = normalize_language(original_language)

    # If language information is unavailable,
    # keep the movie.
    if not language:
        return True

    countries = parse_production_countries(
        production_countries
    )

    # A sole production country is always accepted.
    if len(countries) <= 1:
        return True

    # English-language movie + English-speaking primary
    # producer is a natural match.
    if (
        language == "en"
        and primary_iso in ENGLISH_SPEAKING_COUNTRIES
    ):
        return True

    # IMPORTANT:
    #
    # Do not reject a movie solely because its language
    # differs from the country's dominant language.
    #
    # Many countries produce English-language movies.
    #
    # The primary production country remains authoritative.
    return True


# ============================================================
# Text helpers
# ============================================================


def clean_text(value):

    if value is None:
        return ""

    if not isinstance(value, str) and pd.isna(value):
        return ""

    return str(value).strip()


def truncate_overview(value, max_length=140):
    """
    Keep overview small to reduce JSON size.
    """

    text = clean_text(value)

    if len(text) <= max_length:
        return text

    return text[: max_length - 1].rstrip() + "…"


def extract_year(value):

    if value is None:
        return None

    if not isinstance(value, str) and pd.isna(value):
        return None

    value = str(value).strip()

    match = re.match(r"(\d{4})", value)

    if match:
        return int(match.group(1))

    return None


# ============================================================
# Mock data
# ============================================================


def generate_mock_data():
    """
    Generate a small dataset so the frontend can be tested
    without having the real TMDB CSV.
    """

    print("Generating mock movie dataset...")

    mock_movies = [

        {
            "imdb_id": "tt0111161",
            "title": "The Shawshank Redemption",
            "overview": (
                "Two imprisoned men bond over years, "
                "finding solace and eventual redemption "
                "through acts of common decency."
            ),
            "production_countries": [
                "United States"
            ],
            "original_language": "en",
            "release_date": "1994-09-23",
            "imdb_rating": 9.3,
            "imdb_votes": 2900000,
            "poster_path": (
                "/9cqNxx0GxF0bflZmeSMuL5tnGzr.jpg"
            ),
        },

        {
            "imdb_id": "tt0468569",
            "title": "The Dark Knight",
            "overview": (
                "Batman faces a criminal mastermind whose "
                "reign of chaos pushes Gotham and its heroes."
            ),
            "production_countries": [
                "United States",
                "United Kingdom",
            ],
            "original_language": "en",
            "release_date": "2008-07-18",
            "imdb_rating": 9.0,
            "imdb_votes": 3100000,
            "poster_path": (
                "/qJ2tW6WMUDux911r6m7haRef0WH.jpg"
            ),
        },

        {
            "imdb_id": "tt6751668",
            "title": "Parasite",
            "overview": (
                "A poor family slowly enters the lives of "
                "a wealthy household, leading to unexpected events."
            ),
            "production_countries": [
                "South Korea"
            ],
            "original_language": "ko",
            "release_date": "2019-05-30",
            "imdb_rating": 8.5,
            "imdb_votes": 1000000,
            "poster_path": (
                "/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg"
            ),
        },

        {
            "imdb_id": "tt1375666",
            "title": "Inception",
            "overview": (
                "A skilled thief who steals corporate secrets "
                "through dream-sharing technology is given a chance "
                "to erase his past."
            ),
            "production_countries": [
                "United States",
                "United Kingdom",
            ],
            "original_language": "en",
            "release_date": "2010-07-16",
            "imdb_rating": 8.8,
            "imdb_votes": 2800000,
            "poster_path": (
                "/oYuLEt3zVCKq57qu2F8dT7NIa6f.jpg"
            ),
        },

        {
            "imdb_id": "tt0816692",
            "title": "Interstellar",
            "overview": (
                "Explorers travel through a wormhole in space "
                "in an attempt to ensure humanity's survival."
            ),
            "production_countries": [
                "United States",
                "United Kingdom",
            ],
            "original_language": "en",
            "release_date": "2014-11-07",
            "imdb_rating": 8.7,
            "imdb_votes": 2200000,
            "poster_path": (
                "/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg"
            ),
        },

        {
            "imdb_id": "tt0109830",
            "title": "Forrest Gump",
            "overview": (
                "The presidencies of Kennedy and Johnson unfold "
                "through the perspective of an Alabama man."
            ),
            "production_countries": [
                "United States"
            ],
            "original_language": "en",
            "release_date": "1994-07-06",
            "imdb_rating": 8.8,
            "imdb_votes": 2300000,
            "poster_path": (
                "/arw2vcBveWOVZr6pxd9XTd1TdQa.jpg"
            ),
        },

        # Test case for the original problem:
        # India appears as a secondary production country,
        # but should NOT receive the movie.
        {
            "imdb_id": "tt8579674",
            "title": "1917",
            "overview": (
                "Two young British soldiers are ordered to "
                "deliver a message across enemy territory."
            ),
            "production_countries": [
                "United Kingdom",
                "United States",
                "India",
            ],
            "original_language": "en",
            "release_date": "2019-12-25",
            "imdb_rating": 8.2,
            "imdb_votes": 700000,
            "poster_path": "",
        },
    ]

    return pd.DataFrame(mock_movies)


# ============================================================
# Load dataframe
# ============================================================


def load_data(use_mock=False):

    if use_mock:

        return generate_mock_data()

    if not INPUT_FILE.exists():

        raise FileNotFoundError(
            f"\nCSV file not found:\n{INPUT_FILE}\n\n"
            "Place TMDB_all_movies.csv in the project root "
            "or run with --mock."
        )

    print(f"Loading: {INPUT_FILE}")

    # Read only columns required by the application.
    required_columns = [
        "imdb_id",
        "title",
        "overview",
        "production_countries",
        "original_language",
        "release_date",
        "imdb_rating",
        "imdb_votes",
        "poster_path",
    ]

    df = pd.read_csv(
        INPUT_FILE,
        usecols=lambda column: column in required_columns,
        low_memory=False,
    )

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:

        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    return df


# ============================================================
# Main preparation
# ============================================================


def prepare_data(use_mock=False):

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    COUNTRIES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = load_data(use_mock)

    print(
        f"Initial rows: {len(df):,}"
    )

    # --------------------------------------------------------
    # Numeric cleanup
    # --------------------------------------------------------

    df["imdb_votes"] = pd.to_numeric(
        df["imdb_votes"],
        errors="coerce",
    )

    df["imdb_rating"] = pd.to_numeric(
        df["imdb_rating"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # Filter votes
    # --------------------------------------------------------

    df = df[
        df["imdb_votes"] >= MIN_VOTES
    ].copy()

    print(
        f"After votes >= {MIN_VOTES}: "
        f"{len(df):,}"
    )

    # --------------------------------------------------------
    # Sort globally
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "imdb_votes",
            "imdb_rating",
        ],
        ascending=[
            False,
            False,
        ],
    )

    # --------------------------------------------------------
    # Normalize fields
    # --------------------------------------------------------

    df["title"] = df["title"].map(
        clean_text
    )

    df["overview"] = df["overview"].map(
        truncate_overview
    )

    df["year"] = df["release_date"].map(
        extract_year
    )

    df["original_language"] = (
        df["original_language"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # --------------------------------------------------------
    # Select PRIMARY production country
    # --------------------------------------------------------

    print(
        "Selecting primary production countries..."
    )

    df["primary_country"] = (
        df["production_countries"]
        .map(get_primary_production_country)
    )

    # Remove movies without production country.
    df = df[
        df["primary_country"].notna()
    ].copy()

    print(
        f"Movies with primary country: "
        f"{len(df):,}"
    )

    # --------------------------------------------------------
    # Map primary country -> ISO_A2
    # --------------------------------------------------------

    print(
        "Mapping primary production countries "
        "to ISO-2 codes..."
    )

    df["iso"] = df["primary_country"].map(
        country_to_iso
    )

    unknown_countries = (
        df.loc[
            df["iso"].isna(),
            "primary_country",
        ]
        .dropna()
        .drop_duplicates()
        .tolist()
    )

    if unknown_countries:

        print(
            f"\nWarning: Could not map "
            f"{len(unknown_countries)} "
            f"primary country names."
        )

        print(
            "Examples:",
            unknown_countries[:20],
        )

    df = df[
        df["iso"].notna()
    ].copy()

    # --------------------------------------------------------
    # Language / production-country cross-check
    # --------------------------------------------------------

    print(
        "Running language / country validation..."
    )

    df["language_valid"] = df.apply(
        lambda row: language_country_check(
            row["iso"],
            row["original_language"],
            row["production_countries"],
        ),
        axis=1,
    )

    before_language_check = len(df)

    df = df[
        df["language_valid"]
    ].copy()

    removed_by_language = (
        before_language_check - len(df)
    )

    print(
        f"Language cross-check removed: "
        f"{removed_by_language:,}"
    )

    # --------------------------------------------------------
    # Prevent duplicate movie entries for the same country
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=[
            "iso",
            "imdb_id",
        ]
    )

    # --------------------------------------------------------
    # Create minified movie objects
    # --------------------------------------------------------

    # IMPORTANT:
    #
    # Keep this structure EXACTLY the same as the
    # existing frontend expects.
    #
    # i = IMDb ID
    # t = title
    # c = overview
    # y = year
    # r = rating
    # p = poster path

    df["movie"] = df.apply(
        lambda row: {
            "i": clean_text(
                row["imdb_id"]
            ),

            "t": clean_text(
                row["title"]
            ),

            "c": clean_text(
                row["overview"]
            ),

            "y": row["year"],

            "r": (
                round(
                    float(
                        row["imdb_rating"]
                    ),
                    1,
                )
                if pd.notna(
                    row["imdb_rating"]
                )
                else None
            ),

            "p": clean_text(
                row["poster_path"]
            ),
        },
        axis=1,
    )

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    counts_series = df.groupby(
        "iso"
    ).size()

    counts = {
        iso: int(count)
        for iso, count in counts_series.items()
    }

    counts_path = DATA_DIR / "counts.json"

    with counts_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            counts,
            file,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    print(
        f"\nCreated: {counts_path}"
    )

    print(
        f"Countries: {len(counts)}"
    )

    # --------------------------------------------------------
    # Country shards
    # --------------------------------------------------------

    print(
        "\nCreating country shards..."
    )

    for iso, country_df in df.groupby(
        "iso"
    ):

        # The dataframe is already globally sorted by:
        #
        # imdb_votes DESC
        # imdb_rating DESC

        movies = country_df[
            "movie"
        ].tolist()

        top_movies = movies[
            :TOP_N
        ]

        # --------------------------------------------
        # Top 50
        # --------------------------------------------

        top_path = (
            COUNTRIES_DIR
            / f"{iso}_top.json"
        )

        with top_path.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                top_movies,
                file,
                separators=(",", ":"),
                ensure_ascii=False,
            )

        # --------------------------------------------
        # Full shard only when > 50
        # --------------------------------------------

        if len(movies) > TOP_N:

            full_path = (
                COUNTRIES_DIR
                / f"{iso}_full.json"
            )

            with full_path.open(
                "w",
                encoding="utf-8",
            ) as file:

                json.dump(
                    movies,
                    file,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print(
        "\n" + "=" * 60
    )

    print(
        "DATA PREPARATION COMPLETE"
    )

    print(
        "=" * 60
    )

    print(
        f"Movies after filtering: "
        f"{df['imdb_id'].nunique():,}"
    )

    print(
        f"Country/movie relationships: "
        f"{len(df):,}"
    )

    print(
        f"Countries: "
        f"{len(counts):,}"
    )

    print(
        f"Output directory: "
        f"{DATA_DIR}"
    )

    print(
        "\nTop countries:"
    )

    for iso, count in sorted(
        counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )[:10]:

        print(
            f"  {iso}: {count:,}"
        )


# ============================================================
# CLI
# ============================================================


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Prepare static movie data "
            "for CineLokam."
        )
    )

    parser.add_argument(
        "--mock",
        action="store_true",
        help=(
            "Generate small mock data "
            "instead of reading TMDB CSV."
        ),
    )

    args = parser.parse_args()

    prepare_data(
        use_mock=args.mock
    )


if __name__ == "__main__":
    main()