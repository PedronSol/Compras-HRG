#!/bin/sh
# Cria os papéis com privilégio mínimo e o banco da aplicação (executado uma única vez pelo container postgres).
#   rg_owner → dono do schema; usado apenas para migrações
#   rg_app   → papel sem login ao qual as políticas de RLS se aplicam
#   rg_api   → login da API; membro de rg_app, NÃO é dono das tabelas (RLS sempre ativo)
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v owner_pw="$RG_OWNER_PASSWORD" -v api_pw="$RG_API_PASSWORD" <<'SQL'
CREATE ROLE rg_app NOLOGIN;
CREATE ROLE rg_owner LOGIN PASSWORD :'owner_pw';
CREATE ROLE rg_api LOGIN PASSWORD :'api_pw' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT rg_app TO rg_api;
CREATE DATABASE rg_hospital OWNER rg_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE rg_hospital FROM PUBLIC;
GRANT CONNECT ON DATABASE rg_hospital TO rg_api;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname rg_hospital <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CREATE ON SCHEMA public TO rg_owner;
SQL
