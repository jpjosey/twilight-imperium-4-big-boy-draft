import hashlib
import json
from pathlib import Path

import streamlit as st
from supabase import create_client

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

TILE_DATA = Path("tiles/tiles.json")
IMAGE_DIR = Path("tiles")
ICON_DIR = Path("icons")


def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()


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
    icons += ["blueskip.png"] * t["numblueskips"]
    icons += ["redskip.png"] * t["numredskips"]
    icons += ["greenskip.png"] * t["numgreenskips"]
    icons += ["WHalpha.png"] * t["numalphawormholes"]
    icons += ["WHbeta.png"] * t["numbetawormholes"]
    return [str(ICON_DIR / i) for i in icons]


st.title("Milty Draft PoC")

tiles, images = load_tiles()
players = sb.table("players").select("*").order("id").execute().data

main_tab, tiles_tab, admin_tab = st.tabs(["Main", "Tiles", "Admin"])

with main_tab:
    st.subheader("Sign-up sheet")
    if players:
        for p in players:
            st.write(f"- {p['name']}")
    else:
        st.write("Nobody signed up yet.")

    with st.form("signup"):
        st.subheader("Sign up")
        name = st.text_input("Name")
        pin = st.text_input("PIN", type="password")
        if st.form_submit_button("Sign up"):
            if not name.strip() or not pin:
                st.error("Name and PIN are both required.")
            elif any(p["name"].lower() == name.strip().lower() for p in players):
                st.error("That name is already taken.")
            else:
                sb.table("players").insert(
                    {"name": name.strip(), "pin_hash": hash_pin(pin)}
                ).execute()
                st.rerun()

with tiles_tab:
    weights = get_config("tile_weights", {})
    tile_ids = sorted(tiles.keys(), key=int)

    PER_ROW = 6
    for i in range(0, len(tile_ids), PER_ROW):
        cols = st.columns(PER_ROW)
        for col, tid in zip(cols, tile_ids[i : i + PER_ROW]):
            t = tiles[tid]
            with col:
                if tid in images:
                    st.image(images[tid])
                else:
                    st.write(f"(no image {tid})")
                icons = tile_icons(t)
                if icons:
                    st.image(icons, width=22)
                st.caption(
                    f"{t['totalres']}/{t['totalinf']} tot · "
                    f"{t['optimalres']}/{t['optimalinf']} opt"
                )
                st.number_input(
                    "weight",
                    min_value=0.0,
                    step=0.5,
                    value=float(weights.get(tid, 1)),
                    key=f"w{tid}",
                    label_visibility="collapsed",
                )

    if st.button("Save weights"):
        new_weights = {tid: st.session_state[f"w{tid}"] for tid in tile_ids}
        set_config("tile_weights", new_weights)
        st.success("Weights saved.")

with admin_tab:
    if st.button("CLEAR ALL"):
        sb.table("players").delete().neq("id", 0).execute()
        st.rerun()

    if st.button(f"PROCEED WITH {len(players)} PLAYERS"):
        pass  # placeholder
