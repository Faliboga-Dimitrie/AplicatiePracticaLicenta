INSERT INTO subject_access (user_id, subject_id)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE subject_id = VALUES(subject_id)
