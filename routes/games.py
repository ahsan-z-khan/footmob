from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Game, Group, GroupMembership, AvailabilityVote, TeamAssignment, MatchEvent, POTMVote, FeedItem, User, PlayerAttributes
from database import db
from datetime import datetime, timedelta
import numpy as np

games_bp = Blueprint('games', __name__)

@games_bp.route('/groups/<int:group_id>/create', methods=['GET', 'POST'])
@login_required
def create(group_id):
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can create games')
        return redirect(url_for('groups.view', group_id=group_id))
    
    if request.method == 'POST':
        datetime_str = request.form.get('datetime')
        location = request.form.get('location')
        notes = request.form.get('notes')
        poll_lock_hours = request.form.get('poll_lock_hours', type=int)
        
        if not datetime_str:
            flash('Date and time are required')
            return render_template('games/create.html', group=group)
        
        try:
            game_datetime = datetime.fromisoformat(datetime_str.replace('T', ' '))
        except ValueError:
            flash('Invalid date format')
            return render_template('games/create.html', group=group)
        
        poll_lock_datetime = None
        if poll_lock_hours:
            poll_lock_datetime = game_datetime - timedelta(hours=poll_lock_hours)
        
        game = Game(
            group_id=group_id,
            datetime=game_datetime,
            location=location,
            notes=notes,
            poll_lock_datetime=poll_lock_datetime
        )
        db.session.add(game)
        db.session.flush()
        
        # Create feed item
        content = f"New game created for {game_datetime.strftime('%B %d at %I:%M %p')}"
        if location:
            content += f" at {location}"
        
        feed_item = FeedItem(
            group_id=group_id,
            game_id=game.id,
            item_type='game_created',
            content=content
        )
        db.session.add(feed_item)
        db.session.commit()
        
        # Create notifications for all group members
        from routes.notifications import notify_group_members
        notify_group_members(
            group_id=group_id,
            notification_type='game_created',
            title='New Game Created',
            message=f'A new game has been scheduled for {game_datetime.strftime("%B %d at %I:%M %p")}' + (f' at {location}' if location else ''),
            exclude_user_id=current_user.id,
            game_id=game.id
        )
        
        return redirect(url_for('games.view', game_id=game.id))
    
    return render_template('games/create.html', group=group)

@games_bp.route('/<int:game_id>')
@login_required
def view(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id
    ).first()
    
    if not membership:
        flash('You are not a member of this group')
        return redirect(url_for('main.dashboard'))
    
    user_vote = AvailabilityVote.query.filter_by(
        user_id=current_user.id,
        game_id=game_id
    ).first()
    
    availability_counts = game.get_availability_counts()
    
    in_players = game.get_in_players()
    team_a_players = game.get_team_a_players()
    team_b_players = game.get_team_b_players()
    
    # Get POTM votes if game is live or finished
    user_potm_vote = None
    potm_results = []
    if game.status in ['live', 'finished']:
        user_potm_vote = POTMVote.query.filter_by(
            voter_id=current_user.id,
            game_id=game_id
        ).first()
        
        if game.status == 'finished':
            # Get POTM results
            from sqlalchemy import func
            potm_results = db.session.query(
                User.display_name,
                func.count(POTMVote.id).label('votes')
            ).join(POTMVote, User.id == POTMVote.voted_for_id)\
            .filter(POTMVote.game_id == game_id)\
            .group_by(User.id, User.display_name)\
            .order_by(func.count(POTMVote.id).desc()).all()
    
    events = MatchEvent.query.filter_by(game_id=game_id).order_by(MatchEvent.minute).all()
    score = game.get_score() if game.status in ['live', 'finished'] else {'team_a': 0, 'team_b': 0}
    
    return render_template('games/view.html', 
                         game=game, 
                         membership=membership,
                         user_vote=user_vote,
                         availability_counts=availability_counts,
                         in_players=in_players,
                         team_a_players=team_a_players,
                         team_b_players=team_b_players,
                         user_potm_vote=user_potm_vote,
                         potm_results=potm_results,
                         events=events,
                         score=score)

