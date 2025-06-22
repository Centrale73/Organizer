from agno.storage.agent.sqlite import SqliteAgentStorage
import os
import sqlite3
import datetime
from pathlib import Path

def load_session_storage():
    """Load appropriate storage based on environment"""
    storage_path = os.getenv("AGENT_STORAGE_PATH", "business_agent.db")
    return SqliteAgentStorage(
        table_name="client_sessions",
        db_file=storage_path
    )

def load_personality_storage():
    """Separate storage for personality analysis"""
    storage_path = os.getenv("PERSONALITY_STORAGE_PATH", "personality_data.db")
    return SqliteAgentStorage(
        table_name="personality_sessions",
        db_file=storage_path
    )

def load_task_storage():
    """Separate storage for task extraction"""
    storage_path = os.getenv("TASK_STORAGE_PATH", "task_data.db")
    return SqliteAgentStorage(
        table_name="task_sessions",
        db_file=storage_path
    )

def load_document_storage():
    """Separate storage for document analysis and categorization"""
    storage_path = os.getenv("DOCUMENT_STORAGE_PATH", "document_analysis.db")
    return SqliteAgentStorage(
        table_name="document_sessions",
        db_file=storage_path
    )

# Compatibility aliases for the document organizer app
# These match the naming convention expected by the main application
def loadsessionstorage():
    """Compatibility alias for load_session_storage"""
    try:
        return load_session_storage()
    except Exception as e:
        print(f"Warning: Failed to load session storage: {e}")
        return None

def loadpersonalitystorage():
    """Compatibility alias for load_personality_storage"""
    try:
        return load_personality_storage()
    except Exception as e:
        print(f"Warning: Failed to load personality storage: {e}")
        return None

def loadtaskstorage():
    """Compatibility alias for load_task_storage"""
    try:
        return load_task_storage()
    except Exception as e:
        print(f"Warning: Failed to load task storage: {e}")
        return None

def loaddocumentstorage():
    """Compatibility alias for load_document_storage"""
    try:
        return load_document_storage()
    except Exception as e:
        print(f"Warning: Failed to load document storage: {e}")
        return None

# Additional specialized storage functions for document organizer features
def load_chat_storage():
    """Separate storage for chat sessions in document organizer"""
    storage_path = os.getenv("CHAT_STORAGE_PATH", "document_chat.db")
    return SqliteAgentStorage(
        table_name="chat_sessions",
        db_file=storage_path
    )

def load_categorization_storage():
    """Storage for categorization history and learning"""
    storage_path = os.getenv("CATEGORIZATION_STORAGE_PATH", "categorization_data.db")
    return SqliteAgentStorage(
        table_name="categorization_sessions",
        db_file=storage_path
    )

def load_organization_storage():
    """Storage for file organization patterns and history"""
    storage_path = os.getenv("ORGANIZATION_STORAGE_PATH", "organization_data.db")
    return SqliteAgentStorage(
        table_name="organization_sessions",
        db_file=storage_path
    )

def load_confidence_tracking_storage():
    """Storage for tracking categorization confidence and accuracy"""
    storage_path = os.getenv("CONFIDENCE_STORAGE_PATH", "confidence_tracking.db")
    return SqliteAgentStorage(
        table_name="confidence_sessions",
        db_file=storage_path
    )

# Enhanced storage configuration for business automation
def get_storage_config():
    """Get complete storage configuration for the business automation system"""
    try:
        return {
            'session': load_session_storage(),
            'personality': load_personality_storage(),
            'tasks': load_task_storage(),
            'documents': load_document_storage(),
            'chat': load_chat_storage(),
            'categorization': load_categorization_storage(),
            'organization': load_organization_storage(),
            'confidence': load_confidence_tracking_storage()
        }
    except Exception as e:
        print(f"Error loading storage configuration: {e}")
        return {}

def initialize_all_storage():
    """Initialize all storage databases with proper tables"""
    try:
        # Create storage directory if it doesn't exist
        storage_dir = Path("storage_data")
        storage_dir.mkdir(exist_ok=True)
        
        # Initialize each storage to ensure tables are created
        storages = {
            'session': load_session_storage(),
            'personality': load_personality_storage(),
            'tasks': load_task_storage(),
            'documents': load_document_storage(),
            'chat': load_chat_storage(),
            'categorization': load_categorization_storage(),
            'organization': load_organization_storage(),
            'confidence': load_confidence_tracking_storage()
        }
        
        initialized_count = 0
        for name, storage in storages.items():
            if storage is not None:
                initialized_count += 1
                print(f"   ✅ {name.capitalize()}: {storage.db_file}")
            else:
                print(f"   ❌ {name.capitalize()}: Failed to initialize")
        
        print(f"✅ {initialized_count}/{len(storages)} storage databases initialized successfully")
        return storages
        
    except Exception as e:
        print(f"❌ Error initializing storage: {str(e)}")
        return None

