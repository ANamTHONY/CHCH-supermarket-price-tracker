"""Write a concise Actions result without including credentials or page content."""
import json
import os
from pathlib import Path


def summarize(root):
    lines = ['## Daily collection', '']
    manifests = sorted(Path(root).glob('production_*/manifest.json'))
    if not manifests:
        return '\n'.join(lines + ['No collection manifest was produced. Review setup and preflight logs.'])
    for path in manifests:
        state = json.loads(path.read_text(encoding='utf-8'))
        results = state.get('results', [])
        complete = [r for r in results if r['status'] == 'uploaded']
        lines += [f"Date: {state['collected_date']}",
                  f"Uploaded stores: {len(complete)}/{state['expected_stores']}",
                  f"Uploaded rows: {sum(r['rows'] for r in complete)}",
                  f"Collection: {state['status']}",
                  f"Cloud processing: {state.get('cloud_processing', 'not confirmed')}", '']
        lines += [f"- {r['store_name']}: {r['status']} ({r.get('error_type', r.get('reason', 'unknown'))})"
                  for r in results if r['status'] != 'uploaded']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    summary = summarize(Path(__file__).resolve().parents[1] / 'data')
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
            stream.write(summary)
