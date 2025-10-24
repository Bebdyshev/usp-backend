# Создание администратора на продакшене

## Быстрый способ

```bash
cd /home/bebdyshev/Documents/GitHub/usp/backend
python quick_admin.py admin@school.kz admin123 "System Administrator"
```

## Полный способ с настройками

```bash
cd /home/bebdyshev/Documents/GitHub/usp/backend
python create_production_admin.py
```

## Переменные окружения

Можно настроить через переменные окружения:

```bash
export ADMIN_EMAIL="admin@school.kz"
export ADMIN_PASSWORD="secure_password_123"
export ADMIN_NAME="System Administrator"
export ADMIN_FIRST_NAME="Admin"
export ADMIN_LAST_NAME="System"
```

## Проверка

После создания админа:

1. Запустите бэкенд: `python app.py`
2. Откройте фронтенд
3. Войдите с учетными данными админа
4. Настройте систему в разделе "Настройки"

## Безопасность

⚠️ **Важно**: После первого входа смените пароль на более безопасный!

## Устранение проблем

Если возникают ошибки:

1. Проверьте подключение к базе данных
2. Убедитесь, что миграции применены: `alembic current`
3. Проверьте переменные окружения: `echo $POSTGRES_URL`
