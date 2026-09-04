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
FACTION_DATA = Path("factions/factions.json")

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
    "CommodityBonus.png": "trade station",
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
    "numindustrial", "numlegendary", "numtradestations",
]

PHASE_ACTIONS = {
    "faction_ban": "ban a faction",
    "faction_pick": "pick a faction",
    "turn_order": "pick a seat",
    "slice": "pick a slice",
}

BID_LABELS = {
    "bid_faction": "Faction",
    "bid_turn": "Turn Order",
    "bid_slice": "Slice",
}


# ----------------------------------------------------------------- data ----

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


def load_factions():
    return json.loads(FACTION_DATA.read_text())


def load_faction_icons(factions):
    out = {}
    for fid, f in factions.items():
        data = base64.b64encode(Path(f["icon"]).read_bytes()).decode()
        out[fid] = f"data:image/png;base64,{data}"
    return out


def get_config(key, default):
    rows = sb.table("config").select("value").eq("key", key).execute().data
    return rows[0]["value"] if rows else default


def set_config(key, value):
    sb.table("config").upsert({"key": key, "value": value}).execute()


def get_players():
    return sb.table("players").select("*").order("id").execute().data


def log(msg):
    sb.table("log").insert({"message": msg}).execute()


def log_many(msgs):
    if msgs:
        sb.table("log").insert([{"message": m} for m in msgs]).execute()


# ------------------------------------------------------------- rendering ----

def faction_name_html(f, icon_uri):
    img = f'<img src="{icon_uri}" width="24" style="vertical-align:middle">'
    return (
        f'<div style="text-align:center; min-height:34px; line-height:1.4; '
        f'padding-bottom:6px">'
        f'{img} <a href="{f["wiki"]}" target="_blank" '
        f'style="text-decoration:none">{f["name"]}</a> {img}'
        f'</div>'
    )


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
    files += ["CommodityBonus.png"] * t.get("numtradestations", 0)
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
            total[f] += tiles[tid].get(f, 0)
    return total


def show_slice(sl, tiles, images, icons):
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


# ------------------------------------------------------------ generation ----

def weighted_sample(pool, weights, k):
    """Weighted sample of k items from pool without replacement."""
    pool = list(pool)
    w = [float(weights.get(t, 1)) for t in pool]
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


def slice_violations(tile_ids, tiles, s):
    """Return a list of human-readable reasons this slice fails; empty = ok."""
    t = slice_summary(tile_ids, tiles)
    checks = [
        ("wormholes", t["numalphawormholes"] + t["numbetawormholes"],
         s["MinWormholes"], s["MaxWormholes"]),
        ("legendary", t["numlegendary"], s["MinLegendary"], s["MaxLegendary"]),
        ("res", t["totalres"], s["MinRes"], s["MaxRes"]),
        ("inf", t["totalinf"], s["MinInf"], s["MaxInf"]),
        ("optres", t["optimalres"], s["MinOptRes"], s["MaxOptRes"]),
        ("optinf", t["optimalinf"], s["MinOptInf"], s["MaxOptInf"]),
        ("opttotal", t["optimalres"] + t["optimalinf"],
         s["MinOptTotal"], s["MaxOptTotal"]),
    ]
    return [
        f"{name}={val:g} outside [{lo:g},{hi:g}]"
        for name, val, lo, hi in checks
        if not lo <= val <= hi
    ]


def slice_ok(tile_ids, tiles, s):
    return not slice_violations(tile_ids, tiles, s)


