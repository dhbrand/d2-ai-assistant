-- list all tables in the database
SELECT name 
FROM sqlite_master 
WHERE type='table';

-- list all columns in a table
SELECT count(*) 
FROM catalysts

-- catalysts objectives parsed from data col in catalysts table
SELECT * 
FROM objectives

-- no rows returned
SELECT * 
FROM definitions

-- no rows returned
SELECT * 
FROM metadata

SELECT * 
FROM sqlite_sequence
-- objectives 408