def verify_storage_health():
    """Verify that all storage databases are accessible and working"""
    try:
        storages = get_storage_config()
        healthy_count = 0
        
        for name, storage in storages.items():
            try:
                if storage and hasattr(storage, 'db_file'):
                    # Try to access the database
                    with sqlite3.connect(storage.db_file) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                        tables = cursor.fetchall()
                        if tables:
                            healthy_count += 1
                            print(f"   ✅ {name.capitalize()}: Healthy ({len(tables)} tables)")
                        else:
                            print(f"   ⚠️  {name.capitalize()}: Empty database")
                else:
                    print(f"   ❌ {name.capitalize()}: Storage not available")
            except Exception as e:
                print(f"   ❌ {name.capitalize()}: Error - {str(e)}")
        
        print(f"Storage health check: {healthy_count}/{len(storages)} databases healthy")
        return healthy_count == len(storages)
        
    except Exception as e:
        print(f"Error during storage health check: {e}")
        return False

def create_document_organization_tables():
    """Create custom tables for enhanced document organization tracking"""
    try:
        # Document processing history table
        doc_storage_path = os.getenv("DOCUMENT_STORAGE_PATH", "document_analysis.db")
        
        with sqlite3.connect(doc_storage_path) as conn:
            cursor = conn.cursor()
            
            # Document processing history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS document_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    category TEXT,
                    confidence INTEGER,
                    subcategory TEXT,
                    word_count INTEGER,
                    processing_time REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    organized_at TIMESTAMP,
                    status TEXT DEFAULT 'pending'
                )
            """)
            
            # Categorization accuracy tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS categorization_accuracy (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER,
                    original_category TEXT,
                    predicted_category TEXT,
                    confidence_score INTEGER,
                    user_correction TEXT,
                    accuracy_rating INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES document_history (id)
                )
            """)
            
            # Organization patterns
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS organization_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_folder TEXT,
                    target_folder TEXT,
                    category_structure TEXT,
                    success_rate REAL,
                    documents_processed INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            print("✅ Custom document organization tables created successfully")
            return True
            
    except Exception as e:
        print(f"❌ Error creating document organization tables: {e}")
        return False

def cleanup_storage(days_old=30):
    """Clean up old storage entries older than specified days"""
    try:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_old)
        storages = get_storage_config()
        cleaned_count = 0
        
        for name, storage in storages.items():
            if storage and hasattr(storage, 'db_file'):
                try:
                    with sqlite3.connect(storage.db_file) as conn:
                        cursor = conn.cursor()
                        
                        # Clean up old sessions (if timestamp column exists)
                        cursor.execute("""
                            DELETE FROM {} 
                            WHERE created_at < ? OR updated_at < ?
                        """.format(storage.table_name), (cutoff_date, cutoff_date))
                        
                        deleted_rows = cursor.rowcount
                        cleaned_count += deleted_rows
                        
                        if deleted_rows > 0:
                            print(f"Cleaned {deleted_rows} old entries from {name} storage")
                        
                        conn.commit()
                        
                except sqlite3.OperationalError:
                    # Table might not have timestamp columns, skip
                    print(f"Skipping cleanup for {name} storage (no timestamp columns)")
                    continue
                except Exception as e:
                    print(f"Error cleaning {name} storage: {e}")
                    continue
        
        print(f"✅ Storage cleanup completed. Removed {cleaned_count} old entries.")
        return cleaned_count
        
    except Exception as e:
        print(f"❌ Error during storage cleanup: {str(e)}")
        return 0

def backup_storage(backup_dir="backups"):
    """Create backups of all storage databases"""
    try:
        import shutil
        from datetime import datetime
        
        # Create backup directory
        backup_path = Path(backup_dir)
        backup_path.mkdir(exist_ok=True)
        
        # Create timestamped backup folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_folder = backup_path / f"storage_backup_{timestamp}"
        backup_folder.mkdir(exist_ok=True)
        
        storages = get_storage_config()
        backed_up_count = 0
        
        for name, storage in storages.items():
            if storage and hasattr(storage, 'db_file'):
                try:
                    source_file = Path(storage.db_file)
                    if source_file.exists():
                        backup_file = backup_folder / f"{name}_{source_file.name}"
                        shutil.copy2(source_file, backup_file)
                        backed_up_count += 1
                        print(f"   ✅ Backed up {name}: {backup_file}")
                except Exception as e:
                    print(f"   ❌ Failed to backup {name}: {e}")
        
        print(f"✅ Storage backup completed: {backed_up_count} databases backed up to {backup_folder}")
        return str(backup_folder)
        
    except Exception as e:
        print(f"❌ Error during storage backup: {e}")
        return None

# Initialize storage on import for document organizer
if __name__ == "__main__":
    print("Initializing storage systems...")
    initialize_all_storage()
    create_document_organization_tables()
    verify_storage_health()
    print("Storage initialization complete.")
