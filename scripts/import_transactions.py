"""One-time script to import transactions from Google Sheet into the DB."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy.orm import sessionmaker

from packages.database import connections
from packages.database.models import Base, Transaction
from packages.database.queries import insert_transaction
from packages.sheets import fetch_transactions


def main():
    if os.environ.get('DB_HOST'):
        engine = connections.tcp_connection()
    else:
        engine = connections.unix_connection()

    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    deleted = session.query(Transaction).delete()
    session.commit()
    print(f'Cleared {deleted} existing transactions')

    all_sections = fetch_transactions()
    total = 0
    for section in all_sections:
        for txn in section['transactions']:
            if txn.get('parsed_date') is None:
                print(f'  SKIP (no date): {txn["raw"][:80]}')
                continue
            txn_date = txn['parsed_date'].date()
            year = str(txn_date.year)
            insert_transaction(
                session,
                date=txn_date,
                year=year,
                party_a=txn.get('party_a'),
                party_b=txn.get('party_b'),
                a_sends=txn.get('a_sends'),
                b_sends=txn.get('b_sends'),
                is_preseason=txn.get('is_preseason', False),
                a_dollars=txn.get('a_dollars', 0),
                b_dollars=txn.get('b_dollars', 0),
                a_keeper_spots=txn.get('a_keeper_spots', 0),
                b_keeper_spots=txn.get('b_keeper_spots', 0),
                raw=txn.get('raw', ''),
            )
            total += 1
    print(f'Imported {total} transactions')
    session.close()


if __name__ == '__main__':
    main()
