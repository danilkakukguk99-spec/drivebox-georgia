"""SQLite-consistent backup. Store copies on a separate private volume."""
import sqlite3,sys
from server.store import connect
if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('Usage: python -m server.backup /private/backup/orders.sqlite3')
    with connect() as source, sqlite3.connect(sys.argv[1]) as target: source.backup(target)
