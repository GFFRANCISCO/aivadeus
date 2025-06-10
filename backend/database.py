from supabase import create_client
import os
from dotenv import load_dotenv
import re
import sys



SUPABASE_URL = "https://vphtpzlbdcotorqpuonr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZwaHRwemxiZGNvdG9ycXB1b25yIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDU1MDg0OTcsImV4cCI6MjA2MTA4NDQ5N30.XTP7clV__5ZVp9hZCJ2eGhL7HgEUeTcl2uINX0JC9WI"
SUPABASE_BUCKET = "bidding-projects"



if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ ERROR: Missing Supabase credentials in environment variables.", file=sys.stderr)
    print(f"SUPABASE_URL: {SUPABASE_URL}", file=sys.stderr)
    print(f"SUPABASE_KEY: {'present' if SUPABASE_KEY else 'missing'}", file=sys.stderr)
    raise ValueError("Missing Supabase credentials: Please set SUPABASE_URL and SUPABASE_KEY in your environment.")

# Basic URL format check (starts with https://)
if not re.match(r"^https://", SUPABASE_URL):
    raise ValueError(f"Invalid SUPABASE_URL: {SUPABASE_URL}. Must start with 'https://'")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