def generate_slices(tiles, weights, s, num_slices):
    trace = []
    blue_pool = [t for t in tiles if tiles[t]["back"] == "blue" and weights.get(t, 1) > 0]
    red_pool = [t for t in tiles if tiles[t]["back"] == "red" and weights.get(t, 1) > 0]
    no_back = [t for t in tiles if tiles[t]["back"] not in ("blue", "red")]

    trace.append(
        f"SLICEGEN: {len(blue_pool)} blue / {len(red_pool)} red enabled, "
        f"{len(no_back)} tiles with no back"
        + (f" ({', '.join(sorted(no_back, key=int))})" if no_back else "")
    )
    trace.append(
        f"SLICEGEN: want {num_slices} slices of {s['blueTiles']}B+{s['redTiles']}R; "
        f"limits opttotal [{s['MinOptTotal']:g},{s['MaxOptTotal']:g}] "
        f"optres [{s['MinOptRes']:g},{s['MaxOptRes']:g}] "
        f"optinf [{s['MinOptInf']:g},{s['MaxOptInf']:g}] "
        f"res [{s['MinRes']:g},{s['MaxRes']:g}] inf [{s['MinInf']:g},{s['MaxInf']:g}] "
        f"wh [{s['MinWormholes']:g},{s['MaxWormholes']:g}] "
        f"leg [{s['MinLegendary']:g},{s['MaxLegendary']:g}]"
    )

    need_blue = num_slices * s["blueTiles"]
    need_red = num_slices * s["redTiles"]
    if len(blue_pool) < need_blue:
        trace.append(f"SLICEGEN: FAILED - need {need_blue} blue, have {len(blue_pool)}")
        return None, f"Not enough blue tiles: need {need_blue}, have {len(blue_pool)} enabled.", trace
    if len(red_pool) < need_red:
        trace.append(f"SLICEGEN: FAILED - need {need_red} red, have {len(red_pool)}")
        return None, f"Not enough red tiles: need {need_red}, have {len(red_pool)} enabled.", trace

    blues, reds = list(blue_pool), list(red_pool)
    slices = []
    for n in range(num_slices):
        for attempt in range(1, 6):
            cand_b, rest_b = weighted_sample(blues, weights, s["blueTiles"])
            cand_r, rest_r = weighted_sample(reds, weights, s["redTiles"])
            cand = cand_b + cand_r
            bad = slice_violations(cand, tiles, s)
            summ = slice_summary(cand, tiles)
            desc = (
                f"tiles {'+'.join(cand)} "
                f"res {summ['totalres']:g} inf {summ['totalinf']:g} "
                f"opt {summ['optimalres']:g}/{summ['optimalinf']:g} "
                f"= {summ['optimalres'] + summ['optimalinf']:g}"
            )
            if not bad:
                trace.append(f"SLICEGEN: slice {n + 1} ok on try {attempt} - {desc}")
                random.shuffle(cand)
                slices.append(cand)
                blues, reds = rest_b, rest_r
                break
            trace.append(
                f"SLICEGEN: slice {n + 1} try {attempt} rejected - {desc} "
                f"[{'; '.join(bad)}]"
            )
        else:
            trace.append(
                f"SLICEGEN: FAILED at slice {n + 1}; "
                f"{len(blues)} blue / {len(reds)} red left in pool"
            )
            return None, (
                f"Slice {n + 1} failed after 5 attempts. "
                "Try again, loosen settings, or enable more tiles. See the Log tab."
            ), trace
    trace.append(f"SLICEGEN: success, {len(slices)} slices generated")
    return slices, None, trace


def draw_factions(factions, fweights, num_safe, num_maybe):
    pool = [f for f in factions if float(fweights.get(f, 1)) > 0]
    need = num_safe + num_maybe
    if len(pool) < need:
        return None, None, f"Not enough factions: need {need}, have {len(pool)} enabled."
    drawn, _ = weighted_sample(pool, fweights, need)
    return drawn[:num_safe], drawn[num_safe:], None


# ----------------------------------------------------------------- draft ----

def resolve_order(players, bid_field):
    """Highest bid first; ties broken by dice roll (logged)."""
    groups = {}
    for p in players:
        groups.setdefault(p[bid_field] or 0, []).append(p)
    order = []
    for bid in sorted(groups, reverse=True):
        grp = groups[bid]
        if len(grp) == 1:
            order.append(grp[0]["id"])
            continue
        while True:
            rolls = {p["id"]: random.randint(1, 100) for p in grp}
            if len(set(rolls.values())) == len(grp):
                break
        detail = ", ".join(f"{p['name']} rolled {rolls[p['id']]}" for p in grp)
        winner_order = sorted(grp, key=lambda p: -rolls[p["id"]])
        log(
            f"Tie-break on {BID_LABELS[bid_field]} bid of {bid}: {detail} "
            f"-> {', '.join(p['name'] for p in winner_order)}"
        )
        order += [p["id"] for p in winner_order]
    return order


