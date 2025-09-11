from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Group, GroupMembership, User, FeedItem, Game, TeamAssignment, MatchEvent, POTMVote, PlayerAttributes, AdminPlayerRating
from database import db
from datetime import datetime, timezone
from sqlalchemy import func

groups_bp = Blueprint('groups', __name__)

@groups_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        name = request.form.get('name')
        emoji = request.form.get('emoji', '⚽')
        
        if not name:
            flash('Group name is required')
            return render_template('groups/create.html')
        
        group = Group(name=name, emoji=emoji)
        db.session.add(group)
        db.session.flush()
        
        membership = GroupMembership(
            user_id=current_user.id,
            group_id=group.id,
            is_admin=True
        )
        db.session.add(membership)
        db.session.commit()
        
        return redirect(url_for('groups.view', group_id=group.id))
    
    return render_template('groups/create.html')

@groups_bp.route('/<int:group_id>')
@login_required
def view(group_id):
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id
    ).first()
    
    if not membership:
        flash('You are not a member of this group')
        return redirect(url_for('main.dashboard'))
    
    # Auto-update game statuses first
    group.update_game_statuses()
    
    next_game = group.get_next_game()
    last_game = group.get_last_game()
    
    # Get all games for this group
    all_games = Game.query.filter_by(group_id=group_id).order_by(Game.datetime.desc()).all()
    
    feed_items = FeedItem.query.filter_by(group_id=group_id).order_by(
        FeedItem.created_at.desc()
    ).limit(10).all()
    
    members = group.get_members()
    
    # Calculate leaderboard data
    leaderboard_data = calculate_leaderboard(group_id)
    
    # Calculate group statistics
    group_stats = calculate_group_statistics(group_id)
    
    # Get player attributes for all members
    player_attributes = {}
    if membership.is_admin:
        attributes_query = PlayerAttributes.query.filter_by(group_id=group_id).all()
        for attr in attributes_query:
            player_attributes[attr.user_id] = attr
    
    return render_template('groups/view.html', 
                         group=group, 
                         membership=membership,
                         next_game=next_game,
                         last_game=last_game,
                         all_games=all_games,
                         feed_items=feed_items,
                         members=members,
                         leaderboard_data=leaderboard_data,
                         group_stats=group_stats,
                         player_attributes=player_attributes)

@groups_bp.route('/<int:group_id>/members')
@login_required
def members(group_id):
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id
    ).first()
    
    if not membership:
        flash('You are not a member of this group')
        return redirect(url_for('main.dashboard'))
    
    memberships = GroupMembership.query.filter_by(group_id=group_id).join(User).all()
    
    return render_template('groups/members.html', 
                         group=group, 
                         membership=membership,
                         memberships=memberships)

