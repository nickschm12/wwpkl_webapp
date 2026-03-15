import re
import unicodedata
import pandas as pd


def normalize_name(name):
    """Lowercase, strip accents, remove Jr./Sr./II/III, collapse whitespace."""
    if not name:
        return ''
    s = str(name).lower()
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    s = re.sub(r"['\.\,]", '', s)
    s = re.sub(r'\s+(jr?|sr?|ii|iii|iv)\s*$', '', s.strip())
    return ' '.join(s.split())


def _get_positions(player):
    """Return list of eligible positions from Yahoo player dict."""
    pos = player.get('eligible_positions', {}).get('position', [])
    if isinstance(pos, str):
        pos = [pos]
    return pos or []


def _float(val, default=0.0):
    try:
        return float(val) if val is not None and val != '-' else default
    except (ValueError, TypeError):
        return default


def load_batting_projections(csv_file):
    """Parse FanGraphs BatX CSV. Returns {normalized_name: stat_dict}."""
    df = pd.read_csv(csv_file)
    df.columns = [c.strip() for c in df.columns]
    result = {}
    for _, row in df.iterrows():
        name = normalize_name(row.get('Name', ''))
        if not name:
            continue
        result[name] = {
            'name_orig': str(row.get('Name', '')),
            'PA':   _float(row.get('PA')),
            'AB':   _float(row.get('AB')),
            'H':    _float(row.get('H')),
            '2B':   _float(row.get('2B')),
            '3B':   _float(row.get('3B')),
            'HR':   _float(row.get('HR')),
            'R':    _float(row.get('R')),
            'RBI':  _float(row.get('RBI')),
            'BB':   _float(row.get('BB')),
            'HBP':  _float(row.get('HBP')),
            'SF':   _float(row.get('SF')),
            'SB':   _float(row.get('SB')),
            'AVG':  _float(row.get('AVG')),
            'wRC+': _float(row.get('wRC+'), default=100.0),
        }
    return result


def load_pitching_projections(csv_file):
    """Parse FanGraphs Steamer CSV. Returns {normalized_name: stat_dict}."""
    df = pd.read_csv(csv_file)
    df.columns = [c.strip() for c in df.columns]
    result = {}
    for _, row in df.iterrows():
        name = normalize_name(row.get('Name', ''))
        if not name:
            continue
        result[name] = {
            'name_orig': str(row.get('Name', '')),
            'W':    _float(row.get('W')),
            'L':    _float(row.get('L')),
            'G':    _float(row.get('G'), default=1.0),
            'GS':   _float(row.get('GS')),
            'SV':   _float(row.get('SV')),
            'HLD':  _float(row.get('HLD')),
            'IP':   _float(row.get('IP')),
            'H':    _float(row.get('H')),
            'BB':   _float(row.get('BB')),
            'ER':   _float(row.get('ER')),
            'SO':   _float(row.get('SO')),
            'ERA':  _float(row.get('ERA'), default=4.50),
            'WHIP': _float(row.get('WHIP'), default=1.30),
            'FIP':  _float(row.get('FIP'), default=4.50),
        }
    return result


_HITTER_POS = {'C', '1B', '2B', '3B', 'SS', 'OF'}
_PITCHER_POS = {'SP', 'RP', 'P'}
_SKIP_POS    = {'IL', 'IL+', 'NA', 'BN'}

_HITTER_SLOTS = ['C', '1B', '2B', '3B', 'SS', 'OF1', 'OF2', 'OF3', 'UTIL1', 'UTIL2']
_SP_SLOTS     = ['SP1', 'SP2', 'SP3', 'SP4', 'SP5']
_RP_SLOTS     = ['RP1', 'RP2', 'RP3', 'RP4', 'RP5']


