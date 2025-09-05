from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import Group, GroupMembership, User, FeedItem, Game, TeamAssignment, MatchEvent, POTMVote, PlayerAttributes
from database import db
from datetime import datetime
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
    
    feed_items = FeedItem.query.filter_by(group_id=group_id).order_by(
        FeedItem.created_at.desc()
    ).limit(10).all()
    
    members = group.get_members()
    
    # Calculate leaderboard data
    leaderboard_data = calculate_leaderboard(group_id)
    
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
                         feed_items=feed_items,
                         members=members,
                         leaderboard_data=leaderboard_data,
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

    # Get existing attributes
    attributes = PlayerAttributes.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()
    
    if attributes:
        attributes_data = {
            'pace': attributes.pace,
            'stamina': attributes.stamina,
            'strength': attributes.strength,
            'agility': attributes.agility,
            'jumping': attributes.jumping,
            'ball_control': attributes.ball_control,
            'dribbling': attributes.dribbling,
            'passing': attributes.passing,
            'shooting': attributes.shooting,
            'crossing': attributes.crossing,
            'free_kicks': attributes.free_kicks,
            'positioning': attributes.positioning,
            'marking': attributes.marking,
            'tackling': attributes.tackling,
            'interceptions': attributes.interceptions,
            'vision': attributes.vision,
            'decision_making': attributes.decision_making,
            'composure': attributes.composure,
            'concentration': attributes.concentration,
            'determination': attributes.determination,
            'leadership': attributes.leadership,
            'teamwork': attributes.teamwork,
            'goalkeeping': attributes.goalkeeping,
            'handling': attributes.handling,
            'distribution': attributes.distribution,
            'aerial_reach': attributes.aerial_reach,
            'preferred_position': attributes.preferred_position,
            'notes': attributes.notes
        }
        return jsonify({
            'attributes': attributes_data,
            'player_name': user.display_name
        })
    else:
        return jsonify({
            'attributes': None,
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
    
    # Get existing attributes or create new ones
    attributes = PlayerAttributes.query.filter_by(
        user_id=user_id,
        group_id=group_id
    ).first()
    
    if not attributes:
        attributes = PlayerAttributes(
            user_id=user_id,
            group_id=group_id,
            last_updated_by=current_user.id
        )
        db.session.add(attributes)
    else:
        attributes.last_updated_by = current_user.id
        attributes.updated_at = datetime.utcnow()
    
    # Update all attributes from form data
    try:
        # Physical attributes
        attributes.pace = int(request.form.get('pace', 5))
        attributes.stamina = int(request.form.get('stamina', 5))
        attributes.strength = int(request.form.get('strength', 5))
        attributes.agility = int(request.form.get('agility', 5))
        attributes.jumping = int(request.form.get('jumping', 5))
        
        # Technical attributes
        attributes.ball_control = int(request.form.get('ball_control', 5))
        attributes.dribbling = int(request.form.get('dribbling', 5))
        attributes.passing = int(request.form.get('passing', 5))
        attributes.shooting = int(request.form.get('shooting', 5))
        attributes.crossing = int(request.form.get('crossing', 5))
        attributes.free_kicks = int(request.form.get('free_kicks', 5))
        
        # Tactical attributes
        attributes.positioning = int(request.form.get('positioning', 5))
        attributes.marking = int(request.form.get('marking', 5))
        attributes.tackling = int(request.form.get('tackling', 5))
        attributes.interceptions = int(request.form.get('interceptions', 5))
        attributes.vision = int(request.form.get('vision', 5))
        attributes.decision_making = int(request.form.get('decision_making', 5))
        
        # Mental attributes
        attributes.composure = int(request.form.get('composure', 5))
        attributes.concentration = int(request.form.get('concentration', 5))
        attributes.determination = int(request.form.get('determination', 5))
        attributes.leadership = int(request.form.get('leadership', 5))
        attributes.teamwork = int(request.form.get('teamwork', 5))
        
        # Goalkeeping attributes
        attributes.goalkeeping = int(request.form.get('goalkeeping', 1))
        attributes.handling = int(request.form.get('handling', 1))
        attributes.distribution = int(request.form.get('distribution', 1))
        attributes.aerial_reach = int(request.form.get('aerial_reach', 1))
        
        # Position and notes
        attributes.preferred_position = request.form.get('preferred_position', '')
        attributes.notes = request.form.get('notes', '')
        
        # Validate attribute values (1-10 range)
        attribute_fields = [
            'pace', 'stamina', 'strength', 'agility', 'jumping',
            'ball_control', 'dribbling', 'passing', 'shooting', 'crossing', 'free_kicks',
            'positioning', 'marking', 'tackling', 'interceptions', 'vision', 'decision_making',
            'composure', 'concentration', 'determination', 'leadership', 'teamwork'
        ]
        
        for field in attribute_fields:
            value = getattr(attributes, field)
            if not (1 <= value <= 10):
                return jsonify({'error': f'{field} must be between 1 and 10'}), 400
        
        # Validate goalkeeping attributes (1-10 range)
        gk_fields = ['goalkeeping', 'handling', 'distribution', 'aerial_reach']
        for field in gk_fields:
            value = getattr(attributes, field)
            if not (1 <= value <= 10):
                return jsonify({'error': f'{field} must be between 1 and 10'}), 400
        
        db.session.commit()
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