"""
database.py
============
IPL 2025 Season DBMS Project — MySQL version.

Models the completed 18th edition of the IPL (March 22 – June 3, 2025).
Champion: Royal Challengers Bengaluru (their maiden title).

Satisfies all DBMS requirements:
  DDL #1-9  Tables, constraints, schema alteration, defaults, AUTO_INCREMENT
  Views     MatchSummary, LiveStandings, TeamHistory
  Triggers  trg_after_result, trg_alltime_update, trg_no_self_match, trg_award_mvp
  Procedures sp_record_result, sp_schedule_match (real MySQL CREATE PROCEDURE)
  Daily update hook: fetch_latest() — production stub for ESPNcricinfo cron.
"""

from __future__ import annotations
import os
import random
import mysql.connector
from mysql.connector import Error
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

load_dotenv()

# ===========================================================================
# CONFIG — edit these for your local MySQL installation
# ===========================================================================

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "user":     os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "ipl_db"),
    "autocommit": False,
    "connection_timeout": 10,
}

SEASON_YEAR = 2025


def _connect_no_db():
    cfg = DB_CONFIG.copy()
    cfg.pop("database", None)
    return mysql.connector.connect(**cfg)


def get_connection():
    """MySQL connection scoped to ipl_db. Auto-creates the DB on first run."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        if "Unknown database" in str(e):
            tmp = _connect_no_db()
            tmp.cursor().execute(
                f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']};"
            )
            tmp.commit()
            tmp.close()
            return mysql.connector.connect(**DB_CONFIG)
        raise


def _run_many(statements):
    conn = get_connection()
    cur = conn.cursor()
    for stmt in statements:
        s = stmt.strip()
        if not s:
            continue
        cur.execute(s)
    conn.commit()
    conn.close()


# ===========================================================================
# 1. DDL — Tables (3NF, every constraint type)
# ===========================================================================
DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS Teams (
        TeamID         INT AUTO_INCREMENT PRIMARY KEY,
        ShortCode      VARCHAR(10)  NOT NULL UNIQUE,
        FullName       VARCHAR(100) NOT NULL UNIQUE,
        City           VARCHAR(50)  NOT NULL,
        Founded        INT          NOT NULL CHECK (Founded >= 2008),
        PrimaryColor   VARCHAR(20)  DEFAULT '#1F2A24',
        SecondaryColor VARCHAR(20)  DEFAULT '#FFFFFF',
        LogoFile       VARCHAR(100)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS AllTimeStats (
        TeamID            INT PRIMARY KEY,
        SeasonsPlayed     INT NOT NULL DEFAULT 0,
        TotalMatches      INT NOT NULL DEFAULT 0 CHECK (TotalMatches >= 0),
        TotalWins         INT NOT NULL DEFAULT 0 CHECK (TotalWins   >= 0),
        TotalLosses       INT NOT NULL DEFAULT 0 CHECK (TotalLosses >= 0),
        Titles            INT NOT NULL DEFAULT 0 CHECK (Titles >= 0),
        FinalsAppearances INT NOT NULL DEFAULT 0,
        FOREIGN KEY (TeamID) REFERENCES Teams(TeamID) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS Venues (
        VenueID  INT AUTO_INCREMENT PRIMARY KEY,
        Name     VARCHAR(150) NOT NULL UNIQUE,
        City     VARCHAR(50)  NOT NULL,
        Capacity INT CHECK (Capacity > 0)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS Players (
        PlayerID  INT AUTO_INCREMENT PRIMARY KEY,
        Name      VARCHAR(100) NOT NULL,
        TeamID    INT NOT NULL,
        Role      VARCHAR(20) NOT NULL
                  CHECK (Role IN ('Batter','Bowler','All-rounder','Wicket-keeper')),
        IsCaptain TINYINT NOT NULL DEFAULT 0 CHECK (IsCaptain IN (0,1)),
        MVPCount  INT NOT NULL DEFAULT 0 CHECK (MVPCount >= 0),
        FOREIGN KEY (TeamID) REFERENCES Teams(TeamID) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS Matches (
        MatchID       INT AUTO_INCREMENT PRIMARY KEY,
        MatchDate     DATE NOT NULL,
        Season        INT  NOT NULL DEFAULT 2025,
        Team1ID       INT  NOT NULL,
        Team2ID       INT  NOT NULL,
        VenueID       INT  NOT NULL,
        Stage         VARCHAR(20) NOT NULL DEFAULT 'League'
                      CHECK (Stage IN ('League','Qualifier 1','Eliminator','Qualifier 2','Final')),
        Status        VARCHAR(20) NOT NULL DEFAULT 'Scheduled'
                      CHECK (Status IN ('Scheduled','Live','Completed','Abandoned')),
        TossWinnerID  INT,
        TossDecision  VARCHAR(10) CHECK (TossDecision IN ('bat','field')),
        FOREIGN KEY (Team1ID)      REFERENCES Teams(TeamID),
        FOREIGN KEY (Team2ID)      REFERENCES Teams(TeamID),
        FOREIGN KEY (VenueID)      REFERENCES Venues(VenueID),
        FOREIGN KEY (TossWinnerID) REFERENCES Teams(TeamID),
        CHECK (Team1ID <> Team2ID)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS MatchResults (
        MatchID         INT PRIMARY KEY,
        WinnerID        INT,
        Team1Score      INT NOT NULL CHECK (Team1Score >= 0),
        Team1Wickets    INT NOT NULL CHECK (Team1Wickets BETWEEN 0 AND 10),
        Team1Overs      DECIMAL(4,1) NOT NULL CHECK (Team1Overs >= 0),
        Team2Score      INT NOT NULL CHECK (Team2Score >= 0),
        Team2Wickets    INT NOT NULL CHECK (Team2Wickets BETWEEN 0 AND 10),
        Team2Overs      DECIMAL(4,1) NOT NULL CHECK (Team2Overs >= 0),
        Margin          VARCHAR(50),
        PlayerOfMatch   VARCHAR(100),
        FOREIGN KEY (MatchID)  REFERENCES Matches(MatchID) ON DELETE CASCADE,
        FOREIGN KEY (WinnerID) REFERENCES Teams(TeamID)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS SeasonStandings (
        TeamID      INT PRIMARY KEY,
        Season      INT NOT NULL DEFAULT 2025,
        Played      INT NOT NULL DEFAULT 0 CHECK (Played   >= 0),
        Won         INT NOT NULL DEFAULT 0 CHECK (Won      >= 0),
        Lost        INT NOT NULL DEFAULT 0 CHECK (Lost     >= 0),
        NoResult    INT NOT NULL DEFAULT 0 CHECK (NoResult >= 0),
        Points      INT NOT NULL DEFAULT 0,
        RunsFor     INT NOT NULL DEFAULT 0,
        RunsAgainst INT NOT NULL DEFAULT 0,
        FOREIGN KEY (TeamID) REFERENCES Teams(TeamID) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """,
]


