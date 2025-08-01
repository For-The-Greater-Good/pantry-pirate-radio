-- Initialize PostgreSQL settings
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;
-- Create extensions
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT postgis_version();
-- Set default tablespace
SET default_tablespace = '';
SET default_table_access_method = heap;
