from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import Group, GroupMembership, User, MatchEvent, POTMVote
from database import db
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    user_groups = Group.query.join(GroupMembership).filter(
        GroupMembership.user_id == current_user.id
    ).all()
    
    # Calculate stats for template
    upcoming_games = [group.get_next_game() for group in user_groups if group.get_next_game()]
    total_members = sum(len(group.get_members()) for group in user_groups)
    
    return render_template('dashboard.html', 
                         groups=user_groups,
                         upcoming_games=upcoming_games,
                         total_members=total_members)

@main_bp.route('/join', methods=['GET', 'POST'])
@login_required
def join_group():
    if request.method == 'POST':
        invite_code = request.form.get('invite_code', '').strip().upper()
        
        if not invite_code:
            flash('Please enter an invite code', 'error')
            return render_template('join_group.html')
        
        group = Group.query.filter_by(invite_code=invite_code).first()
        if not group:
            flash('Invalid invite code', 'error')
            return render_template('join_group.html')
        
        # Check if user is already a member
        existing_membership = GroupMembership.query.filter_by(
            user_id=current_user.id,
            group_id=group.id
        ).first()
        
        if existing_membership:
            flash('You are already a member of this group', 'info')
            return redirect(url_for('groups.view', group_id=group.id))
        
        # Add user to group
        membership = GroupMembership(
            user_id=current_user.id,
            group_id=group.id,
            is_admin=False
        )
        db.session.add(membership)
        db.session.commit()
        
        flash(f'Successfully joined {group.name}!', 'success')
        return redirect(url_for('groups.view', group_id=group.id))
    
    return render_template('join_group.html')

@main_bp.route('/profile')
@login_required
def profile():
    # Get user's groups and admin roles
    user_groups = Group.query.join(GroupMembership).filter(
        GroupMembership.user_id == current_user.id
    ).all()
    
    admin_groups = Group.query.join(GroupMembership).filter(
        GroupMembership.user_id == current_user.id,
        GroupMembership.is_admin == True
    ).all()
    
    # Get user's match statistics
    total_goals = MatchEvent.query.filter_by(
        scorer_id=current_user.id,
        event_type='goal'
    ).count()
    
    total_assists = MatchEvent.query.filter_by(
        assist_id=current_user.id
    ).count()
    
    total_own_goals = MatchEvent.query.filter_by(
        scorer_id=current_user.id,
        event_type='own_goal'
    ).count()
    
    # Get POTM wins
    potm_wins = POTMVote.query.filter_by(voted_for_id=current_user.id).count()
    
    return render_template('profile.html',
                         user_groups=user_groups,
                         admin_groups=admin_groups,
                         total_goals=total_goals,
                         total_assists=total_assists,
                         total_own_goals=total_own_goals,
                         potm_wins=potm_wins)

@main_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            display_name = request.form.get('display_name', '').strip()
            
            if not display_name:
                flash('Display name is required', 'error')
            elif len(display_name) > 100:
                flash('Display name must be 100 characters or less', 'error')
            else:
                current_user.display_name = display_name
                db.session.commit()
                flash('Profile updated successfully', 'success')
        
        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if not current_password or not new_password or not confirm_password:
                flash('All password fields are required', 'error')
            elif not check_password_hash(current_user.password_hash, current_password):
                flash('Current password is incorrect', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match', 'error')
            elif len(new_password) < 6:
                flash('New password must be at least 6 characters', 'error')
            else:
                current_user.password_hash = generate_password_hash(new_password)
                db.session.commit()
                flash('Password changed successfully', 'success')
        
        return redirect(url_for('main.settings'))
    
    return render_template('settings.html')