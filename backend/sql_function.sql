-- Step 1: Drop all existing versions of the function
DROP FUNCTION IF EXISTS match_code_chunks(vector, int);
DROP FUNCTION IF EXISTS match_code_chunks(vector, int, float);

-- Step 2: Create the improved version with similarity threshold
CREATE OR REPLACE FUNCTION match_code_chunks (
  query_embedding vector(1536),
  match_count int DEFAULT 5,
  similarity_threshold float DEFAULT 0.35
) 
RETURNS TABLE (
  id bigint,
  file_path text,
  content text,
  similarity float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    cc.id,
    cc.file_path,
    cc.content,
    1 - (cc.embedding <=> query_embedding) as similarity
  FROM
    code_chunks cc
  WHERE
    1 - (cc.embedding <=> query_embedding) > similarity_threshold
  ORDER BY
    cc.embedding <=> query_embedding
  LIMIT
    match_count;
$$;