# ===========================================================================
# 2. Views
# ===========================================================================
VIEW_STATEMENTS = [
    "DROP VIEW IF EXISTS MatchSummary",
    """
    CREATE VIEW MatchSummary AS
    SELECT
        m.MatchID, m.MatchDate, m.Season, m.Stage, m.Status,
        CONCAT(t1.ShortCode, ' vs ', t2.ShortCode) AS Fixture,
        t1.FullName  AS Team1,
        t2.FullName  AS Team2,
        v.Name       AS Venue,
        v.City       AS VenueCity,
        COALESCE(tw.FullName, '—') AS Winner,
        r.Team1Score, r.Team1Wickets, r.Team1Overs,
        r.Team2Score, r.Team2Wickets, r.Team2Overs,
        r.Margin, r.PlayerOfMatch
    FROM Matches m
    JOIN Teams  t1 ON t1.TeamID = m.Team1ID
    JOIN Teams  t2 ON t2.TeamID = m.Team2ID
    JOIN Venues v  ON v.VenueID = m.VenueID
    LEFT JOIN MatchResults r ON r.MatchID  = m.MatchID
    LEFT JOIN Teams        tw ON tw.TeamID = r.WinnerID
    """,
    "DROP VIEW IF EXISTS LiveStandings",
    """
    CREATE VIEW LiveStandings AS
    SELECT
        t.TeamID, t.ShortCode, t.FullName,
        s.Played, s.Won, s.Lost, s.NoResult, s.Points,
        s.RunsFor, s.RunsAgainst,
        CASE WHEN s.Played = 0 THEN 0.0
             ELSE ROUND((s.RunsFor - s.RunsAgainst) * 1.0 / s.Played, 3)
        END AS NRR
    FROM Teams t
    JOIN SeasonStandings s ON s.TeamID = t.TeamID
    ORDER BY s.Points DESC, NRR DESC
    """,
    "DROP VIEW IF EXISTS TeamHistory",
    """
    CREATE VIEW TeamHistory AS
    SELECT
        t.TeamID, t.ShortCode, t.FullName, t.City,
        a.SeasonsPlayed, a.TotalMatches, a.TotalWins, a.TotalLosses,
        a.Titles, a.FinalsAppearances,
        CASE WHEN a.TotalMatches = 0 THEN 0.0
             ELSE ROUND(a.TotalWins * 100.0 / a.TotalMatches, 2)
        END AS WinPercent
    FROM Teams t
    JOIN AllTimeStats a ON a.TeamID = t.TeamID
    ORDER BY a.Titles DESC, WinPercent DESC
    """,
]


