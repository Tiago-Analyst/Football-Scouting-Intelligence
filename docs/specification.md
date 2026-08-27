# MASTER SPEC — Football Recruitment Intelligence Web Platform

> **This is the authoritative specification for the project**, recorded verbatim
> as supplied. It governs the phase order, the engineering rules and the
> constraints on provider data. Where any other document disagrees with this
> one, this one wins.
>
> It lives here because it previously existed only in conversation, which made
> it impossible to answer "what is left to build?" without guessing.
> `docs/architecture.md` records what was built and why; this records what was
> asked for.

You are building a production-quality football scouting and recruitment intelligence web platform.

## WORKING NAME
Football Recruitment Intelligence

## IMPORTANT — START NOW WITHOUT THE REAL FOOTYSTATS API KEY

Proceed with the project even though the real FootyStats API key is not yet available.

Build all infrastructure and application components that do not depend on verified FootyStats fields.

For FootyStats integration, create a provider abstraction and use clearly labelled mock/sample data only.

Do NOT assume that any FootyStats metric exists until it has been verified against a real API response.

Any metric, role, score or feature depending on unverified FootyStats fields must be marked as pending data validation.

Once a real API key is provided, the FootyStats provider must be replaceable without redesigning the rest of the application.

Create a demo mode:

- APP_MODE=demo
- APP_MODE=production

In demo mode:
- use clearly labelled mock data
- do not call FootyStats
- keep the website fully navigable
- allow testing of player search, profiles, role scores, similarity, recruitment builder, replacement finder and shortlists with mock data

In production mode:
- use the processed production database populated from FootyStats + Transfermarkt

Create a provider abstraction conceptually similar to:

```python
class PerformanceDataProvider:
    def get_competitions(self):
        ...

    def get_players(self, competition_id, season_id):
        ...

    def get_player_stats(self, player_id, season_id):
        ...
```

Implement initially:

```text
MockPerformanceProvider
```

and later:

```text
FootyStatsProvider
```

The rest of the application must depend on the canonical internal data model, not directly on FootyStats field names.

Do NOT hardcode unverified FootyStats fields such as:
- passes_progressive
- tackles
- xa_per_90
- or any other guessed field name

Until the real API is available, any provider-specific mapping must remain TODO / pending validation.

The architecture should be:

```text
Mock or FootyStats Provider
        ↓
Canonical Internal Model
        ↓
Analytics
        ↓
Database
        ↓
FastAPI
        ↓
Next.js
```

Do not blindly implement everything at once.

Build the project incrementally by phases and ensure each phase is working and tested before moving to the next one.

---

# 1. PRODUCT VISION

The platform is designed to support football recruitment, scouting and player market analysis.

It should help answer questions such as:

- Which U23 midfielders under €5M combine strong defensive activity with progressive passing?
- Which players are statistically similar to a selected player?
- Which players could replace a player in a club's squad?
- Which players fit a specific tactical/recruitment profile?
- What is a player's strongest statistical role?
- Which young players may represent interesting market opportunities?
- Which players have strong performance indicators but relatively low market values?
- Which players are approaching the end of their contracts?
- How do players compare within their positional peer group?

The platform must go beyond simply displaying football statistics.

Its main value must come from:
- derived metrics
- contextual percentiles
- proprietary analytical scores
- player roles
- similarity modelling
- recruitment fit
- market intelligence
- explainability

This should look and behave like a real football recruitment SaaS platform rather than a portfolio dashboard.

It must NOT be a Streamlit application.

---

# 2. TECHNOLOGY STACK

## FRONTEND

Use:
- Next.js
- React
- TypeScript
- Tailwind CSS

Use a professional component architecture.

For charts use an appropriate React charting library such as:
- Recharts
or
- Plotly.js

The UI must be responsive.

Do not use Streamlit.

## BACKEND

Use:
- Python
- FastAPI
- Pydantic
- SQLAlchemy or equivalent ORM/query layer

All important analytical logic must stay server-side.

Do NOT expose proprietary scoring formulas or API credentials to the frontend.

## DATABASE

Production application database:
- PostgreSQL

PostgreSQL should contain:
- player master data
- football statistics
- derived metrics
- percentiles
- role scores
- market values
- transfers
- identity mappings
- user accounts if authentication requires it
- shortlists
- shortlist players
- saved recruitment searches

DuckDB may still be used internally for:
- ETL
- analytical transformations
- offline feature calculation
- development

but the public web application should primarily query PostgreSQL.

## DATA PROCESSING

Python:
- Pandas or Polars
- NumPy
- scikit-learn
- DuckDB where useful

## INFRASTRUCTURE

Recommended architecture:

Frontend:
Vercel

Backend:
Railway / Render / equivalent

Database:
managed PostgreSQL such as Railway Postgres, Neon or Supabase Postgres

CI/CD and scheduled data pipelines:
GitHub Actions

Domain:
custom domain

---

# 3. DATA SOURCES

## PRIMARY PERFORMANCE DATA

FootyStats API

Use FootyStats for:
- player performance
- minutes
- goals
- assists
- xG
- npxG
- xA
- shots
- shots on target
- passes
- completed passes
- passing accuracy
- progressive passes
- key passes
- crosses
- tackles
- interceptions
- blocks
- clearances
- duels
- aerial duels
- dribbles
- fouls
- dispossessions
- goalkeeper statistics
- other available player-level statistics

