#!/usr/bin/env python3
"""
Real-Time Process Monitoring Dashboard

Usage:
  1. Default (loads processes from config.toml [process_dashboard]):
     streamlit run process_dashboard.py

  2. Command-Line Override (monitors specific processes):
     streamlit run process_dashboard.py -- process-name-1 process-name-2
"""
import streamlit as st
import pandas as pd
import toml
import os
import json
import sys
from datetime import datetime
import plotly.graph_objects as go

# --- Configuration ---
CONFIG_FILE = "/Users/manoj/coding/x_config/config.toml"

@st.cache_data(ttl=30)
def load_app_config():
    """Reads the TOML config file to get log directory and default process names."""
    try:
        config = toml.load(CONFIG_FILE)
        log_dir = config["output_path"]["logs"]

        # <-- use [process_dashboard] section -->
        default_processes = config.get("process_dashboard", {}).get("names", [])
        return log_dir, default_processes
    except Exception as e:
        st.error(f"Error loading config file '{CONFIG_FILE}': {e}")
        return None, []

@st.cache_data(ttl=5)
def parse_log_files(process_names, log_dir):
    """Reads and aggregates data from multiple log files."""
    all_records = []
    for name in process_names:
        log_path = os.path.join(log_dir, f"{name}.json")
        if not os.path.exists(log_path):
            continue
        with open(log_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    log_entry = json.loads(line)
                    if "exit_code" in log_entry and "timestamp" in log_entry:
                        status = "success" if log_entry["exit_code"] == 0 else "failure"
                        all_records.append({
                            "timestamp": log_entry["timestamp"],
                            "status": status,
                            "process": name
                        })
                except json.JSONDecodeError:
                    continue
    if not all_records:
        return pd.DataFrame()
    return pd.DataFrame(all_records)

# --- Streamlit App Layout ---
st.set_page_config(page_title="Process Monitoring Dashboard", layout="wide")
st.title("📊 Real-Time Process Statistics")

# --- Logic to Determine Initial Process Selection ---
log_dir, config_processes = load_app_config()
cli_processes = sys.argv[1:] if len(sys.argv) > 1 else None

if cli_processes:
    initial_selection = cli_processes
    st.sidebar.info("Monitoring processes specified via command line.")
else:
    initial_selection = config_processes
    st.sidebar.info("Monitoring default processes from config.toml [process_dashboard].")

# --- UI Elements ---
if log_dir:
    available_logs = [f.replace(".json", "") for f in os.listdir(log_dir) if f.endswith(".json")]
    sanitized_selection = [p for p in initial_selection if p in available_logs]
    
    ignored_processes = [p for p in initial_selection if p not in available_logs]
    if ignored_processes:
        st.sidebar.warning(
            f"Note: The following processes have no logs yet and were not pre-selected: {', '.join(ignored_processes)}"
        )

    selected_processes = st.sidebar.multiselect(
        'Select processes to monitor:',
        options=sorted(available_logs),
        default=sanitized_selection
    )
else:
    selected_processes = []
    st.warning("Could not find log directory from config. The dashboard cannot function.")

# --- Auto-refresh every 5 seconds ---
st.markdown(
    """
    <script>
    function autoRefresh() {
        window.location.reload();
    }
    setInterval(autoRefresh, 5000);
    </script>
    """,
    unsafe_allow_html=True
)

# --- Main Dashboard ---
if not selected_processes:
    st.info("Please select at least one process from the sidebar to begin monitoring.")
else:
    df = parse_log_files(selected_processes, log_dir)

    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values(by='timestamp').reset_index(drop=True)
        df['success_count'] = (df['status'] == 'success').cumsum()
        df['failure_count'] = (df['status'] == 'failure').cumsum()

        total_success = df['success_count'].iloc[-1]
        total_failure = df['failure_count'].iloc[-1]

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric(label="✅ Total Successes", value=int(total_success))
        kpi2.metric(label="❌ Total Failures", value=int(total_failure))
        kpi3.metric(label="Total Runs", value=int(total_success + total_failure))

        # --- Plotly Chart ---
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['success_count'],
            name='Success', mode='lines+markers', line=dict(color='green')
        ))
        fig.add_trace(go.Scatter(
            x=df['timestamp'], y=df['failure_count'],
            name='Failure', mode='lines+markers', line=dict(color='red', width=3)
        ))
        fig.update_layout(
            title_text='Process Runs Over Time - Cumulative rate',
            xaxis_title='Time',
            yaxis_title='Cumulative Count',
            legend_title_text='Status'
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("View Raw Data"):
            st.dataframe(
                df[['timestamp', 'process', 'status']].sort_values('timestamp', ascending=False),
                use_container_width=True
            )
    else:
        st.info(f"Waiting for log data for: {', '.join(selected_processes)}...")