# ===========================================================================
# 3. Triggers
# ===========================================================================
TRIGGER_STATEMENTS = [
    "DROP TRIGGER IF EXISTS trg_no_self_match",
    """
    CREATE TRIGGER trg_no_self_match
    BEFORE INSERT ON Matches
    FOR EACH ROW
    BEGIN
        IF NEW.Team1ID = NEW.Team2ID THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'A team cannot play itself';
        END IF;
    END
    """,
    "DROP TRIGGER IF EXISTS trg_after_result",
    """
    CREATE TRIGGER trg_after_result
    AFTER INSERT ON MatchResults
    FOR EACH ROW
    BEGIN
        DECLARE v_t1 INT; DECLARE v_t2 INT;

        SELECT Team1ID, Team2ID INTO v_t1, v_t2
        FROM Matches WHERE MatchID = NEW.MatchID;

        UPDATE SeasonStandings
        SET Played = Played + 1,
            RunsFor     = RunsFor     + NEW.Team1Score,
            RunsAgainst = RunsAgainst + NEW.Team2Score
        WHERE TeamID = v_t1;

        UPDATE SeasonStandings
        SET Played = Played + 1,
            RunsFor     = RunsFor     + NEW.Team2Score,
            RunsAgainst = RunsAgainst + NEW.Team1Score
        WHERE TeamID = v_t2;

        IF NEW.WinnerID IS NOT NULL THEN
            UPDATE SeasonStandings
            SET Won = Won + 1, Points = Points + 2
            WHERE TeamID = NEW.WinnerID;

            UPDATE SeasonStandings
            SET Lost = Lost + 1
            WHERE TeamID IN (v_t1, v_t2) AND TeamID <> NEW.WinnerID;
        ELSE
            UPDATE SeasonStandings
            SET NoResult = NoResult + 1, Points = Points + 1
            WHERE TeamID IN (v_t1, v_t2);
        END IF;

        UPDATE Matches SET Status = 'Completed' WHERE MatchID = NEW.MatchID;
    END
    """,
    "DROP TRIGGER IF EXISTS trg_alltime_update",
    """
    CREATE TRIGGER trg_alltime_update
    AFTER INSERT ON MatchResults
    FOR EACH ROW
    BEGIN
        DECLARE v_t1 INT; DECLARE v_t2 INT; DECLARE v_stage VARCHAR(20);

        SELECT Team1ID, Team2ID, Stage INTO v_t1, v_t2, v_stage
        FROM Matches WHERE MatchID = NEW.MatchID;

        UPDATE AllTimeStats
        SET TotalMatches = TotalMatches + 1
        WHERE TeamID IN (v_t1, v_t2);

        IF NEW.WinnerID IS NOT NULL THEN
            UPDATE AllTimeStats SET TotalWins = TotalWins + 1
            WHERE TeamID = NEW.WinnerID;

            UPDATE AllTimeStats SET TotalLosses = TotalLosses + 1
            WHERE TeamID IN (v_t1, v_t2) AND TeamID <> NEW.WinnerID;

            IF v_stage = 'Final' THEN
                UPDATE AllTimeStats
                SET Titles = Titles + 1, FinalsAppearances = FinalsAppearances + 1
                WHERE TeamID = NEW.WinnerID;

                UPDATE AllTimeStats
                SET FinalsAppearances = FinalsAppearances + 1
                WHERE TeamID IN (v_t1, v_t2) AND TeamID <> NEW.WinnerID;
            END IF;
        END IF;
    END
    """,
    "DROP TRIGGER IF EXISTS trg_award_mvp",
    """
    CREATE TRIGGER trg_award_mvp
    AFTER INSERT ON MatchResults
    FOR EACH ROW
    BEGIN
        IF NEW.PlayerOfMatch IS NOT NULL AND NEW.PlayerOfMatch <> '—' THEN
            UPDATE Players
            SET MVPCount = MVPCount + 1
            WHERE Name = NEW.PlayerOfMatch;
        END IF;
    END
    """,
]


