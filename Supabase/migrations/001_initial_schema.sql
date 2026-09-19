create extension if not exists pgcrypto;

create table if not exists public.scans (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  image_url text,
  raw_ocr_json jsonb not null default '[]'::jsonb,
  extracted_fields_json jsonb not null default '{}'::jsonb,
  compliance_score numeric(5,2) not null default 0,
  compliance_status text not null check (compliance_status in ('COMPLIANT','WARNING','NON_COMPLIANT')),
  created_at timestamptz not null default now()
);

create table if not exists public.violations (
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references public.scans(id) on delete cascade,
  rule_code text not null,
  description text not null,
  clause text,
  severity text not null,
  created_at timestamptz not null default now()
);

create index if not exists scans_created_at_idx on public.scans(created_at desc);
create index if not exists scans_status_idx on public.scans(compliance_status);
create index if not exists violations_scan_id_idx on public.violations(scan_id);

alter table public.scans enable row level security;
alter table public.violations enable row level security;

-- The backend uses the service-role key and therefore bypasses RLS. Add narrower
-- authenticated/public policies in the Supabase dashboard according to deployment roles.

