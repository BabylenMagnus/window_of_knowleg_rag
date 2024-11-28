import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import string
import logging
import json

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


def get_last_n_messages(chat_id: int, n: int = 5):
    """
    Get the last N messages from a chat's history.
    
    Args:
        chat_id (int): ID of the chat
        n (int): Number of messages to retrieve (default: 5)
    
    Returns:
        List of chat history records, ordered from oldest to newest
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM chat_history 
                WHERE chat_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
                """, 
                (chat_id, n)
            )
            messages = cur.fetchall()
            # Reverse the messages to get them in chronological order
            messages.reverse()
        return [serialize_db_result(msg) for msg in messages]
    finally:
        conn.close()


def update_storage(storage_id: int, name: str, description: str = None):
    """
    Update storage name and description
    
    Args:
        storage_id (int): ID of storage to update
        name (str): New name for storage
        description (str, optional): New description for storage
    
    Returns:
        Dict with updated storage information
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if description is not None:
                cur.execute(
                    """
                    UPDATE storages 
                    SET name = %s, description = %s, updated_at = NOW() 
                    WHERE id = %s 
                    RETURNING *
                    """,
                    (name, description, storage_id)
                )
            else:
                cur.execute(
                    """
                    UPDATE storages 
                    SET name = %s, updated_at = NOW() 
                    WHERE id = %s 
                    RETURNING *
                    """,
                    (name, storage_id)
                )
            updated_storage = cur.fetchone()
            if not updated_storage:
                raise ValueError(f"Storage with ID {storage_id} not found")
            conn.commit()
            return serialize_db_result(updated_storage)
    finally:
        conn.close()


def get_storage_files(storage_id: int):
    """
    Получить список файлов для указанного хранилища
    
    Args:
        storage_id (int): ID хранилища
    
    Returns:
        list: Список файлов в хранилище
    """
    import logging
    import traceback
    from datetime import datetime
    from psycopg2.extras import RealDictCursor

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    def serialize_datetime(obj):
        """
        Преобразует объекты datetime в строки ISO формата
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Проверяем существование хранилища
            cursor.execute("SELECT * FROM storages WHERE id = %s", (storage_id,))
            storage = cursor.fetchone()
            
            if not storage:
                logger.error(f"Storage with ID {storage_id} not found")
                raise ValueError(f"Хранилище с ID {storage_id} не найдено")
            
            # Получаем список файлов для хранилища
            cursor.execute(
                """
                SELECT 
                    id, name, local_path, type, source, 
                    created_at, updated_at
                FROM files 
                WHERE storage_id = %s
                ORDER BY created_at DESC
                """, 
                (storage_id,)
            )
            files = cursor.fetchall()
            
            # Преобразуем datetime в строки
            serialized_files = [
                {k: serialize_datetime(v) for k, v in file.items()} 
                for file in files
            ]
            
            logger.info(f"Retrieved {len(serialized_files)} files for storage {storage_id}")
            
            return serialized_files
    except Exception as e:
        logger.error(f"Error retrieving files for storage {storage_id}: {e}")
        logger.error(traceback.format_exc())
        
        raise ValueError(f"Не удалось получить файлы хранилища: {str(e)}")
    finally:
        conn.close()


def get_file_details(storage_id: int, file_id: int):
    """
    Get detailed information about a specific file
    
    Args:
        storage_id (int): ID of storage
        file_id (int): ID of file
    
    Returns:
        Dict with file information including metadata
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.*, m.metadata 
                FROM files f 
                JOIN storage_files sf ON f.id = sf.file_id
                LEFT JOIN file_metadata m ON f.id = m.file_id 
                WHERE sf.storage_id = %s AND f.id = %s
                """,
                (storage_id, file_id)
            )
            file = cur.fetchone()
            if not file:
                raise ValueError(f"File with ID {file_id} not found in storage {storage_id}")
            return serialize_db_result(file)
    finally:
        conn.close()


def save_file(storage_id: int, filename: str, local_path: str, file_type: str, source: str = None, description: str = None):
    """
    Save file information to database
    
    Args:
        storage_id (int): ID of storage
        filename (str): Original filename
        local_path (str): Path where file is stored locally
        file_type (str): Type of file (pdf, image, etc)
        source (str, optional): Source of file (upload, url)
        description (str, optional): File description
    
    Returns:
        Dict with created file information
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verify storage exists
            cur.execute("SELECT id FROM storages WHERE id = %s", (storage_id,))
            if not cur.fetchone():
                raise ValueError(f"Storage with ID {storage_id} not found")
            
            # Create file record
            cur.execute(
                """
                INSERT INTO files (name, local_path, type, source)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (filename, local_path, file_type, source)
            )
            file = cur.fetchone()
            file_id = file[0]  # Get the ID of created file
            
            # Link file to storage
            cur.execute(
                """
                INSERT INTO storage_files (storage_id, file_id)
                VALUES (%s, %s)
                """,
                (storage_id, file_id)
            )
            
            # Add metadata if description provided
            if description:
                cur.execute(
                    """
                    INSERT INTO file_metadata (file_id, metadata)
                    VALUES (%s, %s::jsonb)
                    """,
                    (file_id, json.dumps({"description": description}))
                )
            
            conn.commit()
            return serialize_db_result(file)
    finally:
        conn.close()


