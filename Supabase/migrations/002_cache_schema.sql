-- PackSure Persistent Result Cache Schema
-- Stores exact SHA-256 image hashes and verified structured analysis payloads

create table if not exists public.package_cache (
  image_hash text primary key,
  pipeline_version text not null,
  rules_version text not null,
  analysis_json jsonb not null default '{}'::jsonb,
  raw_ocr_json jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists package_cache_hash_idx on public.package_cache(image_hash);
create index if not exists package_cache_updated_idx on public.package_cache(updated_at desc);

alter table public.package_cache enable row level security;
