INSERT INTO auth_session (
    user_id, refresh_token_hash, created_at, expires_at
)
VALUES (%s, %s, UTC_TIMESTAMP(), %s)
