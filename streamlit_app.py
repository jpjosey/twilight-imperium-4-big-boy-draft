import base64
import hashlib
import json
import random
from pathlib import Path

import streamlit as st
from supabase import create_client

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

TILE_DATA = Path("tiles/tiles.json")
IMAGE_DIR = Path("tiles")
ICON_DIR = Path("icons")

ICON_LABELS = {
    "legendary.png": "legendary",
    "Cultural.png": "cultural",
    "Hazardous.png": "hazardous",
    "Industrial.png": "industrial",
    "yellowskip.png": "yellow skip",
    "blueskip.png": "blue skip",
    "redskip.png": "red skip",
    "greenskip.png": "green skip",
    "WHalpha.png": "a-hole",
    "WHbeta.png": "b-hole",
}

DEFAULT_SLICE_SETTINGS = {
    "blueTiles": 3,
    "redTiles": 2,
    "MinWormholes": 0,
    "MaxWormholes": 99,
    "MinLegendary": 0,
    "MaxLegendary": 99,
    "MinRes": 0,
    "MaxRes": 99,
    "MinInf": 0,
    "MaxInf": 99,
    "MinOptRes": 0,
    "MaxOptRes": 99,
    "MinOptInf": 0,
    "MaxOptInf": 99,
    "MinOptTotal": 10,
    "MaxOptTotal": 14,
}

SUM_FIELDS = [
    "numalphawormholes", "numbetawormholes", "totalres", "totalinf",
    "optimalres", "optimalinf", "numyellowskips", "numblueskips",
    "numredskips", "numgreenskips", "numcultural", "numhazardous",
    "numindustrial", "numlegendary",
]


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


def load_icons():
    icons = {}
    for fname in ICON_LABELS:
        data = base64.b64encode((ICON_DIR / fname).read_bytes()).decode()
        icons[fname] = f"data:image/png;base64,{data}"
    return icons


def get_config(key, default):
    rows = sb.table("config").select("value").eq("key", key).execute().data
    return rows[0]["value"] if rows else default


def set_config(key, value):
    sb.table("config").upsert({"key": key, "value": value}).execute()


def tile_icon_files(t):
    files = []
    files += ["legendary.png"] * t["numlegendary"]
    files += ["Cultural.png"] * t["numcultural"]
    files += ["Hazardous.png"] * t["numhazardous"]
    files += ["Industrial.png"] * t["numindustrial"]
    files += ["yellowskip.png"] * t["numyellowskips"]
    files += ["blueskip.png"] * t["numblueskips"]
    files += ["redskip.png"] * t["numredskips"]
    files += ["greenskip.png"] * t["numgreenskips"]
    files += ["WHalpha.png"] * t["numalphawormholes"]
    files += ["WHbeta.png"] * t["numbetawormholes"]
    return files


def icon_row_html(t, icons):
    imgs = "".join(
        f'<img src="{icons[f]}" width="22" title="{ICON_LABELS[f]}" '
        f'style="margin-right:3px">'
        for f in tile_icon_files(t)
    )
    return f'<div style="height:26px">{imgs}</div>'


def slice_summary(tile_ids, tiles):
    total = {f: 0 for f in SUM_FIELDS}
    for tid in tile_ids:
        for f in SUM_FIELDS:
            total[f] += tiles[tid][f]
    return total


def weighted_sample(pool, weights, k):
    """Weighted sample of k items from pool without replacement."""
    pool = list(pool)
    w = [weights[t] for t in pool]
    picked = []
    for _ in range(k):
        total = sum(w)
        r = random.random() * total
        acc = 0.0
        for i, wt in enumerate(w):
            acc += wt
            if r <= acc:
                picked.append(pool.pop(i))
                w.pop(i)
                break
    return picked, pool


def slice_ok(tile_ids, tiles, s):
    t = slice_summary(tile_ids, tiles)
    wh = t["numalphawormholes"] + t["numbetawormholes"]
    opt_total = t["optimalres"] + t["optimalinf"]
    return (
        s["MinWormholes"] <= wh <= s["MaxWormholes"]
        and s["MinLegendary"] <= t["numlegendary"] <= s["MaxLegendary"]
        and s["MinRes"] <= t["totalres"] <= s["MaxRes"]
        and s["MinInf"] <= t["totalinf"] <= s["MaxInf"]
        and s["MinOptRes"] <= t["optimalres"] <= s["MaxOptRes"]
        and s["MinOptInf"] <= t["optimalinf"] <= s["MaxOptInf"]
        and s["MinOptTotal"] <= opt_total <= s["MaxOptTotal"]
    )


def generate_slices(tiles, weights, s, num_slices):
    blue_pool = [t for t in tiles if tiles[t]["back"] == "blue" and weights.get(t, 1) > 0]
    red_pool = [t for t in tiles if tiles[t]["back"] == "red" and weights.get(t, 1) > 0]

    need_blue = num_slices * s["blueTiles"]
    need_red = num_slices * s["redTiles"]
    if len(blue_pool) < need_blue:
        return None, f"Not enough blue tiles: need {need_blue}, have {len(blue_pool)} enabled."
    if len(red_pool) < need_red:
        return None, f"Not enough red tiles: need {need_red}, have {len(red_pool)} enabled."

    blues, reds = list(blue_pool), list(red_pool)
    slices = []
    for n in range(num_slices):
        for _ in range(5):
            cand_b, rest_b = weighted_sample(blues, weights, s["blueTiles"])
            cand_r, rest_r = weighted_sample(reds, weights, s["redTiles"])
            cand = cand_b + cand_r
            if slice_ok(cand, tiles, s):
                random.shuffle(cand)
                slices.append(cand)
                blues, reds = rest_b, rest_r
                break
        else:
            return None, (
                f"Slice {n + 1} failed after 5 attempts. "
                "Try again, loosen settings, or enable more tiles."
            )
    return slices, None

