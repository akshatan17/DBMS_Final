"""
app.py — IPL 2025 DBMS Project · Streamlit UI (MySQL edition)

Pages:
  Dashboard           — live KPIs, points table, recent matches
  Teams               — all 10 franchises with logos, colors, all-time stats
  Matches             — schedule, completed results, schedule new match
  Live Standings      — points table (view-backed)
  All-Time Stats      — historical leaderboard
  MVP Leaderboard     — Player of the Match counts (loyalty-points analogue)
  Daily Update        — triggers the "fetch latest" hook
  SQL Playground      — all 10 required queries + free-form SELECT
  About / Schema      — concept walkthrough

Backend: MySQL via mysql-connector-python.
"""

from __future__ import annotations
import os
import time
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import (
    init_db, get_connection, DB_CONFIG,
    sp_record_result, sp_schedule_match,
    fetch_latest,
)
from queries import QUERY_CATALOG, run_query, run_raw


# ---------------------------------------------------------------------------
# Page config + theme
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="IPL 2025 · DBMS",
    page_icon="🏏",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_css():
    """Read style.css with explicit UTF-8 encoding (Windows-safe)."""
    css_path = os.path.join(os.path.dirname(__file__), "style.css")
    with open(css_path, encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css()

# Initialise database with friendly error message
try:
    init_db()
except Exception as e:
    st.error(
        f"❌ Could not connect to MySQL.\n\n"
        f"**Check that:**\n"
        f"1. MySQL server is running on `{DB_CONFIG['host']}:{DB_CONFIG['port']}`\n"
        f"2. The password in `database.py` matches your MySQL root password\n"
        f"3. Your user has CREATE DATABASE privilege\n\n"
        f"**Error detail:**\n```\n{e}\n```"
    )
    st.stop()

PLOTLY_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", color="#F5F7FB", size=12),
    margin=dict(l=10, r=10, t=10, b=10),
    colorway=["#00B2D6", "#E8B23A", "#4A8C5F", "#E0524A", "#94A3C0", "#6FB988"],
    title=dict(text=""),
)


# ---------------------------------------------------------------------------
# Helpers — MySQL-aware
# ---------------------------------------------------------------------------
def fetch_df(sql: str, params=()) -> pd.DataFrame:
    """Run a SELECT and return DataFrame. Uses pandas + mysql-connector cursor."""
    import warnings
    warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy.*")
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params if params else None)
    finally:
        conn.close()
    return df


