import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Supabase config


SUPABASE_URL = "https://vphtpzlbdcotorqpuonr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZwaHRwemxiZGNvdG9ycXB1b25yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU1MDg0OTcsImV4cCI6MjA2MTA4NDQ5N30.XTP7clV__5ZVp9hZCJ2eGhL7HgEUeTcl2uINX0JC9WI"
SUPABASE_BUCKET = "bidding-projects"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Bidding Dashboard", layout="wide")
st.title("🕷️ Aiva Crawler | Dashboard")

# Fetch data
@st.cache_data
def fetch_data():
    data = supabase.table("BiddingDB").select("*").execute().data
    return pd.DataFrame(data)

df = fetch_data()

if df.empty:
    st.warning("No bidding data found.")
    st.stop()

# --- Sidebar Filters ---
with st.sidebar:
    st.header("🔍 Filter Bids")

    entity_filter = st.selectbox("Entity", options=["All"] + sorted(df["Entity"].dropna().unique().tolist()))
    category_filter = st.selectbox("Category", options=["All"] + sorted(df["category"].dropna().unique().tolist()))
    status_filter = st.selectbox("Status", options=["All"] + sorted(df["Status"].dropna().unique().tolist()))
    classification_filter = st.selectbox("Classification", options=["All"] + sorted(df["Classification"].dropna().unique().tolist()))

# --- Apply Filters ---
filtered_df = df.copy()
if entity_filter != "All":
    filtered_df = filtered_df[filtered_df["Entity"] == entity_filter]
if category_filter != "All":
    filtered_df = filtered_df[filtered_df["category"] == category_filter]
if status_filter != "All":
    filtered_df = filtered_df[filtered_df["Status"] == status_filter]
if classification_filter != "All":
    filtered_df = filtered_df[filtered_df["Classification"] == classification_filter]

# --- Display Table ---
st.markdown("### 📄 Filtered Bidding Data")
selected_row = st.dataframe(filtered_df, use_container_width=True)

# --- Modal-like Card View ---
st.markdown("---")
st.markdown("### 🔍 View Record Details")

record_id = st.text_input("Enter record Reference No. to view", "")
record = None

if record_id:
    try:
        record = df[df["ReferenceNo"] == record_id].iloc[0]
        with st.expander("📌 Record Details", expanded=True):
            st.markdown(f"### {record['Title']}")
            st.markdown(f"**Entity:** {record['Entity']}")
            st.markdown(f"**Category:** {record['category']}")
            st.markdown(f"**Classification:** {record['Classification']}")
            st.markdown(f"**Status:** {record['Status']}")
            st.markdown(f"**ABC:** {record['ABC']}")
            st.markdown(f"**Publish Date:** {record['PublishDate']}")
            st.markdown(f"**Closing Date:** {record['ClosingDate']}")
            st.markdown(f"**Summary:** {record['Summary']}")
            st.markdown(f"**Page URL:** [Link]({record['PageURL']})")

            # Approve button
            if st.button("✅ Approve Bidding"):
                st.success(f"Bidding '{record['Title']}' has been approved.")
    except IndexError:
        st.error("No record found with that ReferenceNo.")
