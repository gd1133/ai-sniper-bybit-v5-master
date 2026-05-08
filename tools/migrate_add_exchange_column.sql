-- Migração: adiciona suporte multi-corretora (Bybit/Binance) na tabela public.clientes
-- Execute no SQL Editor do Supabase.

alter table public.clientes
add column if not exists exchange text not null default 'bybit';

update public.clientes
set exchange = lower(coalesce(exchange, 'bybit'));

update public.clientes
set exchange = case
    when exchange in ('bybit', 'binance') then exchange
    else 'bybit'
end;