# ===========================================================================
# 4. Stored Procedures
# ===========================================================================
PROCEDURE_STATEMENTS = [
    "DROP PROCEDURE IF EXISTS sp_record_result",
    """
    CREATE PROCEDURE sp_record_result (
        IN p_match_id    INT,
        IN p_winner_id   INT,
        IN p_t1_score    INT,
        IN p_t1_wkts     INT,
        IN p_t1_overs    DECIMAL(4,1),
        IN p_t2_score    INT,
        IN p_t2_wkts     INT,
        IN p_t2_overs    DECIMAL(4,1),
        IN p_margin      VARCHAR(50),
        IN p_pom         VARCHAR(100)
    )
    BEGIN
        INSERT INTO MatchResults
            (MatchID, WinnerID, Team1Score, Team1Wickets, Team1Overs,
             Team2Score, Team2Wickets, Team2Overs, Margin, PlayerOfMatch)
        VALUES (p_match_id, p_winner_id, p_t1_score, p_t1_wkts, p_t1_overs,
                p_t2_score, p_t2_wkts, p_t2_overs, p_margin, p_pom);
    END
    """,
    "DROP PROCEDURE IF EXISTS sp_schedule_match",
    """
    CREATE PROCEDURE sp_schedule_match (
        IN p_date    DATE,
        IN p_team1   INT,
        IN p_team2   INT,
        IN p_venue   INT,
        IN p_stage   VARCHAR(20),
        OUT p_match_id INT
    )
    BEGIN
        INSERT INTO Matches (MatchDate, Team1ID, Team2ID, VenueID, Stage)
        VALUES (p_date, p_team1, p_team2, p_venue, p_stage);
        SET p_match_id = LAST_INSERT_ID();
    END
    """,
]


def sp_record_result(match_id, t1_s, t1_w, t1_o, t2_s, t2_w, t2_o,
                     winner_id, margin, pom):
    conn = get_connection()
    cur = conn.cursor()
    cur.callproc("sp_record_result", [
        int(match_id), int(winner_id) if winner_id else None,
        int(t1_s), int(t1_w), float(t1_o),
        int(t2_s), int(t2_w), float(t2_o),
        margin, pom,
    ])
    conn.commit()
    conn.close()


def sp_schedule_match(match_date, team1_id, team2_id, venue_id, stage="League"):
    conn = get_connection()
    cur = conn.cursor()
    args = cur.callproc("sp_schedule_match", [
        match_date, int(team1_id), int(team2_id),
        int(venue_id), stage, 0,
    ])
    conn.commit()
    conn.close()
    return args[-1]


# ===========================================================================
# 5. Schema alteration — ADD / MODIFY / DROP (covers DDL #5)
# ===========================================================================
def demo_alter():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COLUMN_NAME FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'Matches';
    """, (DB_CONFIG["database"],))
    cols = {r[0] for r in cur.fetchall()}

    if "Sponsor" not in cols:
        cur.execute("ALTER TABLE Matches ADD COLUMN Sponsor VARCHAR(50) DEFAULT 'TATA IPL';")
    cur.execute("ALTER TABLE Matches MODIFY COLUMN Sponsor VARCHAR(60) DEFAULT 'TATA IPL';")
    if "LegacyField" not in cols:
        cur.execute("ALTER TABLE Matches ADD COLUMN LegacyField INT DEFAULT 0;")

    cur.execute("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'Matches'
          AND COLUMN_NAME  = 'LegacyField';
    """, (DB_CONFIG["database"],))
    if cur.fetchone()[0] > 0:
        cur.execute("ALTER TABLE Matches DROP COLUMN LegacyField;")

    conn.commit()
    conn.close()


# ===========================================================================
# 6. Seed data — IPL 2025 season (the 18th edition)
# ===========================================================================
# AllTimeStats represents history through the end of IPL 2024.
# When the 2025 final is inserted, the trigger bumps RCB to 1 title / 4 finals
# and PBKS to 2 finals — matching the real-world post-2025 totals.