IMPORTANT:

Before building analytical models with real data, retrieve actual API responses and build a data profiling report.

Never assume that a field exists only because it was expected.

Do not invent statistics.

Do not silently replace an unavailable statistic with another statistic.

If a required metric does not exist:
- flag it
- document it
- disable the feature that depends on it if necessary

## PRIMARY MARKET DATA

Transfermarkt dataset:
dcaribou/transfermarkt-datasets

Use Transfermarkt for:
- player identity
- current club
- age
- date of birth
- nationality
- preferred foot
- height
- position
- sub-position where available
- current market value
- market value history
- transfer history
- contract expiry where available
- previous clubs
- current club information

Do not scrape Transfermarkt directly.

Use the existing public dataset.

---

# 4. DATA ARCHITECTURE

Use a layered pipeline.

## RAW / BRONZE

Store raw API responses.

Example:

```text
data/raw/footystats/
data/raw/transfermarkt/
```

Keep raw snapshots so transformations are reproducible.

## SILVER

Clean and standardise:
- players
- competitions
- clubs
- seasons
- statistics
- market data

Perform identity resolution between providers.

## GOLD

Create analytical tables:
- per90 metrics
- ratios
- percentiles
- intelligence scores
- player role scores
- similarity features
- recruitment features

Production flow:

```text
FootyStats API
        +
Transfermarkt dataset
        ↓
Raw data
        ↓
Validation
        ↓
Identity Resolution
        ↓
Standardised Data
        ↓
Derived Metrics
        ↓
Percentiles
        ↓
Intelligence Scores
        ↓
Role Scores
        ↓
Similarity Features
        ↓
Recruitment Features
        ↓
PostgreSQL
        ↓
FastAPI
        ↓
Next.js
```

---

# 5. DATA MODEL

Create at minimum:

## dim_player

```text
player_id
full_name
normalized_name
date_of_birth
age
nationality
secondary_nationality
preferred_foot
height_cm
primary_position
secondary_position
current_club_id
current_market_value
contract_expiry
```

## dim_club

```text
club_id
club_name
country
competition_id
```

## dim_competition

```text
competition_id
competition_name
country
```

## dim_season

```text
season_id
season_name
start_year
end_year
```

## bridge_player_source

```text
player_id
footystats_player_id
transfermarkt_player_id
match_method
match_confidence
manual_override
```

## fact_player_season_stats

```text
player_id
club_id
competition_id
season_id

appearances
starts
minutes

goals
non_penalty_goals
assists

xg
npxg
xa

shots
shots_on_target

passes
passes_completed
progressive_passes
key_passes

crosses
accurate_crosses

dribbles
successful_dribbles

tackles
successful_tackles
interceptions
blocks
clearances

duels
duels_won
aerial_duels
aerial_duels_won

fouls_committed
fouls_drawn
dispossessed
dribbled_past

plus all other validated FootyStats fields.
```

## fact_player_derived_metrics

```text
goals_per90
non_penalty_goals_per90
assists_per90
xg_per90
npxg_per90
xa_per90

shots_per90
shots_on_target_per90
shot_accuracy
shot_conversion
shot_quality

passes_per90
completed_passes_per90
progressive_passes_per90
key_passes_per90

tackles_per90
successful_tackles_per90
interceptions_per90
blocks_per90
clearances_per90

duels_per90
duels_won_per90
duel_win_percentage

aerial_duels_per90
aerial_duels_won_per90
aerial_duel_win_percentage

dribbles_per90
successful_dribbles_per90
dribble_success_percentage

dispossessed_per90
fouls_drawn_per90
fouls_committed_per90
```

## fact_player_percentiles

```text
player_id
season_id
competition_id
position_group
metric
percentile
```

## fact_player_intelligence_scores

```text
player_id
season_id
ball_progression_score
ball_security_score
chance_creation_score
defensive_activity_score
duel_dominance_score
one_v_one_threat_score
goal_threat_score
finishing_score
aerial_presence_score
```

## fact_player_role_scores

```text
player_id
season_id
role_id
role_score
```

## dim_role

```text
role_id
role_name
position_group
description
```

## fact_market_value

```text
player_id
date
market_value
```

## fact_transfer

```text
player_id
transfer_date
from_club
to_club
transfer_fee
transfer_type
```

## user_shortlist

```text
shortlist_id
user_id
name
created_at
```

## user_shortlist_player

```text
shortlist_id
player_id
notes
added_at
```

## fact_data_quality

```text
source
entity
check_name
status
record_count
executed_at
```

---

# 6. IDENTITY RESOLUTION

FootyStats IDs and Transfermarkt IDs cannot be assumed to match.

Build a proper identity resolution process.

Never join only on player name.

Use combinations of:
- normalized player name
- date of birth
- nationality
- current club
- position

Normalize player names:
- lowercase
- remove accents
- remove punctuation
- collapse whitespace
- standardize common formatting differences

Generate:

```text
match_confidence
```

Example logic:

```text
1.00  Exact normalized name + exact DOB + compatible club
0.98  Exact DOB + very strong fuzzy name
0.95  Exact normalized name + DOB
0.90  DOB + nationality + strong fuzzy name + club
```

Below a defined confidence threshold:
do not automatically match.

Create:

```text
manual_player_mapping
```

to allow manual overrides.

Every mapping must store:
- mapping method
- confidence
- whether it was manually confirmed

