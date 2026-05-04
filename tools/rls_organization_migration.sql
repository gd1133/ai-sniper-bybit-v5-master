-- ============================================================
-- Migração: RLS por Organização (clientes e trades)
-- Seguro para re-executar — usa DROP POLICY IF EXISTS antes
-- de cada CREATE POLICY para evitar o erro 42710.
-- ============================================================

-- 1. Garante a extensão pgcrypto (necessária para gen_random_uuid)
create extension if not exists pgcrypto;

-- 2. Adiciona coluna organization_id se ainda não existir
alter table public.clientes
    add column if not exists organization_id uuid default gen_random_uuid();

-- Popula registros que ficaram sem organization_id
update public.clientes
set organization_id = gen_random_uuid()
where organization_id is null;

-- 3. Adiciona organization_id em trades (ligada ao cliente)
alter table public.trades
    add column if not exists organization_id uuid;

-- Propaga organization_id do cliente para os trades existentes
update public.trades t
set organization_id = c.organization_id
from public.clientes c
where t.client_id = c.id
  and t.organization_id is null;

-- ============================================================
-- 4. Ativa Row Level Security
-- ============================================================
alter table public.clientes enable row level security;
alter table public.trades    enable row level security;

-- ============================================================
-- 5. Políticas para a tabela clientes
--    Remove antes de criar para ser idempotente
-- ============================================================

drop policy if exists clientes_select_tenant on public.clientes;
create policy clientes_select_tenant on public.clientes
    for select
    using (
        organization_id = (auth.jwt() ->> 'organization_id')::uuid
    );

drop policy if exists clientes_insert_tenant on public.clientes;
create policy clientes_insert_tenant on public.clientes
    for insert
    with check (
        organization_id = (auth.jwt() ->> 'organization_id')::uuid
    );

drop policy if exists clientes_update_tenant on public.clientes;
create policy clientes_update_tenant on public.clientes
    for update
    using (
        organization_id = (auth.jwt() ->> 'organization_id')::uuid
    );

drop policy if exists clientes_delete_tenant on public.clientes;
create policy clientes_delete_tenant on public.clientes
    for delete
    using (
        organization_id = (auth.jwt() ->> 'organization_id')::uuid
    );

-- ============================================================
-- 6. Políticas para a tabela trades
--    Acesso via client_id → clientes.organization_id
-- ============================================================

drop policy if exists trades_select_tenant on public.trades;
create policy trades_select_tenant on public.trades
    for select
    using (
        exists (
            select 1 from public.clientes c
            where c.id = public.trades.client_id
              and c.organization_id = (auth.jwt() ->> 'organization_id')::uuid
        )
    );

drop policy if exists trades_insert_tenant on public.trades;
create policy trades_insert_tenant on public.trades
    for insert
    with check (
        exists (
            select 1 from public.clientes c
            where c.id = public.trades.client_id
              and c.organization_id = (auth.jwt() ->> 'organization_id')::uuid
        )
    );

drop policy if exists trades_update_tenant on public.trades;
create policy trades_update_tenant on public.trades
    for update
    using (
        exists (
            select 1 from public.clientes c
            where c.id = public.trades.client_id
              and c.organization_id = (auth.jwt() ->> 'organization_id')::uuid
        )
    );

drop policy if exists trades_delete_tenant on public.trades;
create policy trades_delete_tenant on public.trades
    for delete
    using (
        exists (
            select 1 from public.clientes c
            where c.id = public.trades.client_id
              and c.organization_id = (auth.jwt() ->> 'organization_id')::uuid
        )
    );

-- ============================================================
-- Índices de suporte para as políticas RLS
-- ============================================================
create index if not exists idx_clientes_organization_id on public.clientes(organization_id);
create index if not exists idx_trades_organization_id   on public.trades(organization_id);
