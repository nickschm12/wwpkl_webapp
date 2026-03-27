"""
Create the rights_player_details table.

Usage:
    PROJECT_ID=484894850064 DB_SECRET_ID=wwpkl_db DB_SECRET_VERSION=2 \
    venv/bin/python scripts/migrate_add_rights.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from packages.database import connections
from packages.database.models import Base, RightsPlayerDetails

if os.environ.get('DB_HOST'):
    engine = connections.tcp_connection()
else:
    engine = connections.unix_connection()

Base.metadata.create_all(engine, tables=[RightsPlayerDetails.__table__])
print('Created rights_player_details table.')