def reveal_bids(players, state):
    order_f = resolve_order(players, "bid_faction")
    order_t = resolve_order(players, "bid_turn")
    order_s = resolve_order(players, "bid_slice")

    totals = {
        p["id"]: (p["bid_faction"] or 0) + (p["bid_turn"] or 0) + (p["bid_slice"] or 0)
        for p in players
    }
    top = max(totals.values()) if totals else 0

    state["schedule"] = (
        [["faction_ban", pid] for pid in order_f]
        + [["faction_pick", pid] for pid in order_f]
        + [["turn_order", pid] for pid in order_t]
        + [["slice", pid] for pid in order_s]
    )
    state["step"] = 0
    state["revealed"] = True
    state["bonus_tg"] = {str(pid): top - t for pid, t in totals.items()}

    log("All players locked in. Bids revealed.")
    for p in players:
        log(
            f"{p['name']} bid F{p['bid_faction'] or 0} / T{p['bid_turn'] or 0} / "
            f"S{p['bid_slice'] or 0} (total {totals[p['id']]}) "
            f"-> {top - totals[p['id']]} bonus TG"
        )
    return state


def current_entry(state):
    sched = state.get("schedule") or []
    step = state.get("step", 0)
    return sched[step] if step < len(sched) else None


def describe(entry, pmap):
    if not entry:
        return "draft complete"
    phase, pid = entry
    return f"{pmap.get(pid, '?')} to {PHASE_ACTIONS[phase]}"


def commit(state, expected_step, message):
    """Write state back only if nobody else moved first."""
    live = get_config("draft_state", None)
    if not live or live.get("step") != expected_step:
        st.warning("Someone beat you to it - reloading.")
        st.rerun()
        return
    state["step"] = expected_step + 1
    set_config("draft_state", state)
    log(message)
    st.rerun()


# ------------------------------------------------------------------- app ----

st.title("TI4 Big Boy Draft")

tiles, images = load_tiles()
icons = load_icons()
factions = load_factions()
faction_icons = load_faction_icons(factions)
players = get_players()
pmap = {p["id"]: p["name"] for p in players}
state = get_config("draft_state", None)

# late reveal guard: everyone locked but reveal never ran
if state and not state.get("revealed") and players and all(p["locked"] for p in players):
    state = reveal_bids(players, state)
    set_config("draft_state", state)

# --- sidebar login ---
with st.sidebar:
    st.header("Who are you?")
    me = None
    if "player_id" in st.session_state:
        me = next((p for p in players if p["id"] == st.session_state.player_id), None)
    if me:
        st.success(f"You are **{me['name']}**")
        if st.button("Log out"):
            del st.session_state.player_id
            st.rerun()
    elif players:
        name = st.selectbox("Name", [p["name"] for p in players])
        pin = st.text_input("PIN", type="password", key="login_pin")
        if st.button("Log in"):
            p = next(p for p in players if p["name"] == name)
            if p["pin_hash"] == hash_pin(pin):
                st.session_state.player_id = p["id"]
                st.rerun()
            else:
                st.error("Wrong PIN")
    else:
        st.write("Nobody has signed up yet.")

main_tab, tiles_tab, factions_tab, settings_tab, log_tab = st.tabs(
    ["Main", "Tiles", "Factions", "Settings", "Log"]
)

