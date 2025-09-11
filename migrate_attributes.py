#!/usr/bin/env python3
"""
Migration script to convert existing PlayerAttributes to the new multi-admin system.
This script will:
1. Take existing PlayerAttributes records
2. Create AdminPlayerRating records for each admin in the group
3. Recalculate averaged PlayerAttributes
"""

from app import app
from database import db
from models import PlayerAttributes, AdminPlayerRating, GroupMembership


def migrate_existing_attributes(dry_run=False):
    with app.app_context():
        existing_attributes = PlayerAttributes.query.all()

        print(f"Found {len(existing_attributes)} existing player attributes to migrate")

        for attr in existing_attributes:
            print(
                f"Migrating attributes for user {attr.user_id} in group {attr.group_id}"
            )

            admins = GroupMembership.query.filter_by(
                group_id=attr.group_id, is_admin=True
            ).all()

            print(f"  Found {len(admins)} admins in group")

            # Create AdminPlayerRating for each admin with the existing values
            for admin_membership in admins:
                existing_rating = AdminPlayerRating.query.filter_by(
                    user_id=attr.user_id,
                    admin_id=admin_membership.user_id,
                    group_id=attr.group_id,
                ).first()

                if not existing_rating:
                    admin_rating = AdminPlayerRating(
                        user_id=attr.user_id,
                        admin_id=admin_membership.user_id,
                        group_id=attr.group_id,
                        pace=int(attr.pace),
                        stamina=int(attr.stamina),
                        strength=int(attr.strength),
                        agility=int(attr.agility),
                        jumping=int(attr.jumping),
                        ball_control=int(attr.ball_control),
                        dribbling=int(attr.dribbling),
                        passing=int(attr.passing),
                        shooting=int(attr.shooting),
                        crossing=int(attr.crossing),
                        free_kicks=int(attr.free_kicks),
                        positioning=int(attr.positioning),
                        marking=int(attr.marking),
                        tackling=int(attr.tackling),
                        interceptions=int(attr.interceptions),
                        vision=int(attr.vision),
                        decision_making=int(attr.decision_making),
                        composure=int(attr.composure),
                        concentration=int(attr.concentration),
                        determination=int(attr.determination),
                        leadership=int(attr.leadership),
                        teamwork=int(attr.teamwork),
                        goalkeeping=int(attr.goalkeeping),
                        handling=int(attr.handling),
                        distribution=int(attr.distribution),
                        aerial_reach=int(attr.aerial_reach),
                        preferred_position=attr.preferred_position,
                        notes=attr.notes,
                    )
                    db.session.add(admin_rating)
                    print(
                        f"    Created admin rating for admin {admin_membership.user_id}"
                    )

            PlayerAttributes.calculate_and_update(attr.user_id, attr.group_id)
            print(f"    Recalculated averaged attributes")

        if dry_run:
            print("DRY RUN: Rolling back changes")
            db.session.rollback()
        else:
            db.session.commit()
        print("Migration completed successfully!")


if __name__ == "__main__":
    import sys
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        print("Running in DRY RUN mode - no changes will be saved")
    migrate_existing_attributes(dry_run)
