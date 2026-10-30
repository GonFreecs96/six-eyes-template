#!/usr/bin/env python3
"""
Claude Code UserPromptSubmit hook: injects BigQuery context rules for warehouse-shaped queries.

Reads JSON from stdin, matches against governed rules, emits JSON with injected context.
Exits 0 always; silent on errors.
"""
import sys
import json
import re
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple


def get_config_dir() -> Path:
    """Get config directory, honoring $CLAUDE_PROJECT_DIR."""
    if claude_project := os.environ.get('CLAUDE_PROJECT_DIR'):
        return Path(claude_project) / 'config' / 'context'
    return Path(__file__).resolve().parents[2] / 'config' / 'context'


def normalize(text: str) -> str:
    """Normalize text: lowercase, remove punctuation, collapse whitespace."""
    text = text.lower()
    # Replace common punctuation and separators with spaces
    text = re.sub(r'[_\-/.,;:!?()[\]{}"\']', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def truncate(text: str, limit: int) -> str:
    """Truncate text at word boundary, capped at limit chars."""
    if len(text) <= limit:
        return text
    text = text[:limit]
    last_space = text.rfind(' ')
    if last_space > 0:
        text = text[:last_space]
    return text + '…'


def load_rules() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load rules from YAML files. Raises if yaml is not available."""
    import yaml
    config_dir = get_config_dir()

    entity_rules = yaml.safe_load((config_dir / 'entity-rules.yaml').read_text()) or []
    traps_path = config_dir / 'integration-payload-traps.yaml'
    integration_rules = yaml.safe_load(traps_path.read_text()) if traps_path.is_file() else []
    feed_cutovers = yaml.safe_load((config_dir / 'feed-cutovers.yaml').read_text()) or []

    return entity_rules, integration_rules, feed_cutovers


def normalize_records(entity_rules: List[Dict], integration_rules: List[Dict],
                     feed_cutovers: List[Dict]) -> List[Dict[str, Any]]:
    """Normalize all records to common format."""
    records = []

    for rule in entity_rules + integration_rules:
        records.append({
            'id': rule['id'],
            'entity': rule['entity'],
            'cols': rule.get('applies_to_columns', []),
            'text': rule['message'],
            'source': rule['source']
        })

    # Process feed cutovers
    for cutover in feed_cutovers:
        label_slug = normalize(cutover['label']).replace(' ', '_')
        records.append({
            'id': label_slug,
            'entity': 'feed_cutover',
            'cols': [],
            'text': f"{cutover.get('date_display') or cutover['date']} — {cutover['label']}: {cutover['effect']}",
            'source': cutover['source']
        })

    return records


def is_warehouse_shaped(prompt: str, records: List[Dict[str, Any]]) -> bool:
    """Check if prompt looks warehouse-shaped."""
    norm_prompt = normalize(prompt)

    # (a) Check for acme warehouse table patterns
    if re.search(r'\bacme_analytics\b', norm_prompt):
        return True

    table_fragments = [
        'acme events', 'acme signups', 'acme subscriptions', 'acme invoices',
        'acme partner referrals', 'stg lifecycle', 'stg checkout'
    ]
    for frag in table_fragments:
        if frag in norm_prompt:
            return True

    # (b) Check known column tokens (individual tokens from column names, excluding generic words)
    generic_col_tokens = {'status', 'version', 'date', 'type', 'name', 'code', 'reason', 'amount',
                          'count'}
    all_col_tokens = set()
    for record in records:
        for col in record['cols']:
            norm_col = normalize(col)
            for token in norm_col.split():
                # Exclude genuinely generic column tokens, and short suffix
                # fragments ('at' from occurred_at, 'id', 'is') that would
                # otherwise open the gate on ordinary English prose.
                if len(token) >= 3 and token not in generic_col_tokens:
                    all_col_tokens.add(token)

    for token in all_col_tokens:
        if re.search(rf'\b{re.escape(token)}\b', norm_prompt):
            return True

    # (c) Entity nouns
    entity_nouns = ['signup', 'subscription', 'invoice', 'trial', 'churn',
                    'renewal', 'checkout', 'billing', 'cohort', 'partner']
    for noun in entity_nouns:
        if re.search(rf'\b{noun}s?\b', norm_prompt):
            return True

    # (d) Product/integration tokens
    product_tokens = ['acme_analytics', 'partner_referral', 'client_surface', 'plan_tier']
    for token in product_tokens:
        if re.search(rf'\b{re.escape(token)}\b', norm_prompt):
            return True

    # (e) Measurement words
    measurement_words = [
        'conversion rate', 'trial rate', 'mrr', 'arr',
        'conversion', 'convert', 'funnel',
        'drop off', 'dropoff',
        'trend', 'decline'
    ]
    for word in measurement_words:
        if re.search(rf'\b{re.escape(word)}\b', norm_prompt):
            return True

    return False


def score_record(record: Dict[str, Any], prompt: str) -> Tuple[int, bool]:
    """Score a single record. Returns (score, has_anchor)."""
    norm_prompt = normalize(prompt)
    score = 0

    stopwords = {
        'what', 'which', 'how', 'many', 'show', 'give', 'does', 'did',
        'was', 'were', 'used', 'use', 'per', 'and', 'the', 'for', 'with',
        'from', 'this', 'that', 'our', 'are', 'is', 'on', 'in', 'of', 'to',
        'a', 'by', 'at', 'it', 'be', 'can', 'should', 'would', 'most', 'more',
        'than', 'into', 'out', 'over', 'all', 'any', 'get', 'got', 'run',
        'need', 'want', 'look', 'tell', 'explain'
    }

    # +3 per distinct cols entry that matches (exact matches only)
    cols_matched = set()
    for col in record['cols']:
        norm_col = normalize(col)
        # Exact phrase match (normalized form)
        if re.search(rf'\b{re.escape(norm_col)}\b', norm_prompt):
            cols_matched.add(norm_col)
            continue
        # Exact match (raw underscored form)
        if re.search(rf'\b{re.escape(col.lower())}\b', norm_prompt):
            cols_matched.add(col.lower())

    col_hits = len(cols_matched)
    score += 3 * col_hits

    # +2 per distinct token of normalized id (length >= 4, not stopword)
    id_tokens = set()
    for token in normalize(record['id']).split():
        if len(token) >= 4 and token not in stopwords:
            if re.search(rf'\b{re.escape(token)}\b', norm_prompt):
                id_tokens.add(token)
            # Also try plural form (e.g., 'dispute' matches 'disputes')
            elif re.search(rf'\b{re.escape(token)}s\b', norm_prompt):
                id_tokens.add(token)

    id_token_hits = len(id_tokens)
    score += 2 * id_token_hits

    # +1 if entity matches (singular or plural)
    entity = record['entity']
    entity_hit = False
    if entity != 'feed_cutover':
        if re.search(rf'\b{re.escape(entity)}s?\b', norm_prompt):
            entity_hit = True
            score += 1

    # +1 per distinct distinctive prompt term in text (capped at +8)
    prompt_tokens = normalize(prompt).split()
    distinctive_tokens = set()
    for token in prompt_tokens:
        if len(token) >= 3 and token not in stopwords:
            distinctive_tokens.add(token)

    norm_text = normalize(record['text'])
    text_score = 0

    # Unigram hits (+1 each, capped at 5)
    for token in distinctive_tokens:
        if re.search(rf'\b{re.escape(token)}\b', norm_text):
            text_score += 1
    text_score = min(text_score, 5)

    # Bigram hits (+2 each, capped at 5)
    prompt_tokens_list = norm_prompt.split()
    bigram_score = 0
    bigram_matches = set()
    for i in range(len(prompt_tokens_list) - 1):
        token1, token2 = prompt_tokens_list[i], prompt_tokens_list[i + 1]
        # Skip bigrams where both tokens are stopwords
        if token1 in stopwords and token2 in stopwords:
            continue
        # Check if bigram appears as whole phrase in text
        bigram_phrase = f"{token1} {token2}"
        if re.search(rf'\b{re.escape(bigram_phrase)}\b', norm_text):
            bigram_matches.add(bigram_phrase)

    bigram_score = min(len(bigram_matches) * 2, 5)

    # Combined body component (unigrams + bigrams, capped at 10)
    score += min(text_score + bigram_score, 10)

    # Anchor: record must have at least one direct connection (col, id token, or entity hit)
    has_anchor = col_hits > 0 or id_token_hits > 0 or entity_hit

    return score, has_anchor


def select_records(records: List[Dict[str, Any]], prompt: str) -> Tuple[List[Tuple[int, Dict]], List[Tuple[int, Dict]]]:
    """Score and select records into tiers. Returns (tier1_with_scores, tier2_with_scores)."""
    # Score all records
    scored = []
    for record in records:
        score, has_anchor = score_record(record, prompt)
        if score >= 3 and has_anchor:
            scored.append((score, record))

    # Sort by score desc, then id asc
    scored.sort(key=lambda x: (-x[0], x[1]['id']))

    # Tier 1: top 3 (full message)
    # Tier 2: ranks 4-8 (name-only)
    tier1 = scored[:3]
    tier2 = scored[3:8]

    return tier1, tier2


def format_output(tier1: List[Tuple[int, Dict]], tier2: List[Tuple[int, Dict]]) -> str:
    """Format tier 1 and tier 2 records as output block, with 3500-char hard cap."""
    lines = [
        '## Governed warehouse rules matched to this prompt (auto-injected)',
        'These are load-bearing corrections from `data/bq-knowledge.md` (source of truth) via `config/context/`. Read them BEFORE proposing tables, columns, or an approach — including when the ask is only "how would you approach this".',
        ''
    ]

    # Tier 1: full messages (700-char truncation)
    for score, record in tier1:
        id_part = record['id']
        entity_part = record['entity']
        cols_part = ', '.join(record['cols']) if record['cols'] else ''
        text_part = truncate(record['text'], 700)
        source_part = record['source']

        if cols_part:
            line = f"- **{id_part}** ({entity_part} · {cols_part}) — {text_part} _[{source_part}]_"
        else:
            line = f"- **{id_part}** ({entity_part}) — {text_part} _[{source_part}]_"

        lines.append(line)

    # Tier 2: name-only entries (if any)
    tier2_lines = []
    if tier2:
        tier2_lines.append('')
        tier2_lines.append('Also matched (grep bq-knowledge.md for the full rule):')

        for score, record in tier2:
            id_part = record['id']
            entity_part = record['entity']
            cols_part = ', '.join(record['cols']) if record['cols'] else ''
            source_part = record['source']

            if cols_part:
                line = f"- {id_part} ({entity_part} · {cols_part}) _[{source_part}]_"
            else:
                line = f"- {id_part} ({entity_part}) _[{source_part}]_"

            tier2_lines.append(line)

    lines.extend(tier2_lines)
    lines.append('')
    lines.append("Not exhaustive: `grep -n '^## ' data/bq-knowledge.md` for the section map, then grep your tables/columns.")

    return '\n'.join(lines)


def main():
    try:
        # Read JSON from stdin
        input_data = json.loads(sys.stdin.read())
        prompt = input_data.get('prompt') or input_data.get('user_prompt') or ''

        # Load and normalize records
        entity_rules, integration_rules, feed_cutovers = load_rules()
        records = normalize_records(entity_rules, integration_rules, feed_cutovers)

        # Check relevance gate
        if not is_warehouse_shaped(prompt, records):
            sys.exit(0)

        # Select records (tier 1 and tier 2)
        tier1, tier2 = select_records(records, prompt)

        if not tier1 and not tier2:
            sys.exit(0)

        # Format output and enforce 3500-char hard cap
        # Start with tier 1 + tier 2, then drop tier 2 entries from bottom if over limit
        output_block = format_output(tier1, tier2)

        while len(output_block) > 3500 and tier2:
            # Drop the last tier 2 entry
            tier2 = tier2[:-1]
            output_block = format_output(tier1, tier2)

        # If still over limit, tighten tier 1 truncation
        truncation_limit = 700
        while len(output_block) > 3500 and truncation_limit > 400:
            truncation_limit -= 50
            # Re-format with tighter truncation
            lines = [
                '## Governed warehouse rules matched to this prompt (auto-injected)',
                'These are load-bearing corrections from `data/bq-knowledge.md` (source of truth) via `config/context/`. Read them BEFORE proposing tables, columns, or an approach — including when the ask is only "how would you approach this".',
                ''
            ]

            for score, record in tier1:
                id_part = record['id']
                entity_part = record['entity']
                cols_part = ', '.join(record['cols']) if record['cols'] else ''
                text_part = truncate(record['text'], truncation_limit)
                source_part = record['source']

                if cols_part:
                    line = f"- **{id_part}** ({entity_part} · {cols_part}) — {text_part} _[{source_part}]_"
                else:
                    line = f"- **{id_part}** ({entity_part}) — {text_part} _[{source_part}]_"

                lines.append(line)

            if tier2:
                lines.append('')
                lines.append('Also matched (grep bq-knowledge.md for the full rule):')
                for score, record in tier2:
                    id_part = record['id']
                    entity_part = record['entity']
                    cols_part = ', '.join(record['cols']) if record['cols'] else ''
                    source_part = record['source']

                    if cols_part:
                        line = f"- {id_part} ({entity_part} · {cols_part}) _[{source_part}]_"
                    else:
                        line = f"- {id_part} ({entity_part}) _[{source_part}]_"

                    lines.append(line)

            lines.append('')
            lines.append("Not exhaustive: `grep -n '^## ' data/bq-knowledge.md` for the section map, then grep your tables/columns.")
            output_block = '\n'.join(lines)

        # Emit JSON
        output = {
            'hookSpecificOutput': {
                'hookEventName': 'UserPromptSubmit',
                'additionalContext': output_block
            }
        }

        print(json.dumps(output))
        sys.exit(0)

    except BaseException as e:
        sys.exit(0)


if __name__ == '__main__':
    main()
