SELECT user_id, subject_id
FROM subject_access
WHERE subject_id = %s AND user_id <> %s
ORDER BY user_id
