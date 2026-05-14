# EXPLAIN.md — Viva Crib-Sheet
## IPL 2026 · DBMS Mini-Project (MySQL Edition)

Every requirement on the brief, mapped to where it lives in this project,
explained in viva-ready language.

---

## 1. The brief, mapped to the IPL domain

### DDL requirements

| Grocery brief (DDL #) | IPL implementation | Where |
|---|---|---|
| #1 — Products table | **Matches** table (the fact table) | `database.py` `DDL_STATEMENTS` |
| #2 — Inventory tracking | **SeasonStandings** (running totals updated by trigger) | same |
| #3 — Transactions table | **MatchResults** (one row per completed match) | same |
| #4 — PK / FK / NOT NULL / CHECK / UNIQUE | All used — every table demonstrates 3+ constraint types | see §3 below |
| #5 — Schema alteration (ADD / DROP / MODIFY) | `demo_alter()` does all three | `database.py` |
| #6 — Suppliers with constraints | **Venues** table (analogue) — Name UNIQUE NOT NULL, Capacity CHECK | same |
| #7 — Categories linked by FK | **Teams** referenced by Matches; **Stage** as enum-via-CHECK | same |
| #8 — Customers w/ auto-increment + loyalty points | **Players** with `MVPCount` field auto-incremented by `trg_award_mvp` | same |
| #9 — DEFAULTs and AUTO_INCREMENT | Every PK uses AUTO_INCREMENT; many columns have DEFAULTs | throughout |

### Query requirements

| Grocery brief (Q #) | IPL query | Concept |
|---|---|---|
| Q1 — INNER JOIN | Completed matches × Teams × Venues | three-way INNER JOIN |
| Q2 — LEFT JOIN | All matches including ones without a result row | LEFT JOIN with COALESCE |
| Q3 — Low-stock alert | Teams below playoff threshold (Points < 8) | filter aggregate |
| Q4 — Top 5 best-selling | Top 5 teams by points | ORDER BY + LIMIT |
| Q5 — RIGHT JOIN | Venues × Matches (incl. unused venues) | native MySQL RIGHT JOIN |
| Q6 — FULL OUTER JOIN | Teams ↔ AllTimeStats reconciliation | UNION of LEFT JOINs |
| Q7 — SUM(price × qty) | Total runs per team | UNION ALL + SUM + AVG |
| Q8 — Never sold in 30 days | Teams that haven't played in 30 days | NOT IN + DATE_SUB |
| Q9 — GROUP BY + HAVING | Teams with win rate above 50% | aggregate + HAVING |
| Q10 — Subquery | Each team's highest score | derived-table subquery |

### Wider brief (Views / Procedures / Triggers / Daily update)

| Concept | Where |
|---|---|
| **View** for match summaries | `MatchSummary`, `LiveStandings`, `TeamHistory` |
| **Stored procedure** | `sp_record_result()`, `sp_schedule_match()` (real `CREATE PROCEDURE`) |
| **Triggers** | `trg_after_result`, `trg_alltime_update`, `trg_no_self_match`, `trg_award_mvp` |
| **Daily updates from ESPNcricinfo** | `fetch_latest()` hook in `database.py` |

Every box ticked.

---

## 2. Why MySQL (and not SQLite)

Same SQL standard. The differences that matter for this project:

| Feature | SQLite | MySQL |
|---|---|---|
| Auto-increment | `AUTOINCREMENT` | `AUTO_INCREMENT` |
| Float type | `REAL` | `DECIMAL(10,2)` |
| String type | `TEXT` | `VARCHAR(n)` |
| Param placeholder | `?` | `%s` |
| Date arithmetic | `datetime('now','-30 days')` | `DATE_SUB(NOW(), INTERVAL 30 DAY)` |
| Trigger raise | `RAISE(ABORT, '...')` | `SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='...'` |
| RIGHT JOIN | Not supported (flip to LEFT JOIN) | Native |
| FULL OUTER JOIN | Not supported (use UNION trick) | Not supported (use UNION trick) |
| Stored procedures | Not supported (emulated in Python) | Real `CREATE PROCEDURE` with IN/OUT params |
| String concatenation | `||` | `CONCAT(...)` |

The MySQL version gives you a **real `CREATE PROCEDURE`** and **native `RIGHT JOIN`** —
both are stronger viva talking points than the SQLite equivalents.

---

## 3. Tables — every constraint explained

### Teams
```sql
TeamID         INT AUTO_INCREMENT PRIMARY KEY,   -- PK + AUTO_INCREMENT (req #9)
ShortCode      VARCHAR(10)  NOT NULL UNIQUE,     -- NOT NULL + UNIQUE
FullName       VARCHAR(100) NOT NULL UNIQUE,
City           VARCHAR(50)  NOT NULL,
Founded        INT          NOT NULL CHECK (Founded >= 2008),  -- CHECK
PrimaryColor   VARCHAR(20)  DEFAULT '#1F2A24',   -- DEFAULT
SecondaryColor VARCHAR(20)  DEFAULT '#FFFFFF',
LogoFile       VARCHAR(100)
```

Demonstrates PK, AUTO_INCREMENT, NOT NULL, UNIQUE, CHECK, DEFAULT — six of the eight constraint types in one table.

### AllTimeStats
```sql
TeamID INT PRIMARY KEY,                          -- PK that is also a FK = 1:1 relationship
...
FOREIGN KEY (TeamID) REFERENCES Teams(TeamID) ON DELETE CASCADE
```

If a team is removed, its stats go too — that's `ON DELETE CASCADE`.

### Players (the loyalty-points analogue)
```sql
PlayerID  INT AUTO_INCREMENT PRIMARY KEY,        -- req #8: auto-increment customer id
Name      VARCHAR(100) NOT NULL,
TeamID    INT NOT NULL,
Role      VARCHAR(20) NOT NULL
          CHECK (Role IN ('Batter','Bowler','All-rounder','Wicket-keeper')),  -- enum via CHECK
IsCaptain TINYINT NOT NULL DEFAULT 0 CHECK (IsCaptain IN (0,1)),
MVPCount  INT NOT NULL DEFAULT 0 CHECK (MVPCount >= 0),  -- req #8: loyalty points
FOREIGN KEY (TeamID) REFERENCES Teams(TeamID) ON DELETE CASCADE
```

`MVPCount` plays the role of "loyalty points" from the grocery brief — it's auto-incremented by trigger every time the player wins Player of the Match.

### Matches
```sql
MatchID  INT AUTO_INCREMENT PRIMARY KEY,
Team1ID, Team2ID INT NOT NULL,
VenueID  INT NOT NULL,
Stage    VARCHAR(20) NOT NULL DEFAULT 'League'
         CHECK (Stage IN ('League','Qualifier 1','Eliminator','Qualifier 2','Final')),
Status   VARCHAR(20) NOT NULL DEFAULT 'Scheduled'
         CHECK (Status IN ('Scheduled','Live','Completed','Abandoned')),
...
FOREIGN KEY (Team1ID) REFERENCES Teams(TeamID),
FOREIGN KEY (Team2ID) REFERENCES Teams(TeamID),
FOREIGN KEY (VenueID) REFERENCES Venues(VenueID),
CHECK (Team1ID <> Team2ID)        -- table-level CHECK
```

Note the **table-level CHECK** at the end — prevents a team from playing itself even before the trigger fires. Belt and braces.

### MatchResults (analogue of Transactions)
```sql
MatchID         INT PRIMARY KEY,                 -- PK = FK = 1:1 with Matches
WinnerID        INT,                              -- nullable for no-result
Team1Score      INT NOT NULL CHECK (Team1Score >= 0),
Team1Wickets    INT NOT NULL CHECK (Team1Wickets BETWEEN 0 AND 10),  -- BETWEEN
Team1Overs      DECIMAL(4,1) NOT NULL,
...
FOREIGN KEY (MatchID) REFERENCES Matches(MatchID) ON DELETE CASCADE
```

`BETWEEN 0 AND 10` is shorthand for `>= 0 AND <= 10`. Wickets can only go up to 10.

### SeasonStandings (the running-inventory analogue)
```sql
TeamID INT PRIMARY KEY,
Played, Won, Lost, NoResult, Points,
RunsFor, RunsAgainst INT DEFAULT 0
```

Maintained **entirely by triggers**. The app never directly writes to this table when a result is recorded — it just inserts into MatchResults and lets the trigger cascade do the rest. That's the whole point.

---

## 4. Schema alteration — ADD, MODIFY, DROP

`demo_alter()` in `database.py` runs all three forms on startup (idempotent):

```sql
-- (1) ADD
ALTER TABLE Matches ADD COLUMN Sponsor VARCHAR(50) DEFAULT 'TATA IPL';

-- (2) MODIFY (change a column's type / size)
ALTER TABLE Matches MODIFY COLUMN Sponsor VARCHAR(60) DEFAULT 'TATA IPL';

-- (3) DROP (we add a throwaway column then drop it)
ALTER TABLE Matches ADD COLUMN LegacyField INT DEFAULT 0;
ALTER TABLE Matches DROP COLUMN LegacyField;
```

All three are MySQL-native. In your viva: "We demonstrate all three forms — ADD, MODIFY, and DROP — at startup."

---

## 5. Triggers — the showpiece

### `trg_no_self_match` (BEFORE INSERT on Matches)
```sql
IF NEW.Team1ID = NEW.Team2ID THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'A team cannot play itself';
END IF;
```

`SIGNAL SQLSTATE '45000'` is MySQL's way of raising a custom error from inside a trigger. The insert is aborted; the transaction rolls back.

### `trg_after_result` (AFTER INSERT on MatchResults)
Cascades 4 updates to SeasonStandings:
1. Bumps `Played` for both teams (and RunsFor/RunsAgainst)
2. Adds 2 points + bumps `Won` for the winner
3. Bumps `Lost` for the loser
4. Flips Matches.Status from 'Scheduled' to 'Completed'

The Python procedure call is *one line*; the trigger does all four updates atomically.

### `trg_alltime_update` (AFTER INSERT on MatchResults)
Updates AllTimeStats — TotalMatches/Wins/Losses for both teams. If the match's `Stage = 'Final'`, also increments `Titles` for the winner and `FinalsAppearances` for both.

### `trg_award_mvp` (AFTER INSERT on MatchResults)
**This is the loyalty-points analogue.**
```sql
IF NEW.PlayerOfMatch IS NOT NULL AND NEW.PlayerOfMatch <> '—' THEN
    UPDATE Players SET MVPCount = MVPCount + 1
    WHERE Name = NEW.PlayerOfMatch;
END IF;
```

Whenever a result is recorded with a named Player of the Match, their MVPCount automatically goes up. Same pattern as "loyalty points for every order" in the grocery brief — driven by a trigger, not application code.

---

## 6. Stored procedures — real MySQL this time

### `sp_record_result()`
```sql
CREATE PROCEDURE sp_record_result (
    IN p_match_id INT, IN p_winner_id INT,
    IN p_t1_score INT, IN p_t1_wkts INT, IN p_t1_overs DECIMAL(4,1),
    IN p_t2_score INT, IN p_t2_wkts INT, IN p_t2_overs DECIMAL(4,1),
    IN p_margin VARCHAR(50), IN p_pom VARCHAR(100)
)
BEGIN
    INSERT INTO MatchResults
        (MatchID, WinnerID, Team1Score, ...)
    VALUES (p_match_id, p_winner_id, p_t1_score, ...);
END
```

10 IN parameters. The procedure does one thing: insert into MatchResults. The triggers above do everything else.

### `sp_schedule_match()` — uses an OUT parameter
```sql
CREATE PROCEDURE sp_schedule_match (
    IN p_date DATE, IN p_team1 INT, IN p_team2 INT,
    IN p_venue INT, IN p_stage VARCHAR(20),
    OUT p_match_id INT
)
BEGIN
    INSERT INTO Matches (...) VALUES (...);
    SET p_match_id = LAST_INSERT_ID();
END
```

The OUT parameter returns the new MatchID to the caller. In Python:
```python
args = cur.callproc("sp_schedule_match", [date, t1, t2, venue, stage, 0])
new_id = args[-1]   # OUT parameter
```

---

## 7. Views

### `MatchSummary`
A LEFT JOIN of Matches + Teams (twice — once per side) + Venues + MatchResults. One readable row per fixture with everything an app needs to display it. The Schedule page is just `SELECT * FROM MatchSummary`.

### `LiveStandings`
Reads SeasonStandings, computes NRR with a CASE expression. The standings page is just `SELECT * FROM LiveStandings`.

### `TeamHistory`
Reads AllTimeStats + Teams, computes WinPercent. The All-Time page is just `SELECT * FROM TeamHistory`.

**Why use views?**
1. **Encapsulation** — the app code reads from one named object; the joins live in the database.
2. **Reusability** — many pages read these same combinations; one view, multiple consumers.
3. **Permissions** — in production you can grant SELECT on the view without granting access to the underlying tables.

---

## 8. The 10 queries — what to say about each

| # | Concept | One-line takeaway |
|---|---|---|
| 1 | INNER JOIN | Three-way join — every match with parent rows |
| 2 | LEFT JOIN | Keeps matches even without results; uses COALESCE to fill nulls |
| 3 | Low-points filter | Direct analogue of low-stock. WHERE Points < 8. |
| 4 | Top-N | `ORDER BY ... LIMIT 5` — the leaderboard |
| 5 | RIGHT JOIN | MySQL supports this natively (SQLite doesn't) |
| 6 | FULL OUTER JOIN | Even MySQL 8 lacks it — emulated with UNION of LEFT JOINs |
| 7 | SUM aggregate | UNION ALL stacks both innings; SUM + AVG aggregate per team |
| 8 | NOT IN subquery | DATE_SUB(NOW(), INTERVAL 30 DAY) for date arithmetic |
| 9 | GROUP BY + HAVING | WHERE filters rows; HAVING filters groups |
| 10 | Subquery | Derived table in the FROM clause |

**Viva trap to be ready for:** Q6 — MySQL still doesn't support `FULL OUTER JOIN` syntactically. Standard workaround is `(A LEFT JOIN B) UNION (B LEFT JOIN A)`. Same as what you'd do in SQLite or any pre-Oracle DBMS.

---

## 9. The daily-update hook

`fetch_latest()` in `database.py` is the function a daily cron would run.

```python
def fetch_latest():
    # In production:
    #   import requests
    #   from bs4 import BeautifulSoup
    #   html = requests.get('https://www.espncricinfo.com/...').text
    #   soup = BeautifulSoup(html, 'html.parser')
    #   for card in soup.select('.match-card'):
    #       sp_record_result(...)
    #
    # For the demo we pick the next Scheduled match and simulate.
    ...
```

The architecture is real. What's simulated is the *data source*. In the viva you can honestly say: "The daily-update flow is wired in — the function exists, it calls the stored procedure, the triggers cascade. Swapping the simulated scores for an HTTP fetch is a one-function change."

---

## 10. Data flow when a result is recorded

```
User submits scores
        │
        ▼
sp_record_result(...)            -- MySQL stored procedure (real CREATE PROCEDURE)
        │
        ▼
INSERT INTO MatchResults VALUES (...)
        │
        ├─► trg_after_result fires:
        │     - Played + 1 on both teams
        │     - 2 points + Won + 1 on winner
        │     - Lost + 1 on loser
        │     - RunsFor / RunsAgainst updated (for NRR)
        │     - Matches.Status flipped to 'Completed'
        │
        ├─► trg_alltime_update fires:
        │     - TotalMatches + 1 on both
        │     - TotalWins + 1 on winner, TotalLosses + 1 on loser
        │     - If Stage='Final': Titles + 1, FinalsAppearances + 1
        │
        └─► trg_award_mvp fires:
              - MVPCount + 1 on Players where Name = PlayerOfMatch
        ▼
All views (LiveStandings, TeamHistory) reflect the new state on next SELECT.
```

**This is the most important diagram in the project.** Memorise it.

---

## 11. Likely viva questions

| Question | Short answer |
|---|---|
| Why split AllTimeStats from SeasonStandings? | Different cadences. SeasonStandings resets each year; AllTimeStats accumulates forever. Different update frequencies → separate tables. |
| What normal form? | 3NF. No transitive dependencies. Team city is in Teams, venue capacity is in Venues, etc. |
| What does AUTO_INCREMENT do? | Generates sequential integer values for the column on each INSERT, so you never have to assign IDs manually. |
| Difference between WHERE and HAVING? | WHERE filters rows before grouping. HAVING filters groups after aggregation. You can use aggregates (SUM, AVG, COUNT) only in HAVING. |
| What's a view? Is it stored? | A view stores the query, not the data. Every SELECT on the view re-executes the underlying SQL. |
| Why a stored procedure if it does one INSERT? | Encapsulation. The app calls one named procedure; future changes (validation, logging, multi-step) happen inside the procedure without touching the app. |
| What if a trigger errors? | The whole transaction rolls back, including the original INSERT that fired it. ACID. |
| Difference between trigger and procedure? | Trigger auto-fires on a table event (INSERT/UPDATE/DELETE). Procedure is explicitly called by name. |
| What does ON DELETE CASCADE do? | When the parent row is deleted, child rows are deleted too. Used for tight 1:1 / 1:N where children have no meaning without the parent. |
| What's NRR? | Net Run Rate. Simplified here as `(RunsFor - RunsAgainst) / Played`. Full formula uses overs faced/bowled. |
| Why MySQL and not Oracle? | MySQL covers every concept in the syllabus and is what the labs used. Oracle would work too — only minor syntax differences. |

---

## 12. Demo script (5 minutes)

1. **Dashboard** — point at KPIs, the points table with top-4 highlighted, recent + upcoming cards.
2. **Teams** — scroll the 10 franchises. Note the trophy counts. Expand a squad — point out the MVP badges.
3. **Matches → Record Result** — pick a scheduled match, fill scores, pick a Player of the Match, submit. Without writing a single UPDATE statement, watch the next page reflect new standings + MVP count.
4. **MVP Leaderboard** — show the new MVP was awarded automatically. Explain `trg_award_mvp`.
5. **Live Standings** — explain this entire page is `SELECT * FROM LiveStandings`. The view does the work.
6. **Daily Update** — click "Pull latest result". Explain this is where the ESPNcricinfo scraper would run.
7. **SQL Playground** — open Q5 (RIGHT JOIN), run it. Explain MySQL supports this natively. Then Q6 (FULL OUTER via UNION) — explain even MySQL doesn't support FULL OUTER, so we use the UNION workaround.
8. **About / Schema** — close with the concept map.

🏏 Good luck.