def build_lineup(roster, batting_proj, pitching_proj):
    """
    Construct the optimal projected starting lineup for one team.

    Selection criteria:
      - Hitters ranked by wRC+ (best available per position slot)
      - SPs ranked by FIP ascending (lower = better)
      - RPs ranked by ERA ascending; excess SPs spill into RP pool

    Returns:
      display_rows  – list of dicts for template rendering
      team_stats    – dict matching calculate_roto_standings() column names
      unmatched     – list of rostered player names not found in projections
    """
    hitters  = []   # (pid, full_name, positions, bat_proj)
    sp_pool  = []   # (pid, full_name, pit_proj)  — SP-eligible
    rp_pool  = []   # (pid, full_name, pit_proj)  — RP/P-eligible only
    unmatched = []

    for player in roster:
        pid       = player.get('player_id', id(player))
        name_data = player.get('name', {})
        full_name = name_data.get('full', '') if isinstance(name_data, dict) else str(name_data)
        norm      = normalize_name(full_name)
        positions = set(_get_positions(player)) - _SKIP_POS

        is_hitter  = bool(positions & _HITTER_POS)
        is_pitcher = bool(positions & _PITCHER_POS)

        if is_hitter and norm in batting_proj:
            hitters.append((pid, full_name, list(positions), batting_proj[norm]))
        elif is_pitcher and norm in pitching_proj:
            proj = pitching_proj[norm]
            if 'SP' in positions:
                sp_pool.append((pid, full_name, proj))
            else:
                rp_pool.append((pid, full_name, proj))
        else:
            if is_hitter or is_pitcher:
                unmatched.append(full_name)

    used = set()
    slots = {}  # slot_name -> (full_name, proj) | None

    def pick_hitter(pos):
        eligible = [(pid, name, proj)
                    for pid, name, positions, proj in hitters
                    if pos in positions and pid not in used]
        if not eligible:
            return None
        eligible.sort(key=lambda x: x[2]['wRC+'], reverse=True)
        pid, name, proj = eligible[0]
        used.add(pid)
        return (name, proj)

    # Infield + catcher
    for pos in ['C', '1B', '2B', '3B', 'SS']:
        slots[pos] = pick_hitter(pos)

    # Outfield (3 slots)
    of_eligible = [(pid, name, proj) for pid, name, positions, proj in hitters
                   if 'OF' in positions and pid not in used]
    of_eligible.sort(key=lambda x: x[2]['wRC+'], reverse=True)
    for i, (pid, name, proj) in enumerate(of_eligible[:3]):
        slots[f'OF{i + 1}'] = (name, proj)
        used.add(pid)
    for i in range(len(of_eligible), 3):
        slots[f'OF{i + 1}'] = None

    # UTIL (2 slots) — best remaining hitters
    util_eligible = [(pid, name, proj) for pid, name, _, proj in hitters
                     if pid not in used]
    util_eligible.sort(key=lambda x: x[2]['wRC+'], reverse=True)
    for i, (pid, name, proj) in enumerate(util_eligible[:2]):
        slots[f'UTIL{i + 1}'] = (name, proj)
        used.add(pid)
    for i in range(len(util_eligible), 2):
        slots[f'UTIL{i + 1}'] = None

    # SP (5 slots) — best FIP
    sp_pool.sort(key=lambda x: x[2]['FIP'])
    for i, (pid, name, proj) in enumerate(sp_pool[:5]):
        slots[f'SP{i + 1}'] = (name, proj)
        used.add(pid)
    for i in range(len(sp_pool), 5):
        slots[f'SP{i + 1}'] = None

    # RP (5 slots) — best ERA; excess SPs join the pool
    extra_sps = [(pid, name, proj) for pid, name, proj in sp_pool[5:]
                 if pid not in used]
    all_rp = [(pid, name, proj) for pid, name, proj in (rp_pool + extra_sps)
              if pid not in used]
    all_rp.sort(key=lambda x: x[2]['ERA'])
    for i, (pid, name, proj) in enumerate(all_rp[:5]):
        slots[f'RP{i + 1}'] = (name, proj)
        used.add(pid)
    for i in range(len(all_rp), 5):
        slots[f'RP{i + 1}'] = None

    # ── Aggregate stats ──────────────────────────────────────────────────────
    totals = dict(
        H=0, AB=0, BB_bat=0, HBP=0, SF=0, doubles=0, triples=0, HR_bat=0,
        runs=0, hits=0, homeruns=0, rbis=0, sb=0,
        IP=0, ER=0, H_pit=0, BB_pit=0,
        wins=0, loses=0, saves=0, strikeouts=0, holds=0,
    )

    for slot in _HITTER_SLOTS:
        entry = slots.get(slot)
        if not entry:
            continue
        _, p = entry
        totals['runs']    += p['R']
        totals['hits']    += p['H']
        totals['homeruns']+= p['HR']
        totals['rbis']    += p['RBI']
        totals['sb']      += p['SB']
        totals['H']       += p['H']
        totals['AB']      += p['AB']
        totals['BB_bat']  += p['BB']
        totals['HBP']     += p['HBP']
        totals['SF']      += p['SF']
        totals['doubles'] += p['2B']
        totals['triples'] += p['3B']
        totals['HR_bat']  += p['HR']

    for slot in _SP_SLOTS + _RP_SLOTS:
        entry = slots.get(slot)
        if not entry:
            continue
        _, p = entry
        totals['wins']       += p['W']
        totals['loses']      += p['L']
        totals['saves']      += p['SV']
        totals['strikeouts'] += p['SO']
        totals['holds']      += p['HLD']
        totals['IP']         += p['IP']
        totals['ER']         += p['ER']
        totals['H_pit']      += p['H']
        totals['BB_pit']     += p['BB']

    # Rate stats
    if totals['AB'] > 0:
        avg = totals['H'] / totals['AB']
        tb  = totals['H'] + totals['doubles'] + 2 * totals['triples'] + 3 * totals['HR_bat']
        obp_denom = totals['AB'] + totals['BB_bat'] + totals['HBP'] + totals['SF']
        obp = (totals['H'] + totals['BB_bat'] + totals['HBP']) / obp_denom if obp_denom else 0
        slg = tb / totals['AB']
        ops = obp + slg
    else:
        avg = ops = 0.0

    if totals['IP'] > 0:
        era  = totals['ER'] / totals['IP'] * 9
        whip = (totals['H_pit'] + totals['BB_pit']) / totals['IP']
    else:
        era = whip = 0.0

    team_stats = {
        'runs':       round(totals['runs']),
        'hits':       round(totals['hits']),
        'homeruns':   round(totals['homeruns']),
        'rbis':       round(totals['rbis']),
        'sb':         round(totals['sb']),
        'avg':        round(avg,  3),
        'ops':        round(ops,  3),
        'wins':       round(totals['wins']),
        'loses':      round(totals['loses']),
        'saves':      round(totals['saves']),
        'strikeouts': round(totals['strikeouts']),
        'holds':      round(totals['holds']),
        'era':        round(era,  2),
        'whip':       round(whip, 2),
    }

    # ── Build template display rows ───────────────────────────────────────────
    display_rows = []

    for slot in _HITTER_SLOTS:
        entry = slots.get(slot)
        if entry:
            name, p = entry
            avg_val = p['H'] / p['AB'] if p['AB'] > 0 else p.get('AVG', 0)
            stat_str = (f"{p['HR']:.0f} HR · {p['R']:.0f} R · "
                        f"{p['RBI']:.0f} RBI · {p['SB']:.0f} SB · "
                        f"{avg_val:.3f} AVG")
        else:
            name, stat_str = '—', ''
        display_rows.append({'slot': slot, 'name': name,
                              'type': 'hitter', 'stats': stat_str})

    for slot in _SP_SLOTS:
        entry = slots.get(slot)
        if entry:
            name, p = entry
            stat_str = (f"{p['W']:.0f} W · {p['SO']:.0f} K · "
                        f"{p['ERA']:.2f} ERA · {p['WHIP']:.2f} WHIP")
        else:
            name, stat_str = '—', ''
        display_rows.append({'slot': slot, 'name': name,
                              'type': 'sp', 'stats': stat_str})

    for slot in _RP_SLOTS:
        entry = slots.get(slot)
        if entry:
            name, p = entry
            stat_str = (f"{p['SV']:.0f} SV · {p['HLD']:.0f} HLD · "
                        f"{p['SO']:.0f} K · {p['ERA']:.2f} ERA")
        else:
            name, stat_str = '—', ''
        display_rows.append({'slot': slot, 'name': name,
                              'type': 'rp', 'stats': stat_str})

    return display_rows, team_stats, unmatched