with main_tab:
    slices = get_config("slices", None)

    # ---------------------------------------------------- pre-draft ----
    if not state:
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
                    log(f"{name.strip()} signed up.")
                    st.rerun()

    # -------------------------------------------------------- draft ----
    else:
        assign = state.get("assignments", {})
        n = len(players)

        st.subheader("Players")
        cols = st.columns(max(n, 1))
        for col, p in zip(cols, players):
            a = assign.get(str(p["id"]), {})
            with col:
                st.markdown(f"**{p['name']}**")
                if not state.get("revealed"):
                    st.write("locked in" if p["locked"] else "_thinking..._")
                else:
                    st.caption(
                        f"bids F{p['bid_faction'] or 0} / T{p['bid_turn'] or 0} / "
                        f"S{p['bid_slice'] or 0}"
                    )
                    st.caption(f"+{state['bonus_tg'].get(str(p['id']), 0)} TG")
                    if a.get("faction"):
                        f = factions[a["faction"]]
                        st.markdown(
                            faction_name_html(f, faction_icons[a["faction"]]),
                            unsafe_allow_html=True,
                        )
                    if a.get("seat"):
                        st.write(f"Seat {a['seat']}")
                    if a.get("slice") is not None:
                        st.write(f"Slice {a['slice'] + 1}")

        st.divider()

        # ------------------------------------------------ bidding ----
        if not state.get("revealed"):
            st.subheader("Secret bids")
            st.caption(
                "Everything you are bidding on is shown below. "
                "Nobody sees anybody's bids until everyone has locked in."
            )
            if me is None:
                st.info("Log in via the sidebar to place your bids.")
            elif me["locked"]:
                st.success("You are locked in. Waiting for the others.")
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    bf = st.number_input("Faction bid", min_value=0, step=1, value=0)
                    st.caption(
                        "Highest bidder bans a faction first and lowest bans last. "
                        "Then, in that same order, highest picks their faction first "
                        "and lowest picks last."
                    )
                with c2:
                    bt = st.number_input("Turn order bid", min_value=0, step=1, value=0)
                    st.caption(
                        "Highest bidder picks their seat first and lowest picks last. "
                        "Seat 1 is the speaker."
                    )
                with c3:
                    bs = st.number_input("Slice bid", min_value=0, step=1, value=0)
                    st.caption(
                        "Highest bidder picks their slice first and lowest picks last."
                    )
                st.caption(
                    "You can only lock in once. Bonus trade goods = "
                    "(highest total bids of anyone) minus (your total bid)."
                    "Ties will be broken by a dice roll (visible in the log tab).
                )
                if st.button("LOCK IN"):
                    sb.table("players").update(
                        {
                            "bid_faction": int(bf),
                            "bid_turn": int(bt),
                            "bid_slice": int(bs),
                            "locked": True,
                        }
                    ).eq("id", me["id"]).execute()
                    log(f"{me['name']} locked in their bids.")
                    fresh = get_players()
                    if all(p["locked"] for p in fresh):
                        set_config("draft_state", reveal_bids(fresh, state))
                    st.rerun()

            entry = None
            nxt = None
            step = 0
            phase = None
            my_turn = False

        # ------------------------------------------------ drafting ----
        else:
            entry = current_entry(state)
            sched = state["schedule"]
            step = state["step"]
            nxt = sched[step + 1] if step + 1 < len(sched) else None

            if entry is None:
                st.header("DRAFT COMPLETE")

            st.subheader("Draft order")
            rows = []
            for i, (ph, pid) in enumerate(state.get("schedule", [])):
                text = f"{i + 1}. {pmap.get(pid, '?')} - {PHASE_ACTIONS[ph]}"
                if i < step:
                    rows.append(
                        f'<div style="opacity:0.35; line-height:1.6">{text}</div>'
                    )
                elif i == step:
                    rows.append(
                        f'<div style="font-size:1.5em; font-weight:700; '
                        f'line-height:1.6; margin:4px 0">&#9654; {text}</div>'
                    )
                else:
                    rows.append(f'<div style="line-height:1.6">{text}</div>')
            st.markdown("".join(rows), unsafe_allow_html=True)

            phase = entry[0] if entry else None
            my_turn = bool(me and entry and entry[1] == me["id"])

        # ------------------------------- pools (always visible) ----
        # --- factions ---
        st.divider()
        st.subheader("FACTIONS")

        if state.get("maybe"):
            st.markdown("**Maybe pool**")
            mcols = st.columns(min(len(state["maybe"]), 5))
            for i, fid in enumerate(state["maybe"]):
                f = factions[fid]
                with mcols[i % len(mcols)]:
                    st.image(f["quickref"])
                    st.markdown(
                        faction_name_html(f, faction_icons[fid]),
                        unsafe_allow_html=True,
                    )
                    if my_turn and phase == "faction_ban":
                        if st.button("BAN", key=f"ban{fid}"):
                            s2 = dict(state)
                            s2["maybe"] = [x for x in state["maybe"] if x != fid]
                            s2["banned"] = state.get("banned", []) + [fid]
                            # last ban of the phase: survivors join the pool
                            if not nxt or nxt[0] != "faction_ban":
                                s2["pool"] = state["pool"] + s2["maybe"]
                                s2["maybe"] = []
                            commit(
                                s2, step,
                                f"{me['name']} banned {f['name']}.",
                            )

        st.markdown("**Faction pool**")
        pool = state.get("pool", [])
        if pool:
            pcols = st.columns(min(len(pool), 5))
            for i, fid in enumerate(pool):
                f = factions[fid]
                with pcols[i % len(pcols)]:
                    st.image(f["quickref"])
                    st.markdown(
                        faction_name_html(f, faction_icons[fid]),
                        unsafe_allow_html=True,
                    )
                    if my_turn and phase == "faction_pick":
                        if st.button("PICK", key=f"pick{fid}"):
                            s2 = dict(state)
                            s2["pool"] = [x for x in pool if x != fid]
                            a2 = dict(state.get("assignments", {}))
                            mine = dict(a2.get(str(me["id"]), {}))
                            mine["faction"] = fid
                            a2[str(me["id"])] = mine
                            s2["assignments"] = a2
                            commit(
                                s2, step,
                                f"{me['name']} picked {f['name']}.",
                            )
        else:
            st.caption("empty")

        if state.get("banned"):
            st.markdown("**Banned**")
            bcols = st.columns(min(len(state["banned"]), 5))
            for i, fid in enumerate(state["banned"]):
                with bcols[i % len(bcols)]:
                    st.markdown(
                        faction_name_html(factions[fid], faction_icons[fid]),
                        unsafe_allow_html=True,
                    )

        # --- turn order ---
        st.divider()
        st.subheader("TURN ORDER")
        scols = st.columns(n)
        for i, seat in enumerate(range(1, n + 1)):
            with scols[i]:
                label = "Speaker" if seat == 1 else f"Seat {seat}"
                st.markdown(f"**{label}**")
                owner = next(
                    (pmap[int(k)] for k, a in assign.items() if a.get("seat") == seat),
                    None,
                )
                if owner:
                    st.write(owner)
                elif my_turn and phase == "turn_order":
                    if st.button("PICK", key=f"seat{seat}"):
                        s2 = dict(state)
                        a2 = dict(state.get("assignments", {}))
                        mine = dict(a2.get(str(me["id"]), {}))
                        mine["seat"] = seat
                        a2[str(me["id"])] = mine
                        s2["assignments"] = a2
                        commit(s2, step, f"{me['name']} took seat {seat}.")
                else:
                    st.caption("open")

        # --- slices ---
        st.divider()
        st.subheader("SLICE POOL")
        for i, sl in enumerate(slices or []):
            owner = next(
                (pmap[int(k)] for k, a in assign.items() if a.get("slice") == i),
                None,
            )
            st.markdown(f"**Slice {i + 1}**" + (f" - {owner}" if owner else ""))
            show_slice(sl, tiles, images, icons)
            if owner is None and my_turn and phase == "slice":
                if st.button("PICK", key=f"slice{i}"):
                    s2 = dict(state)
                    a2 = dict(state.get("assignments", {}))
                    mine = dict(a2.get(str(me["id"]), {}))
                    mine["slice"] = i
                    a2[str(me["id"])] = mine
                    s2["assignments"] = a2
                    commit(s2, step, f"{me['name']} took slice {i + 1}.")
            st.divider()

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

