#!/usr/bin/env python3
import argparse
import psycopg2
import sys
import time

def wait_for_db(host, port, user, password, timeout):
    """Wait for PostgreSQL to become available"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # Try to connect to the database
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname='postgres'  # Connect to default postgres db
            )
            conn.close()
            print(f"✅ PostgreSQL is ready! Connected to {host}:{port}")
            return True
        except psycopg2.OperationalError as e:
            print(f"⏳ Waiting for PostgreSQL at {host}:{port}... ({e})")
            time.sleep(2)
    
    print(f"❌ Timeout waiting for PostgreSQL at {host}:{port}")
    return False

def main():
    parser = argparse.ArgumentParser(description='Wait for PostgreSQL to become available')
    parser.add_argument('--db_host', required=True, help='Database host')
    parser.add_argument('--db_port', type=int, default=5432, help='Database port')
    parser.add_argument('--db_user', required=True, help='Database user')
    parser.add_argument('--db_password', required=True, help='Database password')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds')
    
    args = parser.parse_args()
    
    print(f"🔄 Waiting for PostgreSQL at {args.db_host}:{args.db_port}...")
    
    if wait_for_db(args.db_host, args.db_port, args.db_user, args.db_password, args.timeout):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()