---

# 7. MINIMUM SAMPLE RULES

Do not produce misleading player rankings for extremely small samples.

Default rules:

## >= 900 minutes
FULL SAMPLE

Include:
- rankings
- role scores
- recruitment results
- similarity results

## 450-899 minutes
LOW SAMPLE

Allow profiles and metrics but display a visible:

```text
Low Sample Size
```

badge.

## <450 minutes

Do not include by default in:
- rankings
- similarity
- recruitment recommendations

Allow users to manually lower the minutes filter.

All calculations must use actual minutes.

---

# 8. POSITION GROUPS

Create standardized position groups:

```text
GK
CB
FB_WB
DM
CM
AM
WINGER
FORWARD
```

Where source positions differ, map them into these categories.

Maintain the raw source position as well.

Percentile comparisons must primarily happen against compatible position groups.

Do not compare CB tackling numbers directly against forwards for role scoring.

---

# 9. INTELLIGENCE METRICS

IMPORTANT:

Intelligence Scores must not combine raw statistics directly.

First transform the underlying metrics into contextual percentiles.

Each component metric should therefore have a value between 0 and 100 before applying weights.

Scores must also range 0-100.

Store both:
- final score
- component scores

This is necessary for explainability.

## BALL PROGRESSION

```text
Progressive Passes /90      45%
Completed Passes /90        20%
Key Passes /90              15%
Successful Dribbles /90     20%
```

## BALL SECURITY

```text
Pass Completion %           45%
Dribble Success %           20%
Inverse Dispossessed /90    25%
Completed Passes /90        10%
```

For inverse metrics:
higher dispossessions should result in lower percentile scores.

## CHANCE CREATION

```text
xA /90                      40%
Key Passes /90              35%
Accurate Crosses /90        15%
Assists /90                 10%
```

## DEFENSIVE ACTIVITY

```text
Successful Tackles /90      35%
Interceptions /90           35%
Blocks /90                  15%
Duels Won /90               15%
```

## DUEL DOMINANCE

```text
Duels Won %                 50%
Aerial Duels Won %          30%
Duels Won /90               20%
```

## 1V1 THREAT

```text
Successful Dribbles /90     50%
Dribble Success %           30%
Fouls Drawn /90             20%
```

## GOAL THREAT

```text
npxG /90                    35%
Shots /90                   25%
Shots on Target /90         20%
Successful Dribbles /90     10%
xA /90                      10%
```

## FINISHING

```text
Non-Penalty Goals /90       35%
npxG /90                    20%
Shot Conversion %           20%
Shot Accuracy %             15%
Shot Quality                10%
```

where:

```text
Shot Quality = npxG / non-penalty shots
```

Do not describe Finishing Score as objective finishing ability.

Clearly state that:
- finishing metrics can be noisy
- finishing overperformance can regress
- sample size matters

---

# 10. PLAYER ROLE ENGINE

Create the following roles.

## CENTRE BACK

### 1. Ball-Playing Centre-Back

```text
Progressive Passes /90      30%
Pass Completion %           20%
Completed Passes /90        15%
Interceptions /90           15%
Duels Won %                 10%
Aerial Duels Won %          10%
```

### 2. Defensive Stopper

```text
Interceptions /90           25%
Successful Tackles /90      20%
Blocks /90                  15%
Clearances /90              15%
Duels Won %                 15%
Aerial Duels Won %          10%
```

## FULL-BACK / WING-BACK

### 3. Defensive Full-Back

```text
Successful Tackles /90      25%
Interceptions /90           20%
Inverse Dribbled Past /90   20%
Duels Won %                 15%
Progressive Passes /90      10%
Aerial Duels Won %          10%
```

### 4. Attacking Full-Back

```text
Accurate Crosses /90        25%
Progressive Passes /90      20%
Key Passes /90              15%
xA /90                      15%
Successful Dribbles /90     15%
Pass Completion %           10%
```

## DEFENSIVE MIDFIELD

### 5. Ball-Winning Midfielder

```text
Successful Tackles /90      25%
Interceptions /90           25%
Duels Won %                 20%
Aerial Duels Won %          10%
Ball Security               10%
Progressive Passes /90      10%
```

### 6. Deep-Lying Playmaker

```text
Progressive Passes /90      30%
Completed Passes /90        20%
Pass Completion %           20%
Key Passes /90              10%
xA /90                      10%
Inverse Dispossessed /90    10%
```

## CENTRAL MIDFIELD

### 7. Box-to-Box Midfielder

```text
Progressive Passes /90      15%
Successful Tackles /90      15%
Interceptions /90           15%
Duels Won %                 15%
Successful Dribbles /90     10%
xA /90                      10%
npxG /90                    10%
Pass Completion %           10%
```

## ATTACKING MIDFIELD

### 8. Advanced Playmaker

```text
xA /90                      30%
Key Passes /90              25%
Progressive Passes /90      15%
Successful Dribbles /90     15%
Pass Completion %           10%
npxG /90                     5%
```

## WINGERS

### 9. Creative Winger

```text
xA /90                      25%
Key Passes /90              20%
Accurate Crosses /90        20%
Successful Dribbles /90     20%
Dribble Success %           10%
npxG /90                     5%
```

### 10. Direct Winger

```text
Successful Dribbles /90     25%
npxG /90                    20%
Dribble Success %           15%
Shots /90                   15%
xA /90                      10%
Fouls Drawn /90             10%
Inverse Dispossessed /90     5%
```