@groups_bp.route('/<int:group_id>/members/<int:user_id>/promote', methods=['POST'])
@login_required
def promote_member(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    
    admin_membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not admin_membership:
        flash('Only admins can promote members')
        return redirect(url_for('groups.members', group_id=group_id))
    
    membership = GroupMembership.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first_or_404()
    
    membership.is_admin = True
    db.session.commit()
    
    flash('Member promoted to admin')
    return redirect(url_for('groups.members', group_id=group_id))

@groups_bp.route('/<int:group_id>/members/<int:user_id>/demote', methods=['POST'])
@login_required
def demote_member(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    
    admin_membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not admin_membership:
        flash('Only admins can demote members')
        return redirect(url_for('groups.members', group_id=group_id))
    
    membership = GroupMembership.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first_or_404()
    
    admin_count = GroupMembership.query.filter_by(
        group_id=group_id,
        is_admin=True
    ).count()
    
    if admin_count <= 1:
        flash('Cannot demote the last admin')
        return redirect(url_for('groups.members', group_id=group_id))
    
    membership.is_admin = False
    db.session.commit()
    
    flash('Admin demoted to member')
    return redirect(url_for('groups.members', group_id=group_id))

@groups_bp.route('/<int:group_id>/players/<int:user_id>/attributes', methods=['GET'])
@login_required
def get_player_attributes(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    
    admin_membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not admin_membership:
        return jsonify({'error': 'Only admins can access player attributes'}), 403
    
    # Check if the user is a member of the group
    target_membership = GroupMembership.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()
    
    if not target_membership:
        return jsonify({'error': 'User is not a member of this group'}), 404
    
    # Get the user information
    from models import User
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Get current admin's rating for this player
    admin_rating = AdminPlayerRating.query.filter_by(
        user_id=user_id,
        admin_id=current_user.id,
        group_id=group_id
    ).first()
    
    # Get averaged attributes
    averaged_attributes = PlayerAttributes.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()
    
    if admin_rating:
        admin_attributes_data = {
            'pace': admin_rating.pace,
            'stamina': admin_rating.stamina,
            'strength': admin_rating.strength,
            'agility': admin_rating.agility,
            'jumping': admin_rating.jumping,
            'ball_control': admin_rating.ball_control,
            'dribbling': admin_rating.dribbling,
            'passing': admin_rating.passing,
            'shooting': admin_rating.shooting,
            'crossing': admin_rating.crossing,
            'free_kicks': admin_rating.free_kicks,
            'positioning': admin_rating.positioning,
            'marking': admin_rating.marking,
            'tackling': admin_rating.tackling,
            'interceptions': admin_rating.interceptions,
            'vision': admin_rating.vision,
            'decision_making': admin_rating.decision_making,
            'composure': admin_rating.composure,
            'concentration': admin_rating.concentration,
            'determination': admin_rating.determination,
            'leadership': admin_rating.leadership,
            'teamwork': admin_rating.teamwork,
            'goalkeeping': admin_rating.goalkeeping,
            'handling': admin_rating.handling,
            'distribution': admin_rating.distribution,
            'aerial_reach': admin_rating.aerial_reach,
            'preferred_position': admin_rating.preferred_position,
            'notes': admin_rating.notes
        }
    else:
        admin_attributes_data = None
    
    averaged_attributes_data = None
    if averaged_attributes:
        averaged_attributes_data = {
            'pace': averaged_attributes.pace,
            'stamina': averaged_attributes.stamina,
            'strength': averaged_attributes.strength,
            'agility': averaged_attributes.agility,
            'jumping': averaged_attributes.jumping,
            'ball_control': averaged_attributes.ball_control,
            'dribbling': averaged_attributes.dribbling,
            'passing': averaged_attributes.passing,
            'shooting': averaged_attributes.shooting,
            'crossing': averaged_attributes.crossing,
            'free_kicks': averaged_attributes.free_kicks,
            'positioning': averaged_attributes.positioning,
            'marking': averaged_attributes.marking,
            'tackling': averaged_attributes.tackling,
            'interceptions': averaged_attributes.interceptions,
            'vision': averaged_attributes.vision,
            'decision_making': averaged_attributes.decision_making,
            'composure': averaged_attributes.composure,
            'concentration': averaged_attributes.concentration,
            'determination': averaged_attributes.determination,
            'leadership': averaged_attributes.leadership,
            'teamwork': averaged_attributes.teamwork,
            'goalkeeping': averaged_attributes.goalkeeping,
            'handling': averaged_attributes.handling,
            'distribution': averaged_attributes.distribution,
            'aerial_reach': averaged_attributes.aerial_reach,
            'preferred_position': averaged_attributes.preferred_position,
            'notes': averaged_attributes.notes
        }
    
    return jsonify({
        'admin_attributes': admin_attributes_data,
        'averaged_attributes': averaged_attributes_data,
        'player_name': user.display_name
    })

@groups_bp.route('/<int:group_id>/players/<int:user_id>/attributes', methods=['POST'])
@login_required
def update_player_attributes(group_id, user_id):
    group = Group.query.get_or_404(group_id)
    
    admin_membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not admin_membership:
        return jsonify({'error': 'Only admins can update player attributes'}), 403
    
    # Check if the user is a member of the group
    target_membership = GroupMembership.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()
    
    if not target_membership:
        return jsonify({'error': 'User is not a member of this group'}), 404
    
    # Get or create admin rating for this player
    admin_rating = AdminPlayerRating.query.filter_by(
        user_id=user_id,
        admin_id=current_user.id,
        group_id=group_id
    ).first()
    
    if not admin_rating:
        admin_rating = AdminPlayerRating(
            user_id=user_id,
            admin_id=current_user.id,
            group_id=group_id
        )
        db.session.add(admin_rating)
    else:
        admin_rating.updated_at = datetime.now(timezone.utc)
    
    # Update all attributes from form data
    try:
        # Physical attributes
        admin_rating.pace = int(request.form.get('pace', 5))
        admin_rating.stamina = int(request.form.get('stamina', 5))
        admin_rating.strength = int(request.form.get('strength', 5))
        admin_rating.agility = int(request.form.get('agility', 5))
        admin_rating.jumping = int(request.form.get('jumping', 5))
        
        # Technical attributes
        admin_rating.ball_control = int(request.form.get('ball_control', 5))
        admin_rating.dribbling = int(request.form.get('dribbling', 5))
        admin_rating.passing = int(request.form.get('passing', 5))
        admin_rating.shooting = int(request.form.get('shooting', 5))
        admin_rating.crossing = int(request.form.get('crossing', 5))
        admin_rating.free_kicks = int(request.form.get('free_kicks', 5))
        
        # Tactical attributes
        admin_rating.positioning = int(request.form.get('positioning', 5))
        admin_rating.marking = int(request.form.get('marking', 5))
        admin_rating.tackling = int(request.form.get('tackling', 5))
        admin_rating.interceptions = int(request.form.get('interceptions', 5))
        admin_rating.vision = int(request.form.get('vision', 5))
        admin_rating.decision_making = int(request.form.get('decision_making', 5))
        
        # Mental attributes
        admin_rating.composure = int(request.form.get('composure', 5))
        admin_rating.concentration = int(request.form.get('concentration', 5))
        admin_rating.determination = int(request.form.get('determination', 5))
        admin_rating.leadership = int(request.form.get('leadership', 5))
        admin_rating.teamwork = int(request.form.get('teamwork', 5))
        
        # Goalkeeping attributes
        admin_rating.goalkeeping = int(request.form.get('goalkeeping', 1))
        admin_rating.handling = int(request.form.get('handling', 1))
        admin_rating.distribution = int(request.form.get('distribution', 1))
        admin_rating.aerial_reach = int(request.form.get('aerial_reach', 1))
        
        # Position and notes
        admin_rating.preferred_position = request.form.get('preferred_position', '')
        admin_rating.notes = request.form.get('notes', '')
        
        # Validate attribute values (1-10 range)
        attribute_fields = [
            'pace', 'stamina', 'strength', 'agility', 'jumping',
            'ball_control', 'dribbling', 'passing', 'shooting', 'crossing', 'free_kicks',
            'positioning', 'marking', 'tackling', 'interceptions', 'vision', 'decision_making',
            'composure', 'concentration', 'determination', 'leadership', 'teamwork'
        ]
        
        for field in attribute_fields:
            value = getattr(admin_rating, field)
            if not (1 <= value <= 10):
                return jsonify({'error': f'{field} must be between 1 and 10'}), 400
        
        # Validate goalkeeping attributes (1-10 range)
        gk_fields = ['goalkeeping', 'handling', 'distribution', 'aerial_reach']
        for field in gk_fields:
            value = getattr(admin_rating, field)
            if not (1 <= value <= 10):
                return jsonify({'error': f'{field} must be between 1 and 10'}), 400
        
        db.session.commit()
        
        # Recalculate averaged attributes
        PlayerAttributes.calculate_and_update(user_id, group_id)
        
        return jsonify({'success': True, 'message': 'Player attributes updated successfully'})
        
    except ValueError as e:
        return jsonify({'error': 'Invalid attribute values provided'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': 'Failed to update player attributes'}), 500

def calculate_leaderboard(group_id):
    """Calculate leaderboard data for all group members"""
    leaderboard = []
    
    # Get all finished games for this group
    finished_games = Game.query.filter_by(group_id=group_id, status='finished').all()
    
    # Get all group members
    group_members = User.query.join(GroupMembership).filter(
        GroupMembership.group_id == group_id
    ).all()
    
    for member in group_members:
        player_stats = {
            'user_id': member.id,
            'display_name': member.display_name,
            'goals': 0,
            'assists': 0,
            'own_goals': 0,
            'potm_awards': 0,
            'games_played': 0,
            'wins': 0,
            'draws': 0,
            'losses': 0,
            'points': 0,
            'total_contributions': 0
        }
        
        # Count goals, assists, own goals
        player_stats['goals'] = MatchEvent.query.filter(
            MatchEvent.scorer_id == member.id,
            MatchEvent.event_type == 'goal',
            MatchEvent.game_id.in_([game.id for game in finished_games])
        ).count()
        
        player_stats['assists'] = MatchEvent.query.filter(
            MatchEvent.assist_id == member.id,
            MatchEvent.game_id.in_([game.id for game in finished_games])
        ).count()
        
        player_stats['own_goals'] = MatchEvent.query.filter(
            MatchEvent.scorer_id == member.id,
            MatchEvent.event_type == 'own_goal',
            MatchEvent.game_id.in_([game.id for game in finished_games])
        ).count()
        
        # Count POTM awards
        player_stats['potm_awards'] = POTMVote.query.filter(
            POTMVote.voted_for_id == member.id,
            POTMVote.game_id.in_([game.id for game in finished_games])
        ).count()
        
        # Calculate wins, draws, losses, points
        for game in finished_games:
            # Check if player was assigned to a team
            team_assignment = TeamAssignment.query.filter_by(
                game_id=game.id,
                user_id=member.id
            ).first()
            
            if team_assignment:
                player_stats['games_played'] += 1
                score = game.get_score()
                
                # Determine result based on team assignment
                if team_assignment.team == 'A':
                    if score['team_a'] > score['team_b']:
                        player_stats['wins'] += 1
                        player_stats['points'] += 3
                    elif score['team_a'] == score['team_b']:
                        player_stats['draws'] += 1
                        player_stats['points'] += 1
                    else:
                        player_stats['losses'] += 1
                else:  # Team B
                    if score['team_b'] > score['team_a']:
                        player_stats['wins'] += 1
                        player_stats['points'] += 3
                    elif score['team_a'] == score['team_b']:
                        player_stats['draws'] += 1
                        player_stats['points'] += 1
                    else:
                        player_stats['losses'] += 1
        
        # Calculate total contributions (goals + assists)
        player_stats['total_contributions'] = player_stats['goals'] + player_stats['assists']
        
        # Only include players who have played games
        if player_stats['games_played'] > 0:
            leaderboard.append(player_stats)
    
    # Sort by points (descending), then by total contributions (descending), then by goals (descending)
    leaderboard.sort(key=lambda x: (x['points'], x['total_contributions'], x['goals']), reverse=True)
    
    return leaderboard


def calculate_group_statistics(group_id):
    """Calculate overall group statistics"""
    # Get all finished games for this group
    finished_games = Game.query.filter_by(group_id=group_id, status='finished').all()
    
    # Get all games (including upcoming)
    all_games = Game.query.filter_by(group_id=group_id).all()
    
    # Get all group members
    group_members = User.query.join(GroupMembership).filter(
        GroupMembership.group_id == group_id
    ).all()
    
    stats = {
        'total_games': len(finished_games),
        'upcoming_games': len([g for g in all_games if g.status == 'upcoming']),
        'total_goals': 0,
        'total_assists': 0,
        'total_own_goals': 0,
        'attendance_rate': 0,
        'average_goals_per_game': 0,
        'most_active_player': None,
        'top_scorer': None
    }
    
    if finished_games:
        # Count total goals and assists
        stats['total_goals'] = MatchEvent.query.filter(
            MatchEvent.event_type == 'goal',
            MatchEvent.game_id.in_([game.id for game in finished_games])
        ).count()
        
        stats['total_assists'] = MatchEvent.query.filter(
            MatchEvent.assist_id.isnot(None),
            MatchEvent.game_id.in_([game.id for game in finished_games])
        ).count()
        
        stats['total_own_goals'] = MatchEvent.query.filter(
            MatchEvent.event_type == 'own_goal',
            MatchEvent.game_id.in_([game.id for game in finished_games])
        ).count()
        
        # Calculate average goals per game
        if len(finished_games) > 0:
            stats['average_goals_per_game'] = round(stats['total_goals'] / len(finished_games), 1)
        
        # Calculate attendance rate
        total_possible_attendances = len(finished_games) * len(group_members)
        actual_attendances = TeamAssignment.query.filter(
            TeamAssignment.game_id.in_([game.id for game in finished_games])
        ).count()
        
        if total_possible_attendances > 0:
            stats['attendance_rate'] = round((actual_attendances / total_possible_attendances) * 100, 1)
        
        # Find most active player (most games played)
        player_games = {}
        for member in group_members:
            games_played = TeamAssignment.query.filter(
                TeamAssignment.user_id == member.id,
                TeamAssignment.game_id.in_([game.id for game in finished_games])
            ).count()
            if games_played > 0:
                player_games[member.display_name] = games_played
        
        if player_games:
            stats['most_active_player'] = max(player_games.items(), key=lambda x: x[1])
        
        # Find top scorer
        scorer_goals = {}
        for member in group_members:
            goals = MatchEvent.query.filter(
                MatchEvent.scorer_id == member.id,
                MatchEvent.event_type == 'goal',
                MatchEvent.game_id.in_([game.id for game in finished_games])
            ).count()
            if goals > 0:
                scorer_goals[member.display_name] = goals
        
        if scorer_goals:
            stats['top_scorer'] = max(scorer_goals.items(), key=lambda x: x[1])
    
    return stats

@groups_bp.route('/<int:group_id>/activity')
@login_required
def activity(group_id):
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id
    ).first()
    
    if not membership:
        flash('You are not a member of this group')
        return redirect(url_for('main.dashboard'))
    
    # Get all feed items for this group (paginated)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    feed_items = FeedItem.query.filter_by(group_id=group_id).order_by(
        FeedItem.created_at.desc()
    ).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    return render_template('groups/activity.html', 
                         group=group, 
                         membership=membership,
                         feed_items=feed_items)