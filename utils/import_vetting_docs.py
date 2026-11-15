#!/usr/bin/env python3
"""
Bulk-attach signed Vetted Membership forms to members.

Each file (.pdf, or a .jpg/.jpeg/.png scan, converted to PDF) is matched to a
member from its file name, tried in this order:

  1. A row in the --overrides CSV                 (always wins)
  2. A Stripe customer ID anywhere in the name    VM-Jane-Doe_cus_Ab12Cd34.pdf
  3. An email address as the whole name           jane@example.com.pdf
  4. The member's name                            VM-Doe-Jane-06-01-2013.pdf

For name matching, the "VM"/"Incomplete" prefixes, dates, times, and words like
"Unknown" or "Vetted" are dropped, and a member matches when both their first
and last name appear among what is left, in any order (so Last-First,
First-Last, and middle names all work). A name that fits more than one member
is reported and skipped; add an override for it.

Forms whose name starts with "Incomplete" are skipped unless you pass
--include-incomplete. When several forms match one member, the newest by the
date in its name is used (complete forms beat incomplete ones).

Overrides CSV: two columns, file name and Stripe ID, no header needed. Leave
the Stripe ID empty (or write "skip") to ignore a file.

  VM-Jane_Doe 15-May-2017 22-38-53.pdf,cus_Ab12Cd34
  VM_John  Smith-AGAIN-2025-05-10.pdf,cus_Ef56Gh78
  VM-Roe-Richard.PDF,skip

Dry run by default; nothing is written until you pass --commit. Members who
already have a vetting document are skipped unless you pass --overwrite.
With --sql they are never skipped: the SQL replaces whatever is on file.

Usage (from the repo root):

  venv/bin/python3 utils/import_vetting_docs.py ~/vetting-pdfs
  venv/bin/python3 utils/import_vetting_docs.py ~/vetting-pdfs --overrides fixes.csv --commit

Or, instead of --commit, write the updates to a SQL file to review and run yourself:

  venv/bin/python3 utils/import_vetting_docs.py ~/vetting-pdfs --overrides fixes.csv --sql vetting.sql
  mysql -u synshop -p shopid < vetting.sql

To list members who have no vetting document yet (active and vetted first):

  venv/bin/python3 utils/import_vetting_docs.py --missing
  venv/bin/python3 utils/import_vetting_docs.py --missing --active-only   # active and vetted only

The encryption key comes from $ENCRYPTION_KEY, or you are prompted for it.
"""

import argparse
import csv
import datetime
import importlib.util
import io
import re
import sys
from pathlib import Path

import MySQLdb as mysql
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent

# vetting_doc is a MEDIUMBLOB
MAX_PDF_BYTES = 16 * 1024 * 1024 - 1

PDF_SUFFIXES = {'.pdf'}
IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png'}

STRIPE_ID_RE = re.compile(r'cus_[A-Za-z0-9]+')
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
INCOMPLETE_RE = re.compile(r'^\W*(\d{4}-\d{2}-\d{2}\W*)?incomplete', re.I)

MONTHS = {m: i for i, names in enumerate([
    ('jan', 'january'), ('feb', 'february'), ('mar', 'march'), ('apr', 'april'),
    ('may',), ('jun', 'june'), ('jul', 'july'), ('aug', 'august'),
    ('sep', 'sept', 'september'), ('oct', 'october'), ('nov', 'november'), ('dec', 'december'),
], start=1) for m in names}

# Words in file names that are never part of a member's name
NOISE_WORDS = {'vm', 'incomplete', 'incompletevm', 'unknown', 'vetted', 'again', 'form', 'membership'}


def load_module(name, path):
    # Loaded by path: importing the identity package would run its __init__,
    # which builds the whole app and can start the cron scheduler.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def connect_db():
    config_path = REPO_ROOT / 'identity' / 'config.py'
    if not config_path.exists():
        sys.exit('ERROR: missing %s' % config_path)
    config = load_module('shopid_config', config_path)
    crypto = load_module('shopid_crypto', REPO_ROOT / 'identity' / 'crypto' / 'CryptoUtil.py')
    settings = load_module('shopid_settings', REPO_ROOT / 'identity' / 'crypto' / 'SettingsUtil.py')

    key = settings.EncryptionKey.get()
    try:
        password = crypto.decrypt(config.ENCRYPTED_DATABASE_PASSWORD, key)
    except Exception as e:
        sys.exit('ERROR: could not decrypt the database password: %s' % e)

    return mysql.connect(
        host=config.DATABASE_HOST,
        port=getattr(config, 'DATABASE_PORT', 3306),
        user=config.DATABASE_USER,
        passwd=password,
        db=config.DATABASE_SCHEMA,
    )


