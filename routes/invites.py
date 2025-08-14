from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import Group, GroupMembership, User
from database import db
import qrcode
import io
import base64

invites_bp = Blueprint('invites', __name__)

@invites_bp.route('/<string:invite_code>')
def join_preview(invite_code):
    group = Group.query.filter_by(invite_code=invite_code).first_or_404()
    
    if current_user.is_authenticated:
        existing_membership = GroupMembership.query.filter_by(
            user_id=current_user.id,
            group_id=group.id
        ).first()
        
        if existing_membership:
            return redirect(url_for('groups.view', group_id=group.id))
    
    member_count = GroupMembership.query.filter_by(group_id=group.id).count()
    next_game = group.get_next_game()
    
    return render_template('invites/preview.html', 
                         group=group, 
                         member_count=member_count,
                         next_game=next_game)

@invites_bp.route('/<string:invite_code>/join', methods=['POST'])
def join_group(invite_code):
    group = Group.query.filter_by(invite_code=invite_code).first_or_404()
    
    if not current_user.is_authenticated:
        display_name = request.form.get('display_name')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([display_name, username, password, confirm_password]):
            flash('All fields are required')
            return redirect(url_for('invites.join_preview', invite_code=invite_code))
        
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('invites.join_preview', invite_code=invite_code))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long')
            return redirect(url_for('invites.join_preview', invite_code=invite_code))
        
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already taken')
            return redirect(url_for('invites.join_preview', invite_code=invite_code))
        
        from flask_bcrypt import generate_password_hash
        password_hash = generate_password_hash(password)
        user = User(username=username, password_hash=password_hash, display_name=display_name)
        db.session.add(user)
        db.session.flush()
        
        from flask_login import login_user
        login_user(user)
    else:
        user = current_user
    
    existing_membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group.id
    ).first()
    
    if existing_membership:
        return redirect(url_for('groups.view', group_id=group.id))
    
    membership = GroupMembership(
        user_id=user.id,
        group_id=group.id,
        is_admin=False
    )
    db.session.add(membership)
    db.session.commit()
    
    # Create notifications for all existing group members
    from routes.notifications import notify_group_members
    notify_group_members(
        group_id=group.id,
        notification_type='member_joined',
        title='New Member Joined',
        message=f'{user.display_name} has joined the group',
        exclude_user_id=user.id,
        related_user_id=user.id
    )
    
    return redirect(url_for('groups.view', group_id=group.id))

@invites_bp.route('/groups/<int:group_id>/invite')
@login_required
def manage_invite(group_id):
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can manage invites')
        return redirect(url_for('groups.view', group_id=group_id))
    
    invite_url = url_for('invites.join_preview', invite_code=group.invite_code, _external=True)
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(invite_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    qr_code_base64 = base64.b64encode(img_buffer.getvalue()).decode()
    
    return render_template('invites/manage.html', 
                         group=group,
                         invite_url=invite_url,
                         qr_code=qr_code_base64)

@invites_bp.route('/groups/<int:group_id>/invite/regenerate', methods=['POST'])
@login_required
def regenerate_invite(group_id):
    group = Group.query.get_or_404(group_id)
    
    membership = GroupMembership.query.filter_by(
        user_id=current_user.id,
        group_id=group_id,
        is_admin=True
    ).first()
    
    if not membership:
        flash('Only admins can regenerate invites')
        return redirect(url_for('groups.view', group_id=group_id))
    
    group.invite_code = group.generate_invite_code()
    db.session.commit()
    
    flash('Invite code regenerated')
    return redirect(url_for('invites.manage_invite', group_id=group_id))