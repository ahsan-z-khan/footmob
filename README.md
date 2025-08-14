# FootMob - Football Match Organizer

A minimal web app for small football groups to plan games, collect availability, form teams, and track match outcomes.

## Features

- **Groups**: Create groups with invite codes/QR codes
- **Games**: Schedule matches with automatic availability polling
- **Teams**: Form balanced teams from available players
- **Live Tracking**: Real-time match tracking with goals, assists, and POTM voting
- **Feed**: Activity feed showing group updates and results

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application**:
   ```bash
   python app.py
   ```

3. **Access the app**: Visit http://localhost:5000

## User Flow

1. **Create or join a group** using invite codes
2. **Admin creates games** with date, time, and location
3. **Members vote availability** (IN/OUT/MAYBE)
4. **Admin forms teams** from available players
5. **Start live match** with real-time score tracking
6. **Add goals/assists** and vote for Player of the Match
7. **View game summary** with final scores and POTM results

## Database

The app uses SQLite by default. The database file (`footmob.db`) will be created automatically when you first run the application.

## Tech Stack

- **Backend**: Python Flask
- **Database**: SQLAlchemy (SQLite)
- **Frontend**: HTML templates with Tailwind CSS
- **Authentication**: Flask-Login (simple username-based)

## Design Principles

- **Minimal UI**: Clean black and white design
- **Mobile-friendly**: Responsive design for phone usage
- **Simple UX**: Clear flows with minimal clicks
- **No payments**: Focus on organizing, not monetization