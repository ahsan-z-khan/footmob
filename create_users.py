#!/usr/bin/env python3
"""
Script to create users from players.json and make them join a group
"""

import json
import sys
import os
from flask import Flask
from flask_bcrypt import generate_password_hash
from database import db
from models import User, Group, GroupMembership

# Add the current directory to Python path to import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def create_app():
    """Create and configure the Flask app"""
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///footmob.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    return app

def load_players():
    """Load players from players.json"""
    try:
        with open('players.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: players.json file not found!")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: Invalid JSON in players.json!")
        sys.exit(1)

def create_users_and_join_group(players, invite_code, password="123456"):
    """Create users from players list and make them join the group"""
    
    # Find the group by invite code
    group = Group.query.filter_by(invite_code=invite_code).first()
    if not group:
        print(f"Error: No group found with invite code '{invite_code}'!")
        return False
    
    print(f"Found group: {group.name} (ID: {group.id})")
    
    created_users = 0
    existing_users = 0
    joined_group = 0
    
    for player in players:
        username = player['username']
        display_name = player['name']
        
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            print(f"User '{username}' already exists, skipping creation...")
            user = existing_user
            existing_users += 1
        else:
            # Create new user
            password_hash = generate_password_hash(password)
            user = User(
                username=username,
                password_hash=password_hash,
                display_name=display_name
            )
            
            db.session.add(user)
            db.session.flush()  # Flush to get the user ID
            
            print(f"Created user: {display_name} (@{username})")
            created_users += 1
        
        # Check if user is already a member of the group
        existing_membership = GroupMembership.query.filter_by(
            user_id=user.id,
            group_id=group.id
        ).first()
        
        if existing_membership:
            print(f"  - {display_name} is already a member of the group")
        else:
            # Add user to the group
            membership = GroupMembership(
                user_id=user.id,
                group_id=group.id,
                is_admin=False
            )
            db.session.add(membership)
            print(f"  - Added {display_name} to the group")
            joined_group += 1
    
    # Commit all changes
    try:
        db.session.commit()
        print(f"\nSummary:")
        print(f"- Created {created_users} new users")
        print(f"- Found {existing_users} existing users")
        print(f"- Added {joined_group} users to the group '{group.name}'")
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error committing changes: {e}")
        return False

def main():
    """Main function"""
    invite_code = "7IPX6DWV"
    password = "123456"
    
    print("FootMob User Creation Script")
    print("=" * 40)
    print(f"Invite Code: {invite_code}")
    print(f"Default Password: {password}")
    print()
    
    # Create Flask app and application context
    app = create_app()
    
    with app.app_context():
        # Load players data
        players = load_players()
        print(f"Loaded {len(players)} players from players.json")
        print()
        
        # Create users and join group
        success = create_users_and_join_group(players, invite_code, password)
        
        if success:
            print("\n✅ Script completed successfully!")
        else:
            print("\n❌ Script failed!")
            sys.exit(1)

if __name__ == "__main__":
    main()
