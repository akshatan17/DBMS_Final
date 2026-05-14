"""
queries.py
==========
The 10 demonstrable SQL queries — MySQL version.
Maps every requirement on the grocery brief to the IPL domain:

  Grocery Q1 INNER JOIN          -> Matches × Teams × Venues
  Grocery Q2 LEFT JOIN           -> Matches × MatchResults (incl. unplayed)
  Grocery Q3 Low-stock alert     -> Teams below playoff threshold
  Grocery Q4 Top 5 best-selling  -> Top 5 teams by points
  Grocery Q5 RIGHT JOIN          -> Venues × Matches (incl. unused venues)
  Grocery Q6 FULL OUTER JOIN     -> Teams ∪ AllTimeStats via UNION
  Grocery Q7 SUM(Price*Quantity) -> Total runs (SUM of scores) per team
  Grocery Q8 NEVER sold in 30d   -> Teams that haven't played in 30 days
  Grocery Q9 GROUP BY + HAVING   -> Teams with win rate above 50%
  Grocery Q10 Subquery           -> Each team's highest score this season
"""

import pandas as pd
from database import get_connection


QUERY_CATALOG = {
    "1_inner_join": {
        "label": "1. INNER JOIN — Completed matches with team names and venue",
        "sql": """
            SELECT m.MatchID, m.MatchDate,
                   t1.ShortCode AS Team1, t2.ShortCode AS Team2,
                   v.Name AS Venue
            FROM   Matches m
            INNER JOIN Teams  t1 ON t1.TeamID  = m.Team1ID
            INNER JOIN Teams  t2 ON t2.TeamID  = m.Team2ID
            INNER JOIN Venues v  ON v.VenueID  = m.VenueID
            WHERE  m.Status = 'Completed'
            ORDER  BY m.MatchDate DESC;
        """,
        "explain": "Three-way INNER JOIN — every completed match with all parent rows."
    },

    "2_left_join": {
        "label": "2. LEFT JOIN — All matches including those without a result row",
        "sql": """
            SELECT m.MatchID, m.MatchDate, m.Status,
                   COALESCE(t.ShortCode, 'TBD') AS Winner,
                   COALESCE(r.Margin, '—')     AS Margin
            FROM   Matches m
            LEFT JOIN MatchResults r ON r.MatchID = m.MatchID
            LEFT JOIN Teams t        ON t.TeamID  = r.WinnerID
            ORDER BY m.MatchDate DESC
            LIMIT 15;
        """,
        "explain": "Keeps every Match row even when MatchResults has no record yet."
    },

    "3_below_threshold": {
        "label": "3. Teams below playoff threshold (low-points alert — analogue of low-stock)",
        "sql": """
            SELECT t.ShortCode, t.FullName, s.Played, s.Points,
                   (8 - s.Points) AS PointsBelowSafety
            FROM   Teams t
            JOIN   SeasonStandings s ON s.TeamID = t.TeamID
            WHERE  s.Played > 0
              AND  s.Points < 8
            ORDER  BY s.Points ASC;
        """,
        "explain": "Filter rows where Points < 8 (rough playoff cut-off). Direct analogue of the 'stock below threshold' query."
    },

    "4_top_teams": {
        "label": "4. Top 5 teams by points (analogue of top-selling products)",
        "sql": """
            SELECT t.ShortCode, t.FullName, s.Played, s.Won, s.Lost, s.Points
            FROM   Teams t
            JOIN   SeasonStandings s ON s.TeamID = t.TeamID
            ORDER  BY s.Points DESC, (s.RunsFor - s.RunsAgainst) DESC
            LIMIT  5;
        """,
        "explain": "Sorted leaderboard with LIMIT — the live points table."
    },

    "5_right_join": {
        "label": "5. RIGHT JOIN — Venues with their match counts (incl. unused venues)",
        "sql": """
            SELECT v.Name AS Venue, v.City, COUNT(m.MatchID) AS MatchesHosted
            FROM   Matches m
            RIGHT JOIN Venues v ON v.VenueID = m.VenueID
            GROUP BY v.VenueID, v.Name, v.City
            ORDER BY MatchesHosted DESC;
        """,
        "explain": "RIGHT JOIN keeps every Venue, even ones that have hosted zero matches. MySQL supports RIGHT JOIN natively (SQLite needs a flipped LEFT JOIN)."
    },

    "6_full_outer": {
        "label": "6. FULL OUTER JOIN via UNION — Teams ↔ AllTimeStats reconciliation",
        "sql": """
            SELECT t.ShortCode, a.Titles
            FROM   Teams t
            LEFT JOIN AllTimeStats a ON a.TeamID = t.TeamID
            UNION
            SELECT t.ShortCode, a.Titles
            FROM   AllTimeStats a
            LEFT JOIN Teams t ON t.TeamID = a.TeamID;
        """,
        "explain": "MySQL versions before 8 (and the spec-portable form) use LEFT JOIN ∪ LEFT JOIN-swapped to emulate FULL OUTER JOIN."
    },

    "7_total_runs": {
        "label": "7. Total runs scored per team (SUM aggregate — analogue of SUM(price × qty))",
        "sql": """
            SELECT t.ShortCode, t.FullName,
                   SUM(runs_scored) AS TotalRuns,
                   COUNT(*)         AS InningsPlayed,
                   ROUND(AVG(runs_scored), 1) AS AvgPerInnings
            FROM (
                SELECT m.Team1ID AS TeamID, r.Team1Score AS runs_scored
                FROM   MatchResults r
                JOIN   Matches m ON m.MatchID = r.MatchID
                UNION ALL
                SELECT m.Team2ID AS TeamID, r.Team2Score AS runs_scored
                FROM   MatchResults r
                JOIN   Matches m ON m.MatchID = r.MatchID
            ) innings
            JOIN Teams t ON t.TeamID = innings.TeamID
            GROUP BY t.TeamID, t.ShortCode, t.FullName
            ORDER BY TotalRuns DESC;
        """,
        "explain": "UNION ALL stacks both innings of every match; SUM and AVG aggregate per team. Same shape as 'SUM(Price * Quantity)' in the grocery brief."
    },

    "8_not_recent": {
        "label": "8. Teams that haven't played in the last 30 days (analogue of never-sold-in-30-days)",
        "sql": """
            SELECT t.ShortCode, t.FullName
            FROM   Teams t
            WHERE  t.TeamID NOT IN (
                SELECT m.Team1ID FROM Matches m
                WHERE  m.Status = 'Completed'
                  AND  m.MatchDate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                UNION
                SELECT m.Team2ID FROM Matches m
                WHERE  m.Status = 'Completed'
                  AND  m.MatchDate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            )
            ORDER BY t.ShortCode;
        """,
        "explain": "NOT IN subquery + UNION + MySQL date arithmetic. Same shape as 'products never sold in last 30 days'."
    },

    "9_having": {
        "label": "9. GROUP BY + HAVING — Teams with win rate above 50%",
        "sql": """
            SELECT t.ShortCode, s.Played, s.Won,
                   ROUND(s.Won * 100.0 / NULLIF(s.Played, 0), 1) AS WinPercent
            FROM   Teams t
            JOIN   SeasonStandings s ON s.TeamID = t.TeamID
            WHERE  s.Played > 0
            GROUP  BY t.TeamID, t.ShortCode, s.Played, s.Won
            HAVING WinPercent > 50
            ORDER  BY WinPercent DESC;
        """,
        "explain": "HAVING filters the grouped result (can use aggregates; WHERE cannot)."
    },

    "10_subquery": {
        "label": "10. Subquery — Each team's highest score this season",
        "sql": """
            SELECT t.ShortCode, t.FullName,
                   MAX(innings.score) AS HighestScore
            FROM   Teams t
            LEFT JOIN (
                SELECT m.Team1ID AS TeamID, r.Team1Score AS score
                FROM   MatchResults r
                JOIN   Matches m ON m.MatchID = r.MatchID
                UNION ALL
                SELECT m.Team2ID AS TeamID, r.Team2Score AS score
                FROM   MatchResults r
                JOIN   Matches m ON m.MatchID = r.MatchID
            ) innings ON innings.TeamID = t.TeamID
            GROUP BY t.TeamID, t.ShortCode, t.FullName
            ORDER BY HighestScore DESC;
        """,
        "explain": "Derived-table subquery in the FROM clause. The inner query (UNION ALL) builds a list of every team-innings pair; outer query groups and finds each team's max."
    },
}


def run_query(qid: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(QUERY_CATALOG[qid]["sql"], conn)
    conn.close()
    return df


def run_raw(sql: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df
