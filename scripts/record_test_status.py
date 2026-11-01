"""Record actual test-run output for the About system-health panel."""
from pathlib import Path
from datetime import datetime,timezone
import json
import xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
test=ET.parse(root/'output/verification/noc-pytest.xml').getroot()
suites=list(test) if test.tag=='testsuites' else [test]
backend={key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
ui=json.loads((root/'output/verification/noc-vitest.json').read_text())
payload=dict(status='passed' if not backend['failures'] and not backend['errors'] and ui['success'] else 'failed',
    tests=backend['tests']+ui['numTotalTests'],failures=backend['failures']+ui['numFailedTests'],errors=backend['errors'],
    recorded_at=datetime.now(timezone.utc).isoformat(),backend_tests=backend['tests'],frontend_tests=ui['numTotalTests'],
    description='Pytest full suite and Vitest navigation/workflow suite. Test fixtures do not replace actual live data.')
(root/'docs/test-status.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
print(json.dumps(payload))
