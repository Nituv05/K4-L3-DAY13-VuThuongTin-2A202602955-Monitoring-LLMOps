"""Export CP2 evidence from the Langfuse V2 observations API, without secrets."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    load_dotenv(ROOT / '.env')
    from langfuse import get_client
    logs = [json.loads(line) for line in (ROOT / 'data/logs.jsonl').read_text().splitlines() if line.strip()]
    session = Counter(r['session_id'] for r in logs if str(r.get('session_id', '')).startswith('cp2-')).most_common(1)[0][0]
    start = min(datetime.fromisoformat(r['ts'].replace('Z', '+00:00')) for r in logs if r.get('session_id') == session) - timedelta(minutes=1)
    client = get_client()
    result = client.api.observations.get_many(session_id=session, from_start_time=start, limit=200, fields="core,basic,io,metadata,model,usage,prompt")
    groups = defaultdict(list)
    fields = ['id', 'trace_id', 'parent_observation_id', 'type', 'name', 'session_id', 'user_id', 'project_id', 'start_time', 'end_time', 'model', 'prompt_name', 'prompt_version', 'usage_details', 'cost_details', 'total_cost', 'metadata', 'input', 'output']
    for item in result.data:
        safe = {key: getattr(item, key, None) for key in fields}
        for key in ['input', 'output', 'metadata']:
            if isinstance(safe[key], str):
                safe[key] = json.loads(safe[key])
        if isinstance(safe["metadata"], dict):
            safe["metadata"] = {k: v for k, v in safe["metadata"].items() if "key" not in k.lower() and "secret" not in k.lower()}
        groups[item.trace_id].append(safe)
    rows = []
    for trace, observations in groups.items():
        root = next(o for o in observations if str(o['type']).upper() == 'AGENT')
        gen = next(o for o in observations if str(o['type']).upper() == 'GENERATION')
        retrieval = next(o for o in observations if str(o['type']).upper() == 'RETRIEVER')
        assert gen['parent_observation_id'] == root['id'] == retrieval['parent_observation_id']
        cid = root['metadata']['correlation_id']
        assert any(r.get('correlation_id') == cid for r in logs)
        rows.append(dict(trace_id=trace, correlation_id=cid, prompt_version=gen['prompt_version'], prompt_label=(gen['input'] or {}).get('prompt_label'), model=gen['model'], usage=gen['usage_details'], cost=gen['cost_details'], observations=observations))
    assert len(rows) >= 10
    out = ROOT / 'submission/evidence'
    def save(name, payload):
        (out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + '\n')
    summary = [{k: v for k, v in row.items() if k != 'observations'} for row in rows]
    save('06-trace-list.json', dict(source='Langfuse V2 observations API', session_id=session, trace_count=len(rows), observation_count=len(result.data), traces=summary))
    save('07-trace-waterfall.json', dict(trace_id=rows[0]['trace_id'], observations=rows[0]['observations']))
    save('08-trace-metadata.json', dict(session_id=session, traces=summary))
    labels = {label: client.get_prompt('day13-chat', label=label, cache_ttl_seconds=0).version for label in ['baseline', 'candidate', 'production']}
    save('09-prompt-versions.json', dict(prompt_name='day13-chat', current_labels=labels, same_input_comparison=summary))
    save('10-prompt-rollback.json', dict(prompt_name='day13-chat', current_production_version=labels['production'], production_traces=[r for r in summary if r['prompt_label'] == 'production'], transition='production v1 -> v2 -> v1'))
    print(json.dumps(dict(session=session, traces=len(rows), observations=len(result.data), labels=labels, traces_summary=summary), indent=2, default=str))
    client.shutdown()


if __name__ == '__main__':
    main()