def name_tokens(text):
    return [t for t in re.split(r'[^a-z]+', text.lower()) if t]


def file_name_tokens(stem):
    """The words in a file name that could be part of a person's name."""
    return {t for t in name_tokens(stem) if t not in NOISE_WORDS and t not in MONTHS}


def _date(y, m, d):
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return None


def file_date(stem):
    """The first date in a file name, or None. Used to pick the newest form."""
    patterns = [
        # 2025-04-08, 2025.09.16
        (r'(\d{4})[-.](\d{1,2})[-.](\d{1,2})', lambda g: _date(int(g[0]), int(g[1]), int(g[2]))),
        # 06-Jan-2019, 7-July-2019
        (r'(\d{1,2})-([A-Za-z]{3,9})-(\d{4})',
         lambda g: _date(int(g[2]), MONTHS.get(g[1].lower(), 0), int(g[0]))),
        # 06-01-2013, 4-18-23 (US month-day-year)
        (r'(?<!\d)(\d{1,2})-(\d{1,2})-(\d{4}|\d{2})(?!\d)',
         lambda g: _date(int(g[2]), int(g[0]), int(g[1]))),
        # Feb-2020
        (r'([A-Za-z]{3,9})-(\d{4})', lambda g: _date(int(g[1]), MONTHS.get(g[0].lower(), 0), 1)),
    ]
    found = []
    for pattern, build in patterns:
        for m in re.finditer(pattern, stem):
            d = build(m.groups())
            if d:
                found.append((m.start(), d))
    return min(found)[1] if found else None


def load_members(db):
    # Same precedence as get_member: Stripe's copy first, then ours
    cur = db.cursor()
    cur.execute("""
        SELECT m.stripe_id,
               COALESCE(sc.full_name, m.full_name, ''),
               COALESCE(sc.email, m.email, ''),
               m.vetting_doc IS NOT NULL
        FROM members m
        LEFT JOIN stripe_cache sc ON m.stripe_id = sc.stripe_id
    """)
    members = {}
    for stripe_id, full_name, email, has_doc in cur.fetchall():
        members[stripe_id] = {
            'name': full_name,
            'email': email,
            'has_doc': bool(has_doc),
            'tokens': name_tokens(full_name),
        }
    return members


def report_missing(db, active_only=False):
    """Print members with no vetting document; ACTIVE and VETTED members first."""
    cur = db.cursor()
    cur.execute("""
        SELECT m.stripe_id,
               COALESCE(sc.full_name, m.full_name, ''),
               COALESCE(sc.email, m.email, ''),
               m.member_status,
               m.is_vetted
        FROM members m
        LEFT JOIN stripe_cache sc ON m.stripe_id = sc.stripe_id
        WHERE m.vetting_doc IS NULL
    """ + ("AND m.member_status = 'ACTIVE' AND m.is_vetted = 'VETTED'" if active_only else ""))
    rows = sorted(cur.fetchall(), key=lambda r: (r[3] != 'ACTIVE', r[4] != 'VETTED', r[1].lower()))

    print('%-8s  %-10s  %-28s  %s' % ('STATUS', 'VETTED', 'NAME', 'EMAIL'))
    for _, name, email, status, vetted in rows:
        print('%-8s  %-10s  %-28s  %s' % (status, vetted, name, email))

    print()
    if active_only:
        print('%d active, vetted members have no vetting document.' % len(rows))
    else:
        vetted_active = sum(1 for r in rows if r[3] == 'ACTIVE' and r[4] == 'VETTED')
        print('%d members have no vetting document, %d of them active and vetted.' % (len(rows), vetted_active))