st.title("TI4 Big Boy Draft")

tiles, images = load_tiles()
icons = load_icons()
players = sb.table("players").select("*").order("id").execute().data

main_tab, tiles_tab, settings_tab = st.tabs(["Main", "Tiles", "Settings"])

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

    slices = get_config("slices", None)
    if slices:
        st.divider()
        st.subheader("SLICE POOL")
        for i, sl in enumerate(slices):
            st.markdown(f"**Slice {i + 1}**")
            cols = st.columns(len(sl))
            for col, tid in zip(cols, sl):
                with col:
                    if tid in images:
                        st.image(images[tid])
            summary = slice_summary(sl, tiles)
            st.markdown(icon_row_html(summary, icons), unsafe_allow_html=True)
            opt_total = summary["optimalres"] + summary["optimalinf"]
            st.markdown(
                f"Totals: :yellow[{summary['totalres']}] :blue[{summary['totalinf']}]  \n"
                f"Optimal: :yellow[{summary['optimalres']}] :blue[{summary['optimalinf']}]"
                f" (:green[{opt_total}] total)"
            )

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
                st.markdown(icon_row_html(t, icons), unsafe_allow_html=True)
                st.markdown(
                    f"Totals: :yellow[{t['totalres']}] :blue[{t['totalinf']}]  \n"
                    f"Optimal: :yellow[{t['optimalres']}] :blue[{t['optimalinf']}]"
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

with settings_tab:
    settings = get_config("slice_settings", DEFAULT_SLICE_SETTINGS)
    settings = {**DEFAULT_SLICE_SETTINGS, **settings}
    weights = get_config("tile_weights", {})

    if st.button("CLEAR ALL"):
        sb.table("players").delete().neq("id", 0).execute()
        sb.table("config").delete().eq("key", "slices").execute()
        st.rerun()

    min_slices = max(len(players), 1)
    num_slices = st.number_input(
        "Number of slices to generate",
        min_value=min_slices,
        step=1,
        value=int(settings.get("numSlices", len(players) + 2) or min_slices)
        if int(settings.get("numSlices", len(players) + 2)) >= min_slices
        else min_slices,
        key="s_numSlices",
    )

    if st.button(f"PROCEED WITH {len(players)} PLAYERS"):
        new_slices, err = generate_slices(
            tiles, {k: float(v) for k, v in weights.items()}, settings, int(num_slices)
        )
        if err:
            st.error(err)
        else:
            set_config("slices", new_slices)
            st.success(f"Generated {len(new_slices)} slices.")
            st.rerun()

    st.divider()
    st.subheader("Slice Settings")

    pairs = [
        ("MinWormholes", "MaxWormholes", "Wormholes"),
        ("MinLegendary", "MaxLegendary", "Legendaries"),
        ("MinRes", "MaxRes", "Total resources"),
        ("MinInf", "MaxInf", "Total influence"),
        ("MinOptRes", "MaxOptRes", "Optimal resources"),
        ("MinOptInf", "MaxOptInf", "Optimal influence"),
        ("MinOptTotal", "MaxOptTotal", "Optimal total"),
    ]

    c1, c2 = st.columns(2)
    with c1:
        st.number_input(
            "Blue tiles per slice", min_value=0, step=1,
            value=int(settings["blueTiles"]), key="s_blueTiles",
        )
    with c2:
        st.number_input(
            "Red tiles per slice", min_value=0, step=1,
            value=int(settings["redTiles"]), key="s_redTiles",
        )

    for min_key, max_key, label in pairs:
        c1, c2 = st.columns(2)
        with c1:
            st.number_input(
                f"Min {label}", min_value=0.0, step=0.5,
                value=float(settings[min_key]), key=f"s_{min_key}",
            )
        with c2:
            st.number_input(
                f"Max {label}", min_value=0.0, step=0.5,
                value=float(settings[max_key]), key=f"s_{max_key}",
            )

    if st.button("Save settings"):
        new_settings = {
            "blueTiles": st.session_state["s_blueTiles"],
            "redTiles": st.session_state["s_redTiles"],
            "numSlices": st.session_state["s_numSlices"],
        }
        for min_key, max_key, _ in pairs:
            new_settings[min_key] = st.session_state[f"s_{min_key}"]
            new_settings[max_key] = st.session_state[f"s_{max_key}"]
        bad = [
            lbl for mn, mx, lbl in pairs
            if new_settings[mn] > new_settings[mx]
        ]
        if bad:
            st.error(f"Min exceeds Max for: {', '.join(bad)}")
        else:
            set_config("slice_settings", new_settings)
            st.success("Settings saved.")
