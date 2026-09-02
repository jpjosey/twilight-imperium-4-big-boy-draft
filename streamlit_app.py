import hashlib
import json
from pathlib import Path

import streamlit as st
from supabase import create_client

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

TILE_DATA = Path("tiles/tiles.json")
IMAGE_DIR = Path("tiles/images")
ICON_DIR = Path("icons")


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


@st.cache_data
def load_tiles():
    tiles = json.loads(TILE_DATA.read_text())
    images = {}
    for p in IMAGE_DIR.glob("*.png"):
        num = p.stem.split("_")[0].lstrip("0")
        if num:
            images[num] = str(p)
    return tiles, images


def get_config(key, default):
    rows = sb.table("config").select("value").eq("key", key).execute().data
    return rows[0]["value"] if rows else default


def set_config(key, value):
    sb.table("config").upsert({"key": key, "value": value}).execute()


def tile_icons(t):
    icons = []
    icons += ["legendary.png"] * t["numlegendary"]
    icons += ["Cultural.png"] * t["numcultural"]
    icons += ["Hazardous.png"] * t["numhazardous"]
    icons += ["Industrial.png"] * t["numindustrial"]
    icons += ["yellowskip.png"] * t["numyellowskips"]
    icons +=
