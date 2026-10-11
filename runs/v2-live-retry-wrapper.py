import sys
sys.path.insert(0, '/Users/zmaxx/Projects/impeach/scripts')
import retry_finalized_probe
args = retry_finalized_probe.parse_args()
args.deadline_margin = 120
raise SystemExit(retry_finalized_probe.retry(args))
