# coding: utf-8

import sys as _sys
import json as _json
import statistics as _stats


data = [_json.loads(_.strip()) for _ in _sys.stdin]

cmds = {_["subcommand"] for _ in data}

for cmd in cmds:
    d = sorted([_["duration"] for _ in data if _["subcommand"] == cmd])
    if len(d) < 2:
        continue
    print(f"{cmd:<10} total {sum(d):<8.4f} count {len(d):<3} mean {_stats.mean(d):.4f} median {_stats.median(d):.4f} stdev {_stats.stdev(d):.4f}")
