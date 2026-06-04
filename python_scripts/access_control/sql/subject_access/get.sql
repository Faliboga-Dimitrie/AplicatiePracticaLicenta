SELECT user_id, subject_id
FROM subject_access
WHERE user_id = %s AND subject_id = %s