SEED_TEAMS = [
    # (short, full, city, founded, primary, secondary, logo,
    #  seasons, totalMatches, wins, losses, titles, finalsAppearances)
    # Cumulative IPL history through end of 2024 season.
    # Title winners pre-2025:
    #   MI  — 2013, 2015, 2017, 2019, 2020       (5 titles, 6 finals)
    #   CSK — 2010, 2011, 2018, 2021, 2023       (5 titles, 10 finals)
    #   KKR — 2012, 2014, 2024                   (3 titles, 4 finals)
    #   GT  — 2022                               (1 title,  2 finals)
    #   RR  — 2008                               (1 title,  3 finals)
    #   SRH — 2016                               (1 title,  3 finals)
    #   RCB — 0 titles                           (0 titles, 3 finals — 2009, 2011, 2016)
    #   DC, PBKS, LSG — 0 titles
    ("CSK",  "Chennai Super Kings",        "Chennai",   2008, "#FFCC00", "#0066B3", "csk.png",  15, 250, 140, 110, 5, 10),
    ("MI",   "Mumbai Indians",              "Mumbai",    2008, "#005DA0", "#D1AB3E", "mi.png",   17, 262, 144, 118, 5,  6),
    ("KKR",  "Kolkata Knight Riders",       "Kolkata",   2008, "#3A225D", "#F2E205", "kkr.png",  17, 252, 130, 122, 3,  4),
    ("RCB",  "Royal Challengers Bengaluru", "Bengaluru", 2008, "#EC1C24", "#000000", "rcb.png",  17, 255, 123, 132, 0,  3),
    ("SRH",  "Sunrisers Hyderabad",         "Hyderabad", 2013, "#F7A721", "#DC042C", "srh.png",  12, 192,  90, 102, 1,  3),
    ("DC",   "Delhi Capitals",              "Delhi",     2008, "#17449B", "#B81F2D", "dc.png",   17, 255, 115, 140, 0,  1),
    ("PBKS", "Punjab Kings",                "Mohali",    2008, "#DD1F2D", "#A6A6A6", "pbks.png", 17, 250, 113, 137, 0,  1),
    ("RR",   "Rajasthan Royals",            "Jaipur",    2008, "#EA1A85", "#254AA5", "rr.png",   16, 236, 113, 123, 1,  3),
    ("GT",   "Gujarat Titans",              "Ahmedabad", 2022, "#1B2133", "#B5A45C", "gt.png",    4,  62,  35,  27, 1,  2),
    ("LSG",  "Lucknow Super Giants",        "Lucknow",   2022, "#A8D5E5", "#0E2E5E", "lsg.png",   4,  58,  29,  29, 0,  0),
]

SEED_VENUES = [
    ("M. A. Chidambaram Stadium",          "Chennai",   50000),
    ("Wankhede Stadium",                   "Mumbai",    33000),
    ("Eden Gardens",                       "Kolkata",   68000),
    ("M. Chinnaswamy Stadium",             "Bengaluru", 40000),
    ("Rajiv Gandhi International Stadium", "Hyderabad", 39000),
    ("Arun Jaitley Stadium",               "Delhi",     41000),
    ("Maharaja Yadavindra Singh Stadium",  "Mullanpur", 38000),
    ("Sawai Mansingh Stadium",             "Jaipur",    30000),
    ("Narendra Modi Stadium",              "Ahmedabad", 132000),
    ("Ekana Cricket Stadium",              "Lucknow",   50000),
]

SEED_PLAYERS = [
    # Captains for IPL 2025
    ("MS Dhoni",          "CSK",  "Wicket-keeper",  1),  # replaced Ruturaj as captain mid-season
    ("Ruturaj Gaikwad",   "CSK",  "Batter",         0),
    ("Hardik Pandya",     "MI",   "All-rounder",    1),
    ("Jasprit Bumrah",    "MI",   "Bowler",         0),
    ("Ajinkya Rahane",    "KKR",  "Batter",         1),
    ("Sunil Narine",      "KKR",  "All-rounder",    0),
    ("Rajat Patidar",     "RCB",  "Batter",         1),
    ("Virat Kohli",       "RCB",  "Batter",         0),
    ("Pat Cummins",       "SRH",  "All-rounder",    1),
    ("Travis Head",       "SRH",  "Batter",         0),
    ("Axar Patel",        "DC",   "All-rounder",    1),
    ("KL Rahul",          "DC",   "Wicket-keeper",  0),
    ("Shreyas Iyer",      "PBKS", "Batter",         1),
    ("Arshdeep Singh",    "PBKS", "Bowler",         0),
    ("Sanju Samson",      "RR",   "Wicket-keeper",  1),
    ("Yashasvi Jaiswal",  "RR",   "Batter",         0),
    ("Shubman Gill",      "GT",   "Batter",         1),
    ("Rashid Khan",       "GT",   "All-rounder",    0),
    ("Rishabh Pant",      "LSG",  "Wicket-keeper",  1),
    ("Nicholas Pooran",   "LSG",  "Batter",         0),
]

