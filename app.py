import sqlite3
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timedelta
import streamlit.components.v1 as components


DB_PATH = Path("sensibull.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

# ---------- IV Rank & Percentile (last 365 days) ----------
def get_iv_summary():
    conn = get_connection()
    cutoff_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    six_months_ago = (datetime.today() - timedelta(days=180)).strftime("%Y-%m-%d")
    one_month_ago = (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
    one_week_ago = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    df = pd.read_sql_query("""
        SELECT s.tradingsymbol,
               s.name,
               i.iv,
               i.date,
               i.close
        FROM scripts s
        JOIN iv i ON s.tradingsymbol = i.script
        WHERE date(i.date) >= date(?)
        ORDER BY i.date
    """, conn, params=(cutoff_date,))
    conn.close()

    if df.empty:
        return pd.DataFrame(columns=[
            "tradingsymbol", "name", "IV", "iv_rank", "iv_percentile",
            "iv_mean_ratio", "recent_iv_jump",
            "six_months_return", "one_month_return", "one_week_return"
        ])

    result = []
    for symbol, group in df.groupby(["tradingsymbol", "name"]):
        current_iv = group.iloc[-1]["iv"]
        current_price = group.iloc[-1]["close"]
        recent_mean_iv = group.iloc[-6:]["iv"].mean() if len(group) >= 6 else group["iv"].mean()
        min_iv = group["iv"].min()
        max_iv = group["iv"].max()
        mean_iv = group["iv"].mean()

        # Defensive helpers
        def safe_last(series):
            return series.iloc[-1] if not series.empty else None

        six_month_ago_price = safe_last(group[group["date"] <= six_months_ago]["close"])
        one_month_ago_price = safe_last(group[group["date"] <= one_month_ago]["close"])
        one_week_ago_price = safe_last(group[group["date"] <= one_week_ago]["close"])

        iv_rank = (current_iv - min_iv) / (max_iv - min_iv) * 100 if max_iv > min_iv else None
        iv_percentile = (group["iv"] <= current_iv).sum() / len(group) * 100
        iv_mean_ratio = current_iv / mean_iv if mean_iv else None
        recent_iv_jump = current_iv / recent_mean_iv if recent_mean_iv else None

        six_months_return = ((current_price - six_month_ago_price) / six_month_ago_price * 100
                             if six_month_ago_price else 0)
        one_month_return = ((current_price - one_month_ago_price) / one_month_ago_price * 100
                            if one_month_ago_price else 0)
        one_week_return = ((current_price - one_week_ago_price) / one_week_ago_price * 100
                           if one_week_ago_price else 0)

        result.append({
            "tradingsymbol": symbol[0],
            "name": symbol[1],
            "current_price": round(current_price, 2),
            "IV": round(current_iv, 2),
            "iv_rank": round(iv_rank, 2) if iv_rank is not None else None,
            "iv_percentile": round(iv_percentile, 2),
            "iv_mean_ratio": round(iv_mean_ratio, 2) if iv_mean_ratio else None,
            "recent_iv_jump": round(recent_iv_jump, 2) if recent_iv_jump else None,
            "six_months_return": round(six_months_return, 2) if six_months_return else 0,
            "one_month_return": round(one_month_return, 2) if one_month_return else 0,
            "one_week_return": round(one_week_return, 2) if one_week_return else 0
        })

    return pd.DataFrame(result)

# ---------- OHLC + IV Plot ----------
def get_ohlc(script):
    conn = get_connection()
    cutoff_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")

    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, iv FROM iv WHERE script = ? AND date(date) >= date(?) ORDER BY date",
        conn,
        params=(script, cutoff_date),
    )
    conn.close()
    return df

def plot_ohlc_iv(df, script):
    fig = go.Figure()
    df['Change'] = df['close'].diff()
    df['%Change'] = df['Change'] / df['close'].shift(1) * 100
    fig.add_trace(go.Candlestick(
        x=df["date"],
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name=f"OHLC: {script}",
        customdata=df[['Change', '%Change']],
    ))

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["iv"],
        mode="lines",
        name=f"IV:",
        yaxis="y2"
    ))

    fig.update_layout(
        title=f"OHLC + IV (last 365 days) for {script}",
        xaxis=dict(title="Date"),
        yaxis=dict(title="Price"),
        # plot_bgcolor="white",      # chart area
        # paper_bgcolor="white",     # outside area
        font=dict(color="black"),  # ensure text is visible
        yaxis2=dict(title="IV", overlaying="y", side="right"),
        hovermode="x unified"
    )
    return fig

