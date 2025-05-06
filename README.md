# USP Backend

## Database Setup (PostgreSQL)

1. Install Docker and Docker Compose if you don't have them installed.

2. Start the PostgreSQL container:
   ```
   docker-compose up -d
   ```

3. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Run the application:
   ```
   uvicorn app:app --reload
   ```

## Database Connection

The application is configured to connect to PostgreSQL with the following details:
- Host: localhost
- Port: 5432
- Database: usp
- Username: postgres
- Password: password

You can modify these settings in `config.py` if needed.

## Health Check Endpoint

The application includes a health check endpoint that verifies database connectivity:

```
GET /health
```

Example response when healthy:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

If the database connection fails, the endpoint will return a 503 Service Unavailable status. 