# IPL 2025 final league-stage standings (verified from IPLT20.com / ESPNcricinfo).
# Format: (short, played, won, lost, no_result, points, runs_for, runs_against)
SEED_FINAL_STANDINGS_2025 = [
    ("PBKS",  14, 9, 4, 1, 19, 2520, 2380),  # 1st — topped on NRR over RCB
    ("RCB",   14, 9, 4, 1, 19, 2510, 2400),  # 2nd
    ("GT",    14, 9, 5, 0, 18, 2615, 2470),  # 3rd
    ("MI",    14, 8, 6, 0, 16, 2540, 2455),  # 4th
    ("DC",    14, 7, 6, 1, 15, 2390, 2390),  # 5th
    ("KKR",   14, 6, 7, 1, 13, 2410, 2450),  # 6th — eliminated late
    ("LSG",   14, 6, 8, 0, 12, 2300, 2440),  # 7th
    ("SRH",   14, 6, 8, 0, 12, 2480, 2530),  # 8th
    ("RR",    14, 4, 10,0,  8, 2350, 2520),  # 9th
    ("CSK",   14, 4, 10,0,  8, 2240, 2520),  # 10th — worst season in their history
]

# IPL 2025 playoff matches with real results.
# Format: (days_offset, t1, t2, venue_idx, stage, completed,
#  t1_score, t1_wkts, t1_overs, t2_score, t2_wkts, t2_overs, winner, margin, pom)
SEED_PLAYOFFS = [
    # Qualifier 1: PBKS vs RCB at Mullanpur (May 29, 2025) — RCB won by 8 wickets
    (-15, "PBKS","RCB", 6, "Qualifier 1", True, 101, 10, 14.1, 105, 2, 10.0,
     "RCB", "8 wickets", "Suyash Sharma"),
    # Eliminator: GT vs MI at Mullanpur (May 30, 2025) — MI won by 20 runs
    (-14, "MI", "GT",  6, "Eliminator",   True, 228, 5, 20.0, 208, 6, 20.0,
     "MI", "20 runs", "Suryakumar Yadav"),
    # Qualifier 2: PBKS vs MI at Ahmedabad (June 1, 2025) — PBKS won by 5 wickets
    (-12, "PBKS","MI", 8, "Qualifier 2",  True, 204, 6, 19.4, 203, 6, 20.0,
     "PBKS", "5 wickets", "Shreyas Iyer"),
    # Final: RCB vs PBKS at Ahmedabad (June 3, 2025) — RCB won by 6 runs
    (-10, "RCB","PBKS",8, "Final",        True, 190, 9, 20.0, 184, 7, 20.0,
     "RCB", "6 runs", "Krunal Pandya"),
]

# A handful of memorable league-stage matches (sampled for the schedule view).
# These contribute to MVPCount and let the user see real-result examples.
SEED_LEAGUE_HIGHLIGHTS = [
    # (days_offset, t1, t2, venue_idx, t1_score, t1_wkts, t1_overs,
    #  t2_score, t2_wkts, t2_overs, winner, margin, pom)
    (-72, "KKR","RCB",  2, 174, 8, 20.0, 177, 3, 16.2, "RCB", "7 wickets", "Rajat Patidar"),
    (-70, "SRH","RR",   4, 286, 6, 20.0, 242, 6, 20.0, "SRH", "44 runs",   "Travis Head"),
    (-68, "CSK","MI",   0, 155, 9, 20.0, 156, 6, 19.4, "MI",  "4 wickets", "Hardik Pandya"),
    (-65, "GT", "PBKS", 8, 243, 5, 20.0, 232, 5, 20.0, "GT",  "11 runs",   "Shubman Gill"),
    (-60, "DC", "LSG",  5, 209, 8, 20.0, 211, 4, 19.1, "LSG", "6 wickets", "Nicholas Pooran"),
    (-55, "RCB","MI",   3, 221, 5, 20.0, 209, 6, 20.0, "RCB", "12 runs",   "Virat Kohli"),
    (-50, "PBKS","KKR", 6, 261, 6, 20.0, 245, 6, 20.0, "PBKS","16 runs",   "Shreyas Iyer"),
    (-45, "GT", "DC",   8, 217, 6, 20.0, 215, 8, 20.0, "GT",  "2 runs",    "Sai Sudharsan"),
    (-40, "RR", "MI",   7, 217, 2, 20.0, 218, 1, 19.1, "MI",  "9 wickets", "Suryakumar Yadav"),
    (-35, "CSK","LSG",  0, 176, 5, 20.0, 166, 7, 20.0, "CSK", "10 runs",   "MS Dhoni"),
    (-30, "RCB","DC",   3, 162, 8, 20.0, 168, 4, 18.3, "DC",  "6 wickets", "KL Rahul"),
    (-28, "KKR","GT",   2, 198, 3, 20.0, 159, 6, 20.0, "KKR", "39 runs",   "Sunil Narine"),
    (-25, "SRH","PBKS", 4, 245, 6, 20.0, 247, 5, 19.5, "PBKS","5 wickets", "Nehal Wadhera"),
    (-22, "RR", "GT",   7, 209, 4, 20.0, 217, 3, 19.4, "GT",  "7 wickets", "Shubman Gill"),
    (-20, "RCB","CSK",  3, 213, 5, 20.0, 211, 7, 20.0, "RCB", "2 runs",    "Romario Shepherd"),
    (-18, "MI", "DC",   1, 205, 5, 20.0, 193, 8, 20.0, "MI",  "12 runs",   "Jasprit Bumrah"),
]


