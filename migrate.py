#!/usr/bin/env python3
"""
Скрипт для ручного запуска миграций базы данных
Использование: python migrate.py
"""

import subprocess
import sys
import os
from dotenv import load_dotenv

def run_migrations():
    """Запускает миграции Alembic"""
    load_dotenv()
    
    try:
        print("🔄 Запуск миграций базы данных...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        print("✅ Миграции выполнены успешно!")
        if result.stdout:
            print("Вывод:")
            print(result.stdout)
            
    except subprocess.CalledProcessError as e:
        print("❌ Ошибка при выполнении миграций:")
        print(f"Код возврата: {e.returncode}")
        if e.stderr:
            print(f"Ошибка: {e.stderr}")
        if e.stdout:
            print(f"Вывод: {e.stdout}")
        sys.exit(1)
        
    except FileNotFoundError:
        print("❌ Alembic не найден. Убедитесь, что он установлен:")
        print("pip install alembic")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()