from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import Notification, User, Group, Game
from database import db
from datetime import datetime, timezone
from sqlalchemy import desc

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route('/count', methods=['GET'])
@login_required
def get_notification_count():
    """Get the count of unread notifications for the current user"""
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'count': count})

@notifications_bp.route('', methods=['GET'])
@login_required
def get_notifications():
    """Get recent notifications for the current user"""
    limit = request.args.get('limit', 20, type=int)
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(desc(Notification.created_at)).limit(limit).all()
    
    return jsonify({
        'notifications': [notification.to_dict() for notification in notifications]
    })

@notifications_bp.route('/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a specific notification as read"""
    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first()
    
    if not notification:
        return jsonify({'error': 'Notification not found'}), 404
    
    notification.mark_as_read()
    
    return jsonify({'success': True})

@notifications_bp.route('/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read for the current user"""
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).all()
    
    for notification in notifications:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    return jsonify({'success': True, 'marked_count': len(notifications)})

def create_notification(user_id, notification_type, title, message, group_id=None, game_id=None, related_user_id=None):
    """
    Helper function to create a new notification
    
    Args:
        user_id: ID of the user to notify
        notification_type: Type of notification (e.g., 'game_created', 'member_joined')
        title: Short title for the notification
        message: Detailed message
        group_id: Optional group ID
        game_id: Optional game ID
        related_user_id: Optional ID of related user
    """
    notification = Notification(
        user_id=user_id,
        group_id=group_id,
        type=notification_type,
        title=title,
        message=message,
        game_id=game_id,
        related_user_id=related_user_id
    )
    
    db.session.add(notification)
    db.session.commit()
    
    return notification

def notify_group_members(group_id, notification_type, title, message, exclude_user_id=None, game_id=None, related_user_id=None):
    """
    Helper function to notify all members of a group
    
    Args:
        group_id: ID of the group
        notification_type: Type of notification
        title: Short title for the notification
        message: Detailed message
        exclude_user_id: Optional user ID to exclude from notifications (e.g., the user who triggered the event)
        game_id: Optional game ID
        related_user_id: Optional ID of related user
    """
    from models import GroupMembership
    
    # Get all group members
    memberships = GroupMembership.query.filter_by(group_id=group_id).all()
    
    notifications_created = 0
    for membership in memberships:
        if exclude_user_id and membership.user_id == exclude_user_id:
            continue
            
        create_notification(
            user_id=membership.user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            group_id=group_id,
            game_id=game_id,
            related_user_id=related_user_id
        )
        notifications_created += 1
    
    return notifications_created