def get_storage_by_id(storage_id: int):
    """
    Получить информацию о хранилище по его ID
    
    Args:
        storage_id (int): ID хранилища
    
    Returns:
        dict: Информация о хранилище
    """
    import logging
    import traceback
    from psycopg2.extras import RealDictCursor

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    conn = get_db_connection()
    try:
        # Используем RealDictCursor для словарного доступа
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Получаем информацию о хранилище
            cursor.execute("SELECT * FROM storages WHERE id = %s", (storage_id,))
            storage = cursor.fetchone()
            
            if not storage:
                logger.error(f"Storage with ID {storage_id} not found")
                raise ValueError(f"Хранилище с ID {storage_id} не найдено")
            
            return dict(storage)
    except Exception as e:
        logger.error(f"Ошибка при получении хранилища: {e}")
        logger.error(traceback.format_exc())
        
        raise ValueError(f"Ошибка при получении хранилища: {str(e)}")
    finally:
        conn.close()


def add_url_to_storage_collection(storage_id: int, url: str):
    """
    Добавить URL в хранилище
    
    Args:
        storage_id (int): ID хранилища
        url (str): URL для добавления
    
    Returns:
        dict: Информация о добавленном URL
    """
    import traceback
    import logging
    from datetime import datetime
    from psycopg2.extras import RealDictCursor

    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    def serialize_datetime(obj):
        """
        Преобразует объекты datetime в строки ISO формата
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Проверяем существование хранилища
            logger.info(f"Checking storage with ID: {storage_id}")
            cursor.execute("SELECT * FROM storages WHERE id = %s", (storage_id,))
            storage = cursor.fetchone()
            
            if not storage:
                logger.error(f"Storage with ID {storage_id} not found")
                raise ValueError(f"Хранилище с ID {storage_id} не найдено")
            
            logger.info(f"Adding URL: {url} to storage")
            
            # Создаем файл для URL с указанием storage_id
            cursor.execute(
                """
                INSERT INTO files 
                (name, local_path, type, source, storage_id) 
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, local_path, type, source, storage_id, created_at, updated_at
                """, 
                (url, url, 'link', 'url', storage_id)
            )
            file_info = cursor.fetchone()
            
            # Преобразуем datetime в строки
            serialized_file_info = {
                k: serialize_datetime(v) for k, v in file_info.items()
            }
            
            conn.commit()
            logger.info(f"Successfully added URL file with ID: {serialized_file_info['id']}")
            
            return serialized_file_info
    except Exception as e:
        conn.rollback()
        logger.error(f"Error in add_url_to_storage_collection: {e}")
        logger.error(traceback.format_exc())
        
        raise ValueError(f"Не удалось добавить URL: {str(e)}")
    finally:
        conn.close()


def delete_storage_file(storage_id: int, file_id: int):
    """
    Delete file from storage
    
    Args:
        storage_id (int): ID of storage
        file_id (int): ID of file
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verify file exists in storage
            cur.execute(
                """
                SELECT f.id, f.local_path 
                FROM files f
                JOIN storage_files sf ON f.id = sf.file_id
                WHERE sf.storage_id = %s AND f.id = %s
                """,
                (storage_id, file_id)
            )
            file = cur.fetchone()
            if not file:
                raise ValueError(f"File with ID {file_id} not found in storage {storage_id}")
            
            # Delete file from storage_files (cascades to file_metadata)
            cur.execute(
                "DELETE FROM storage_files WHERE storage_id = %s AND file_id = %s",
                (storage_id, file_id)
            )
            
            # Delete file record (will cascade delete metadata)
            cur.execute("DELETE FROM files WHERE id = %s", (file_id,))
            conn.commit()
            
            # Return local path for physical file deletion
            return file[1]
    finally:
        conn.close()


def update_file_info(storage_id: int, file_id: int, metadata: dict):
    """
    Update file metadata
    
    Args:
        storage_id (int): ID of storage
        file_id (int): ID of file
        metadata (dict): New metadata values
    
    Returns:
        Dict with updated file information
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verify file exists in storage
            cur.execute(
                """
                SELECT f.id 
                FROM files f
                JOIN storage_files sf ON f.id = sf.file_id
                WHERE sf.storage_id = %s AND f.id = %s
                """,
                (storage_id, file_id)
            )
            if not cur.fetchone():
                raise ValueError(f"File with ID {file_id} not found in storage {storage_id}")
            
            # Update file name if provided
            if "name" in metadata:
                cur.execute(
                    """
                    UPDATE files 
                    SET name = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (metadata["name"], file_id)
                )
            
            # Update or insert metadata
            cur.execute(
                """
                INSERT INTO file_metadata (file_id, metadata)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (file_id) DO UPDATE
                SET metadata = file_metadata.metadata || EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING *
                """,
                (file_id, json.dumps(metadata))
            )
            
            # Get updated file info
            cur.execute(
                """
                SELECT f.*, m.metadata 
                FROM files f
                LEFT JOIN file_metadata m ON f.id = m.file_id
                WHERE f.id = %s
                """,
                (file_id,)
            )
            file = cur.fetchone()
            conn.commit()
            return serialize_db_result(file)
    finally:
        conn.close()