def execute(sql: str, params=()):
    """Run an INSERT/UPDATE/DELETE and return lastrowid."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid


def logo_html(short: str, primary: str, secondary: str, logo_file: str = None,
              size: int = 56) -> str:
    """Render a team logo: real image if file exists, else colored initials circle."""
    logo_path = os.path.join(os.path.dirname(__file__), "logos", logo_file or "")
    if logo_file and os.path.exists(logo_path):
        import base64
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = logo_file.rsplit(".", 1)[-1].lower()
        return (f'<img src="data:image/{ext};base64,{b64}" '
                f'style="width:{size}px;height:{size}px;border-radius:50%;'
                f'object-fit:cover;border:2px solid rgba(255,255,255,.12);'
                f'background:rgba(255,255,255,.04);">')
    return (
        f'<div class="team-logo-circle" '
        f'style="width:{size}px;height:{size}px;'
        f'background:linear-gradient(135deg,{primary} 0%, {secondary} 100%);'
        f'color:white;">{short}</div>'
    )


def status_pill(status: str) -> str:
    cls = {"Completed": "pill-done", "Live": "pill-live",
           "Scheduled": "pill-sched", "Abandoned": "pill-done"}.get(status, "pill-sched")
    return f'<span class="status-pill {cls}">{status}</span>'


# ---------------------------------------------------------------------------
# Sidebar nav
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">🏏 IPL 2025</div>
        <div class="sidebar-tag">DBMS · MySQL</div>
        """,
        unsafe_allow_html=True,
    )

    nav = [
        "🏠  Dashboard",
        "🛡️  Teams",
        "📅  Matches",
        "🏆  Live Standings",
        "📈  All-Time Stats",
        "🎖️  MVP Leaderboard",
        "🔄  Daily Update",
        "🧪  SQL Playground",
        "📚  About / Schema",
    ]
    if "nav_choice" not in st.session_state:
        st.session_state["nav_choice"] = nav[0]
    page = st.radio("Navigate", nav, key="nav_choice", label_visibility="collapsed")

    st.markdown(
        f"""
        <div class="sidebar-foot">
        <strong>Data source</strong><br/>
        Curated from public IPL records<br/><br/>
        <strong>Schema</strong><br/>
        7 tables · 3 views · 4 triggers · 2 procedures<br/><br/>
        <strong>Engine</strong><br/>
        MySQL @ {DB_CONFIG['host']}:{DB_CONFIG['port']}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# 1. DASHBOARD
# ===========================================================================
def page_dashboard():
    st.markdown("""
        <div class="hero">
            <div class="hero-sub">Tata IPL · Season 2025</div>
            <h1>The 18th Edition</h1>
            <p>Live points table, schedules, results, and historical stats for all
            10 IPL franchises — backed by a normalised MySQL database with views,
            triggers, and stored procedures.</p>
        </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    total_matches = int(fetch_df("SELECT COUNT(*) AS c FROM Matches").iloc[0]["c"])
    completed     = int(fetch_df("SELECT COUNT(*) AS c FROM Matches WHERE Status='Completed'").iloc[0]["c"])
    scheduled     = int(fetch_df("SELECT COUNT(*) AS c FROM Matches WHERE Status='Scheduled'").iloc[0]["c"])
    teams_n       = int(fetch_df("SELECT COUNT(*) AS c FROM Teams").iloc[0]["c"])

    c1.metric("Total Matches", total_matches)
    c2.metric("Completed", completed)
    c3.metric("Upcoming", scheduled)
    c4.metric("Franchises", teams_n)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    left, right = st.columns([1.4, 1])

    with left:
        st.markdown('<div class="eyebrow">Standings</div>', unsafe_allow_html=True)
        st.markdown("### Current points table")
        df = fetch_df("SELECT * FROM LiveStandings;")
        if df.empty or df["Played"].sum() == 0:
            st.info("No matches played yet this season.")
        else:
            # Custom HTML mini-standings — guaranteed readable.
            # Build as one continuous string so Markdown doesn't treat
            # indented lines as code blocks.
            rows_html = ""
            for pos, (_, r) in enumerate(df.iterrows(), start=1):
                try:
                    nrr_str = f"{float(r['NRR']):+.2f}"
                except (TypeError, ValueError):
                    nrr_str = "0.00"
                top4_cls = " mini-top4" if pos <= 4 else ""
                rows_html += (
                    f'<div class="mini-row{top4_cls}">'
                    f'<div class="mini-pos">{pos}</div>'
                    f'<div class="mini-team">{r["ShortCode"]}</div>'
                    f'<div class="mini-cell">{int(r["Played"])}</div>'
                    f'<div class="mini-cell mini-w">{int(r["Won"])}</div>'
                    f'<div class="mini-cell mini-l">{int(r["Lost"])}</div>'
                    f'<div class="mini-cell mini-pts">{int(r["Points"])}</div>'
                    f'<div class="mini-cell">{nrr_str}</div>'
                    f'</div>'
                )
            header_html = (
                '<div class="mini-header">'
                '<div></div><div>Team</div>'
                '<div class="mini-cell">P</div>'
                '<div class="mini-cell">W</div>'
                '<div class="mini-cell">L</div>'
                '<div class="mini-cell">Pts</div>'
                '<div class="mini-cell">NRR</div>'
                '</div>'
            )
            st.markdown(
                f'<div class="mini-standings">{header_html}{rows_html}</div>',
                unsafe_allow_html=True,
            )
            st.caption("🟡 Top 4 qualify for playoffs")

    with right:
        st.markdown('<div class="eyebrow">Trophy Cabinet</div>', unsafe_allow_html=True)
        st.markdown("### IPL titles (all-time)")
        df = fetch_df("""
            SELECT t.ShortCode, a.Titles
            FROM Teams t JOIN AllTimeStats a ON a.TeamID = t.TeamID
            WHERE a.Titles > 0
            ORDER BY a.Titles DESC;
        """)
        fig = go.Figure(go.Bar(
            x=df["Titles"], y=df["ShortCode"], orientation="h",
            marker=dict(color="#E8B23A", line=dict(color="rgba(0,0,0,0)")),
            text=df["Titles"], textposition="outside",
            textfont=dict(color="#F5F7FB", family="Oswald, sans-serif"),
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=300,
                          yaxis=dict(autorange="reversed", color="#F5F7FB"),
                          xaxis=dict(color="#F5F7FB", gridcolor="#2A3656"))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('<div class="eyebrow">Most recent</div>', unsafe_allow_html=True)
        st.markdown("### Last 4 results")
        recent = fetch_df("""
            SELECT Fixture, MatchDate, Venue, Winner, Margin
            FROM MatchSummary
            WHERE Status='Completed'
            ORDER BY MatchDate DESC LIMIT 4;
        """)
        for _, r in recent.iterrows():
            st.markdown(f"""
                <div class="match-card">
                    <div class="match-meta">{r['MatchDate']} · {r['Venue']}</div>
                    <div class="match-fixture">{r['Fixture']}</div>
                    <div class="match-result">{r['Winner']} won by {r['Margin']}</div>
                </div>
            """, unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="eyebrow">Coming up</div>', unsafe_allow_html=True)
        st.markdown("### Next 4 matches")
        upcoming = fetch_df("""
            SELECT Fixture, MatchDate, Venue
            FROM MatchSummary
            WHERE Status='Scheduled'
            ORDER BY MatchDate ASC LIMIT 4;
        """)
        for _, r in upcoming.iterrows():
            st.markdown(f"""
                <div class="match-card">
                    <div class="match-meta">{r['MatchDate']} · {r['Venue']}</div>
                    <div class="match-fixture">{r['Fixture']}</div>
                    <div style="margin-top:.4rem;">{status_pill('Scheduled')}</div>
                </div>
            """, unsafe_allow_html=True)


# ===========================================================================
# 2. TEAMS
# ===========================================================================
def page_teams():
    st.markdown('<div class="eyebrow">The Ten</div>', unsafe_allow_html=True)
    st.markdown("# Franchises")
    df = fetch_df("""
        SELECT t.TeamID, t.ShortCode, t.FullName, t.City, t.Founded,
               t.PrimaryColor, t.SecondaryColor, t.LogoFile,
               a.SeasonsPlayed, a.TotalMatches, a.TotalWins, a.TotalLosses,
               a.Titles, a.FinalsAppearances,
               CASE WHEN a.TotalMatches = 0 THEN 0
                    ELSE ROUND(a.TotalWins * 100.0 / a.TotalMatches, 1)
               END AS WinPct
        FROM Teams t
        JOIN AllTimeStats a ON a.TeamID = t.TeamID
        ORDER BY a.Titles DESC, WinPct DESC;
    """)

    cols_per_row = 2
    for i in range(0, len(df), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, (_, row) in enumerate(df.iloc[i:i+cols_per_row].iterrows()):
            with cols[j]:
                logo = logo_html(row["ShortCode"], row["PrimaryColor"],
                                 row["SecondaryColor"], row["LogoFile"])
                titles_str = "🏆 " * int(row["Titles"]) if row["Titles"] else "— No titles yet —"
                st.markdown(f"""
                    <div class="team-card" style="border-left-color:{row['PrimaryColor']};">
                        <div class="team-logo-wrap">
                            {logo}
                            <div>
                                <div class="team-short">{row['ShortCode']}</div>
                                <div class="team-name">{row['FullName']}</div>
                                <div class="team-meta">{row['City']} · est. {row['Founded']}</div>
                            </div>
                        </div>
                        <div class="team-trophies">{titles_str}</div>
                        <div class="team-stats">
                            <div>
                                <div class="team-stat-num">{int(row['TotalMatches'])}</div>
                                <div class="team-stat-lbl">Total Matches</div>
                            </div>
                            <div>
                                <div class="team-stat-num">{int(row['TotalWins'])}</div>
                                <div class="team-stat-lbl">Wins</div>
                            </div>
                            <div>
                                <div class="team-stat-num">{row['WinPct']}%</div>
                                <div class="team-stat-lbl">Win Rate</div>
                            </div>
                            <div>
                                <div class="team-stat-num">{int(row['Titles'])}</div>
                                <div class="team-stat-lbl">IPL Titles</div>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                with st.expander(f"Squad highlights · {row['ShortCode']}"):
                    players = fetch_df(
                        "SELECT Name, Role, IsCaptain, MVPCount FROM Players "
                        "WHERE TeamID=%s ORDER BY IsCaptain DESC, MVPCount DESC;",
                        (int(row["TeamID"]),),
                    )
                    for _, p in players.iterrows():
                        cap = " · 🪖 Captain" if p["IsCaptain"] else ""
                        mvp = f" · 🎖️ {int(p['MVPCount'])} MVP" if p['MVPCount'] else ""
                        st.markdown(f"**{p['Name']}**  ·  {p['Role']}{cap}{mvp}")


# ===========================================================================
# 3. MATCHES
# ===========================================================================
def page_matches():
    st.markdown('<div class="eyebrow">Fixtures</div>', unsafe_allow_html=True)
    st.markdown("# Matches")

    tab1, tab2, tab3 = st.tabs(["📅 Schedule", "✅ Record Result", "➕ Schedule New Match"])

    with tab1:
        c1, c2 = st.columns([1, 1])
        with c1:
            status_filter = st.selectbox(
                "Status", ["All", "Completed", "Scheduled", "Live"],
                key="match_status_filter",
            )
        with c2:
            team_options = ["All"] + fetch_df(
                "SELECT ShortCode FROM Teams ORDER BY ShortCode"
            )["ShortCode"].tolist()
            team_filter = st.selectbox("Team", team_options, key="match_team_filter")

        sql = """
            SELECT MatchID, MatchDate, Fixture, Stage, Status,
                   Venue, Winner, Margin
            FROM MatchSummary WHERE 1=1
        """
        params = []
        if status_filter != "All":
            sql += " AND Status = %s"; params.append(status_filter)
        if team_filter != "All":
            sql += " AND Fixture LIKE %s"; params.append(f"%{team_filter}%")
        sql += " ORDER BY MatchDate DESC;"

        df = fetch_df(sql, tuple(params))
        if df.empty:
            st.info("No matches match those filters.")
        else:
            for _, r in df.iterrows():
                margin_txt = (
                    f"<div class='match-result'>{r['Winner']} won by {r['Margin']}</div>"
                    if r["Status"] == "Completed"
                    else f"<div style='margin-top:.4rem;'>{status_pill(r['Status'])}</div>"
                )
                st.markdown(f"""
                    <div class="match-card">
                        <div class="match-meta">
                            Match #{r['MatchID']} · {r['MatchDate']} · {r['Stage']} · {r['Venue']}
                        </div>
                        <div class="match-fixture">{r['Fixture']}</div>
                        {margin_txt}
                    </div>
                """, unsafe_allow_html=True)

    with tab2:
        st.markdown("### Record result for a scheduled match")
        st.caption(
            "This calls the **MySQL stored procedure** `sp_record_result()` "
            "(real `CREATE PROCEDURE` — not Python-emulated). "
            "Triggers cascade: `trg_after_result` updates SeasonStandings, "
            "`trg_alltime_update` updates AllTimeStats, "
            "`trg_award_mvp` increments the Player-of-the-Match's MVPCount."
        )

        scheduled = fetch_df("""
            SELECT m.MatchID, m.MatchDate, t1.ShortCode AS T1, t2.ShortCode AS T2,
                   m.Team1ID, m.Team2ID, t1.FullName AS T1Full, t2.FullName AS T2Full
            FROM Matches m
            JOIN Teams t1 ON t1.TeamID = m.Team1ID
            JOIN Teams t2 ON t2.TeamID = m.Team2ID
            WHERE m.Status = 'Scheduled'
            ORDER BY m.MatchDate ASC;
        """)
        if scheduled.empty:
            st.info("No scheduled matches available. Use the next tab to add one.")
        else:
            mid = st.selectbox(
                "Match",
                scheduled["MatchID"].tolist(),
                format_func=lambda x: (
                    f"#{x} · {scheduled.set_index('MatchID').loc[x,'MatchDate']} · "
                    f"{scheduled.set_index('MatchID').loc[x,'T1']} vs "
                    f"{scheduled.set_index('MatchID').loc[x,'T2']}"
                ),
                key="rec_match",
            )
            row = scheduled.set_index("MatchID").loc[mid]

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{row['T1Full']}**")
                s1 = st.number_input(f"{row['T1']} score",   0, 350, 180, key="s1")
                w1 = st.number_input(f"{row['T1']} wickets", 0, 10, 6,    key="w1")
                o1 = st.number_input(f"{row['T1']} overs",   0.0, 20.0, 20.0, step=0.1, key="o1")
            with c2:
                st.markdown(f"**{row['T2Full']}**")
                s2 = st.number_input(f"{row['T2']} score",   0, 350, 175, key="s2")
                w2 = st.number_input(f"{row['T2']} wickets", 0, 10, 8,    key="w2")
                o2 = st.number_input(f"{row['T2']} overs",   0.0, 20.0, 20.0, step=0.1, key="o2")

            winner_id = st.radio(
                "Winner",
                [int(row["Team1ID"]), int(row["Team2ID"])],
                format_func=lambda x: row["T1Full"] if x == row["Team1ID"] else row["T2Full"],
                key="rec_winner",
                horizontal=True,
            )

            c1, c2 = st.columns(2)
            margin = c1.text_input("Margin (e.g. '23 runs' or '6 wickets')", key="rec_margin")

            # Player of the Match dropdown — populated from Players table
            players = fetch_df(
                "SELECT Name FROM Players WHERE TeamID IN (%s, %s) ORDER BY Name;",
                (int(row["Team1ID"]), int(row["Team2ID"])),
            )
            pom_options = ["— None —"] + players["Name"].tolist()
            pom_sel = c2.selectbox("Player of the Match", pom_options, key="rec_pom")
            pom = None if pom_sel == "— None —" else pom_sel

            if st.button("Record Result · cascades triggers", type="primary"):
                try:
                    sp_record_result(int(mid), int(s1), int(w1), float(o1),
                                     int(s2), int(w2), float(o2),
                                     int(winner_id), margin, pom)
                    winner_name = (row["T1Full"] if winner_id == row["Team1ID"]
                                   else row["T2Full"])
                    st.success(
                        f"✅ Result recorded. {winner_name} wins. "
                        f"Standings, all-time stats and MVP counts updated by triggers."
                    )
                    time.sleep(0.8)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

    with tab3:
        st.markdown("### Schedule a new match")
        st.caption(
            "Uses MySQL stored procedure `sp_schedule_match()`. "
            "Trigger `trg_no_self_match` aborts the insert if a team is matched against itself."
        )

        teams = fetch_df("SELECT TeamID, ShortCode, FullName FROM Teams ORDER BY ShortCode;")
        venues = fetch_df("SELECT VenueID, Name FROM Venues ORDER BY Name;")

        with st.form("sched_match", clear_on_submit=True):
            c1, c2 = st.columns(2)
            t1 = c1.selectbox(
                "Team 1", teams["TeamID"].tolist(),
                format_func=lambda x: teams.set_index("TeamID").loc[x, "FullName"],
                key="sch_t1",
            )
            t2 = c2.selectbox(
                "Team 2", teams["TeamID"].tolist(),
                format_func=lambda x: teams.set_index("TeamID").loc[x, "FullName"],
                index=1, key="sch_t2",
            )
            c1, c2, c3 = st.columns(3)
            vid = c1.selectbox(
                "Venue", venues["VenueID"].tolist(),
                format_func=lambda x: venues.set_index("VenueID").loc[x, "Name"],
                key="sch_v",
            )
            md = c2.date_input("Match date", date.today(), key="sch_d")
            stage = c3.selectbox(
                "Stage",
                ["League", "Qualifier 1", "Eliminator", "Qualifier 2", "Final"],
                key="sch_stage",
            )

            if st.form_submit_button("Add to schedule"):
                if t1 == t2:
                    st.error("A team cannot play itself.")
                else:
                    try:
                        new_id = sp_schedule_match(
                            md.strftime("%Y-%m-%d"),
                            int(t1), int(t2), int(vid), stage,
                        )
                        st.success(f"✅ Match #{new_id} scheduled.")
                        time.sleep(0.4); st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")


# ===========================================================================
# 4. LIVE STANDINGS
# ===========================================================================
def page_standings():
    st.markdown('<div class="eyebrow">Points Table</div>', unsafe_allow_html=True)
    st.markdown("# Live Standings · 2025")
    st.caption(
        "Reads directly from the `LiveStandings` view — built on SeasonStandings "
        "(maintained by `trg_after_result`) with NRR computed on-the-fly in a CASE expression."
    )

    df = fetch_df("SELECT * FROM LiveStandings;")
    if df.empty:
        st.info("No standings data yet.")
        return

    teams = fetch_df(
        "SELECT TeamID, PrimaryColor, SecondaryColor, LogoFile, ShortCode, FullName FROM Teams;"
    )
    team_meta = teams.set_index("TeamID").to_dict("index")

    header = """
        <div class="standings-header">
            <div>Pos</div><div>Team</div>
            <div class="ctr">P</div>
            <div class="ctr">W</div>
            <div class="ctr">L</div>
            <div class="ctr">Pts</div>
            <div class="ctr">NRR</div>
            <div class="ctr">Status</div>
        </div>
    """
    st.markdown(header, unsafe_allow_html=True)

    for pos, (_, row) in enumerate(df.iterrows(), start=1):
        meta = team_meta[row["TeamID"]]
        logo = logo_html(meta["ShortCode"], meta["PrimaryColor"],
                         meta["SecondaryColor"], meta["LogoFile"], size=38)
        qual = "🟡 Playoff" if pos <= 4 else "—"
        row_cls = "standings-row top4" if pos <= 4 else "standings-row"
        nrr_val = row['NRR']
        try:
            nrr_str = f"{float(nrr_val):+.2f}"
        except (TypeError, ValueError):
            nrr_str = "0.00"

        st.markdown(f"""
            <div class="{row_cls}">
                <div class="standings-pos">{pos}</div>
                <div class="standings-team">
                    {logo}
                    <div>
                        <div class="standings-short">{meta['ShortCode']}</div>
                        <div class="standings-full">{meta['FullName']}</div>
                    </div>
                </div>
                <div class="ctr">{int(row['Played'])}</div>
                <div class="ctr standings-w">{int(row['Won'])}</div>
                <div class="ctr standings-l">{int(row['Lost'])}</div>
                <div class="ctr standings-pts">{int(row['Points'])}</div>
                <div class="ctr">{nrr_str}</div>
                <div class="ctr standings-qual">{qual}</div>
            </div>
        """, unsafe_allow_html=True)


# ===========================================================================
# 5. ALL-TIME STATS
# ===========================================================================
def page_alltime():
    st.markdown('<div class="eyebrow">Historical</div>', unsafe_allow_html=True)
    st.markdown("# All-Time IPL Stats")
    st.caption("Cumulative across every IPL season. Backed by the `TeamHistory` view.")

    df = fetch_df("SELECT * FROM TeamHistory;")
    # ensure numeric (some MySQL drivers return Decimal)
    df["WinPercent"] = pd.to_numeric(df["WinPercent"])
    df["TotalWins"]  = pd.to_numeric(df["TotalWins"])

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Win % across all seasons")
        fig = go.Figure(go.Bar(
            x=df["WinPercent"], y=df["ShortCode"], orientation="h",
            marker=dict(color="#4A8C5F"),
            text=[f"{v}%" for v in df["WinPercent"]],
            textposition="outside",
            textfont=dict(color="#F5F7FB"),
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=400,
                          yaxis=dict(autorange="reversed", color="#F5F7FB"),
                          xaxis=dict(color="#F5F7FB", gridcolor="#2A3656", title="Win %"))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.markdown("### Total wins")
        fig = go.Figure(go.Bar(
            x=df["TotalWins"], y=df["ShortCode"], orientation="h",
            marker=dict(color="#00B2D6"),
            text=df["TotalWins"], textposition="outside",
            textfont=dict(color="#F5F7FB"),
        ))
        fig.update_layout(**PLOTLY_LAYOUT, height=400,
                          yaxis=dict(autorange="reversed", color="#F5F7FB"),
                          xaxis=dict(color="#F5F7FB", gridcolor="#2A3656", title="Wins"))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("### Complete historical table")
    display = df[["ShortCode", "FullName", "SeasonsPlayed", "TotalMatches",
                  "TotalWins", "TotalLosses", "Titles", "FinalsAppearances",
                  "WinPercent"]].copy()
    display.columns = ["Team", "Full Name", "Seasons", "Matches",
                       "Wins", "Losses", "Titles", "Finals", "Win %"]
    st.dataframe(display, use_container_width=True, hide_index=True)


# ===========================================================================
# 6. MVP LEADERBOARD (Player loyalty-points analogue)
# ===========================================================================
def page_mvp():
    st.markdown('<div class="eyebrow">Honours</div>', unsafe_allow_html=True)
    st.markdown("# Player of the Match Leaderboard")
    st.caption(
        "Auto-maintained by the `trg_award_mvp` trigger — every recorded "
        "result with a named Player of the Match increments that player's MVPCount. "
        "(Analogue of 'loyalty points for every order' in the grocery brief.)"
    )

    df = fetch_df("""
        SELECT p.PlayerID, p.Name, p.Role, p.MVPCount,
               t.ShortCode AS Team, t.FullName AS TeamFull,
               t.PrimaryColor, t.SecondaryColor, t.LogoFile
        FROM Players p
        JOIN Teams t ON t.TeamID = p.TeamID
        ORDER BY p.MVPCount DESC, p.Name ASC;
    """)

    if df.empty:
        st.info("No players yet.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Players tracked", len(df))
    c2.metric("Total MVP awards", int(df["MVPCount"].sum()))
    c3.metric("Top tally", int(df["MVPCount"].max()) if not df.empty else 0)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    for pos, (_, p) in enumerate(df.iterrows(), start=1):
        if p["MVPCount"] == 0:
            continue  # skip zero-MVP players in the highlight list
        logo = logo_html(p["Team"], p["PrimaryColor"], p["SecondaryColor"],
                         p["LogoFile"], size=32)
        stars = "🎖️ " * int(p["MVPCount"])
        st.markdown(f"""
            <div class="mvp-row">
                <div class="mvp-rank">#{pos}</div>
                {logo}
                <div class="mvp-info">
                    <div class="mvp-name">{p['Name']}</div>
                    <div class="mvp-meta">{p['Team']} · {p['Role']}</div>
                </div>
                <div class="mvp-count">{stars}<span style="opacity:.6;margin-left:8px;">×{int(p['MVPCount'])}</span></div>
            </div>
        """, unsafe_allow_html=True)

    if (df["MVPCount"] == 0).any():
        with st.expander("Players with no MVP awards yet"):
            zero = df[df["MVPCount"] == 0][["Name", "Team", "Role"]]
            st.dataframe(zero, use_container_width=True, hide_index=True)


# ===========================================================================
# 7. DAILY UPDATE (ESPNcricinfo hook)
# ===========================================================================
def page_update():
    st.markdown('<div class="eyebrow">Automation</div>', unsafe_allow_html=True)
    st.markdown("# Daily Update")
    st.caption(
        "Production hook for pulling fresh match data. "
        "In a deployed system, this function would scrape ESPNcricinfo "
        "on a daily cron job."
    )

    st.markdown("""
    ### How this works

    The function `fetch_latest()` in `database.py`:

    1. Queries for the next `Scheduled` match in chronological order.
    2. **For this demo** — generates plausible scores and calls `sp_record_result()`.
    3. Triggers cascade: SeasonStandings updates, AllTimeStats updates,
       MVP count increments, match Status flips to `Completed`.

    In production, step 2 would be replaced with an HTTP fetch + parse.
    The docstring shows the exact lines that would call `requests.get()`
    and `BeautifulSoup` on the ESPNcricinfo schedule page.
    """)

    next_match = fetch_df("""
        SELECT m.MatchID, m.MatchDate,
               t1.ShortCode AS T1, t2.ShortCode AS T2,
               v.Name AS Venue
        FROM Matches m
        JOIN Teams t1 ON t1.TeamID = m.Team1ID
        JOIN Teams t2 ON t2.TeamID = m.Team2ID
        JOIN Venues v ON v.VenueID = m.VenueID
        WHERE m.Status = 'Scheduled'
        ORDER BY m.MatchDate ASC LIMIT 1;
    """)

    if next_match.empty:
        st.info("No scheduled matches to fetch — every match in the database is complete.")
        return

    r = next_match.iloc[0]
    st.markdown(f"""
        <div class="match-card">
            <div class="match-meta">Next on schedule · {r['MatchDate']} · {r['Venue']}</div>
            <div class="match-fixture">{r['T1']} vs {r['T2']}</div>
            <div style="margin-top:.4rem;">{status_pill('Scheduled')}</div>
        </div>
    """, unsafe_allow_html=True)

    if st.button("🔄  Pull latest result", type="primary"):
        with st.spinner("Fetching from data source..."):
            time.sleep(1.0)
            new_id = fetch_latest()
        if new_id:
            st.success(f"✅ Match #{new_id} marked Completed. Standings refreshed by triggers.")
            time.sleep(0.6); st.rerun()
        else:
            st.info("No scheduled matches available.")


# ===========================================================================
# 8. SQL PLAYGROUND
# ===========================================================================
def page_sql():
    st.markdown('<div class="eyebrow">For the viva</div>', unsafe_allow_html=True)
    st.markdown("# SQL Playground")
    st.caption("All 10 required queries with explanations. Plus a free-form SELECT box.")

    tab1, tab2 = st.tabs(["📋 Required queries", "✏️ Free-form SQL"])

    with tab1:
        for qid, q in QUERY_CATALOG.items():
            with st.expander(q["label"]):
                st.markdown(f"*{q['explain']}*")
                st.code(q["sql"].strip(), language="sql")
                if st.button("Run query", key=f"run_{qid}"):
                    try:
                        df = run_query(qid)
                        st.success(f"Returned {len(df)} row(s).")
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.error(str(e))

    with tab2:
        st.caption("Only SELECT statements (read-only).")
        sql = st.text_area("SQL", value="SELECT * FROM MatchSummary LIMIT 10;", height=140)
        if st.button("Run", key="run_free"):
            if not sql.strip().lower().startswith("select"):
                st.error("Only SELECT statements allowed in the playground.")
            else:
                try:
                    df = run_raw(sql)
                    st.success(f"{len(df)} row(s).")
                    st.dataframe(df, use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(str(e))


# ===========================================================================
# 9. ABOUT / SCHEMA
# ===========================================================================
def page_about():
    st.markdown('<div class="eyebrow">Documentation</div>', unsafe_allow_html=True)
    st.markdown("# About this project")

    st.markdown("""
A complete **DBMS mini-project** modelling the IPL 2025 season.
Built with **Python + Streamlit** for the UI and **MySQL** for the database.

This implementation directly satisfies every requirement on the brief —
relational schema, normalization, schema alteration, joins, queries,
functions, views, stored procedures, and triggers — and includes a hook
for daily updates from ESPNcricinfo.
    """)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
### 🗂️ Tables (7)
- **Teams** — the 10 franchises
- **AllTimeStats** — historical totals (1:1 with Teams)
- **Venues** — IPL grounds
- **Players** — captains + stars, with MVPCount
- **Matches** — fixture fact table
- **MatchResults** — 1:1 with completed matches
- **SeasonStandings** — live 2025 points table

### 🔑 Constraints
PRIMARY KEY, FOREIGN KEY (with ON DELETE CASCADE / SET NULL),
NOT NULL, UNIQUE, CHECK (incl. BETWEEN, IN-list, table-level),
DEFAULT, AUTO_INCREMENT.

### 🛠️ ALTER TABLE
The function `demo_alter()` performs all three:
**ADD COLUMN** Sponsor · **MODIFY COLUMN** width ·
**DROP COLUMN** LegacyField (added and immediately dropped to prove the syntax).
        """)
    with c2:
        st.markdown("""
### ⚙️ Advanced objects

**Views (3)**
- `MatchSummary` — readable fixture+result row
- `LiveStandings` — current points table with NRR
- `TeamHistory` — all-time team performance

**Triggers (4)**
- `trg_no_self_match` — blocks a team from playing itself
- `trg_after_result` — updates SeasonStandings on result insert
- `trg_alltime_update` — updates AllTimeStats and Titles
- `trg_award_mvp` — increments MVPCount on Player of the Match

**Stored Procedures (2)**
- `sp_record_result()` — records match outcome
- `sp_schedule_match()` — adds new fixture (with OUT param)

**Daily-update hook**
- `fetch_latest()` — production-ready entry point with
  the BeautifulSoup outline for ESPNcricinfo scraping
        """)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.markdown("### Table row counts")
    counts = []
    for t in ["Teams", "Venues", "Players", "Matches", "MatchResults",
              "SeasonStandings", "AllTimeStats"]:
        n = int(fetch_df(f"SELECT COUNT(*) AS c FROM {t}").iloc[0]["c"])
        counts.append({"Table": t, "Rows": n})
    df = pd.DataFrame(counts)
    fig = go.Figure(go.Bar(
        x=df["Table"], y=df["Rows"], text=df["Rows"],
        textposition="outside",
        marker=dict(color="#00B2D6"),
        textfont=dict(color="#F5F7FB"),
    ))
    fig.update_layout(**PLOTLY_LAYOUT, height=320,
                      xaxis=dict(color="#F5F7FB"),
                      yaxis=dict(color="#F5F7FB", gridcolor="#2A3656"))
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
PAGES = {
    "🏠  Dashboard":         page_dashboard,
    "🛡️  Teams":              page_teams,
    "📅  Matches":            page_matches,
    "🏆  Live Standings":     page_standings,
    "📈  All-Time Stats":     page_alltime,
    "🎖️  MVP Leaderboard":    page_mvp,
    "🔄  Daily Update":       page_update,
    "🧪  SQL Playground":     page_sql,
    "📚  About / Schema":     page_about,
}
PAGES[page]()
