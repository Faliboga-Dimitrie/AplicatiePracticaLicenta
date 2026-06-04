SELECT 1 AS has_access
FROM mri_case c
JOIN subject_access sa ON sa.subject_id = c.subject_id
WHERE c.id = %s AND sa.user_id = %s
LIMIT 1
