import hashlib
import streamlit as st
from supabase import create_client

sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

def hash_pin(pin: str) -> str:
  return hashlib.sha256(pin.encode()).hexdigest()

st.title("TI4 Big Boy Draft POC")

players = sb.table("players").select("*").execute().data

if not players:
  st.subheader("New Game Setup")
  names - st.text_area("Player names (one per line)")
  if st.button("Create"):
    rows = [{"name": n.strip()} for n in names.splitlines() if n.strip()]
    if rows:
      sb.table("players").insert(rows).execute()
      st.rerun()
  st.stop()

# --- Already identified in this session ---
if "player_id" in st.session_state:
    me = next(p for p in players if p["id"] == st.session_state.player_id)
    st.success(f"You are **{me['name']}**")
    if st.button("Log out"):
        del st.session_state.player_id
        st.rerun()
    st.stop()

# --- Claim / login screen ---
st.subheader("Who are you?")
for p in players:
    with st.expander(p["name"]):
        if p["pin_hash"] is None:
            pin = st.text_input("Choose a PIN", type="password", key=f"set{p['id']}")
            if st.button("Claim", key=f"claim{p['id']}") and pin:
                sb.table("players").update({"pin_hash": hash_pin(pin)}).eq("id", p["id"]).execute()
                st.session_state.player_id = p["id"]
                st.rerun()
        else:
            pin = st.text_input("Enter your PIN", type="password", key=f"in{p['id']}")
            if st.button("Log in", key=f"login{p['id']}"):
                if hash_pin(pin) == p["pin_hash"]:
                    st.session_state.player_id = p["id"]
                    st.rerun()
                else:
                    st.error("Wrong PIN")
