# backend/test_db.py
"""
Database Connection Test Script
Run this to verify your database connection is working properly
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError
import pymysql

# Load environment variables
load_dotenv()

def test_mysql_connection():
    """Test MySQL connection using pymysql"""
    print("\n" + "=" * 60)
    print("🔍 Testing MySQL Connection with PyMySQL")
    print("=" * 60)
    
    try:
        # Get database URL from environment
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not found in .env file")
            return False
        
        print(f"📡 Database URL: {database_url.replace('://', '://***:***@')}")
        
        # Parse connection details from URL
        # Format: mysql+pymysql://username:password@host/database
        import re
        match = re.search(r'mysql\+pymysql://([^:]+):([^@]+)@([^/]+)/(.+)', database_url)
        
        if not match:
            print("❌ Invalid DATABASE_URL format")
            print("   Expected: mysql+pymysql://username:password@host/database")
            return False
        
        username, password, host, database = match.groups()
        
        print(f"📊 Host: {host}")
        print(f"📊 Database: {database}")
        print(f"📊 Username: {username}")
        print(f"📊 Password: {'*' * len(password)}")
        
        # Test connection with pymysql
        print("\n🔄 Connecting to MySQL...")
        connection = pymysql.connect(
            host=host,
            user=username,
            password=password,
            database=database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        
        print("✅ Connection successful!")
        
        # Test query
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION() as version")
            result = cursor.fetchone()
            print(f"📊 MySQL Version: {result['version']}")
            
            cursor.execute("SELECT DATABASE() as current_db")
            result = cursor.fetchone()
            print(f"📊 Current Database: {result['current_db']}")
            
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            print(f"📊 Tables Found: {len(tables)}")
            if tables:
                print("   Tables:")
                for table in tables:
                    table_name = list(table.values())[0]
                    print(f"   - {table_name}")
            else:
                print("   ⚠️  No tables found. Run migrations first.")
        
        connection.close()
        print("\n✅ MySQL connection test passed!")
        return True
        
    except pymysql.err.OperationalError as e:
        print(f"\n❌ Operational Error: {e}")
        print("\nPossible issues:")
        print("   - MySQL server is not running")
        print("   - Wrong host or port")
        print("   - Wrong username or password")
        return False
    except pymysql.err.ProgrammingError as e:
        print(f"\n❌ Programming Error: {e}")
        print("\nPossible issues:")
        print("   - Database does not exist")
        print("   - Wrong database name")
        print("   - Insufficient permissions")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        return False

def test_sqlalchemy_connection():
    """Test database connection using SQLAlchemy"""
    print("\n" + "=" * 60)
    print("🔍 Testing Database Connection with SQLAlchemy")
    print("=" * 60)
    
    try:
        database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not found in .env file")
            return False
        
        print(f"📡 Connecting to: {database_url.replace('://', '://***:***@')}")
        
        # Create engine
        engine = create_engine(database_url, echo=False)
        
        # Test connection
        with engine.connect() as connection:
            print("✅ Connection successful!")
            
            # Test query
            result = connection.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            print(f"📊 Test Query Result: {row[0]}")
            
            # Get MySQL version
            result = connection.execute(text("SELECT VERSION() as version"))
            row = result.fetchone()
            print(f"📊 MySQL Version: {row[0]}")
            
            # Get database name
            result = connection.execute(text("SELECT DATABASE() as db"))
            row = result.fetchone()
            print(f"📊 Database: {row[0]}")
            
            # List tables
            result = connection.execute(text("SHOW TABLES"))
            tables = result.fetchall()
            print(f"📊 Tables Found: {len(tables)}")
            if tables:
                print("   Tables:")
                for table in tables:
                    print(f"   - {table[0]}")
            else:
                print("   ⚠️  No tables found. Run migrations first.")
        
        print("\n✅ SQLAlchemy connection test passed!")
        return True
        
    except OperationalError as e:
        print(f"\n❌ Operational Error: {e}")
        print("\nPossible issues:")
        print("   - MySQL server is not running")
        print("   - Wrong host or port")
        print("   - Wrong username or password")
        print("   - Database does not exist")
        return False
    except ProgrammingError as e:
        print(f"\n❌ Programming Error: {e}")
        print("\nPossible issues:")
        print("   - Database does not exist")
        print("   - Wrong database name")
        print("   - Insufficient permissions")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        return False

def test_flask_db_connection():
    """Test database connection using Flask app context"""
    print("\n" + "=" * 60)
    print("🔍 Testing Database Connection with Flask-SQLAlchemy")
    print("=" * 60)
    
    try:
        from app import create_app
        from extensions import db
        
        app = create_app()
        
        with app.app_context():
            print("🔄 Testing Flask-SQLAlchemy connection...")
            
            # Test connection
            result = db.session.execute(text("SELECT 1 as test"))
            row = result.fetchone()
            print(f"✅ Connection successful! Test result: {row[0]}")
            
            # Test query
            result = db.session.execute(text("SELECT VERSION() as version"))
            row = result.fetchone()
            print(f"📊 MySQL Version: {row[0]}")
            
            # Test database name
            result = db.session.execute(text("SELECT DATABASE() as db"))
            row = result.fetchone()
            print(f"📊 Database: {row[0]}")
            
            # List tables
            result = db.session.execute(text("SHOW TABLES"))
            tables = result.fetchall()
            print(f"📊 Tables Found: {len(tables)}")
            if tables:
                print("   Tables:")
                for table in tables:
                    print(f"   - {table[0]}")
            else:
                print("   ⚠️  No tables found. Run migrations first.")
            
            # Test user table if it exists
            if 'users' in [t[0] for t in tables]:
                result = db.session.execute(text("SELECT COUNT(*) FROM users"))
                count = result.fetchone()[0]
                print(f"📊 Users Count: {count}")
        
        print("\n✅ Flask-SQLAlchemy connection test passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

def check_table_schema():
    """Check if all required tables exist"""
    print("\n" + "=" * 60)
    print("🔍 Checking Database Schema")
    print("=" * 60)
    
    required_tables = [
        'users',
        'messages',
        'message_status',
        'message_reactions',
        'friends',
        'friend_requests',
        'blocked_users',
        'groups',
        'group_members',
        'files',
        'voice_notes',
        'message_attachments',
        'notifications',
        'user_sessions',
        'login_history',
        'audit_logs',
        'archived_chats',
        'pinned_chats',
        'user_devices',
        'typing_indicators'
    ]
    
    try:
        from app import create_app
        from extensions import db
        
        app = create_app()
        
        with app.app_context():
            result = db.session.execute(text("SHOW TABLES"))
            existing_tables = [t[0] for t in result.fetchall()]
            
            print("\n📊 Schema Check:")
            missing_tables = []
            for table in required_tables:
                if table in existing_tables:
                    print(f"   ✅ {table}")
                else:
                    print(f"   ❌ {table} - MISSING")
                    missing_tables.append(table)
            
            if missing_tables:
                print(f"\n⚠️  Missing {len(missing_tables)} tables")
                print("   Run migrations: flask db upgrade")
            else:
                print("\n✅ All required tables exist!")
            
            return len(missing_tables) == 0
            
    except Exception as e:
        print(f"\n❌ Error checking schema: {e}")
        return False

def run_all_tests():
    """Run all database connection tests"""
    print("\n" + "=" * 60)
    print("🔐 Secure Chat Application - Database Connection Test")
    print("=" * 60)
    
    results = {
        'mysql_pymysql': False,
        'sqlalchemy': False,
        'flask_db': False,
        'schema': False
    }
    
    # Test 1: PyMySQL connection
    results['mysql_pymysql'] = test_mysql_connection()
    
    # Test 2: SQLAlchemy connection
    results['sqlalchemy'] = test_sqlalchemy_connection()
    
    # Test 3: Flask-SQLAlchemy connection
    results['flask_db'] = test_flask_db_connection()
    
    # Test 4: Check schema
    results['schema'] = check_table_schema()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    for test, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"   {test.replace('_', ' ').title()}: {status}")
    
    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All tests passed! Database connection is working properly.")
    else:
        print("\n⚠️  Some tests failed. Please check the errors above.")
    
    return all_passed

if __name__ == '__main__':
    run_all_tests()