"""Build separate coherent 2026 homegrown and established consensus tables."""
import argparse,json
from projection_release_v1_11_1 import DEFAULTS,build

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in DEFAULTS.items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(build(p.parse_args()),indent=2))
if __name__=='__main__':main()
