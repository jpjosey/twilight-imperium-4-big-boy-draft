import hashlib
import streamlit as st
from supabase import create_client

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def hash_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

st.title("TI4 Big Boy Draft PoC")

players = sb.table("players").select("*").order("id").execute().data

main_tab, admin_tab = st.tabs(["Main", "Admin"])

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

with admin_tab:
    if st.button("CLEAR ALL"):
        sb.table("players").delete().neq("id", 0).execute()
        st.rerun()

    if st.button(f"PROCEED WITH {len(players)} PLAYERS"):
        pass  # placeholder