### 11. Inside Forward

```text
npxG /90                    30%
Non-Penalty Goals /90       25%
Shots /90                   15%
Successful Dribbles /90     15%
xA /90                      10%
Shot Conversion %            5%
```

## FORWARDS

### 12. Poacher

```text
Non-Penalty Goals /90       30%
npxG /90                    30%
Shots on Target /90         15%
Shot Conversion %           15%
Shot Quality                10%
```

### 13. Complete Forward

```text
npxG /90                    20%
Non-Penalty Goals /90       15%
xA /90                      15%
Key Passes /90              10%
Duels Won %                 10%
Aerial Duels Won %          10%
Successful Dribbles /90     10%
Pass Completion %            5%
Fouls Drawn /90              5%
```

### 14. Target Forward

```text
Aerial Duels Won %          25%
Aerial Duels Won /90        20%
Duels Won %                 15%
npxG /90                    20%
Fouls Drawn /90             10%
Key Passes /90               5%
xA /90                       5%
```

## GOALKEEPER

### 15. Shot Stopper

```text
Save %                      45%
Inside Box Saves /90        20%
Saves /90                   15%
Inverse Goals Conceded /90  20%
```

Clearly communicate that basic goalkeeper statistics are highly team-context dependent.

Do not infer elite shot stopping without an advanced metric such as post-shot xG if it is unavailable.

---

# 11. BEST ROLE

Calculate all compatible role scores for every eligible player.

Example:

```text
Player X

Deep-Lying Playmaker       91
Box-to-Box                 84
Ball-Winning Midfielder    73
```

Display:

```text
BEST ROLE
Deep-Lying Playmaker
91 / 100
```

Also display alternative compatible roles.

Role score represents statistical fit with the profile.

It must NOT be described as:
- probability
- player quality
- scouting grade

---

# 12. SIMILAR PLAYER ENGINE

Create a player similarity system.

Workflow:

1. select target player
2. determine compatible position group
3. filter eligible players
4. apply minimum minutes
5. create relevant feature vector
6. normalize features
7. calculate similarity
8. rank nearest players

Initial modelling approach:

```text
StandardScaler or robust standardisation
+
Cosine Similarity
```

Evaluate whether using percentile profiles or z-scores provides more stable results.

Similarity features must be position-specific.

Example midfielder feature vector:

```text
progressive_passes_per90
passes_completed_per90
pass_completion
key_passes_per90
xa_per90
successful_dribbles_per90
tackles_per90
interceptions_per90
duel_win_percentage
aerial_duel_win_percentage
dispossessed_per90
```

Return:

```text
Similarity Index
0-100
```

IMPORTANT:

Never describe similarity as probability.

Display:

```text
Statistical Similarity Index
```

Allow filters:
- maximum age
- minimum age
- maximum market value
- leagues
- countries
- different league only
- exclude same club
- younger than selected player
- contract ending soon

Results table:

```text
Player
Age
Club
League
Best Role
Similarity Index
Market Value
Contract Expiry
```

---

# 13. RECRUITMENT PROFILE BUILDER

Create an interactive Recruitment Profile Builder.

Users should be able to define the type of player they want.

Example:

```text
PROFILE:
Progressive #6
```

Weights:

```text
Ball Progression       30%
Ball Security          20%
Defensive Activity     25%
Duel Dominance         15%
Chance Creation        10%
```

Filters:

```text
Position
Age range
Market value range
Minimum minutes
Selected leagues
Nationality
Preferred foot
Height
Contract expiry
```

Return an ordered recruitment shortlist.

Example:

```text
1. Player A      92
2. Player B      89
3. Player C      86
```

Every recommendation must be explainable.

Example:

```text
WHY PLAYER A?

Progressive Passing       94th percentile
Defensive Activity        91
Ball Security             88
Age                       21
Market Value              €3.5m
```

---

# 14. RECRUITMENT FIT

Separate recruitment dimensions.

Show:

```text
Performance Fit
Age Fit
Market Fit
Contract Fit
```

Optional Overall Recruitment Fit:

```text
Performance Fit         70%
Age Fit                 10%
Market Fit              10%
Contract Fit            10%
```

The individual dimensions must always remain visible.

Do not present Overall Recruitment Fit as objective truth.

---

# 15. REPLACEMENT FINDER

Allow:

```text
Club
→ Player
→ Find Replacement
```

Calculate potential replacements using:

```text
Statistical Similarity      55%
Role Fit                    30%
Market Fit                  15%
```

Filters:

```text
maximum market value
age
selected leagues
countries
exclude same club
minimum minutes
contract situation
```

Display:

```text
Player
Similarity
Role Fit
Age
Club
League
Market Value
Contract
Overall Replacement Score
```

Every result should be explainable.

---

# 16. MARKET OPPORTUNITIES

Build a Market Opportunities module.

Possible filters:

```text
Age <= X
Market Value <= X
Role Score >= X
Minutes >= X
Contract Expiry <= X months
Selected leagues
Selected positions
```

Identify potentially interesting recruitment candidates.

Do NOT label players as objectively:

```text
undervalued
```

unless there is a validated valuation model.

Instead use terminology such as:

```text
Potential Market Opportunity
```

Example criteria:

```text
Age <= 23
Role Score >= 80
Minutes >= 900
Market Value <= €5m
Contract <= 18 months
```

