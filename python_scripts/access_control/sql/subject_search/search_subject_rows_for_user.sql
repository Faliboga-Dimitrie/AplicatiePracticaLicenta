SELECT
    s.id AS subject_id,
    s.name AS subject_name,
    s.age AS subject_age,
    s.notes AS subject_notes,
    {case_columns}
FROM subject_access sa
JOIN subject s ON s.id = sa.subject_id
LEFT JOIN mri_case c ON c.subject_id = s.id
WHERE {where_clause}
{order_clause}
