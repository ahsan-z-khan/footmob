from database import db
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import DateTime
import secrets
import string

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    memberships = db.relationship('GroupMembership', back_populates='user', cascade='all, delete-orphan')
    availability_votes = db.relationship('AvailabilityVote', back_populates='user', cascade='all, delete-orphan')
    events_scored = db.relationship('MatchEvent', foreign_keys='MatchEvent.scorer_id', back_populates='scorer')
    events_assisted = db.relationship('MatchEvent', foreign_keys='MatchEvent.assist_id', back_populates='assist')
    potm_votes = db.relationship('POTMVote', foreign_keys='POTMVote.voter_id', back_populates='voter', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', foreign_keys='Notification.user_id', back_populates='user', cascade='all, delete-orphan')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    emoji = db.Column(db.String(10), default='⚽')
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    invite_code = db.Column(db.String(8), unique=True)
    
    memberships = db.relationship('GroupMembership', back_populates='group', cascade='all, delete-orphan')
    games = db.relationship('Game', back_populates='group', cascade='all, delete-orphan')
    feed_items = db.relationship('FeedItem', back_populates='group', cascade='all, delete-orphan')
    
    def __init__(self, **kwargs):
        super(Group, self).__init__(**kwargs)
        self.invite_code = self.generate_invite_code()
    
    def generate_invite_code(self):
        return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    
    def get_admins(self):
        return User.query.join(GroupMembership).filter(
            GroupMembership.group_id == self.id,
            GroupMembership.is_admin == True
        ).all()
    
    def get_members(self):
        return User.query.join(GroupMembership).filter(
            GroupMembership.group_id == self.id
        ).all()
    
    def get_next_game(self):
        from datetime import datetime, timedelta
        
        # First, auto-update any expired games
        expired_games = Game.query.filter(
            Game.group_id == self.id,
            Game.status == 'upcoming',
            Game.datetime < datetime.utcnow()
        ).all()
        
        # Update expired games to 'finished' status if they weren't manually managed
        for game in expired_games:
            game.status = 'finished'
        
        if expired_games:
            db.session.commit()
        
        # Now get the next upcoming or live game
        return Game.query.filter(
            Game.group_id == self.id,
            Game.status.in_(['upcoming', 'live']),
            Game.datetime >= datetime.utcnow() - timedelta(hours=6)  # Allow 6 hours grace period for live games
        ).order_by(Game.datetime.asc()).first()
    
    def get_last_game(self):
        return Game.query.filter(
            Game.group_id == self.id,
            Game.status == 'finished'
        ).order_by(Game.datetime.desc()).first()
    
    def update_game_statuses(self):
        """Auto-update game statuses based on current time"""
        from datetime import datetime
        
        # Update expired upcoming games to finished
        expired_games = Game.query.filter(
            Game.group_id == self.id,
            Game.status == 'upcoming',
            Game.datetime < datetime.utcnow()
        ).all()
        
        updated = False
        for game in expired_games:
            game.status = 'finished'
            updated = True
        
        if updated:
            db.session.commit()
        
        return len(expired_games)

class GroupMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    joined_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    user = db.relationship('User', back_populates='memberships')
    group = db.relationship('Group', back_populates='memberships')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'group_id'),)

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    datetime = db.Column(DateTime, nullable=False)
    location = db.Column(db.String(200))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='upcoming')  # upcoming, live, finished
    poll_lock_datetime = db.Column(DateTime)
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    started_at = db.Column(DateTime)
    ended_at = db.Column(DateTime)
    
    group = db.relationship('Group', back_populates='games')
    availability_votes = db.relationship('AvailabilityVote', back_populates='game', cascade='all, delete-orphan')
    team_assignments = db.relationship('TeamAssignment', back_populates='game', cascade='all, delete-orphan')
    events = db.relationship('MatchEvent', back_populates='game', cascade='all, delete-orphan')
    potm_votes = db.relationship('POTMVote', back_populates='game', cascade='all, delete-orphan')
    
    def is_poll_locked(self):
        if self.poll_lock_datetime and datetime.utcnow() > self.poll_lock_datetime:
            return True
        return self.status != 'upcoming'
    
    def get_availability_counts(self):
        in_votes = AvailabilityVote.query.filter_by(game_id=self.id, status='in').count()
        out_votes = AvailabilityVote.query.filter_by(game_id=self.id, status='out').count()
        maybe_votes = AvailabilityVote.query.filter_by(game_id=self.id, status='maybe').count()
        return {'in': in_votes, 'out': out_votes, 'maybe': maybe_votes}
    
    def get_in_players(self):
        return User.query.join(AvailabilityVote).filter(
            AvailabilityVote.game_id == self.id,
            AvailabilityVote.status == 'in'
        ).all()
    
    def get_team_a_players(self):
        return User.query.join(TeamAssignment).filter(
            TeamAssignment.game_id == self.id,
            TeamAssignment.team == 'A'
        ).all()
    
    def get_team_b_players(self):
        return User.query.join(TeamAssignment).filter(
            TeamAssignment.game_id == self.id,
            TeamAssignment.team == 'B'
        ).all()
    
    def get_score(self):
        # Regular goals for Team A
        team_a_goals = MatchEvent.query.filter_by(game_id=self.id, event_type='goal').join(
            TeamAssignment, 
            (MatchEvent.scorer_id == TeamAssignment.user_id) & 
            (TeamAssignment.game_id == self.id)
        ).filter(TeamAssignment.team == 'A').count()
        
        # Regular goals for Team B
        team_b_goals = MatchEvent.query.filter_by(game_id=self.id, event_type='goal').join(
            TeamAssignment, 
            (MatchEvent.scorer_id == TeamAssignment.user_id) & 
            (TeamAssignment.game_id == self.id)
        ).filter(TeamAssignment.team == 'B').count()
        
        # Own goals by Team A players (add to Team B's score)
        team_a_own_goals = MatchEvent.query.filter_by(game_id=self.id, event_type='own_goal').join(
            TeamAssignment, 
            (MatchEvent.scorer_id == TeamAssignment.user_id) & 
            (TeamAssignment.game_id == self.id)
        ).filter(TeamAssignment.team == 'A').count()
        
        # Own goals by Team B players (add to Team A's score)
        team_b_own_goals = MatchEvent.query.filter_by(game_id=self.id, event_type='own_goal').join(
            TeamAssignment, 
            (MatchEvent.scorer_id == TeamAssignment.user_id) & 
            (TeamAssignment.game_id == self.id)
        ).filter(TeamAssignment.team == 'B').count()
        
        # Final scores: own goals add to opponent's score
        final_team_a_score = team_a_goals + team_b_own_goals
        final_team_b_score = team_b_goals + team_a_own_goals
        
        return {'team_a': final_team_a_score, 'team_b': final_team_b_score}
    
    def get_responses(self):
        """Get categorized availability responses for this game"""
        attending = User.query.join(AvailabilityVote).filter(
            AvailabilityVote.game_id == self.id,
            AvailabilityVote.status == 'in'
        ).all()
        
        not_attending = User.query.join(AvailabilityVote).filter(
            AvailabilityVote.game_id == self.id,
            AvailabilityVote.status == 'out'
        ).all()
        
        maybe_attending = User.query.join(AvailabilityVote).filter(
            AvailabilityVote.game_id == self.id,
            AvailabilityVote.status == 'maybe'
        ).all()
        
        return {
            'attending': attending,
            'not_attending': not_attending,
            'maybe_attending': maybe_attending
        }

class AvailabilityVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # in, out, maybe
    voted_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    user = db.relationship('User', back_populates='availability_votes')
    game = db.relationship('Game', back_populates='availability_votes')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'game_id'),)

class TeamAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    team = db.Column(db.String(1), nullable=False)  # A or B
    position = db.Column(db.String(20))  # optional position
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    user = db.relationship('User')
    game = db.relationship('Game', back_populates='team_assignments')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'game_id'),)

class MatchEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    event_type = db.Column(db.String(20), nullable=False)  # goal
    scorer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assist_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    minute = db.Column(db.Integer)
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    game = db.relationship('Game', back_populates='events')
    scorer = db.relationship('User', foreign_keys=[scorer_id], back_populates='events_scored')
    assist = db.relationship('User', foreign_keys=[assist_id], back_populates='events_assisted')

class POTMVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    voted_for_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    voted_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    voter = db.relationship('User', foreign_keys=[voter_id], back_populates='potm_votes')
    game = db.relationship('Game', back_populates='potm_votes')
    voted_for = db.relationship('User', foreign_keys=[voted_for_id])
    
    __table_args__ = (db.UniqueConstraint('voter_id', 'game_id'),)

class FeedItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    item_type = db.Column(db.String(50), nullable=False)  # game_created, poll_locked, teams_published, goal_scored, match_finished, potm_announced
    content = db.Column(db.Text, nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    group = db.relationship('Group', back_populates='feed_items')
    game = db.relationship('Game')

class PlayerAttributes(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    
    # Physical Attributes (1-10 scale)
    pace = db.Column(db.Integer, default=5)  # Speed and acceleration
    stamina = db.Column(db.Integer, default=5)  # Endurance and fitness
    strength = db.Column(db.Integer, default=5)  # Physical power
    agility = db.Column(db.Integer, default=5)  # Balance and body control
    jumping = db.Column(db.Integer, default=5)  # Aerial ability
    
    # Technical Attributes (1-10 scale)
    ball_control = db.Column(db.Integer, default=5)  # First touch and ball handling
    dribbling = db.Column(db.Integer, default=5)  # Close control and tricks
    passing = db.Column(db.Integer, default=5)  # Short and long passing accuracy
    shooting = db.Column(db.Integer, default=5)  # Finishing and shot power
    crossing = db.Column(db.Integer, default=5)  # Wide play delivery
    free_kicks = db.Column(db.Integer, default=5)  # Set piece specialist
    
    # Tactical Attributes (1-10 scale)
    positioning = db.Column(db.Integer, default=5)  # Reading the game
    marking = db.Column(db.Integer, default=5)  # Defensive awareness
    tackling = db.Column(db.Integer, default=5)  # Defensive challenges
    interceptions = db.Column(db.Integer, default=5)  # Cutting out passes
    vision = db.Column(db.Integer, default=5)  # Creating opportunities
    decision_making = db.Column(db.Integer, default=5)  # Game intelligence
    
    # Mental Attributes (1-10 scale)
    composure = db.Column(db.Integer, default=5)  # Under pressure performance
    concentration = db.Column(db.Integer, default=5)  # Focus during game
    determination = db.Column(db.Integer, default=5)  # Mental strength
    leadership = db.Column(db.Integer, default=5)  # Captaincy qualities
    teamwork = db.Column(db.Integer, default=5)  # Working with others
    
    # Goalkeeping Attributes (1-10 scale, optional)
    goalkeeping = db.Column(db.Integer, default=1)  # Shot stopping
    handling = db.Column(db.Integer, default=1)  # Catching ability
    distribution = db.Column(db.Integer, default=1)  # Ball distribution
    aerial_reach = db.Column(db.Integer, default=1)  # Commanding area
    
    # Meta information
    preferred_position = db.Column(db.String(20))  # GK, DEF, MID, FWD
    notes = db.Column(db.Text)  # Additional notes from admin
    last_updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))  # Admin who updated
    updated_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id])
    group = db.relationship('Group')
    updated_by = db.relationship('User', foreign_keys=[last_updated_by])
    
    __table_args__ = (db.UniqueConstraint('user_id', 'group_id'),)
    
    def get_overall_rating(self):
        """Calculate overall rating based on all attributes"""
        physical = (self.pace + self.stamina + self.strength + self.agility + self.jumping) / 5
        technical = (self.ball_control + self.dribbling + self.passing + self.shooting + self.crossing + self.free_kicks) / 6
        tactical = (self.positioning + self.marking + self.tackling + self.interceptions + self.vision + self.decision_making) / 6
        mental = (self.composure + self.concentration + self.determination + self.leadership + self.teamwork) / 5
        
        # Weight categories differently based on position
        if self.preferred_position == 'GK':
            gk_attrs = (self.goalkeeping + self.handling + self.distribution + self.aerial_reach) / 4
            return round((gk_attrs * 0.4 + mental * 0.3 + physical * 0.2 + tactical * 0.1), 1)
        elif self.preferred_position == 'DEF':
            return round((tactical * 0.35 + physical * 0.25 + mental * 0.25 + technical * 0.15), 1)
        elif self.preferred_position == 'MID':
            return round((technical * 0.35 + tactical * 0.30 + mental * 0.20 + physical * 0.15), 1)
        elif self.preferred_position == 'FWD':
            return round((technical * 0.40 + physical * 0.25 + mental * 0.20 + tactical * 0.15), 1)
        else:
            # Balanced for unknown position
            return round((technical + tactical + mental + physical) / 4, 1)
    
    def get_attribute_categories(self):
        """Return attributes grouped by category for display"""
        return {
            'physical': {
                'pace': self.pace,
                'stamina': self.stamina,
                'strength': self.strength,
                'agility': self.agility,
                'jumping': self.jumping
            },
            'technical': {
                'ball_control': self.ball_control,
                'dribbling': self.dribbling,
                'passing': self.passing,
                'shooting': self.shooting,
                'crossing': self.crossing,
                'free_kicks': self.free_kicks
            },
            'tactical': {
                'positioning': self.positioning,
                'marking': self.marking,
                'tackling': self.tackling,
                'interceptions': self.interceptions,
                'vision': self.vision,
                'decision_making': self.decision_making
            },
            'mental': {
                'composure': self.composure,
                'concentration': self.concentration,
                'determination': self.determination,
                'leadership': self.leadership,
                'teamwork': self.teamwork
            },
            'goalkeeping': {
                'goalkeeping': self.goalkeeping,
                'handling': self.handling,
                'distribution': self.distribution,
                'aerial_reach': self.aerial_reach
            }
        }

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)  # Optional - for group-specific notifications
    
    # Notification details
    type = db.Column(db.String(50), nullable=False)  # game_created, member_joined, teams_published, goal_scored, etc.
    title = db.Column(db.String(200), nullable=False)  # Short title
    message = db.Column(db.Text, nullable=False)  # Detailed message
    
    # Related entities (optional)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)
    related_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # For notifications about other users
    
    # Notification state
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = db.Column(DateTime, default=lambda: datetime.utcnow())
    read_at = db.Column(DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], back_populates='notifications')
    group = db.relationship('Group')
    game = db.relationship('Game')
    related_user = db.relationship('User', foreign_keys=[related_user_id])
    
    def __repr__(self):
        return f'<Notification {self.title} for {self.user.username}>'
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            db.session.commit()
    
    def to_dict(self):
        """Convert notification to dictionary for JSON responses"""
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'group_id': self.group_id,
            'game_id': self.game_id,
            'related_user': {
                'id': self.related_user.id,
                'name': self.related_user.display_name
            } if self.related_user else None
        }