with factions_tab:
    fweights = get_config("faction_weights", {})
    fids = sorted(factions.keys(), key=lambda k: factions[k]["name"])

    PER_ROW = 3
    for i in range(0, len(fids), PER_ROW):
        cols = st.columns(PER_ROW)
        for col, fid in zip(cols, fids[i : i + PER_ROW]):
            f = factions[fid]
            with col:
                st.image(f["quickref"])
                st.markdown(
                    faction_name_html(f, faction_icons[fid]),
                    unsafe_allow_html=True,
                )
                st.number_input(
                    "weight",
                    min_value=0.0,
                    step=0.5,
                    value=float(fweights.get(fid, 1)),
                    key=f"fw{fid}",
                    label_visibility="collapsed",
                )

    if st.button("Save faction weights"):
        new_fweights = {fid: st.session_state[f"fw{fid}"] for fid in fids}
        set_config("faction_weights", new_fweights)
        st.success("Faction weights saved.")

with settings_tab:
    settings = get_config("slice_settings", DEFAULT_SLICE_SETTINGS)
    settings = {**DEFAULT_SLICE_SETTINGS, **settings}
    weights = get_config("tile_weights", {})
    fweights = get_config("faction_weights", {})
    n = len(players)

    if st.button("CLEAR ALL"):
        sb.table("players").delete().neq("id", 0).execute()
        sb.table("config").delete().eq("key", "slices").execute()
        sb.table("config").delete().eq("key", "draft_state").execute()
        sb.table("log").delete().neq("id", 0).execute()
        st.session_state.pop("player_id", None)
        st.rerun()

    if state:
        st.info("A draft is in progress. CLEAR ALL resets everything.")
    else:
        min_slices = max(n, 1)
        stored = int(settings.get("numSlices", n + 2) or min_slices)
        num_slices = st.number_input(
            "Number of slices to generate",
            min_value=min_slices,
            step=1,
            value=max(stored, min_slices),
            key="s_numSlices",
        )
        c1, c2 = st.columns(2)
        with c1:
            num_safe = st.number_input(
                "Number of safe factions", min_value=0, step=1,
                value=int(settings.get("numSafeFactions", 2)), key="s_numSafe",
            )
        with c2:
            num_maybe = st.number_input(
                "Number of maybe factions (before bans)", min_value=0, step=1,
                value=int(settings.get("numMaybeFactions", 2 * n)), key="s_numMaybe",
            )

        if st.button(f"BEGIN DRAFT WITH {n} PLAYERS"):
            if n < 1:
                st.error("Nobody has signed up.")
            else:
                new_slices, err, trace = generate_slices(
                    tiles, weights, settings, int(num_slices)
                )
                log_many(trace)
                if err:
                    st.error(err)
                else:
                    safe, maybe, ferr = draw_factions(
                        factions, fweights, int(num_safe), int(num_maybe)
                    )
                    if ferr:
                        st.error(ferr)
                    else:
                        sb.table("players").update(
                            {
                                "bid_faction": 0, "bid_turn": 0,
                                "bid_slice": 0, "locked": False,
                            }
                        ).neq("id", 0).execute()
                        set_config("slices", new_slices)
                        set_config(
                            "draft_state",
                            {
                                "revealed": False,
                                "pool": safe,
                                "maybe": maybe,
                                "banned": [],
                                "assignments": {},
                                "schedule": [],
                                "step": 0,
                                "bonus_tg": {},
                            },
                        )
                        log(
                            f"Draft begun with {n} players, {len(new_slices)} slices, "
                            f"{len(safe)} safe / {len(maybe)} maybe factions."
                        )
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
        }
        if not state:
            new_settings["numSlices"] = st.session_state["s_numSlices"]
            new_settings["numSafeFactions"] = st.session_state["s_numSafe"]
            new_settings["numMaybeFactions"] = st.session_state["s_numMaybe"]
        for min_key, max_key, _ in pairs:
            new_settings[min_key] = st.session_state[f"s_{min_key}"]
            new_settings[max_key] = st.session_state[f"s_{max_key}"]
        bad = [lbl for mn, mx, lbl in pairs if new_settings[mn] > new_settings[mx]]
        if bad:
            st.error(f"Min exceeds Max for: {', '.join(bad)}")
        else:
            set_config("slice_settings", {**settings, **new_settings})
            st.success("Settings saved.")

with log_tab:
    rows = sb.table("log").select("*").order("id", desc=True).limit(300).execute().data
    if not rows:
        st.write("Nothing logged yet.")
    for r in rows:
        st.text(f"{r['ts'][11:19]}  {r['message']}")
