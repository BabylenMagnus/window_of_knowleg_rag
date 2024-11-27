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