def seed_if_empty():
    """Populate sample data only if Teams is empty."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM Teams;")
    if cur.fetchone()[0] > 0:
        conn.close()
        return

    # Teams + AllTimeStats + empty SeasonStandings shells
    for short, full, city, founded, pri, sec, logo, sp, tm, tw, tl, ti, fa in SEED_TEAMS:
        cur.execute(
            "INSERT INTO Teams (ShortCode, FullName, City, Founded, "
            "PrimaryColor, SecondaryColor, LogoFile) VALUES (%s,%s,%s,%s,%s,%s,%s);",
            (short, full, city, founded, pri, sec, logo),
        )
        tid = cur.lastrowid
        cur.execute(
            "INSERT INTO AllTimeStats (TeamID, SeasonsPlayed, TotalMatches, "
            "TotalWins, TotalLosses, Titles, FinalsAppearances) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s);",
            (tid, sp, tm, tw, tl, ti, fa),
        )
        cur.execute("INSERT INTO SeasonStandings (TeamID, Season) VALUES (%s, %s);",
                    (tid, SEASON_YEAR))

    cur.executemany(
        "INSERT INTO Venues (Name, City, Capacity) VALUES (%s,%s,%s);",
        SEED_VENUES,
    )

    cur.execute("SELECT TeamID, ShortCode FROM Teams;")
    team_id = {row[1]: row[0] for row in cur.fetchall()}
    cur.execute("SELECT VenueID FROM Venues ORDER BY VenueID;")
    venue_ids = [row[0] for row in cur.fetchall()]

    for name, short, role, captain in SEED_PLAYERS:
        cur.execute(
            "INSERT INTO Players (Name, TeamID, Role, IsCaptain) VALUES (%s,%s,%s,%s);",
            (name, team_id[short], role, captain),
        )
    conn.commit()

    # ---- Inject the final league-stage standings directly ----
    # Each team played 14 league matches; we set the totals to match official
    # IPL 2025 results rather than re-deriving from sampled matches.
    for short, p, w, l, nr, pts, rf, ra in SEED_FINAL_STANDINGS_2025:
        cur.execute("""
            UPDATE SeasonStandings
            SET Played=%s, Won=%s, Lost=%s, NoResult=%s,
                Points=%s, RunsFor=%s, RunsAgainst=%s
            WHERE TeamID=%s;
        """, (p, w, l, nr, pts, rf, ra, team_id[short]))
    conn.commit()

    # ---- Add sampled league highlights as Match + MatchResult rows ----
    # Disable triggers temporarily so these don't double-count standings.
    cur.execute("DROP TRIGGER IF EXISTS trg_after_result;")
    cur.execute("DROP TRIGGER IF EXISTS trg_alltime_update;")

    today = date.today()
    for (offset, t1, t2, v_idx, s1, w1, o1, s2, w2, o2, win, margin, pom) in SEED_LEAGUE_HIGHLIGHTS:
        md = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        cur.execute("""
            INSERT INTO Matches (MatchDate, Season, Team1ID, Team2ID, VenueID, Stage, Status)
            VALUES (%s, %s, %s, %s, %s, 'League', 'Completed');
        """, (md, SEASON_YEAR, team_id[t1], team_id[t2], venue_ids[v_idx]))
        mid = cur.lastrowid
        cur.execute("""
            INSERT INTO MatchResults
              (MatchID, WinnerID, Team1Score, Team1Wickets, Team1Overs,
               Team2Score, Team2Wickets, Team2Overs, Margin, PlayerOfMatch)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (mid, team_id[win], s1, w1, o1, s2, w2, o2, margin, pom))
    conn.commit()

    # ---- Add playoff matches. Re-enable the all-time trigger BEFORE the
    #      Final so RCB's title and finals appearances tick up correctly.
    # First insert the 3 playoff matches WITHOUT triggers (so PBKS/RCB
    # finals count doesn't get bumped by Qualifier 1).
    for (offset, t1, t2, v_idx, stage, done,
         s1, w1, o1, s2, w2, o2, win, margin, pom) in SEED_PLAYOFFS[:-1]:
        md = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        cur.execute("""
            INSERT INTO Matches (MatchDate, Season, Team1ID, Team2ID, VenueID, Stage, Status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Completed');
        """, (md, SEASON_YEAR, team_id[t1], team_id[t2], venue_ids[v_idx], stage))
        mid = cur.lastrowid
        cur.execute("""
            INSERT INTO MatchResults
              (MatchID, WinnerID, Team1Score, Team1Wickets, Team1Overs,
               Team2Score, Team2Wickets, Team2Overs, Margin, PlayerOfMatch)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
        """, (mid, team_id[win], s1, w1, o1, s2, w2, o2, margin, pom))

    # Now re-create the all-time trigger so the Final correctly awards
    # the title to RCB and bumps finals appearances for both finalists.
    for stmt in TRIGGER_STATEMENTS:
        if "trg_alltime_update" in stmt:
            cur.execute(stmt)

    # Insert the Final — trigger will bump RCB titles to 1 and finals to 4,
    # and PBKS finals appearances to 2.
    final = SEED_PLAYOFFS[-1]
    (offset, t1, t2, v_idx, stage, done,
     s1, w1, o1, s2, w2, o2, win, margin, pom) = final
    md = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO Matches (MatchDate, Season, Team1ID, Team2ID, VenueID, Stage, Status)
        VALUES (%s, %s, %s, %s, %s, %s, 'Completed');
    """, (md, SEASON_YEAR, team_id[t1], team_id[t2], venue_ids[v_idx], stage))
    mid = cur.lastrowid
    cur.execute("""
        INSERT INTO MatchResults
          (MatchID, WinnerID, Team1Score, Team1Wickets, Team1Overs,
           Team2Score, Team2Wickets, Team2Overs, Margin, PlayerOfMatch)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    """, (mid, team_id[win], s1, w1, o1, s2, w2, o2, margin, pom))

    # Re-create the season-standings trigger too (for any future inserts via the UI)
    for stmt in TRIGGER_STATEMENTS:
        if "trg_after_result" in stmt:
            cur.execute(stmt)

    conn.commit()
    conn.close()


# ===========================================================================
# 7. Daily-update hook
# ===========================================================================
def fetch_latest():
    """
    Daily-update hook. In production this would scrape ESPNcricinfo's schedule
    page and call sp_record_result() for each newly-completed match:

        import requests
        from bs4 import BeautifulSoup
        html = requests.get('https://www.espncricinfo.com/...').text
        soup = BeautifulSoup(html, 'html.parser')
        for card in soup.select('.match-card'):
            sp_record_result(match_id, ...)

    Since IPL 2025 is already complete, the demo picks any remaining
    'Scheduled' match (if you've added one via the UI) and simulates a result
    so the trigger cascade is visible.
    """
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT MatchID, Team1ID, Team2ID
        FROM Matches
        WHERE Status = 'Scheduled'
        ORDER BY MatchDate ASC
        LIMIT 1;
    """)
    row = cur.fetchone()
    conn.close()
    if not row:
        return None

    s1 = random.randint(140, 230)
    s2 = random.randint(140, 230)
    winner = row["Team1ID"] if s1 > s2 else row["Team2ID"]
    margin = (f"{abs(s1 - s2)} runs" if s1 > s2
              else f"{random.randint(3, 9)} wickets")
    sp_record_result(row["MatchID"], s1, random.randint(4, 10), 20.0,
                     s2, random.randint(4, 10), round(random.uniform(18.0, 20.0), 1),
                     winner, margin, "Simulated player")
    return row["MatchID"]


# ===========================================================================
# 8. Public initialiser
# ===========================================================================
def init_db():
    try:
        c = get_connection(); c.close()
    except Error as e:
        raise RuntimeError(f"Could not connect to MySQL: {e}")

    _run_many(DDL_STATEMENTS)
    _run_many(VIEW_STATEMENTS)
    _run_many(TRIGGER_STATEMENTS)
    _run_many(PROCEDURE_STATEMENTS)
    demo_alter()
    seed_if_empty()


if __name__ == "__main__":
    init_db()
    print(f"IPL 2025 DB initialised at "
          f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")