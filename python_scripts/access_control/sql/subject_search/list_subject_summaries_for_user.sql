SELECT
    s.id AS subject_id,
    s.name AS subject_name,
    s.age AS subject_age,
    s.notes AS subject_notes,
    COUNT(c.id) AS case_count
FROM subject_access sa
JOIN subject s ON s.id = sa.subject_id
LEFT JOIN mri_case c ON c.subject_id = s.id
WHERE sa.user_id = %s
GROUP BY
    s.id,
    s.name,
    s.age,
    s.notes
ORDER BY s.id
