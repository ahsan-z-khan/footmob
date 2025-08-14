# ⚽ FootMob - Football Match Organizer

A minimal web app for small football groups to plan games, collect availability, form teams, and track match outcomes.

## ✨ Features

- **👥 Groups**: Create groups with invite codes/QR codes
- **🏆 Games**: Schedule matches with automatic availability polling
- **⚖️ Teams**: Form balanced teams from available players
- **📱 Live Tracking**: Real-time match tracking with goals, assists, and POTM voting
- **📰 Feed**: Activity feed showing group updates and results

## 🚀 Quick Start

1. **📦 Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **▶️ Run the application**:
   ```bash
   python app.py
   ```

3. **🌐 Access the app**: Visit http://localhost:5000

## 🔄 User Flow

1. **🏁 Create or join a group** using invite codes
2. **⚙️ Admin creates games** with date, time, and location
3. **✅ Members vote availability** (IN/OUT/MAYBE)
4. **🎯 Admin forms teams** from available players
5. **🔴 Start live match** with real-time score tracking
6. **⚽ Add goals/assists** and vote for Player of the Match
7. **📊 View game summary** with final scores and POTM results

## 🎯 Team Formation Algorithms

FootMob features three intelligent team balancing algorithms to create fair and competitive matches:

### 🧠 Smart Draft (Default)
**How it works:**
- Calculates comprehensive player scores based on 4 factors:
  - **Player Attributes (25%)**: Skills like shooting, passing, defense, pace
  - **Historical Performance (30%)**: Goals, assists, win rate from past games
  - **Participation Score (15%)**: Availability and reliability 
  - **Recent Form (30%)**: Performance in last 5 games
- Sorts players by overall score and uses intelligent drafting
- Considers position balance (GK, DEF, MID, FWD)
- Adds slight randomization to avoid predictable teams

**Best for:** Most situations - balances skill, experience, and recent form

### 🎰 Multi-Armed Bandit
**How it works:**
- Treats different balancing strategies as "arms" in a slot machine
- Tests 5 different strategies over 1000 iterations:
  - Skill-balanced, Position-first, Performance-based, Recent form, Smart random
- Uses epsilon-greedy exploration (90% exploit best strategy, 10% explore)
- Learns which strategies work best for your group over time
- Adapts and improves with each use

**Best for:** Groups with diverse skill levels - learns your group's dynamics

### 🌡️ Simulated Annealing  
**How it works:**
- Starts with a random team composition
- Iteratively improves by swapping players between teams
- Uses "temperature" - accepts worse solutions early (exploration), becomes pickier over time
- Three swap strategies: single swap, double swap, position-based swap
- Runs for 2000 iterations with cooling schedule
- Finds globally optimal solution, not just local optimum

**Best for:** Critical matches where perfect balance is essential

### 📊 Team Rating System
Each algorithm considers:
- **⚔️ Attack Rating**: Shooting, ball control, crossing, positioning
- **🎯 Midfield Rating**: Passing, vision, dribbling, decision making  
- **🛡️ Defense Rating**: Tackling, marking, interceptions, strength
- **💨 Pace Rating**: Speed, agility, stamina
- **🥅 Goalkeeper Bonus**: Special handling, distribution, aerial reach

Position multipliers ensure realistic ratings (e.g., forwards get attack boost, defenders get defense boost).

## 🗄️ Database

The app uses SQLite by default. The database file (`footmob.db`) will be created automatically when you first run the application.

## 🛠️ Tech Stack

- **🐍 Backend**: Python Flask
- **💾 Database**: SQLAlchemy (SQLite)
- **🎨 Frontend**: HTML templates with Tailwind CSS
- **🔐 Authentication**: Flask-Login (simple username-based)