@games_bp.route('/<int:game_id>/vote', methods=['POST'])
@login_required
def vote_availability(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id
    ).first()
    
    if not membership:
        flash('You are not a member of this group')
        return redirect(url_for('main.dashboard'))
    
    if game.is_poll_locked():
        flash('Availability poll is locked')
        return redirect(url_for('games.view', game_id=game_id))
    
    status = request.form.get('status')
    if status not in ['in', 'out', 'maybe']:
        flash('Invalid availability status')
        return redirect(url_for('games.view', game_id=game_id))
    
    vote = AvailabilityVote.query.filter_by(
        user_id=current_user.id,
        game_id=game_id
    ).first()
    
    if vote:
        vote.status = status
        vote.voted_at = datetime.utcnow()
    else:
        vote = AvailabilityVote(
            user_id=current_user.id,
            game_id=game_id,
            status=status
        )
        db.session.add(vote)
    
    db.session.commit()
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/lock-poll', methods=['POST'])
@login_required
def lock_poll(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can lock polls')
        return redirect(url_for('games.view', game_id=game_id))
    
    game.poll_lock_datetime = datetime.utcnow()
    
    # Create feed item
    feed_item = FeedItem(
        group_id=game.group_id,
        game_id=game.id,
        item_type='poll_locked',
        content='Availability poll has been locked'
    )
    db.session.add(feed_item)
    db.session.commit()
    
    flash('Poll locked')
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/teams', methods=['GET', 'POST'])
@login_required
def manage_teams(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can manage teams')
        return redirect(url_for('games.view', game_id=game_id))
    
    if request.method == 'POST':
        # Clear existing team assignments
        TeamAssignment.query.filter_by(game_id=game_id).delete()
        
        team_a_players = request.form.getlist('team_a')
        team_b_players = request.form.getlist('team_b')
        
        for player_id in team_a_players:
            assignment = TeamAssignment(
                user_id=int(player_id),
                game_id=game_id,
                team='A'
            )
            db.session.add(assignment)
        
        for player_id in team_b_players:
            assignment = TeamAssignment(
                user_id=int(player_id),
                game_id=game_id,
                team='B'
            )
            db.session.add(assignment)
        
        # Create feed item
        feed_item = FeedItem(
            group_id=game.group_id,
            game_id=game.id,
            item_type='teams_published',
            content='Teams have been published'
        )
        db.session.add(feed_item)
        db.session.commit()
        
        # Create notifications for all group members
        from routes.notifications import notify_group_members
        notify_group_members(
            group_id=game.group_id,
            notification_type='teams_published',
            title='Teams Published',
            message=f'Teams have been published for the game on {game.datetime.strftime("%B %d at %I:%M %p")}',
            exclude_user_id=current_user.id,
            game_id=game_id
        )
        
        flash('Teams published')
        return redirect(url_for('games.view', game_id=game_id))
    
    in_players = game.get_in_players()
    current_team_a = game.get_team_a_players()
    current_team_b = game.get_team_b_players()
    
    return render_template('games/teams.html', 
                         game=game,
                         in_players=in_players,
                         current_team_a=current_team_a,
                         current_team_b=current_team_b)

@games_bp.route('/<int:game_id>/start', methods=['POST'])
@login_required
def start_match(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can start matches')
        return redirect(url_for('games.view', game_id=game_id))
    
    if game.status != 'upcoming':
        flash('Game is not in upcoming status')
        return redirect(url_for('games.view', game_id=game_id))
    
    game.status = 'live'
    game.started_at = datetime.utcnow()
    db.session.commit()
    
    flash('Match started')
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/end', methods=['POST'])
@login_required
def end_match(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can end matches')
        return redirect(url_for('games.view', game_id=game_id))
    
    if game.status != 'live':
        flash('Game is not live')
        return redirect(url_for('games.view', game_id=game_id))
    
    game.status = 'finished'
    game.ended_at = datetime.utcnow()
    
    score = game.get_score()
    
    # Create match finished feed item
    feed_item = FeedItem(
        group_id=game.group_id,
        game_id=game.id,
        item_type='match_finished',
        content=f"Match finished: Team A {score['team_a']} - {score['team_b']} Team B"
    )
    db.session.add(feed_item)
    
    # Announce POTM if there are votes
    from sqlalchemy import func
    potm_winner = db.session.query(
        User.display_name,
        func.count(POTMVote.id).label('votes')
    ).join(POTMVote, User.id == POTMVote.voted_for_id)\
    .filter(POTMVote.game_id == game_id)\
    .group_by(User.id, User.display_name)\
    .order_by(func.count(POTMVote.id).desc()).first()
    
    if potm_winner:
        potm_feed_item = FeedItem(
            group_id=game.group_id,
            game_id=game.id,
            item_type='potm_announced',
            content=f"Player of the Match: {potm_winner.display_name}"
        )
        db.session.add(potm_feed_item)
    
    db.session.commit()
    
    # Create notifications for match finished
    from routes.notifications import notify_group_members
    notify_group_members(
        group_id=game.group_id,
        notification_type='match_finished',
        title='Match Finished',
        message=f'Match finished: Team A {score["team_a"]} - {score["team_b"]} Team B',
        game_id=game_id
    )
    
    # Create notification for POTM if there's a winner
    if potm_winner:
        notify_group_members(
            group_id=game.group_id,
            notification_type='potm_announced',
            title='Player of the Match',
            message=f'{potm_winner.display_name} was voted Player of the Match!',
            game_id=game_id
        )
    
    flash('Match ended')
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/events', methods=['POST'])
@login_required
def add_event(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can add events')
        return redirect(url_for('games.view', game_id=game_id))
    
    # Allow adding events on or after game day
    from datetime import date
    if game.datetime.date() > date.today():
        flash('Can only add events on or after the game date')
        return redirect(url_for('games.view', game_id=game_id))
    
    event_type = request.form.get('event_type')
    scorer_id = request.form.get('scorer_id', type=int)
    assist_id = request.form.get('assist_id', type=int) if request.form.get('assist_id') else None
    minute = request.form.get('minute', type=int)
    
    if not scorer_id or event_type not in ['goal', 'own_goal']:
        flash('Invalid event data')
        return redirect(url_for('games.view', game_id=game_id))
    
    event = MatchEvent(
        game_id=game_id,
        event_type=event_type,
        scorer_id=scorer_id,
        assist_id=assist_id,
        minute=minute
    )
    db.session.add(event)
    db.session.commit()
    
    # Create notifications for goals
    if event_type == 'goal':
        from routes.notifications import notify_group_members
        scorer = User.query.get(scorer_id)
        assist_player = User.query.get(assist_id) if assist_id else None
        
        message = f'{scorer.display_name} scored a goal'
        if assist_player:
            message += f' (assisted by {assist_player.display_name})'
        if minute:
            message += f' at minute {minute}'
        
        notify_group_members(
            group_id=game.group_id,
            notification_type='goal_scored',
            title='Goal Scored!',
            message=message,
            game_id=game_id,
            related_user_id=scorer_id
        )
    
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/events/remove', methods=['POST'])
@login_required
def remove_event(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can remove events')
        return redirect(url_for('games.view', game_id=game_id))
    
    # Allow removing events on or after game day
    from datetime import date
    if game.datetime.date() > date.today():
        flash('Can only remove events on or after the game date')
        return redirect(url_for('games.view', game_id=game_id))
    
    action = request.form.get('action')
    player_id = request.form.get('player_id', type=int)
    
    if not player_id or action not in ['remove_goal', 'remove_assist']:
        flash('Invalid remove action')
        return redirect(url_for('games.view', game_id=game_id))
    
    if action == 'remove_goal':
        # Remove the most recent goal by this player (regular or own goal)
        event = MatchEvent.query.filter_by(
            game_id=game_id,
            scorer_id=player_id
        ).filter(MatchEvent.event_type.in_(['goal', 'own_goal'])).order_by(MatchEvent.id.desc()).first()
        
        if event:
            db.session.delete(event)
            db.session.commit()
        else:
            flash('No goals found to remove for this player')
    
    elif action == 'remove_assist':
        # Remove the most recent assist by this player
        event = MatchEvent.query.filter_by(
            game_id=game_id,
            assist_id=player_id
        ).order_by(MatchEvent.id.desc()).first()
        
        if event:
            event.assist_id = None
            db.session.commit()
        else:
            flash('No assists found to remove for this player')
    
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/assists', methods=['POST'])
@login_required
def add_assist(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can add assists')
        return redirect(url_for('games.view', game_id=game_id))
    
    # Allow adding assists on or after game day
    from datetime import date
    if game.datetime.date() > date.today():
        flash('Can only add assists on or after the game date')
        return redirect(url_for('games.view', game_id=game_id))
    
    assist_player_id = request.form.get('assist_player_id', type=int)
    
    if not assist_player_id:
        flash('Invalid assist data')
        return redirect(url_for('games.view', game_id=game_id))
    
    # Find the most recent goal without an assist
    event = MatchEvent.query.filter_by(
        game_id=game_id,
        event_type='goal',
        assist_id=None
    ).order_by(MatchEvent.id.desc()).first()
    
    if event:
        event.assist_id = assist_player_id
        db.session.commit()
    else:
        flash('No recent goal available to assign assist to')
    
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/potm-vote', methods=['POST'])
@login_required
def vote_potm(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id
    ).first()
    
    if not membership:
        flash('You are not a member of this group')
        return redirect(url_for('main.dashboard'))
    
    # Allow POTM voting on or after game day
    from datetime import date
    if game.datetime.date() > date.today():
        flash('POTM voting is only available on or after the game date')
        return redirect(url_for('games.view', game_id=game_id))
    
    voted_for_id = request.form.get('voted_for_id', type=int)
    if not voted_for_id:
        flash('Please select a player')
        return redirect(url_for('games.view', game_id=game_id))
    
    vote = POTMVote.query.filter_by(
        voter_id=current_user.id,
        game_id=game_id
    ).first()
    
    if vote:
        vote.voted_for_id = voted_for_id
        vote.voted_at = datetime.utcnow()
    else:
        vote = POTMVote(
            voter_id=current_user.id,
            game_id=game_id,
            voted_for_id=voted_for_id
        )
        db.session.add(vote)
    
    db.session.commit()
    flash('POTM vote cast')
    return redirect(url_for('games.view', game_id=game_id))

@games_bp.route('/<int:game_id>/auto-balance', methods=['POST'])
@login_required
def auto_balance_teams(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id,
        is_admin=True
    ).first()
    
    if not membership:
        return jsonify({'error': 'Only admins can auto-balance teams'}), 403
    
    # Get available players (those who voted 'in')
    in_players = game.get_in_players()
    
    if len(in_players) < 2:
        return jsonify({'error': 'Need at least 2 players to form teams'}), 400
    
    # Get balancing algorithm from request
    algorithm = request.json.get('algorithm', 'smart_draft') if request.is_json else request.form.get('algorithm', 'smart_draft')
    
    # Calculate player scores and balance teams using selected algorithm
    if algorithm == 'bandit':
        balanced_teams = calculate_bandit_balanced_teams(in_players, game.group_id)
        method = 'Multi-Armed Bandit'
    elif algorithm == 'simulated_annealing':
        balanced_teams = calculate_simulated_annealing_teams(in_players, game.group_id)
        method = 'Simulated Annealing'
    else:  # smart_draft (default)
        balanced_teams = calculate_balanced_teams(in_players, game.group_id)
        method = 'Smart Draft'
    
    # Calculate additional metrics for ML algorithms
    response_data = {
        'success': True,
        'method': method,
        'team_a': [{'id': p.id, 'name': p.display_name} for p in balanced_teams['team_a']],
        'team_b': [{'id': p.id, 'name': p.display_name} for p in balanced_teams['team_b']],
        'team_a_ratings': calculate_team_ratings(balanced_teams['team_a'], game.group_id),
        'team_b_ratings': calculate_team_ratings(balanced_teams['team_b'], game.group_id)
    }
    
    # Add fitness score and iteration count for ML algorithms
    if algorithm in ['simulated_annealing']:
        response_data['fitness_score'] = balanced_teams.get('fitness', 0.0)
        response_data['iterations'] = balanced_teams.get('iterations', 0)
    elif algorithm == 'bandit':
        # Calculate final fitness for bandit
        fitness = calculate_team_fitness(balanced_teams['team_a'], balanced_teams['team_b'], game.group_id)
        response_data['fitness_score'] = fitness
    
    return jsonify(response_data)

@games_bp.route('/<int:game_id>/team-ratings', methods=['POST'])
@login_required
def get_team_ratings(game_id):
    game = Game.query.get_or_404(game_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=game.group_id
    ).first()
    
    if not membership:
        return jsonify({'error': 'You are not a member of this group'}), 403
    
    # Get team compositions from request (temporary assignments) or database (saved assignments)
    team_a_player_ids = request.form.getlist('team_a')
    team_b_player_ids = request.form.getlist('team_b')
    
    if team_a_player_ids or team_b_player_ids:
        # Use temporary team assignments from frontend
        team_a_players = User.query.filter(User.id.in_(team_a_player_ids)).all() if team_a_player_ids else []
        team_b_players = User.query.filter(User.id.in_(team_b_player_ids)).all() if team_b_player_ids else []
    else:
        # Use saved team assignments
        team_a_players = game.get_team_a_players()
        team_b_players = game.get_team_b_players()
    
    team_a_ratings = calculate_team_ratings(team_a_players, game.group_id)
    team_b_ratings = calculate_team_ratings(team_b_players, game.group_id)
    
    return jsonify({
        'success': True,
        'team_a_ratings': team_a_ratings,
        'team_b_ratings': team_b_ratings
    })

def calculate_team_ratings(players, group_id):
    """
    Calculate team ratings for Attack, Midfield, Defense, and Pace
    """
    if not players:
        return {
            'attack': 0.0,
            'midfield': 0.0,
            'defense': 0.0,
            'pace': 0.0,
            'overall': 0.0
        }
    
    total_attack = 0.0
    total_midfield = 0.0
    total_defense = 0.0
    total_pace = 0.0
    player_count = len(players)
    
    for player in players:
        # Get player attributes
        attributes = PlayerAttributes.query.filter_by(
            user_id=player.id,
            group_id=group_id
        ).first()
        
        if attributes:
            # Attack rating: shooting, finishing, crossing, free_kicks, positioning (for forwards)
            attack_score = (
                attributes.shooting * 0.35 +
                attributes.ball_control * 0.20 +
                attributes.crossing * 0.20 +
                attributes.free_kicks * 0.15 +
                attributes.positioning * 0.10
            )
            
            # Midfield rating: passing, vision, ball_control, dribbling, decision_making
            midfield_score = (
                attributes.passing * 0.30 +
                attributes.vision * 0.25 +
                attributes.ball_control * 0.20 +
                attributes.dribbling * 0.15 +
                attributes.decision_making * 0.10
            )
            
            # Defense rating: tackling, marking, interceptions, positioning, strength
            defense_score = (
                attributes.tackling * 0.25 +
                attributes.marking * 0.25 +
                attributes.interceptions * 0.20 +
                attributes.positioning * 0.20 +
                attributes.strength * 0.10
            )
            
            # Pace rating: pace, agility, stamina
            pace_score = (
                attributes.pace * 0.50 +
                attributes.agility * 0.30 +
                attributes.stamina * 0.20
            )
            
            # Apply position multipliers for more realistic ratings
            player_position = attributes.preferred_position if attributes.preferred_position else 'MID'
            if player_position == 'FWD':
                attack_score *= 1.2
                midfield_score *= 0.9
                defense_score *= 0.7
            elif player_position == 'MID':
                attack_score *= 0.95
                midfield_score *= 1.1
                defense_score *= 0.95
            elif player_position == 'DEF':
                attack_score *= 0.7
                midfield_score *= 0.9
                defense_score *= 1.2
            elif player_position == 'GK':
                # Goalkeepers contribute differently
                attack_score *= 0.3
                midfield_score *= 0.4
                defense_score = (
                    attributes.goalkeeping * 0.4 +
                    attributes.handling * 0.3 +
                    attributes.aerial_reach * 0.2 +
                    attributes.distribution * 0.1
                ) * 1.3  # GK defense boost
            
            total_attack += max(1.0, min(10.0, attack_score))
            total_midfield += max(1.0, min(10.0, midfield_score))
            total_defense += max(1.0, min(10.0, defense_score))
            total_pace += max(1.0, min(10.0, pace_score))
        else:
            # Default ratings for players without attributes
            total_attack += 5.0
            total_midfield += 5.0
            total_defense += 5.0
            total_pace += 5.0
    
    # Calculate averages
    avg_attack = total_attack / player_count
    avg_midfield = total_midfield / player_count
    avg_defense = total_defense / player_count
    avg_pace = total_pace / player_count
    
    # Overall rating is weighted average
    overall = (avg_attack * 0.3 + avg_midfield * 0.3 + avg_defense * 0.3 + avg_pace * 0.1)
    
    return {
        'attack': round(avg_attack, 1),
        'midfield': round(avg_midfield, 1),
        'defense': round(avg_defense, 1),
        'pace': round(avg_pace, 1),
        'overall': round(overall, 1)
    }

def calculate_balanced_teams(players, group_id):
    """
    Intelligent team balancing algorithm that considers:
    1. Player attributes (skills)
    2. Historical performance (goals, assists, wins)
    3. Participation reliability
    4. Recent form
    5. Position balance
    """
    from sqlalchemy import func
    import random
    from itertools import combinations
    
    if len(players) < 2:
        return {'team_a': [], 'team_b': []}
    
    # Calculate comprehensive player scores
    player_scores = []
    
    for player in players:
        score_data = {
            'player': player,
            'overall_score': 0.0,
            'skills_score': 0.0,
            'performance_score': 0.0,
            'participation_score': 0.0,
            'recent_form': 0.0,
            'position': None
        }
        
        # 1. Get player attributes (25% weight)
        attributes = PlayerAttributes.query.filter_by(
            user_id=player.id,
            group_id=group_id
        ).first()
        
        if attributes:
            score_data['skills_score'] = attributes.get_overall_rating()
            score_data['position'] = attributes.preferred_position if attributes.preferred_position else 'MID'
        else:
            # Default score for players without attributes
            score_data['skills_score'] = 5.0
        
        # 2. Calculate historical performance (30% weight)
        finished_games = Game.query.filter_by(
            group_id=group_id,
            status='finished'
        ).all()
        
        games_played = 0
        total_goals = 0
        total_assists = 0
        total_wins = 0
        total_games_with_assignment = 0
        
        for game in finished_games:
            # Check if player was assigned to a team
            team_assignment = TeamAssignment.query.filter_by(
                game_id=game.id,
                user_id=player.id
            ).first()
            
            if team_assignment:
                games_played += 1
                total_games_with_assignment += 1
                
                # Count goals and assists
                goals = MatchEvent.query.filter_by(
                    game_id=game.id,
                    scorer_id=player.id,
                    event_type='goal'
                ).count()
                
                assists = MatchEvent.query.filter_by(
                    game_id=game.id,
                    assist_id=player.id
                ).count()
                
                total_goals += goals
                total_assists += assists
                
                # Check if player won this game
                score = game.get_score()
                if team_assignment.team == 'A' and score['team_a'] > score['team_b']:
                    total_wins += 1
                elif team_assignment.team == 'B' and score['team_b'] > score['team_a']:
                    total_wins += 1
        
        # Performance score based on contributions and win rate
        if games_played > 0:
            goals_per_game = total_goals / games_played
            assists_per_game = total_assists / games_played
            win_rate = total_wins / games_played
            
            # Performance score (0-10 scale)
            score_data['performance_score'] = min(10.0, 
                (goals_per_game * 3) + (assists_per_game * 2) + (win_rate * 4)
            )
        else:
            score_data['performance_score'] = 5.0  # Neutral for new players
        
        # 3. Current availability bonus (15% weight)
        # Since we're only balancing available players, give small bonus based on how early they confirmed
        from sqlalchemy import desc
        current_vote = AvailabilityVote.query.join(Game).filter(
            AvailabilityVote.user_id == player.id,
            Game.id.in_([g.id for g in Game.query.filter_by(group_id=group_id, status='upcoming').all()])
        ).order_by(desc(AvailabilityVote.voted_at)).first()
        
        if current_vote and current_vote.status == 'in':
            # Small bonus for being available (everyone in this function is already 'in')
            score_data['participation_score'] = 7.5  # Neutral bonus for being available
        else:
            score_data['participation_score'] = 7.0  # Default
        
        # 4. Calculate recent form (30% weight - recent 5 games)
        recent_games = Game.query.filter_by(
            group_id=group_id,
            status='finished'
        ).order_by(Game.datetime.desc()).limit(5).all()
        
        recent_performance = 0.0
        recent_count = 0
        
        for game in recent_games:
            team_assignment = TeamAssignment.query.filter_by(
                game_id=game.id,
                user_id=player.id
            ).first()
            
            if team_assignment:
                recent_count += 1
                
                # Recent goals and assists
                goals = MatchEvent.query.filter_by(
                    game_id=game.id,
                    scorer_id=player.id,
                    event_type='goal'
                ).count()
                
                assists = MatchEvent.query.filter_by(
                    game_id=game.id,
                    assist_id=player.id
                ).count()
                
                # Recent win
                score = game.get_score()
                won = False
                if team_assignment.team == 'A' and score['team_a'] > score['team_b']:
                    won = True
                elif team_assignment.team == 'B' and score['team_b'] > score['team_a']:
                    won = True
                
                game_performance = (goals * 2) + assists + (3 if won else 0)
                recent_performance += game_performance
        
        if recent_count > 0:
            score_data['recent_form'] = min(10.0, recent_performance / recent_count)
        else:
            score_data['recent_form'] = score_data['performance_score']
        
        # Calculate overall weighted score
        score_data['overall_score'] = (
            score_data['skills_score'] * 0.25 +
            score_data['performance_score'] * 0.30 +
            score_data['participation_score'] * 0.15 +
            score_data['recent_form'] * 0.30
        )
        
        player_scores.append(score_data)
    
    # Sort players by overall score (descending)
    player_scores.sort(key=lambda x: x['overall_score'], reverse=True)
    
    # Balance teams using smart draft approach
    team_a = []
    team_b = []
    team_a_score = 0.0
    team_b_score = 0.0
    
    # Position tracking
    team_a_positions = {'GK': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    team_b_positions = {'GK': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
    
    # Draft players alternating, but with intelligence
    for i, player_data in enumerate(player_scores):
        player = player_data['player']
        score = player_data['overall_score']
        position = player_data['position'] or 'MID'  # Default to midfielder
        
        # Decide which team to add to based on:
        # 1. Overall score balance
        # 2. Position needs
        # 3. Some randomization to avoid predictable teams
        
        team_a_needs_position = team_a_positions[position] < (len(team_a) / 4 + 1)
        team_b_needs_position = team_b_positions[position] < (len(team_b) / 4 + 1)
        
        score_diff = abs(team_a_score - team_b_score)
        
        # Add to weaker team, but consider position needs
        if len(team_a) == len(team_b):
            # Equal team sizes - use score and position logic
            if team_a_score <= team_b_score and team_a_needs_position:
                target_team = 'A'
            elif team_b_score <= team_a_score and team_b_needs_position:
                target_team = 'B'
            else:
                # Random with slight bias toward score balance
                target_team = 'A' if team_a_score <= team_b_score else 'B'
        else:
            # Different team sizes - add to smaller team unless major score imbalance
            smaller_team = 'A' if len(team_a) < len(team_b) else 'B'
            
            # But if adding to smaller team would create huge imbalance, add to other team
            if smaller_team == 'A' and (team_a_score + score) - team_b_score > 3.0:
                target_team = 'B'
            elif smaller_team == 'B' and (team_b_score + score) - team_a_score > 3.0:
                target_team = 'A'
            else:
                target_team = smaller_team
        
        # Add slight randomization (10% chance to switch)
        if random.random() < 0.1:
            target_team = 'B' if target_team == 'A' else 'A'
        
        if target_team == 'A':
            team_a.append(player)
            team_a_score += score
            team_a_positions[position] += 1
        else:
            team_b.append(player)
            team_b_score += score
            team_b_positions[position] += 1
    
    return {
        'team_a': team_a,
        'team_b': team_b,
        'team_a_score': team_a_score,
        'team_b_score': team_b_score
    }

def calculate_team_fitness(team_a, team_b, group_id):
    """
    Calculate fitness score for a team composition considering:
    1. Skill balance between teams
    2. Position distribution
    3. Historical synergy
    4. Score competitiveness
    """
    if not team_a or not team_b:
        return 0.0
    
    fitness_score = 0.0
    
    # 1. Skill balance (40% of fitness)
    team_a_ratings = calculate_team_ratings(team_a, group_id)
    team_b_ratings = calculate_team_ratings(team_b, group_id)
    
    # Penalize large differences in overall ratings
    rating_diff = abs(team_a_ratings['overall'] - team_b_ratings['overall'])
    balance_score = max(0.0, 10.0 - rating_diff * 2)  # Penalty for imbalance
    fitness_score += balance_score * 0.4
    
    # 2. Position distribution (25% of fitness)
    def get_position_distribution(team):
        positions = {'GK': 0, 'DEF': 0, 'MID': 0, 'FWD': 0}
        for player in team:
            attrs = PlayerAttributes.query.filter_by(user_id=player.id, group_id=group_id).first()
            pos = attrs.preferred_position if attrs and attrs.preferred_position else 'MID'
            # Handle empty strings or invalid positions
            if pos not in positions:
                pos = 'MID'
            positions[pos] += 1
        return positions
    
    team_a_pos = get_position_distribution(team_a)
    team_b_pos = get_position_distribution(team_b)
    
    # Ideal distribution: at least 1 of each position type
    position_score = 0.0
    for pos in ['GK', 'DEF', 'MID', 'FWD']:
        # Reward having at least 1 of each position, penalize having too many of one type
        team_a_pos_score = min(3.0, max(1.0, team_a_pos[pos])) if team_a_pos[pos] > 0 else 0.5
        team_b_pos_score = min(3.0, max(1.0, team_b_pos[pos])) if team_b_pos[pos] > 0 else 0.5
        position_score += (team_a_pos_score + team_b_pos_score) / 2
    
    fitness_score += (position_score / 4) * 0.25  # Normalize and weight
    
    # 3. Team size balance (20% of fitness)
    size_diff = abs(len(team_a) - len(team_b))
    size_score = max(0.0, 10.0 - size_diff * 5)  # Heavy penalty for uneven teams
    fitness_score += size_score * 0.2
    
    # 4. Historical performance balance (15% of fitness)
    team_a_avg_score = sum(get_player_overall_score(p, group_id) for p in team_a) / len(team_a)
    team_b_avg_score = sum(get_player_overall_score(p, group_id) for p in team_b) / len(team_b)
    
    performance_diff = abs(team_a_avg_score - team_b_avg_score)
    performance_score = max(0.0, 10.0 - performance_diff)
    fitness_score += performance_score * 0.15
    
    return min(10.0, fitness_score)

def get_player_overall_score(player, group_id):
    """Get overall score for a single player (reused from existing logic)"""
    attributes = PlayerAttributes.query.filter_by(user_id=player.id, group_id=group_id).first()
    if attributes:
        return attributes.get_overall_rating()
    return 5.0

def calculate_bandit_balanced_teams(players, group_id, n_iterations=1000):
    """
    Multi-Armed Bandit approach to team balancing.
    Treats different team composition strategies as "arms" and learns which work best.
    """
    import random
    import numpy as np
    from collections import defaultdict
    
    if len(players) < 2:
        return {'team_a': [], 'team_b': []}
    
    # Define different balancing strategies (arms)
    strategies = [
        'skill_balanced',      # Balance by skill ratings
        'position_first',      # Prioritize position distribution
        'performance_based',   # Balance by historical performance
        'recent_form',         # Balance by recent form
        'random_smart'         # Smart randomization with constraints
    ]
    
    # Initialize bandit parameters
    arm_rewards = defaultdict(list)
    arm_counts = defaultdict(int)
    epsilon = 0.1  # Exploration rate
    
    best_composition = None
    best_fitness = 0.0
    
    for iteration in range(n_iterations):
        # Choose strategy using epsilon-greedy
        if random.random() < epsilon or not arm_rewards:
            # Exploration: random strategy
            strategy = random.choice(strategies)
        else:
            # Exploitation: choose best strategy based on average reward
            avg_rewards = {arm: np.mean(rewards) for arm, rewards in arm_rewards.items()}
            strategy = max(avg_rewards.keys(), key=lambda k: avg_rewards[k])
        
        # Generate team composition using selected strategy
        composition = generate_composition_by_strategy(players, group_id, strategy)
        
        # Evaluate fitness of this composition
        fitness = calculate_team_fitness(composition['team_a'], composition['team_b'], group_id)
        
        # Update bandit statistics
        arm_rewards[strategy].append(fitness)
        arm_counts[strategy] += 1
        
        # Track best composition
        if fitness > best_fitness:
            best_fitness = fitness
            best_composition = composition
        
        # Adaptive epsilon decay
        if iteration > 100:
            epsilon = max(0.01, epsilon * 0.995)
    
    return best_composition or {'team_a': players[:len(players)//2], 'team_b': players[len(players)//2:]}

def generate_composition_by_strategy(players, group_id, strategy):
    """Generate team composition based on specific strategy"""
    import random
    
    if strategy == 'skill_balanced':
        # Sort by skill, alternate assignment
        player_skills = [(p, get_player_overall_score(p, group_id)) for p in players]
        player_skills.sort(key=lambda x: x[1], reverse=True)
        
        team_a, team_b = [], []
        for i, (player, _) in enumerate(player_skills):
            if i % 2 == 0:
                team_a.append(player)
            else:
                team_b.append(player)
    
    elif strategy == 'position_first':
        # Group by position, distribute evenly
        positions = {'GK': [], 'DEF': [], 'MID': [], 'FWD': []}
        for player in players:
            attrs = PlayerAttributes.query.filter_by(user_id=player.id, group_id=group_id).first()
            pos = attrs.preferred_position if attrs and attrs.preferred_position else 'MID'
            # Handle empty strings or invalid positions
            if pos not in positions:
                pos = 'MID'
            positions[pos].append(player)
        
        team_a, team_b = [], []
        for pos, pos_players in positions.items():
            for i, player in enumerate(pos_players):
                if i % 2 == 0:
                    team_a.append(player)
                else:
                    team_b.append(player)
    
    elif strategy == 'performance_based':
        # Balance by historical performance
        finished_games = Game.query.filter_by(group_id=group_id, status='finished').all()
        player_performance = []
        
        for player in players:
            total_goals = sum(MatchEvent.query.filter_by(game_id=g.id, scorer_id=player.id, event_type='goal').count() for g in finished_games)
            total_assists = sum(MatchEvent.query.filter_by(game_id=g.id, assist_id=player.id).count() for g in finished_games)
            performance = total_goals + total_assists
            player_performance.append((player, performance))
        
        player_performance.sort(key=lambda x: x[1], reverse=True)
        team_a, team_b = [], []
        for i, (player, _) in enumerate(player_performance):
            if i % 2 == 0:
                team_a.append(player)
            else:
                team_b.append(player)
    
    elif strategy == 'recent_form':
        # Balance by recent 3 games performance
        recent_games = Game.query.filter_by(group_id=group_id, status='finished').order_by(Game.datetime.desc()).limit(3).all()
        player_recent = []
        
        for player in players:
            recent_performance = 0
            for game in recent_games:
                goals = MatchEvent.query.filter_by(game_id=game.id, scorer_id=player.id, event_type='goal').count()
                assists = MatchEvent.query.filter_by(game_id=game.id, assist_id=player.id).count()
                recent_performance += goals + assists
            player_recent.append((player, recent_performance))
        
        player_recent.sort(key=lambda x: x[1], reverse=True)
        team_a, team_b = [], []
        for i, (player, _) in enumerate(player_recent):
            if i % 2 == 0:
                team_a.append(player)
            else:
                team_b.append(player)
    
    else:  # random_smart
        # Smart randomization with balance constraints
        shuffled = players.copy()
        random.shuffle(shuffled)
        mid = len(shuffled) // 2
        team_a, team_b = shuffled[:mid], shuffled[mid:]
    
    return {'team_a': team_a, 'team_b': team_b}

def calculate_simulated_annealing_teams(players, group_id, max_iterations=2000, initial_temp=10.0, cooling_rate=0.95):
    """
    Simulated Annealing approach to find optimal team composition.
    Starts with random solution and iteratively improves by accepting/rejecting changes.
    """
    import random
    import math
    
    if len(players) < 2:
        return {'team_a': [], 'team_b': []}
    
    # Initialize with random solution
    shuffled_players = players.copy()
    random.shuffle(shuffled_players)
    mid = len(shuffled_players) // 2
    
    current_team_a = shuffled_players[:mid]
    current_team_b = shuffled_players[mid:]
    current_fitness = calculate_team_fitness(current_team_a, current_team_b, group_id)
    
    # Best solution tracking
    best_team_a = current_team_a.copy()
    best_team_b = current_team_b.copy()
    best_fitness = current_fitness
    
    temperature = initial_temp
    
    for iteration in range(max_iterations):
        # Generate neighbor solution by swapping players between teams
        new_team_a = current_team_a.copy()
        new_team_b = current_team_b.copy()
        
        # Choose swap strategy
        swap_type = random.choice(['single_swap', 'double_swap', 'position_swap'])
        
        if swap_type == 'single_swap' and new_team_a and new_team_b:
            # Swap one player between teams
            player_a = random.choice(new_team_a)
            player_b = random.choice(new_team_b)
            
            new_team_a.remove(player_a)
            new_team_b.remove(player_b)
            new_team_a.append(player_b)
            new_team_b.append(player_a)
        
        elif swap_type == 'double_swap' and len(new_team_a) >= 2 and len(new_team_b) >= 2:
            # Swap two players between teams
            players_a = random.sample(new_team_a, 2)
            players_b = random.sample(new_team_b, 2)
            
            for p in players_a:
                new_team_a.remove(p)
                new_team_b.append(p)
            for p in players_b:
                new_team_b.remove(p)
                new_team_a.append(p)
        
        elif swap_type == 'position_swap':
            # Swap players of same position between teams
            positions_a = {}
            positions_b = {}
            
            for player in new_team_a:
                attrs = PlayerAttributes.query.filter_by(user_id=player.id, group_id=group_id).first()
                pos = attrs.preferred_position if attrs and attrs.preferred_position else 'MID'
                # Handle empty strings or invalid positions
                if pos not in ['GK', 'DEF', 'MID', 'FWD']:
                    pos = 'MID'
                if pos not in positions_a:
                    positions_a[pos] = []
                positions_a[pos].append(player)
            
            for player in new_team_b:
                attrs = PlayerAttributes.query.filter_by(user_id=player.id, group_id=group_id).first()
                pos = attrs.preferred_position if attrs and attrs.preferred_position else 'MID'
                # Handle empty strings or invalid positions
                if pos not in ['GK', 'DEF', 'MID', 'FWD']:
                    pos = 'MID'
                if pos not in positions_b:
                    positions_b[pos] = []
                positions_b[pos].append(player)
            
            # Find common positions and swap
            common_positions = set(positions_a.keys()) & set(positions_b.keys())
            if common_positions:
                pos = random.choice(list(common_positions))
                if positions_a[pos] and positions_b[pos]:
                    player_a = random.choice(positions_a[pos])
                    player_b = random.choice(positions_b[pos])
                    
                    new_team_a.remove(player_a)
                    new_team_b.remove(player_b)
                    new_team_a.append(player_b)
                    new_team_b.append(player_a)
        
        # Calculate fitness of new solution
        new_fitness = calculate_team_fitness(new_team_a, new_team_b, group_id)
        
        # Accept or reject the new solution
        accept = False
        
        if new_fitness > current_fitness:
            # Always accept better solutions
            accept = True
        else:
            # Accept worse solutions with probability based on temperature
            fitness_diff = current_fitness - new_fitness
            probability = math.exp(-fitness_diff / temperature) if temperature > 0 else 0
            accept = random.random() < probability
        
        if accept:
            current_team_a = new_team_a
            current_team_b = new_team_b
            current_fitness = new_fitness
            
            # Update best solution if necessary
            if current_fitness > best_fitness:
                best_team_a = current_team_a.copy()
                best_team_b = current_team_b.copy()
                best_fitness = current_fitness
        
        # Cool down temperature
        temperature *= cooling_rate
        
        # Early stopping if temperature is too low
        if temperature < 0.01:
            break
    
    return {
        'team_a': best_team_a,
        'team_b': best_team_b,
        'fitness': best_fitness,
        'iterations': iteration + 1
    }