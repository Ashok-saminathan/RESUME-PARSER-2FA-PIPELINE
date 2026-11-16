import os

# Must be set before app.config is first imported.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123")
