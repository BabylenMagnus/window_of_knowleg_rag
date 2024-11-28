import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import string
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def serialize_db_result(result):
    if not result:
        return None
    serialized = {}
    for key, value in result.items():
        serialized[key] = serialize_datetime(value)
    return serialized


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB", "jiraiya"), user=os.getenv("POSTGRES_USER", "jiraiya"),
        password=os.getenv("POSTGRES_PASSWORD", "password"), host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "8012"), cursor_factory=RealDictCursor
    )


def generate_valid_nickname(name: str) -> str:
    # Создаем базовый nickname из имени, оставляя только допустимые символы
    base = ''.join(c if c.isalnum() or c in '-_' else '' for c in name.lower())

    # Если базовый nickname пустой, используем 'storage'
    if not base:
        base = 'storage'

    # Добавляем случайный суффикс
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

    # Убеждаемся, что nickname начинается с буквы
    if not base[0].isalpha():
        base = 'n' + base

    # Формируем финальный nickname
    nickname = f"{base}-{random_suffix}"

    # Обрезаем до 63 символов если нужно
    if len(nickname) > 63:
        nickname = nickname[:56] + '-' + random_suffix

    return nickname


def create_storage(name: str, description: str = None):
    conn = get_db_connection()
    try:
        nickname = generate_valid_nickname(name)
        logger.info(f"Generated nickname: {nickname}")
        with conn.cursor() as cur:
            query = """
                INSERT INTO storages (name, description, nickname)
                VALUES (%s, %s, %s)
                RETURNING id, name, description, nickname, created_at, updated_at;
                """
            logger.info(f"Executing query: {query} with params: {(name, description, nickname)}")
            cur.execute(query, (name, description, nickname))
            result = cur.fetchone()
            logger.info(f"Query result: {result}")
            conn.commit()
            serialized = serialize_db_result(result)
            logger.info(f"Serialized result: {serialized}")
            return serialized
    except Exception as e:
        conn.rollback()
        logger.error(f"Error in create_storage: {str(e)}")
        raise e
    finally:
        conn.close()


def list_storages():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, nickname, created_at, updated_at
                FROM storages
                ORDER BY created_at DESC;
                """
            )
            results = cur.fetchall()
            return [serialize_db_result(row) for row in results]
    finally:
        conn.close()


def check_storage_nickname_exists(nickname: str) -> bool:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS(SELECT 1 FROM storages WHERE nickname = %s);
                """, (nickname,)
            )
            return cur.fetchone()['exists']
    finally:
        conn.close()


def check_existing_records():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, description, nickname, created_at, updated_at
                FROM storages
                ORDER BY id;
                """
            )
            results = cur.fetchall()
            for row in results:
                logger.info(f"Existing record: {dict(row)}")
            return [serialize_db_result(row) for row in results]
    finally:
        conn.close()


def get_chats():
    """
    Retrieve all chats, ordered by most recently updated.
    
    Returns:
        List of chat records
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM chats ORDER BY updated_at DESC")
            chats = cur.fetchall()
        return [serialize_db_result(chat) for chat in chats]
    finally:
        conn.close()


def create_chat(name: str, model_id: int = None):
    """
    Create a new chat.
    
    Args:
        name (str): Name of the chat
        model_id (int, optional): ID of the model used for the chat. 
                                  If not provided, use the dummy model.
    
    Returns:
        Dict representing the newly created chat
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # If no model_id is provided, use the dummy model
            if model_id is None:
                dummy_model = ensure_dummy_model()
                model_id = dummy_model['id']
            
            # Create the chat
            cur.execute(
                "INSERT INTO chats (name, model_id) VALUES (%s, %s) RETURNING *", 
                (name, model_id)
            )
            new_chat = cur.fetchone()
            conn.commit()
        return serialize_db_result(new_chat)
    finally:
        conn.close()


def get_chat_history(chat_id: int):
    """
    Retrieve chat history for a specific chat.
    
    Args:
        chat_id (int): ID of the chat to retrieve history for
    
    Returns:
        List of chat history records
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM chat_history WHERE chat_id = %s ORDER BY created_at", 
                (chat_id,)
            )
            history = cur.fetchall()
        return [serialize_db_result(record) for record in history]
    finally:
        conn.close()


def list_models():
    """
    Retrieve all available models.
    
    Returns:
        List of model records
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM models ORDER BY created_at DESC")
            models = cur.fetchall()
        return [serialize_db_result(model) for model in models]
    finally:
        conn.close()


def ensure_dummy_model():
    """
    Ensure a dummy model exists in the models table.
    If no model with ID 1 exists, create a default dummy model.
    
    Returns:
        Dict representing the dummy model
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Check if model with ID 1 exists
            cur.execute("SELECT * FROM models WHERE id = 1")
            existing_model = cur.fetchone()
            
            if existing_model:
                return serialize_db_result(existing_model)
            
            # Create dummy model with ID 1
            cur.execute("""
                INSERT INTO models (
                    id, name, model_path, type, context_window
                ) VALUES (
                    1, 
                    'Dummy Model', 
                    '/dev/null', 
                    'service', 
                    2048
                ) 
                ON CONFLICT (id) DO NOTHING 
                RETURNING *
            """)
            
            # Fetch the inserted or existing model
            cur.execute("SELECT * FROM models WHERE id = 1")
            dummy_model = cur.fetchone()
            
            conn.commit()
            return serialize_db_result(dummy_model)
    finally:
        conn.close()


def create_chat_history(chat_id: int, text: str, author: str):
    """
    Create a new chat history entry.
    
    Args:
        chat_id (int): ID of the chat
        text (str): Text of the chat history entry
        author (str): Author of the message ('user' or 'model')
    
    Returns:
        Dict representing the newly created chat history entry
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Validate that the chat exists
            cur.execute("SELECT id FROM chats WHERE id = %s", (chat_id,))
            if not cur.fetchone():
                raise ValueError(f"Chat with ID {chat_id} does not exist")
            
            # Insert the chat history entry
            cur.execute(
                """
                INSERT INTO chat_history (chat_id, text, author) 
                VALUES (%s, %s, %s) 
                RETURNING *
                """, 
                (chat_id, text, author)
            )
            new_history_entry = cur.fetchone()
            conn.commit()
        return serialize_db_result(new_history_entry)
    finally:
        conn.close()