def write_sql(path, attach, members):
    """Write the planned updates as a SQL script to review and run with the mysql client.
    Each update replaces any vetting document already on file."""
    with open(path, 'w') as f:
        f.write('-- Vetted Membership forms generated by utils/import_vetting_docs.py on %s\n'
                % datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        f.write('-- %d updates. Run against the ShopID schema, e.g.: mysql -u synshop -p shopid < %s\n'
                % (len(attach), Path(path).name))
        f.write('-- Each update replaces any vetting document already on file for that member.\n')
        f.write('\nSTART TRANSACTION;\n\n')
        for file_path, stripe_id, how, pdf in sorted(attach, key=lambda a: members[a[1]]['name'].lower()):
            label = '%s <- %s [%s]' % (members[stripe_id]['name'], file_path.name, how)
            f.write('-- %s\n' % re.sub(r'[\r\n]+', ' ', label))
            f.write("UPDATE members SET vetting_doc = X'%s' WHERE stripe_id = '%s';\n\n"
                    % (pdf.hex(), stripe_id))
        f.write('COMMIT;\n')


def load_overrides(path):
    overrides = {}
    with open(path, newline='') as f:
        for row in csv.reader(f):
            if not row or not row[0].strip() or row[0].startswith('#'):
                continue
            stripe_id = row[1].strip() if len(row) > 1 else ''
            overrides[row[0].strip()] = None if stripe_id.lower() in ('', 'skip') else stripe_id
    return overrides


def match(stem, members):
    """Return (stripe_id, how) or (None, reason)."""
    found = STRIPE_ID_RE.search(stem)
    if found:
        stripe_id = found.group(0)
        if stripe_id in members:
            return stripe_id, 'stripe id'
        return None, 'no member with Stripe ID %s' % stripe_id

    if EMAIL_RE.match(stem):
        ids = [sid for sid, m in members.items() if m['email'].lower() == stem.lower()]
        how = 'email'
    else:
        words = file_name_tokens(stem)
        ids = [sid for sid, m in members.items()
               if len(m['tokens']) >= 2 and m['tokens'][0] in words and m['tokens'][-1] in words]
        how = 'name'

    if len(ids) == 1:
        return ids[0], how
    if not ids:
        return None, 'no member with that %s' % how
    names = ', '.join('%s %s' % (sid, members[sid]['name']) for sid in ids)
    return None, '%s fits %d members (%s); add an override' % (how, len(ids), names)


def read_as_pdf(path):
    """The file's bytes as a PDF, converting image scans. Raises ValueError."""
    if path.suffix.lower() in IMAGE_SUFFIXES:
        with Image.open(path) as img:
            buf = io.BytesIO()
            img.convert('RGB').save(buf, 'PDF', resolution=150)
        data = buf.getvalue()
    else:
        data = path.read_bytes()
        if not data.startswith(b'%PDF-'):
            raise ValueError('not a PDF')
    if len(data) > MAX_PDF_BYTES:
        raise ValueError('larger than 16MB')
    return data


def main():
    parser = argparse.ArgumentParser(description='Attach Vetted Membership forms to members by file name.')
    parser.add_argument('directory', type=Path, nargs='?', help='directory of PDF (or JPG/PNG) files')
    parser.add_argument('--missing', action='store_true',
                        help='instead of importing, list members with no vetting document')
    parser.add_argument('--active-only', action='store_true', help='with --missing, only list members who are both ACTIVE and VETTED')
    parser.add_argument('--commit', action='store_true', help='write to the database (default is a dry run)')
    parser.add_argument('--sql', type=Path, metavar='FILE',
                        help='write the updates to a SQL file to run yourself, instead of to the database; '
                             'includes members who already have a form, replacing it')
    parser.add_argument('--overwrite', action='store_true', help='replace vetting documents already on file')
    parser.add_argument('--overrides', type=Path, help='CSV of file name,stripe_id to fix or skip matches')
    parser.add_argument('--include-incomplete', action='store_true',
                        help='also use forms whose name starts with "Incomplete"')
    args = parser.parse_args()

    if args.missing:
        db = connect_db()
        report_missing(db, args.active_only)
        db.close()
        return 0

    if args.directory is None:
        parser.error('a directory is required (or use --missing)')
    if args.sql and args.commit:
        parser.error('use --sql or --commit, not both')
    if not args.directory.is_dir():
        sys.exit('ERROR: %s is not a directory' % args.directory)

    files = sorted(p for p in args.directory.iterdir()
                   if p.is_file() and p.suffix.lower() in PDF_SUFFIXES | IMAGE_SUFFIXES)
    if not files:
        sys.exit('No PDF or image files in %s' % args.directory)

    overrides = load_overrides(args.overrides) if args.overrides else {}
    unknown = set(overrides) - {p.name for p in files}
    for name in sorted(unknown):
        print('WARNING     override for %s, which is not in the directory' % name)

    db = connect_db()
    members = load_members(db)

    candidates = {}   # stripe_id -> [(path, how, incomplete, date)]
    problems = []
    ignored = []

    for path in files:
        stem = path.stem
        incomplete = bool(INCOMPLETE_RE.match(stem))
        if path.name in overrides:
            stripe_id = overrides[path.name]
            if stripe_id is None:
                ignored.append((path.name, 'skipped by override'))
                continue
            if not STRIPE_ID_RE.fullmatch(stripe_id):
                problems.append((path.name, 'override %r is not a Stripe customer ID' % stripe_id))
                continue
            if stripe_id not in members:
                problems.append((path.name, 'override names %s, which is not a member' % stripe_id))
                continue
            how = 'override'
        else:
            if incomplete and not args.include_incomplete:
                ignored.append((path.name, 'incomplete form (use --include-incomplete)'))
                continue
            stripe_id, how = match(stem, members)
            if stripe_id is None:
                problems.append((path.name, how))
                continue
        candidates.setdefault(stripe_id, []).append((path, how, incomplete, file_date(stem)))

    attach = []
    for stripe_id, forms in candidates.items():
        # Complete beats incomplete, then newest date; undated files sort oldest
        forms.sort(key=lambda f: (not f[2], f[3] or datetime.date.min), reverse=True)
        best, rest = forms[0], forms[1:]
        if rest and (best[2], best[3]) == (rest[0][2], rest[0][3]):
            names = ', '.join(f[0].name for f in forms)
            problems.append((names, 'several forms for %s %s and no newer one; add overrides to pick one'
                             % (stripe_id, members[stripe_id]['name'])))
            continue
        for path, *_ in rest:
            ignored.append((path.name, 'older than %s' % best[0].name))
        if members[stripe_id]['has_doc'] and not (args.overwrite or args.sql):
            ignored.append((best[0].name, '%s already has a vetting document (use --overwrite)' % stripe_id))
            continue
        try:
            pdf = read_as_pdf(best[0])
        except Exception as e:
            problems.append((best[0].name, str(e)))
            continue
        attach.append((best[0], stripe_id, best[1], pdf))

    verb = 'Attaching' if args.commit else 'SQL for' if args.sql else 'Would attach'
    for path, stripe_id, how, _ in sorted(attach, key=lambda a: members[a[1]]['name'].lower()):
        m = members[stripe_id]
        notes = []
        if path.suffix.lower() in IMAGE_SUFFIXES:
            notes.append('image converted to PDF')
        if INCOMPLETE_RE.match(path.stem):
            notes.append('INCOMPLETE')
        if m['has_doc']:
            notes.append('replaces existing')
        print('%s  %-28s <- %s  [%s, %s]%s' % (verb, m['name'], path.name, stripe_id, how,
                                              ' (%s)' % ', '.join(notes) if notes else ''))
    for name, reason in ignored:
        print('Skipped     %s: %s' % (name, reason))
    for name, reason in problems:
        print('UNMATCHED   %s: %s' % (name, reason))

    if args.commit and attach:
        cur = db.cursor()
        for _, stripe_id, _, pdf in attach:
            cur.execute("UPDATE members SET vetting_doc = %s WHERE stripe_id = %s", (pdf, stripe_id))
        db.commit()
    db.close()

    if args.sql and attach:
        write_sql(args.sql, attach, members)

    print()
    print('%d %s, %d skipped, %d unmatched.' % (
        len(attach), 'attached' if args.commit else 'to attach', len(ignored), len(problems)))
    if args.sql and attach:
        print('Wrote %s (%.1f MB). Nothing was changed in the database.'
              % (args.sql.resolve(), args.sql.stat().st_size / 1e6))
    elif args.sql:
        print('No SQL file written: there is nothing to attach (see the Skipped and UNMATCHED lines above).')
    elif attach and not args.commit:
        print('Dry run: re-run with --commit (or --sql FILE) to write these.')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