Display why each player was identified.

---

# 17. WEBSITE INFORMATION ARCHITECTURE

Create the following primary pages.

## HOME

Professional landing page.

Explain:
- what the platform does
- recruitment intelligence
- player search
- similarity analysis
- player roles
- market intelligence

Do not make the homepage look like a dashboard.

It should look like a football technology product.

## PLAYER SEARCH

Powerful searchable player database.

Filters:

```text
Name
Position
Role
Age
Nationality
League
Club
Preferred Foot
Height
Minutes
Market Value
Contract Expiry
```

Advanced metrics filters:

```text
xG /90
xA /90
Shots /90
Progressive Passes /90
Key Passes /90
Tackles /90
Interceptions /90
Dribbles /90
Duels Won %
Aerial Duels Won %
Role Score
```

## PLAYER PROFILE

URL format:

```text
/players/{player-slug}
```

Header:

```text
Player Name
Age
Nationality
Club
League
Position
Preferred Foot
Height
Market Value
Contract Expiry
```

Sections:

```text
Overview
Best Role
Role Compatibility
Intelligence Scores
Radar
Performance Metrics
Percentiles
Market Value History
Transfer History
Similar Players
```

## SIMILAR PLAYERS

Dedicated player similarity interface.

## RECRUITMENT BUILDER

Interactive recruitment specification builder.

## REPLACEMENT FINDER

Player replacement search.

## MARKET OPPORTUNITIES

Potential market opportunities.

## SHORTLISTS

Authenticated users can save players.

## SQUAD ANALYSIS

Future/secondary module.

## MARKET INTELLIGENCE

Incorporate useful market-analysis concepts from the existing Football Recruitment Intelligence project where applicable.

## METHODOLOGY

Explain:
- data sources
- derived metrics
- intelligence metrics
- percentiles
- roles
- similarity
- limitations
- data freshness

## DATA QUALITY

Show:
- last FootyStats refresh
- last Transfermarkt refresh
- competition coverage
- player coverage
- failed matches
- data quality checks

## ABOUT

Project background and creator information.

---

# 18. DESIGN REQUIREMENTS

The platform must feel like a professional football technology product.

Avoid the visual style of:
- Streamlit
- academic dashboards
- generic admin panels

Design direction:

```text
Modern
Minimal
Dark/light friendly
Football-oriented
Data-driven
Professional
```

Use:
- strong typography
- cards
- clean tables
- compact filters
- badges
- tooltips
- responsive layouts

Do not overload pages with charts.

Player Profile example:

```text
--------------------------------------------------

PLAYER NAME

21 years | CM | Portugal | Club X

Market Value: €4.0m
Contract: 2028

--------------------------------------------------

BEST ROLE

Deep-Lying Playmaker
91 / 100

--------------------------------------------------

INTELLIGENCE PROFILE

Radar visualization

Ball Progression       94
Ball Security          89
Defensive Activity     83
Chance Creation        77

--------------------------------------------------

KEY STRENGTHS

Progressive Passing    94th percentile
Interceptions          91st percentile
Pass Completion        88th percentile

--------------------------------------------------

PERFORMANCE

Metric                   Per 90       Percentile

Progressive Passes       7.1          94
Tackles                   2.6          84
Interceptions             1.9          91

--------------------------------------------------

SIMILAR PLAYERS

...
```

Tooltips must explain unfamiliar metrics.

Examples:

```text
What is Ball Progression?
What does 91st percentile mean?
What is Similarity Index?
```

---

# 19. AUTHENTICATION

Support user accounts.

Public users should be able to:
- browse players
- search
- see profiles
- use basic similarity

Authenticated users should additionally be able to:
- create shortlists
- save players
- write private notes
- save recruitment profiles
- save searches

Use secure authentication.

Possible options:
- Auth.js
- Supabase Auth
- equivalent secure solution

Do not build custom password cryptography.

---

# 20. SHORTLISTS

Users must be able to:

```text
Create shortlist
Add player
Add note
Remove player
Compare players
```

Example shortlist:

```text
FC Porto - Defensive Midfielder
```

Shortlist comparison:
maximum 5 players.

Show:

```text
Age
Market Value
Contract
Best Role
Role Fit
Similarity
Radar
Core metrics
```

Allow CSV export of the user's shortlist.

Do NOT allow bulk export of the entire underlying FootyStats database.

---

# 21. SECURITY

FOOTYSTATS_API_KEY must NEVER appear in:

```text
frontend code
Git repository
browser requests
public logs
```

Local:

```text
.env
```

Production:

```text
environment variables / secrets
```

GitHub:

```text
GitHub Actions Secrets
```

Architecture:

```text
Browser
↓
Next.js
↓
FastAPI
↓
Database
```

The frontend should NOT call FootyStats directly.

The public application should normally query processed database tables.

Implement:
- input validation
- SQL injection protection
- CORS restrictions
- authentication validation
- basic rate limiting where appropriate
- safe error messages

Never expose internal stack traces in production.

---

# 22. DATA PIPELINE

Do not call the FootyStats API every time a user opens a player page.

Use batch ingestion.

Pipeline:

```text
FootyStats
↓
Raw JSON
↓
Validation
↓
Transformation
↓
Transfermarkt data
↓
Identity Resolution
↓
Derived Metrics
↓
Percentiles
↓
Intelligence Scores
↓
Role Scores
↓
Similarity Features
↓
PostgreSQL
```

