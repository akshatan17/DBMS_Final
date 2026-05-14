# 🏏 IPL 2026 — DBMS Mini-Project (MySQL Edition)

A complete database-driven application for the IPL 2026 season, built with
**Python + Streamlit** on top of a **MySQL** database.

---

## What's covered

- ✅ Relational schema design (7 tables in 3NF)
- ✅ Schema alteration — `ALTER TABLE` with ADD, MODIFY, and DROP
- ✅ Joins — INNER, LEFT, RIGHT, FULL OUTER (via UNION)
- ✅ Queries — 10 demo queries with explanations
- ✅ Functions — MAX, AVG, COUNT, SUM, ROUND, COALESCE, NULLIF, CASE, DATE_SUB
- ✅ Views (3) — MatchSummary, LiveStandings, TeamHistory
- ✅ Stored procedures (2) — `sp_record_result()`, `sp_schedule_match()` (real MySQL `CREATE PROCEDURE`)
- ✅ Triggers (4) — auto-update standings, all-time stats, MVP count, anti-self-match guard
- ✅ Daily-update hook for ESPNcricinfo (architecture in place; demo simulates)

---

## Setup — once per machine

### 1. Install MySQL (if not already installed)

You probably already have it from your DBMS lab (MySQL Workbench / XAMPP /
WAMP all include MySQL Server). Make sure the MySQL service is running.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Edit `database.py` to match your MySQL setup

Open `database.py` and find the `DB_CONFIG` block at the top:

```python
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "iplpass",
    "database": "ipl_db",
}
```

Change `"password"` to **your** MySQL root password. If your root has no
password (some XAMPP installs), set `"password": ""`.

### 4. Run

```bash
streamlit run app.py
```

The browser opens at `http://localhost:8501`. On first run:

- The database `ipl_db` is created (or reused) automatically
- All 7 tables are built
- Views, triggers, and procedures are created
- Sample data is seeded — 10 teams, 10 venues, 20 players, 30 matches

---

## To reset the database

In MySQL Workbench (or `mysql>` CLI):

```sql
DROP DATABASE ipl_db;
```

Then refresh the Streamlit page. Everything will be rebuilt and re-seeded.

---

## To add real team logos

Drop PNG files into `logos/` named:

`csk.png`, `mi.png`, `kkr.png`, `rcb.png`, `srh.png`,
`dc.png`, `pbks.png`, `rr.png`, `gt.png`, `lsg.png`

Until you do, the app shows colored-initials circles in each team's official
brand colors as a fallback.

---

## App pages

| Page | What it does |
|---|---|
| Dashboard | KPIs, points table, recent + upcoming matches |
| Teams | All 10 franchises with all-time stats and squad |
| Matches | Schedule view, record-result form, schedule-new-match form |
| Live Standings | Points table from the LiveStandings view |
| All-Time Stats | Historical win % and titles by team |
| MVP Leaderboard | Player of the Match counts (trigger-maintained) |
| Daily Update | The fetch-latest hook for ESPNcricinfo |
| SQL Playground | All 10 required queries runnable on demand |
| About / Schema | Concept walkthrough |

---

## Files

```
ipl_dbms/
├── app.py            # Streamlit UI (9 pages)
├── database.py       # MySQL schema, triggers, views, procedures, seed
├── queries.py        # The 10 required SQL queries
├── style.css         # Dark theme (navy + gold + cyan)
├── EXPLAIN.md        # ⭐ Viva crib-sheet — read this before your demo
├── README.md         # This file
├── requirements.txt
└── logos/            # Drop team logo PNGs here (optional)
```

**Read `EXPLAIN.md`** — it has every concept, every query, every trigger
explained line-by-line in viva-ready language.

---

## Common problems

**"Access denied for user 'root'@'localhost'"** — wrong password in
`DB_CONFIG`. Open MySQL Workbench and confirm what password works there,
then paste that into `database.py`.

**"Can't connect to MySQL server"** — the MySQL service isn't running.
On Windows: open Services, find "MySQL" (or "MySQL80"), start it.
On Mac: `brew services start mysql`.

**"Unknown database 'ipl_db'"** — auto-create didn't fire. Run
`CREATE DATABASE ipl_db;` manually in Workbench, then re-run Streamlit.

🏏 Good luck.