# ---------- Streamlit App ----------
def main():
    st.set_page_config(page_title="IV Dashboard", layout="wide")
    st.title("📈 IV Dashboard")

    # IV Metrics Definitions
    with st.expander("📚 IV Metrics Definitions"):
        st.markdown("""
        **IV Rank**: Measures where current IV sits relative to its 365-day range (0-100%)
        - Formula: `(current_iv - min_iv) / (max_iv - min_iv) × 100`
        - High rank (>80) suggests IV is expensive, low rank (<20) suggests IV is cheap

        **IV Percentile**: Percentage of days over the last 365 days where IV was at or below current level
        - Formula: `(days_with_iv ≤ current_iv) / total_days × 100`
        - More robust than rank as it's not skewed by extreme outliers

        **IV Mean Ratio**: Current IV compared to its 365-day average
        - Formula: `current_iv / mean_iv`
        - >1.0 means IV is above average, <1.0 means below average

        **Recent IV Jump**: Current IV compared to recent 6-day average IV
        - Formula: `current_iv / recent_6day_mean_iv`
        - Helps identify sudden spikes or drops in volatility expectations
        """)

    df = get_iv_summary()
    st.subheader("IV Rank & Percentile Table (last 365 days)")

    if df.empty:
        st.warning("No data available")
        return

    # Render HTML table
    # Render HTML table with DataTables
    html = """
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.6/css/jquery.dataTables.min.css">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.6/js/jquery.dataTables.min.js"></script>

    <style>
    /* Force light background + readable text */
    body { background-color: white; color: black; }
    table.dataTable { background-color: white; color: black; }
    table.dataTable thead th { background-color: #f2f2f2; color: black; }
    table.dataTable tbody tr { background-color: white; color: black; }
    table.dataTable tbody tr:hover { background-color: #f5f5f5; }
    </style>

    <table id="ivTable" class="display" style="width:100%">
    <thead>
        <tr>
        <th>Trading Symbol</th>
        <th>Name</th>
        <th>Current Price</th>
        <th>IV</th>
        <th>IV Rank</th>
        <th>IV Percentile</th>
        <th>IV Mean Ratio</th>
        <th>Recent IV Jump</th>
        <th>% 6 Mo Return</th>
        <th>% 1 Mo Return</th>
        <th>% 1 Wk Return</th>
        </tr>
    </thead>
    <tbody>
    """
    for _, row in df.sort_values("iv_rank", ascending=False).iterrows():
        html += (
            f"<tr>"
            f"<td><a href='https://www.screener.in/company/{row['tradingsymbol']}' target='_blank'>{row['tradingsymbol']}</a></td>"
            f"<td><a href='https://in.tradingview.com/chart/?symbol=NSE%3A{row['tradingsymbol']}' target='_blank'>{row['name']}</a></td>"
            f"<td>{row['current_price']}</td>"
            f"<td>{row['IV']}</td>"
            f"<td>{row['iv_rank']}</td>"
            f"<td>{row['iv_percentile']}</td>"
            f"<td>{row['iv_mean_ratio']}</td>"
            f"<td>{row['recent_iv_jump']}</td>"
            f"<td>{row['six_months_return']}</td>"
            f"<td>{row['one_month_return']}</td>"
            f"<td>{row['one_week_return']}</td>"
            f"</tr>"
        )
    html += """
    </tbody>
    </table>

    <script>
    $(document).ready(function() {
        $('#ivTable').DataTable({
            "order": [[4, "desc"]]  // default sort by IV Rank descending
        });
    });
    </script>
    """

    # st.markdown(html, unsafe_allow_html=True)
    components.html(html, height=500, scrolling=False)


if __name__ == "__main__":
    main()