Suggested refresh:

```text
FootyStats: 2-3 times per week initially
Transfermarkt: weekly
```

Make refresh frequency configurable.

---

# 23. GITHUB ACTIONS

Create scheduled GitHub Actions.

Pipeline should:

1. retrieve latest FootyStats data
2. retrieve/latest Transfermarkt dataset
3. validate sources
4. run identity resolution
5. build transformed tables
6. calculate derived metrics
7. calculate percentiles
8. calculate intelligence scores
9. calculate roles
10. run data quality tests
11. update production data only if tests succeed

If validation fails:

DO NOT publish corrupted data.

Keep previous production version active.

Store pipeline logs and summary statistics.

---

# 24. DATA QUALITY RULES

Implement automated checks.

Examples:

```text
No duplicate: player + competition + season
minutes >= 0
goals >= 0
xG >= 0
xA >= 0
percentage fields between valid ranges
role scores: 0 <= score <= 100
intelligence scores: 0 <= score <= 100
similarity: 0 <= similarity <= 100
market value >= 0
valid competition references
valid player references
no unresolved low-confidence matches inserted automatically
minimum player coverage per competition
minimum metric coverage per competition
```

Check for suspicious source changes such as:

```text
player count suddenly dropping 80%
API fields disappearing
metric suddenly becoming null for entire league
```

Raise explicit pipeline errors.

---

# 25. PERCENTILE CONTEXT

Support multiple percentile contexts.

## PRIMARY

Position + competition + season

Example:

```text
Player is 92nd percentile for progressive passing
among midfielders in Liga Portugal 2026/27.
```

## SECONDARY

Position + selected league group

Example:

```text
Player compared with midfielders across:
Portugal
Belgium
Netherlands
Denmark
Austria
```

## GLOBAL DATABASE

Position + all currently covered competitions

The UI must always show the comparison context.

Do NOT hide the reference population.

Example:

```text
Progressive Passes
92nd percentile

Compared with:
Central Midfielders
Liga Portugal
2026/27
```

IMPORTANT:

Cross-league performance is NOT automatically adjusted for league strength.

Do not invent a league strength coefficient.

Clearly state:

```text
Cross-league percentiles do not currently account for differences in competition strength.
```

A future competition-strength model may be added later.

---

# 26. FASTAPI ENDPOINTS

Design a clean API.

Examples:

```text
GET /api/players
```

Supports:

```text
search
position
role
age_min
age_max
competition
club
nationality
foot
market_value_min
market_value_max
minutes_min
```

Other endpoints:

```text
GET /api/players/{player_id}
GET /api/players/{player_id}/stats
GET /api/players/{player_id}/roles
GET /api/players/{player_id}/market-value
GET /api/players/{player_id}/transfers
GET /api/players/{player_id}/similar
POST /api/recruitment/search
POST /api/replacement/search
GET /api/competitions
GET /api/clubs
GET /api/roles
```

Authenticated:

```text
GET /api/shortlists
POST /api/shortlists
POST /api/shortlists/{id}/players
DELETE /api/shortlists/{id}/players/{player_id}
PATCH /api/shortlists/{id}/players/{player_id}
```

Do not return unnecessary raw provider data.

Return the information required by the UI.

---

# 27. PERFORMANCE

Do not calculate expensive models on every frontend request.

Precompute:

```text
derived metrics
percentiles
intelligence scores
role scores
```

Similarity feature vectors should also be prepared in advance where practical.

Use server-side caching for frequently requested resources.

Examples:

```text
competition list
popular players
player profiles
role definitions
```

Database queries must be indexed appropriately.

Likely indexes:

```text
player name
position
competition
club
season
market value
age
```

Recruitment searches should return paginated results.

Never load 20,000 players into the browser just to filter client-side.

---

# 28. INTELLECTUAL PROPERTY / PRODUCT PROTECTION

This is intended to potentially evolve from a portfolio project into a real product.

Therefore:

Do NOT expose internal implementation details unnecessarily.

Keep server-side:
- intelligence score implementation
- role score implementation
- similarity algorithm
- recruitment ranking algorithm
- identity resolution logic
- future proprietary models

The frontend should receive results, not implementation.

Example:

Frontend may receive:

```json
{
  "ball_progression_score": 91,
  "role": "Deep-Lying Playmaker",
  "role_score": 88
}
```

It should not receive internal source code or full model implementation.

The backend repository may eventually be private.

Architecture must support frontend/backend separation from day one.

Do not rely on security through obscurity.

Document methodology enough for analytical transparency without requiring exposure of proprietary source code.

---

# 29. DATA LICENSING

The project uses external data providers.

Never assume ownership of provider data.

Do not provide a public bulk download of FootyStats data.

Do not create functionality whose primary purpose is to redistribute FootyStats raw data.

The product should provide analytical outputs and recruitment intelligence built on top of the data.

Examples of acceptable product concepts:

```text
Player profile
Percentiles
Role score
Similarity
Recruitment ranking
Market analysis
Shortlist
```

Avoid:

```text
Download all FootyStats data
```

Keep provider attribution and licensing requirements configurable.

Before commercialisation, licensing terms must be reviewed again.

---

# 30. DEVELOPMENT PHASES

DO NOT IMPLEMENT THE ENTIRE APPLICATION IN ONE STEP.

## PHASE 0 — PROJECT FOUNDATION

Create:

```text
/frontend
/backend
/data
/pipelines
/tests
/docs
```

Configure:

```text
Next.js
FastAPI
PostgreSQL
environment variables
Docker where useful
linting
formatting
testing
```

Deliver a working:

```text
Next.js → FastAPI → PostgreSQL
```

connection.

STOP and validate.

## PHASE 0.5 — DESIGN SYSTEM + SITE SHELL

Create:
- global layout
- navigation
- typography
- cards
- buttons
- tables
- filters
- badges
- responsive breakpoints
- dark/light support where appropriate
- loading states
- empty states
- error states

Use mock content only.

STOP and validate.

## PHASE 1A — MOCK PERFORMANCE PROVIDER

Create:

```text
MockPerformanceProvider
```

Create realistic but clearly fake football player data.

The mock dataset should support testing of:
- Player Search
- Player Profile
- Percentiles
- Intelligence Scores
- Role Scores
- Similarity
- Recruitment Builder
- Replacement Finder
- Shortlists

Clearly label demo data in the UI.

STOP and validate.

## PHASE 1B — TRANSFERMARKT PIPELINE

Implement Transfermarkt dataset ingestion independently of FootyStats.

Validate:
- players
- clubs
- competitions
- market values
- transfers
- contract dates if available
- positions
- height
- preferred foot

STOP and validate.

## PHASE 2 — DATA MODEL

Create PostgreSQL schema.

Load:

```text
players
clubs
competitions
seasons
performance mock data
market data
```

STOP and validate.

## PHASE 3 — IDENTITY RESOLUTION FRAMEWORK

Implement provider-independent identity resolution.

Until FootyStats is available, test with mock source identities against Transfermarkt.

Generate a report:

```text
matched
unmatched
ambiguous
manual review
```

STOP and inspect.

## PHASE 4 — METRICS ENGINE WITH MOCK DATA

Implement:
- per90 calculations
- ratios
- inverse metrics
- score utilities

Write unit tests.

STOP and validate.

## PHASE 5 — PERCENTILE ENGINE

Implement:
- league percentiles
- selected-league percentiles
- global percentiles
- position-group context

STOP and validate.

## PHASE 6 — INTELLIGENCE SCORE ENGINE

Implement intelligence score framework using mock canonical metrics.

Keep score definitions configurable.

Prefer:

```text
config/intelligence_scores.yaml
```

rather than formulas spread throughout source code.

STOP and inspect outputs.

## PHASE 7 — PLAYER ROLE ENGINE

Implement role engine using mock canonical metrics.

Store role definitions in:

```text
config/player_roles.yaml
```

STOP and inspect example players.

## PHASE 8 — SIMILARITY ENGINE

Implement position-specific similarity using mock data.

Validate:
- identical vectors
- near-identical vectors
- different position behaviour
- filtering
- similarity range

STOP and inspect.

## PHASE 9 — DEMO WEBSITE

Create a fully navigable demo website using mock data.

Pages:
- Home
- Player Search
- Player Profile
- Similar Players
- Recruitment Builder
- Replacement Finder
- Market Opportunities
- Shortlists
- Methodology
- Data Quality
- About

STOP.

## PHASE 10 — AUTHENTICATION

Implement secure authentication.

STOP.

## PHASE 11 — SHORTLISTS

Implement:
- save
- notes
- compare
- remove

STOP.

## PHASE 12 — FOOTYSTATS REAL API VALIDATION

Only begin this phase after a real FootyStats API key is provided.

Retrieve real FootyStats sample responses.

Generate:

```text
docs/footystats_data_profile.csv
```

Columns:

```text
field_name
data_type
null_percentage
minimum
maximum
example_value
endpoint
notes
```

Also generate:

```text
docs/footystats_metric_availability.md
```

Categories:

```text
Identity
Playing Time
Goals
Expected Goals
Shooting
Passing
Progression
Creation
Dribbling
Defending
Duels
Aerial
Discipline
Goalkeeping
```

Mark every expected metric:

```text
AVAILABLE
DERIVABLE
UNAVAILABLE
UNCLEAR
```

STOP.

Do not implement provider mappings until this is reviewed.

## PHASE 13 — FOOTYSTATS PROVIDER

Implement:

```text
FootyStatsProvider
```

Map verified FootyStats fields into the canonical internal model.

Example concept:

```text
real_footystats_field_name
        ↓
canonical_metric_name
```

Do not let the rest of the application depend directly on provider-specific field names.

STOP and validate.

## PHASE 14 — REAL INGESTION

Build production FootyStats ingestion.

Store raw data.

Add:
- retry handling
- rate-limit handling
- logging
- snapshotting
- validation

STOP and test.

## PHASE 15 — REAL IDENTITY RESOLUTION

Run:

```text
FootyStats ↔ Transfermarkt
```

matching.

Generate:

```text
matched
unmatched
ambiguous
manual review
```

STOP and inspect.

## PHASE 16 — REAL DERIVED METRICS

Replace mock analytical input with verified real metrics.

Disable or adapt metrics that are unavailable.

Never silently substitute metrics.

STOP.

## PHASE 17 — REAL PERCENTILES / SCORES / ROLES

Calculate:
- percentiles
- intelligence scores
- role scores

Validate sample players manually.

STOP.

## PHASE 18 — REAL SIMILARITY ENGINE

Recompute real similarity features.

Validate results qualitatively.

STOP.

## PHASE 19 — RECRUITMENT BUILDER

Connect real data to:
- Recruitment Profile Builder
- Recruitment Fit
- explanations

STOP.

## PHASE 20 — REPLACEMENT FINDER

Connect real data.

STOP.

## PHASE 21 — MARKET OPPORTUNITIES

Connect real data.

STOP.

## PHASE 22 — PIPELINES

Implement production GitHub Actions and automated refresh.

STOP.

## PHASE 23 — PRODUCTION DEPLOYMENT

Deploy:

```text
frontend
backend
database
```

Configure:
- production environment variables
- CORS
- domain
- HTTPS
- logging

STOP.

## PHASE 24 — POLISH

Improve:
- responsive design
- error handling
- loading states
- empty states
- tooltips
- methodology
- data quality
- SEO
- performance
- accessibility

---

# 31. ENGINEERING RULES

Follow these rules throughout development.

1. Do not invent API fields.

2. Do not silently substitute unavailable metrics.

3. Inspect actual FootyStats responses before implementing real provider mappings.

4. Keep calculations modular.

5. Keep score definitions configurable.

6. Write tests for important analytical formulas.

7. Do not expose secrets.

8. Do not call FootyStats directly from the frontend.

9. Do not hardcode the API key.

10. Do not unnecessarily redistribute raw provider data.

11. Do not calculate heavy analytics in React.

12. Do not put business logic in UI components.

13. Use FastAPI services/modules for analytical logic.

14. Use migrations for PostgreSQL schema changes.

15. Use type-safe frontend interfaces.

16. Add structured logging.

17. Do not delete previous working functionality without justification.

18. Do not make architectural changes without documenting why.

19. When uncertain about the data, stop and inspect rather than guessing.

20. Never describe analytical scores as objective player quality.

21. Never describe Similarity Index as probability.

22. Never describe Transfermarkt market value as expected transfer fee.

23. Always show sample-size warnings.

24. Always expose the comparison population used for percentiles.

25. Document important methodology decisions.

26. Prefer simple, explainable models before complex machine learning.

27. In demo mode, every fake/demo player and fake statistic must be clearly labelled as mock/demo data where appropriate.

28. Do not create hard dependencies on FootyStats before the real API schema is validated.

29. Build provider adapters so another performance provider could be added in the future without redesigning the whole application.

30. Before completing each development phase:
- run tests
- run linting
- report what was implemented
- report remaining issues
- list files changed
- provide instructions for manual validation

31. Do not move to the next phase automatically if validation reveals significant data-quality issues.

---

# 32. PROJECT STRUCTURE

Use an approximate structure like:

```text
football-recruitment-intelligence/

│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── features/
│   ├── hooks/
│   ├── lib/
│   ├── types/
│   └── public/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── analytics/
│   │   ├── repositories/
│   │   ├── providers/
│   │   ├── core/
│   │   └── main.py
│   │
│   └── tests/
│
├── pipelines/
│   ├── footystats/
│   ├── transfermarkt/
│   ├── identity_resolution/
│   ├── transformations/
│   ├── metrics/
│   ├── quality/
│   └── load/
│
├── config/
│   ├── player_roles.yaml
│   ├── intelligence_scores.yaml
│   ├── position_mapping.yaml
│   └── competitions.yaml
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── manual/
│
├── docs/
│   ├── architecture.md
│   ├── methodology.md
│   ├── data_dictionary.md
│   ├── footystats_metric_availability.md
│   └── identity_resolution.md
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── .env.example
├── README.md
└── LICENSE
```

---

# 33. PRODUCT POSITIONING

Treat this as a football recruitment intelligence platform, not merely a dashboard.

The product combines:

## Data Engineering

```text
APIs
→ ETL
→ Data Quality
→ Entity Resolution
→ PostgreSQL
```

## Football Analytics

```text
Per90
→ Percentiles
→ Role Profiles
→ Contextual Statistics
```

## Data Science

```text
Similarity
→ Rankings
→ Scoring
```

## Software Engineering

```text
FastAPI
→ Next.js
→ Authentication
→ Deployment
→ CI/CD
```

The application should be suitable to present to:
- football clubs
- recruitment departments
- scouts
- agents
- sports analytics teams
- technical directors
- data teams in football

It should therefore prioritise:
- clarity
- explainability
- robust data engineering
- professional design
- reproducibility
- safe handling of external data
- modular architecture

---

# 34. FINAL DEVELOPMENT BEHAVIOUR

Start development now even without the FootyStats API key.

Do not wait for the API key to build:
- project foundation
- website shell
- FastAPI
- PostgreSQL
- Transfermarkt ingestion
- mock provider
- canonical model
- metrics framework
- percentiles
- intelligence score framework
- role engine
- similarity engine
- recruitment UI
- replacement UI
- market opportunities UI
- authentication
- shortlists
- tests

However:

DO NOT pretend that the real FootyStats integration is complete.

DO NOT map guessed FootyStats fields.

DO NOT claim that any specific metric is available until it has been validated against the real API.

When the API key is later provided, pause normal feature development and perform the FootyStats Real API Validation phase first.

The goal is that replacing:

```text
MockPerformanceProvider
```

with:

```text
FootyStatsProvider
```

should not require redesigning the application.

Build this as a robust, modular, production-oriented football recruitment intelligence product.
